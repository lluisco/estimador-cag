"""Cada turno emite un único evento ``turn_observed`` con todo lo necesario para el CSV de stress."""

import pytest
from structlog.testing import capture_logs

from app.sessions import SessionStore
from tests.conftest import estimate, new_session

MAX_TURNS = 3

REQUIRED_FIELDS = {
    "turn_index", "session_id", "enriched_transcript_chars", "attachments_total_chars",
    "messages_in_window", "anchors_count", "summary_chars", "tokens_in", "tokens_out",
    "cost_usd", "latency_ms", "cache_hit_kind", "last_resolved_tier",
}


@pytest.fixture
def session_store() -> SessionStore:
    return SessionStore(max_turns=MAX_TURNS)


def _observed(client, session_id: str, turns: int) -> list[dict]:
    with capture_logs() as logs:
        for turn in range(1, turns + 1):
            response = estimate(client, session_id, f"Turno {turn}: refinamos el alcance de la app")
            assert response.status_code == 200, response.text
    return [e for e in logs if e["event"] == "turn_observed"]


def test_one_event_per_turn_with_all_fields(conversational_client):
    session_id = new_session(conversational_client)
    events = _observed(conversational_client, session_id, 2)

    assert len(events) == 2
    for event in events:
        assert REQUIRED_FIELDS <= event.keys()
        assert event["session_id"] == session_id
        assert event["cache_hit_kind"] == "none"
        assert event["attachments_total_chars"] == 0


def test_turn_index_keeps_growing_past_the_window(conversational_client):
    session_id = new_session(conversational_client)
    events = _observed(conversational_client, session_id, MAX_TURNS + 3)

    assert [e["turn_index"] for e in events] == list(range(1, MAX_TURNS + 4))
    # la ventana se satura, el índice no
    assert max(e["messages_in_window"] for e in events) == 2 * MAX_TURNS


def test_usage_includes_auxiliary_calls(conversational_client):
    """Estimación + metadata = 2 llamadas; cuando la ventana se desborda, + resumidor = 3."""
    session_id = new_session(conversational_client)
    events = _observed(conversational_client, session_id, MAX_TURNS + 1)

    assert events[0]["llm_calls"] == 2
    assert events[-1]["llm_calls"] == 3
    assert events[-1]["tokens_in"] == 3 * 10   # el fake devuelve 10 tokens de entrada por llamada
    assert events[-1]["latency_ms"] == 3 * 1
    assert events[-1]["cost_usd"] > events[0]["cost_usd"]
    assert events[-1]["summary_chars"] > 0
