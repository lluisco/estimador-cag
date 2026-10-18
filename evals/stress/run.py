"""Runner del stress test del CAG: una fila de CSV por turno.

    # contra un servidor arrancado con EXPOSE_SESSION_DEBUG=true
    uv run python -m evals.stress.run --http http://localhost:8000 \\
        --scenarios growing,pivot,contradiction --attachment-sizes 0,5,20,50,100 \\
        --repeats 3 --output evals/stress/results.csv

    # in-process (TestClient). --fake sustituye el LLM por el FakeLLMWrapper de los tests: coste 0
    uv run python -m evals.stress.run --fake --max-turns 3 --repeats 1

Matriz: los escenarios multi-turno (growing, pivot, contradiction) corren sin adjunto, una
conversación de 20 turnos por repetición, y se leen sus fotos en CHECKPOINTS. Los tamaños de
``--attachment-sizes`` se aplican a un escenario aparte de un turno (``attachments``): mismo
transcript corto, solo cambia el adjunto. Cruzar ambos ejes costaría ~900 turnos.
"""

import argparse
import csv
import sys
import tempfile
import time
from pathlib import Path

import httpx

from evals.stress.fixtures.build_pdfs import CANARIES, build_all
from evals.stress.metrics import CostBudgetMetric, LatencyBudgetMetric, MemoryDriftMetric
from evals.stress.scenarios import CHECKPOINTS, SCENARIOS, TOTAL_TURNS, Scenario, fact_has_left_window

API = "/api/v1"
ATTACHMENT_TRANSCRIPT = (
    "Necesito estimar una plataforma web de gestión de proyectos internos. "
    "Adjunto la especificación del cliente."
)

OBSERVED_FIELDS = [
    "turn_index", "session_id", "enriched_transcript_chars", "attachments_total_chars",
    "messages_in_window", "anchors_count", "summary_chars", "tokens_in", "tokens_out",
    "cost_usd", "latency_ms", "cache_hit_kind", "last_resolved_tier", "llm_calls", "unpriced_calls",
]
RUN_FIELDS = [
    "scenario", "attachment_kb", "repeat", "scenario_turn", "is_checkpoint", "http_status", "error",
    "request_ms", "cumulative_cost_usd", "technologies",
    "facts_tested", "facts_recalled", "memory_recall", "facts_lost", "attempts",
    "latency_budget_ok", "cost_budget_ok",
    "canaries_found", "canary_start", "canary_middle", "canary_end",
]
CSV_FIELDS = RUN_FIELDS[:6] + OBSERVED_FIELDS + RUN_FIELDS[6:]


class BudgetExceeded(Exception):
    pass


def _make_client(args: argparse.Namespace):
    if args.http:
        return httpx.Client(base_url=args.http, timeout=args.timeout)
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app

    settings.EXPOSE_SESSION_DEBUG = True
    if args.fake:
        from app.services.llm_service import get_llm_wrapper
        from tests.conftest import FakeLLMWrapper
        import app.services.session_service as session_service

        fake = FakeLLMWrapper()
        app.dependency_overrides[get_llm_wrapper] = lambda: fake
        session_service.validate_input = lambda _: None   # evita la red (moderation)
    return TestClient(app)


def _memory_columns(scenario: Scenario | None, turn: int, snapshot: dict, failed_turns: set[int]) -> dict:
    """Recall de los facts declarados antes de ``turn`` que ya salieron de la ventana.

    Un turno que devolvió error no entró en la sesión: sus facts no se evalúan, porque
    contarlos como olvidados mediría el fallo del turno y no la memoria."""
    if scenario is None:
        return {"facts_tested": 0, "facts_recalled": 0, "memory_recall": "", "facts_lost": ""}
    window = snapshot["max_turns"]
    tested = recalled = 0
    lost: list[str] = []
    for fact_turn, fact in scenario.facts_declared_before(turn):
        if fact_turn in failed_turns or not fact_has_left_window(fact_turn, turn, window):
            continue
        tested += 1
        result = MemoryDriftMetric(fact, scenario.fact_where[fact]).evaluate(snapshot)
        recalled += int(result.passed)
        if not result.passed:
            lost.append(fact)
    return {
        "facts_tested": tested,
        "facts_recalled": recalled,
        "memory_recall": round(recalled / tested, 3) if tested else "",
        "facts_lost": "|".join(lost),
    }


def _canary_columns(attachment_kb: int, summary_text: str) -> dict:
    if not attachment_kb:
        return {"canaries_found": "", "canary_start": "", "canary_middle": "", "canary_end": ""}
    hits = {pos: int(name.lower() in summary_text.lower()) for pos, name in CANARIES.items()}
    return {"canaries_found": sum(hits.values()), **{f"canary_{pos}": v for pos, v in hits.items()}}


