"""El tier se resuelve por reglas, llega al prompt y se expone en GET /sessions/{id}."""

import pytest

from app.sessions import ProjectMetadata
from tests.conftest import estimate, new_session

NDA_MSG = "Turno 1: firmamos un NDA con el cliente para la app de reservas"
PLAIN_MSG = "Quiero una app de reservas para un restaurante pequeño"


def _state(client, session_id: str) -> dict:
    return client.get(f"/api/v1/sessions/{session_id}").json()


def _last_system_prompt(fake_wrapper) -> str:
    return fake_wrapper.calls_for("EstimationResult")[-1]["messages"][0]["content"]


def test_tier_is_none_before_any_turn(conversational_client):
    state = _state(conversational_client, new_session(conversational_client))
    assert state["last_resolved_tier"] is None
    assert state["last_tier_rule"] is None


def test_nda_resolves_executive_without_being_asked(conversational_client):
    session_id = new_session(conversational_client)
    estimate(conversational_client, session_id, NDA_MSG)

    state = _state(conversational_client, session_id)
    assert state["last_resolved_tier"] == "executive"
    assert state["last_tier_rule"] == "nda_detected"


def test_caller_override_wins_over_rules(conversational_client):
    session_id = new_session(conversational_client)
    response = conversational_client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        data={"transcript": NDA_MSG, "tier": "developer"},
    )
    assert response.status_code == 200, response.text

    state = _state(conversational_client, session_id)
    assert state["last_resolved_tier"] == "developer"
    assert state["last_tier_rule"] == "caller_override"


def test_invalid_tier_is_rejected(conversational_client):
    session_id = new_session(conversational_client)
    response = conversational_client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        data={"transcript": NDA_MSG, "tier": "jefe"},
    )
    assert response.status_code == 422


def test_no_signals_gives_default(conversational_client):
    session_id = new_session(conversational_client)
    estimate(conversational_client, session_id, PLAIN_MSG)

    state = _state(conversational_client, session_id)
    assert state["last_resolved_tier"] == "default"
    assert state["last_tier_rule"] == "no_rule_matched"


def test_audience_block_reaches_the_llm(conversational_client, fake_wrapper):
    session_id = new_session(conversational_client)
    estimate(conversational_client, session_id, NDA_MSG)

    system = _last_system_prompt(fake_wrapper)
    assert 'tier="executive"' in system
    assert 'tier="pm"' not in system and 'tier="developer"' not in system


def test_default_tier_adds_no_audience_block(conversational_client, fake_wrapper):
    session_id = new_session(conversational_client)
    estimate(conversational_client, session_id, PLAIN_MSG)
    assert "<audience" not in _last_system_prompt(fake_wrapper)


def test_nda_kept_in_metadata_still_drives_the_tier_later(conversational_client, fake_wrapper):
    # el extractor guarda el NDA en agreed_scope en el turno 1; el turno 2 no lo menciona
    fake_wrapper.metadata_queue = [ProjectMetadata(agreed_scope="Alcance cerrado bajo NDA")]
    session_id = new_session(conversational_client)
    estimate(conversational_client, session_id, PLAIN_MSG)
    estimate(conversational_client, session_id, "Añadimos un módulo de facturación a la app")

    state = _state(conversational_client, session_id)
    assert state["last_resolved_tier"] == "executive"
    assert state["last_tier_rule"] == "nda_detected"


def test_failed_estimation_does_not_update_the_tier(conversational_client, fake_wrapper):
    session_id = new_session(conversational_client)
    estimate(conversational_client, session_id, PLAIN_MSG)             # turno 1 ok -> default

    def boom(_messages):
        raise RuntimeError("fallo simulado del LLM")

    fake_wrapper.estimation_factory = boom
    with pytest.raises(RuntimeError):
        estimate(conversational_client, session_id, NDA_MSG)           # intentaría executive

    state = _state(conversational_client, session_id)
    assert state["last_resolved_tier"] == "default"                    # sigue el del turno 1
    assert state["turns"] == 1
