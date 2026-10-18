"""GET /sessions/{id}: last_turn siempre; el contenido de la memoria solo con EXPOSE_SESSION_DEBUG."""

import pytest

from app.config import settings
from app.sessions import SessionStore
from tests.conftest import estimate, new_session

ANCHOR_MSG = "El presupuesto está cerrado en 30000 EUR para la app"
PLAIN_MSG = "Añadimos un panel de administración para el hotel"


@pytest.fixture
def session_store() -> SessionStore:
    return SessionStore(max_turns=1)   # ventana mínima: fuerza anclas y resumen enseguida


def _state(client, session_id: str) -> dict:
    return client.get(f"/api/v1/sessions/{session_id}").json()


def test_last_turn_is_exposed_without_content(conversational_client):
    session_id = new_session(conversational_client)
    assert _state(conversational_client, session_id)["last_turn"] is None

    response = estimate(conversational_client, session_id, "Una app de reservas para un hotel pequeño")
    assert response.status_code == 200, response.text
    state = _state(conversational_client, session_id)

    assert state["last_turn"]["turn_index"] == 1
    assert state["last_turn"]["session_id"] == session_id
    assert state["memory"] is None   # apagado por defecto


def test_memory_snapshot_exposes_summary_and_anchors(conversational_client, monkeypatch):
    monkeypatch.setattr(settings, "EXPOSE_SESSION_DEBUG", True)
    session_id = new_session(conversational_client)
    for msg in (ANCHOR_MSG, PLAIN_MSG, PLAIN_MSG):
        assert estimate(conversational_client, session_id, msg).status_code == 200

    memory = _state(conversational_client, session_id)["memory"]
    assert memory["anchors"] == [ANCHOR_MSG]
    assert memory["summary"] == "RESUMEN-1"
