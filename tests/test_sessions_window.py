"""La ventana deslizante acota el historial que llega al LLM; la memoria sobrevive a ella."""

import pytest

from app.sessions import ProjectMetadata, SessionStore
from tests.conftest import estimate, new_session

MAX_TURNS = 3


@pytest.fixture
def session_store() -> SessionStore:
    """Sobrescribe la fixture de conftest: ventana pequeña para no necesitar muchos turnos."""
    return SessionStore(max_turns=MAX_TURNS)


def _send_turns(client, session_id: str, count: int) -> None:
    for turn in range(1, count + 1):
        response = estimate(client, session_id, f"Turno {turn}: refinamos el alcance de la app de reservas")
        assert response.status_code == 200, response.text


def test_eight_turns_never_exceed_window(conversational_client, fake_wrapper):
    session_id = new_session(conversational_client)
    _send_turns(conversational_client, session_id, 8)

    calls = fake_wrapper.calls_for("EstimationResult")
    assert len(calls) == 8
    for call in calls:
        messages = call["messages"]
        assert messages[0]["role"] == "system"                       # el system prompt nunca se descarta
        # MAX_TURNS pares previos + el mensaje en curso: 1 + 2 * MAX_TURNS + 1
        assert len(messages) <= 2 * MAX_TURNS + 2
        assert sum(m["role"] == "user" for m in messages) <= MAX_TURNS + 1

    state = conversational_client.get(f"/api/v1/sessions/{session_id}").json()
    assert state["turns"] == MAX_TURNS
    assert state["max_turns"] == MAX_TURNS


def test_history_keeps_most_recent_turns(conversational_client, fake_wrapper):
    session_id = new_session(conversational_client)
    _send_turns(conversational_client, session_id, 5)
    estimate(conversational_client, session_id, "Turno 6: última pregunta sobre la estimación")

    last = fake_wrapper.calls_for("EstimationResult")[-1]["messages"]
    previous_users = [m["content"] for m in last[1:-1] if m["role"] == "user"]
    # con MAX_TURNS=3, al turno 6 le llegan los turnos 3, 4 y 5
    assert len(previous_users) == MAX_TURNS
    assert previous_users[0].startswith("Turno 3:")
    assert previous_users[-1].startswith("Turno 5:")


def test_metadata_survives_turns_that_leave_the_window(conversational_client, fake_wrapper):
    fake_wrapper.metadata_queue = [ProjectMetadata(project_name="Atlas")]  # solo el turno 1 aporta un hecho
    session_id = new_session(conversational_client)
    _send_turns(conversational_client, session_id, 8)

    last = fake_wrapper.calls_for("EstimationResult")[-1]["messages"]
    conversation = " ".join(m["content"] for m in last[1:])
    assert "Turno 1:" not in conversation                            # fuera del historial...
    assert "- Project name: Atlas" in last[0]["content"]             # ...pero vivo en la memoria