def run_session(client, args, writer, state, scenario: Scenario | None, name: str,
                attachment_kb: int, repeat: int, pdfs: dict, turns: list[tuple[int, str]]) -> None:
    latency_metric = LatencyBudgetMetric(args.latency_budget_ms)
    cost_metric = CostBudgetMetric(args.cost_budget_usd)

    created = client.post(f"{API}/sessions")
    created.raise_for_status()
    session_id = created.json()["session_id"]
    session_cost = 0.0
    failed_turns: set[int] = set()

    for turn_index, transcript in turns:
        files = []
        if attachment_kb:
            files = [("attachments", (f"attach_{attachment_kb}kb.pdf", pdfs[attachment_kb].read_bytes(), "application/pdf"))]

        row = {"scenario": name, "attachment_kb": attachment_kb, "repeat": repeat, "scenario_turn": turn_index,
               "is_checkpoint": int(turn_index in CHECKPOINTS)}
        # un error 5xx (p. ej. 502 por validación del esquema) se reintenta como haría un cliente real,
        # para que la sesión no pierda el turno. request_ms es el del último intento.
        for attempt in range(1, args.retries + 2):
            t0 = time.perf_counter()
            response = client.post(f"{API}/sessions/{session_id}/estimate", data={"transcript": transcript}, files=files)
            row["request_ms"] = int((time.perf_counter() - t0) * 1000)   # petición completa, no solo LLM
            if response.status_code < 500:
                break
        row["attempts"] = attempt
        row["http_status"] = response.status_code

        if response.status_code != 200:   # el turno no avanza la sesión: se registra y se sigue
            failed_turns.add(turn_index)
            row["error"] = response.text[:200].replace("\n", " ")
            writer.writerow(row)
            continue

        snapshot = client.get(f"{API}/sessions/{session_id}").json()
        if snapshot.get("memory") is None:
            raise SystemExit("El servidor no expone 'memory': arráncalo con EXPOSE_SESSION_DEBUG=true")
        observed = snapshot["last_turn"]
        session_cost += observed["cost_usd"]
        state["cost"] += observed["cost_usd"]

        row.update({k: observed[k] for k in OBSERVED_FIELDS})
        row["cumulative_cost_usd"] = round(session_cost, 6)
        row["technologies"] = "|".join(snapshot["project_metadata"]["mentioned_technologies"])
        row["latency_budget_ok"] = int(latency_metric.evaluate(observed).passed)
        row["cost_budget_ok"] = int(cost_metric.evaluate(observed).passed)
        row.update(_memory_columns(scenario, observed["turn_index"], snapshot, failed_turns))
        row.update(_canary_columns(attachment_kb, response.json()["result"]["summary"]))
        writer.writerow(row)

        if state["cost"] > args.max_cost_usd:
            raise BudgetExceeded(f"coste acumulado {state['cost']:.4f} USD > --max-cost-usd {args.max_cost_usd}")


def run(args: argparse.Namespace) -> int:
    scenario_names = [s for s in args.scenarios.split(",") if s]
    unknown = set(scenario_names) - set(SCENARIOS)
    if unknown:
        raise SystemExit(f"escenarios desconocidos: {sorted(unknown)}; válidos: {sorted(SCENARIOS)}")
    sizes = [int(s) for s in args.attachment_sizes.split(",") if s]

    turns_per_scenario = min(args.max_turns, TOTAL_TURNS)
    planned = (len(scenario_names) * turns_per_scenario + len(sizes)) * args.repeats
    print(f"Plan: {planned} turnos (~{planned * 2.4:.0f} llamadas al LLM), tope de coste {args.max_cost_usd} USD")

    client = _make_client(args)
    state = {"cost": 0.0}
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp, out_path.open("w", newline="", encoding="utf-8") as fh:
        pdfs = build_all(Path(tmp))
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, restval="")
        writer.writeheader()
        try:
            for repeat in range(1, args.repeats + 1):
                for name in scenario_names:
                    scenario = SCENARIOS[name]
                    turns = [(t.turn_index, t.transcript) for t in scenario.turns[:turns_per_scenario]]
                    run_session(client, args, writer, state, scenario, name, 0, repeat, pdfs, turns)
                    fh.flush()
                for kb in sizes:
                    if kb and kb not in pdfs:
                        raise SystemExit(f"tamaño de adjunto sin PDF: {kb} (disponibles: 0,{','.join(map(str, pdfs))})")
                    run_session(client, args, writer, state, None, "attachments", kb, repeat, pdfs,
                                [(1, ATTACHMENT_TRANSCRIPT)])
                    fh.flush()
        except BudgetExceeded as exc:
            print(f"ABORTADO: {exc}", file=sys.stderr)
            return 2
        except httpx.ConnectError:
            print(f"ABORTADO: no hay servidor en {args.http}. Arráncalo con EXPOSE_SESSION_DEBUG=true "
                  "(uv run uvicorn app.main:app) o usa el modo in-process sin --http.", file=sys.stderr)
            return 3
    print(f"Hecho: coste total {state['cost']:.4f} USD -> {out_path}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--http", help="URL base del servidor; sin ella, corre in-process con TestClient")
    p.add_argument("--fake", action="store_true", help="in-process con FakeLLMWrapper (coste 0)")
    p.add_argument("--scenarios", default="growing,pivot,contradiction")
    p.add_argument("--attachment-sizes", default="0,5,20,50,100", help="KB de texto extraído; '' para omitir")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--max-turns", type=int, default=TOTAL_TURNS, help="recorta los escenarios (ensayos baratos)")
    p.add_argument("--output", default="evals/stress/results.csv")
    p.add_argument("--latency-budget-ms", type=int, default=4000)
    p.add_argument("--cost-budget-usd", type=float, default=0.01)
    p.add_argument("--max-cost-usd", type=float, default=2.0, help="aborta si el coste acumulado lo supera")
    p.add_argument("--timeout", type=float, default=180.0)
    p.add_argument("--retries", type=int, default=1, help="reintentos por turno ante un error 5xx")
    args = p.parse_args(argv)
    if args.http and args.fake:
        p.error("--fake solo aplica in-process (sin --http)")
    return args


if __name__ == "__main__":
    sys.exit(run(parse_args()))
