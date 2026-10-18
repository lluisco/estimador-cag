"""Convierte results.csv en las tablas del REPORT.md (Markdown, sin gráficos ni pandas).

    uv run python -m evals.stress.analyze evals/stress/results.csv [--output evals/stress/tables.md]

Solo calcula cifras; la lectura ("dónde se rompe mi CAG y por qué") la escribes tú.
Las filas con error HTTP se cuentan como fallos y se excluyen de latencias, costes y recall.
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

from evals.stress.scenarios import CHECKPOINTS

TOKEN_BINS = [(0, 3_000), (3_000, 5_000), (5_000, 8_000), (8_000, 12_000), (12_000, 20_000), (20_000, 10**9)]
NUMERIC = {
    "attachment_kb", "repeat", "scenario_turn", "http_status", "turn_index", "attachments_total_chars",
    "messages_in_window", "anchors_count", "summary_chars", "tokens_in", "tokens_out", "cost_usd",
    "latency_ms", "request_ms", "cumulative_cost_usd", "llm_calls", "unpriced_calls", "facts_tested",
    "facts_recalled", "memory_recall", "latency_budget_ok", "cost_budget_ok", "canaries_found",
    "canary_start", "canary_middle", "canary_end", "attempts",
}


def load(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8", newline="") as fh:
        for raw in csv.DictReader(fh):
            rows.append({k: (float(v) if k in NUMERIC and v != "" else v) for k, v in raw.items()})
    return rows


def percentile(values: list[float], q: float) -> float | None:
    """Interpolación lineal. Con pocas muestras el P95 es casi el máximo: se muestra ``n`` al lado."""
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def fmt(value, digits=0, na="–") -> str:
    if value is None:
        return na
    return f"{value:,.{digits}f}" if digits else f"{value:,.0f}"


def table(headers: list[str], body: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in body]
    return "\n".join(lines)


def is_ok(row: dict) -> bool:
    return row["http_status"] == 200


def summary_table(rows: list[dict]) -> str:
    groups = defaultdict(list)
    for r in rows:
        groups[(r["scenario"], int(r["attachment_kb"]))].append(r)
    body = []
    for (scenario, kb), group in sorted(groups.items()):
        ok = [r for r in group if is_ok(r)]
        lat = [r["latency_ms"] for r in ok]
        tested = sum(r["facts_tested"] for r in ok)
        recalled = sum(r["facts_recalled"] for r in ok)
        n_ok = len(ok) or 1
        body.append([
            scenario, f"{kb} KB" if kb else "–", len(group), len(group) - len(ok),
            fmt(percentile(lat, 0.5)), fmt(percentile(lat, 0.95)),
            fmt(sum(r["cost_usd"] for r in ok), 4),
            f"{sum(r['cache_hit_kind'] == 'exact' for r in ok) / n_ok:.0%}",
            f"{sum(r['cache_hit_kind'] == 'semantic' for r in ok) / n_ok:.0%}",
            f"{recalled / tested:.2f} ({int(tested)})" if tested else "n/a",
        ])
    return table(["escenario", "adjunto", "turnos", "errores", "P50 ms", "P95 ms", "coste total USD",
                  "hit exact", "hit semantic", "recall medio (facts)"], body)


def latency_vs_tokens(rows: list[dict]) -> str:
    ok = [r for r in rows if is_ok(r)]
    body = []
    for lo, hi in TOKEN_BINS:
        group = [r for r in ok if lo <= r["tokens_in"] < hi]
        if not group:
            continue
        label = f"{lo:,}–{hi:,}" if hi < 10**9 else f"≥ {lo:,}"
        body.append([label, len(group), fmt(mean([r["tokens_in"] for r in group])),
                     fmt(mean([r["tokens_out"] for r in group])),
                     fmt(percentile([r["latency_ms"] for r in group], 0.5)),
                     fmt(percentile([r["latency_ms"] for r in group], 0.95))])
    return table(["tokens_in", "n", "tokens_in medio", "tokens_out medio", "P50 latency ms", "P95 latency ms"], body)


def cost_vs_turn(rows: list[dict]) -> tuple[str, dict[str, float | None]]:
    ok = [r for r in rows if is_ok(r) and r["attachment_kb"] == 0 and r["scenario"] != "attachments"]
    body, ratios = [], {}
    for scenario in sorted({r["scenario"] for r in ok}):
        by_turn = defaultdict(list)
        for r in ok:
            if r["scenario"] == scenario:
                by_turn[int(r["turn_index"])].append(r)
        base = mean([r["cost_usd"] for r in by_turn.get(1, [])])
        last = max(by_turn, default=None)
        for turn in [t for t in CHECKPOINTS if t in by_turn]:
            cost = mean([r["cost_usd"] for r in by_turn[turn]])
            body.append([scenario, turn, len(by_turn[turn]), fmt(cost, 5),
                         fmt(mean([r["cumulative_cost_usd"] for r in by_turn[turn]]), 5),
                         f"{cost / base:.1f}x" if base and cost is not None else "–"])
        if last and base:
            ratios[scenario] = mean([r["cost_usd"] for r in by_turn[last]]) / base
    return table(["escenario", "turno", "n", "coste del turno USD", "coste acumulado USD", "vs turno 1"], body), ratios


def recall_vs_n(rows: list[dict]) -> str:
    ok = [r for r in rows if is_ok(r) and r["attachment_kb"] == 0 and r["scenario"] != "attachments"]
    body = []
    for scenario in sorted({r["scenario"] for r in ok}):
        for n in CHECKPOINTS:
            group = [r for r in ok if r["scenario"] == scenario and int(r["turn_index"]) == n]
            tested = sum(r["facts_tested"] for r in group)
            recalled = sum(r["facts_recalled"] for r in group)
            body.append([scenario, n, int(tested), int(recalled), f"{recalled / tested:.2f}" if tested else "n/a"])
    return table(["escenario", "N", "facts evaluados", "recordados", "recall"], body)


def attachments_table(rows: list[dict]) -> str:
    groups = defaultdict(list)
    for r in rows:
        if r["scenario"] == "attachments":
            groups[int(r["attachment_kb"])].append(r)
    body = []
    for kb, group in sorted(groups.items()):
        ok = [r for r in group if is_ok(r)]
        canaries = [r for r in ok if r["canaries_found"] != ""]

        def rate(key):
            return f"{mean([r[key] for r in canaries]):.2f}" if canaries else "–"

        body.append([f"{kb} KB" if kb else "0", len(group), len(group) - len(ok),
                     fmt(mean([r["attachments_total_chars"] for r in ok])),
                     fmt(mean([r["tokens_in"] for r in ok])),
                     fmt(percentile([r["latency_ms"] for r in ok], 0.5)),
                     fmt(mean([r["cost_usd"] for r in ok]), 5),
                     rate("canary_start"), rate("canary_middle"), rate("canary_end")])
    return table(["adjunto", "n", "errores", "chars adjunto", "tokens_in medio", "P50 latency ms",
                  "coste medio USD", "recall inicio", "recall medio", "recall final"], body)


def extras(rows: list[dict]) -> str:
    ok = [r for r in rows if is_ok(r)]
    lines = [f"- Turnos con error HTTP: {len(rows) - len(ok)} de {len(rows)} ({(len(rows) - len(ok)) / len(rows):.1%})."]
    if ok:
        lat = sum(r["latency_budget_ok"] for r in ok) / len(ok)
        cost = sum(r["cost_budget_ok"] for r in ok) / len(ok)
        lines.append(f"- Presupuesto de latencia cumplido en {lat:.0%} de los turnos; el de coste, en {cost:.0%}.")
        lines.append(f"- Latencia de LLM vs petición completa (medianas): "
                     f"{fmt(percentile([r['latency_ms'] for r in ok], .5))} ms vs "
                     f"{fmt(percentile([r['request_ms'] for r in ok], .5))} ms.")
        lines.append(f"- Turnos con modelo sin precio (coste subestimado): {int(sum(r['unpriced_calls'] > 0 for r in ok))}.")
    if any("attempts" in r and r["attempts"] != "" for r in rows):
        retried = [r for r in rows if r.get("attempts") not in ("", None) and r["attempts"] > 1]
        lines.append(f"- Turnos que necesitaron reintento: {len(retried)} de {len(rows)} "
                     f"({len(retried) / len(rows):.1%}); fallos definitivos tras reintentar: {len(rows) - len(ok)}.")
    lost = Counter()
    for r in ok:
        for fact in filter(None, r.get("facts_lost", "").split("|")):
            lost[(r["scenario"], fact)] += 1
    if lost:
        detail = ", ".join(f"{sc}/{fact}: {n}" for (sc, fact), n in sorted(lost.items()))
        lines.append(f"- Facts perdidos (apariciones de fallo en snapshots evaluados): {detail}.")
    pivot_last = [r for r in ok if r["scenario"] == "pivot" and int(r["turn_index"]) == max(
        (int(x["turn_index"]) for x in ok if x["scenario"] == "pivot"), default=0)]
    if pivot_last:
        both = sum("react" in r["technologies"].lower() and "flutter" in r["technologies"].lower() for r in pivot_last)
        lines.append(f"- `pivot`: en el último turno, {both} de {len(pivot_last)} sesiones tienen React y Flutter "
                     f"a la vez en `mentioned_technologies`.")
    return "\n".join(lines)


def build(rows: list[dict]) -> str:
    cost_table, ratios = cost_vs_turn(rows)
    ratio_lines = "\n".join(f"- `{s}`: el coste del último turno es {x:.1f}x el del turno 1." for s, x in sorted(ratios.items()))
    return "\n\n".join([
        "## Tabla resumen\n\n" + summary_table(rows),
        "## Curva 1: latencia vs tokens_in\n\n" + latency_vs_tokens(rows),
        "## Curva 2: coste vs turno\n\n" + cost_table + ("\n\n" + ratio_lines if ratio_lines else ""),
        "## Curva 3: recall vs N\n\n" + recall_vs_n(rows),
        "## Adjuntos\n\n" + attachments_table(rows),
        "## Otros datos\n\n" + extras(rows),
    ]) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv_path", type=Path)
    p.add_argument("--output", type=Path, help="si se omite, imprime por pantalla")
    args = p.parse_args(argv)
    rows = load(args.csv_path)
    if not rows:
        print("El CSV no tiene filas.", file=sys.stderr)
        return 1
    text = build(rows)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Tablas escritas en {args.output}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
