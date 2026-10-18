"""El runner corre in-process con el LLM falso y deja un CSV coherente."""

import csv

import pytest

from app.config import settings
from evals.stress.run import CSV_FIELDS, parse_args, run


@pytest.fixture(autouse=True)
def _restore_app_state(monkeypatch):
    from app.main import app
    import app.services.session_service as session_service

    monkeypatch.setattr(settings, "EXPOSE_SESSION_DEBUG", settings.EXPOSE_SESSION_DEBUG)
    monkeypatch.setattr(session_service, "validate_input", session_service.validate_input)
    yield
    app.dependency_overrides.clear()


def _run(tmp_path, *extra) -> list[dict]:
    out = tmp_path / "results.csv"
    args = parse_args(["--fake", "--output", str(out), "--repeats", "1", *extra])
    assert run(args) == 0
    with out.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_one_row_per_turn_with_all_columns(tmp_path):
    rows = _run(tmp_path, "--scenarios", "growing,pivot", "--max-turns", "3", "--attachment-sizes", "0,5")
    assert len(rows) == 2 * 3 + 2
    assert list(rows[0].keys()) == CSV_FIELDS
    growing = [r for r in rows if r["scenario"] == "growing"]
    assert [r["turn_index"] for r in growing] == ["1", "2", "3"]
    assert all(r["http_status"] == "200" and r["cache_hit_kind"] == "none" for r in growing)


def test_attachment_rows_report_chars_and_canaries(tmp_path):
    rows = _run(tmp_path, "--scenarios", "", "--attachment-sizes", "0,5,100")
    by_kb = {int(r["attachment_kb"]): r for r in rows}
    assert by_kb[0]["attachments_total_chars"] == "0" and by_kb[0]["canaries_found"] == ""
    assert 5_000 <= int(by_kb[5]["attachments_total_chars"]) < 5_300
    assert int(by_kb[100]["attachments_total_chars"]) < 60_300   # recortado a MAX_ATTACHMENT_CHARS


def test_cost_cap_aborts_the_run(tmp_path):
    out = tmp_path / "results.csv"
    args = parse_args(["--fake", "--output", str(out), "--repeats", "1", "--max-turns", "3",
                       "--max-cost-usd", "0.00001"])
    assert run(args) == 2


def test_unknown_scenario_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        run(parse_args(["--fake", "--output", str(tmp_path / "x.csv"), "--scenarios", "nope"]))


def test_facts_from_failed_turns_are_not_evaluated():
    from evals.stress.run import _memory_columns
    from evals.stress.scenarios import CONTRADICTION

    snapshot = {"max_turns": 6, "project_metadata": {}, "memory": {"summary": "", "anchors": []}}
    # turno 3 ("30000") falló y turno 1 ("Kestrel") no: solo se evalúa Kestrel
    cols = _memory_columns(CONTRADICTION, 10, snapshot, failed_turns={3})
    assert cols["facts_tested"] == 1
    assert _memory_columns(CONTRADICTION, 10, snapshot, failed_turns=set())["facts_tested"] == 2


def test_failed_turn_is_retried_and_attempts_are_recorded(tmp_path, monkeypatch):
    """El primer intento de cada turno devuelve 502; el reintento lo salva y la sesión no pierde turnos."""
    from fastapi.testclient import TestClient

    real_post = TestClient.post
    seen: set[str] = set()

    def flaky_post(self, url, *a, **kw):
        if url.endswith("/estimate") and url not in seen | {None}:
            seen.add(url)
            import httpx
            return httpx.Response(502, text="boom")
        seen.discard(url)   # el siguiente turno de esta sesión vuelve a fallar una vez
        return real_post(self, url, *a, **kw)

    monkeypatch.setattr(TestClient, "post", flaky_post)
    rows = _run(tmp_path, "--scenarios", "growing", "--max-turns", "3", "--attachment-sizes", "", "--retries", "1")
    assert [r["http_status"] for r in rows] == ["200"] * 3
    assert [r["attempts"] for r in rows] == ["2"] * 3
    assert [r["turn_index"] for r in rows] == ["1", "2", "3"]


def test_no_retries_records_the_failure(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import httpx

    real_post = TestClient.post
    monkeypatch.setattr(TestClient, "post", lambda self, url, *a, **kw:
                        httpx.Response(502, text="boom") if url.endswith("/estimate") else real_post(self, url, *a, **kw))
    rows = _run(tmp_path, "--scenarios", "growing", "--max-turns", "2", "--attachment-sizes", "", "--retries", "0")
    assert [(r["http_status"], r["attempts"]) for r in rows] == [("502", "1")] * 2


def test_lost_facts_are_named_in_the_csv(tmp_path):
    rows = _run(tmp_path, "--scenarios", "contradiction", "--max-turns", "10", "--attachment-sizes", "")
    last = rows[-1]
    assert last["facts_tested"] == "2" and last["facts_recalled"] == "0"
    assert last["facts_lost"] == "Kestrel|30000"   # el fake no recuerda nada: aquí se ve qué se perdió
