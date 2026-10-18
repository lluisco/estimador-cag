"""/sessions/{id}/estimate-acb: traza del Boss en la respuesta y solo el resultado final en la sesión."""

from app.services.critic import CriticFeedback, Issue, IssueCategory, Severity, Verdict
from tests.conftest import make_canned_result, new_session

MSG = "Quiero una app de reservas para un restaurante con pagos online"


def _estimate_acb(client, session_id: str, transcript: str = MSG, **form):
    return client.post(
        f"/api/v1/sessions/{session_id}/estimate-acb",
        data={"transcript": transcript, **form},
    )


def _needs_iteration(description: str = "falta el módulo de pagos") -> CriticFeedback:
    return CriticFeedback(
        verdict=Verdict.NEEDS_ITERATION,
        issues=[Issue(category=IssueCategory.SCOPE_MISREAD, severity=Severity.MAJOR,
                      field_path="phases[1]", description=description)],
        confidence_in_review=80,
    )


def _accept() -> CriticFeedback:
    return CriticFeedback(verdict=Verdict.ACCEPT, confidence_in_review=90)


def _numbered_drafts(fake_wrapper) -> None:
    """Cada llamada al actor devuelve un borrador distinguible por el coste total."""
    counter = {"n": 0}

    def factory(_messages):
        counter["n"] += 1
        return make_canned_result(total_cost_eur=20_000 + counter["n"] * 1_000)

    fake_wrapper.estimation_factory = factory


def test_accept_on_first_try_returns_trace(conversational_client, fake_wrapper):
    fake_wrapper.critic_queue = [_accept()]
    session_id = new_session(conversational_client)

    response = _estimate_acb(conversational_client, session_id)

    assert response.status_code == 200, response.text
    acb = response.json()["acb"]
    assert acb["outcome"] == "accepted"
    assert [it["verdict"] for it in acb["iterations"]] == ["accept"]
    assert len(fake_wrapper.calls_for("EstimationResult")) == 1
    assert len(fake_wrapper.calls_for("CriticFeedback")) == 1


def test_critic_feedback_reaches_the_actor_on_the_next_iteration(conversational_client, fake_wrapper):
    fake_wrapper.critic_queue = [_needs_iteration("falta el módulo de pagos"), _accept()]
    session_id = new_session(conversational_client)

    _estimate_acb(conversational_client, session_id)

    first, second = fake_wrapper.calls_for("EstimationResult")
    assert "<critic_feedback>" not in first["messages"][-1]["content"]
    assert "<critic_feedback>" in second["messages"][-1]["content"]
    assert "falta el módulo de pagos" in second["messages"][-1]["content"]


def test_session_keeps_only_the_final_result(conversational_client, fake_wrapper, session_store):
    _numbered_drafts(fake_wrapper)                                       # 21.000, 22.000...
    fake_wrapper.critic_queue = [_needs_iteration(), _accept()]
    session_id = new_session(conversational_client)

    response = _estimate_acb(conversational_client, session_id)

    assert response.json()["result"]["total_cost_eur"] == 22_000         # el segundo borrador
    history = session_store.get(session_id).history.messages
    assert len(history) == 2                                             # un turno, no dos
    assert "22000 EUR" in history[1]["content"]
    assert "21000 EUR" not in history[1]["content"]                      # el borrador se descartó


def test_exhausted_iterations_synthesize_with_warnings(conversational_client, fake_wrapper):
    fake_wrapper.critic_queue = [_needs_iteration() for _ in range(3)]
    session_id = new_session(conversational_client)

    body = _estimate_acb(conversational_client, session_id).json()

    assert body["acb"]["outcome"] == "max_iterations"
    assert len(body["acb"]["iterations"]) == 3
    assert body["result"]["summary"].startswith("Advertencias de la revisión:")
    assert len(fake_wrapper.calls_for("EstimationResult")) == 3


def test_critic_failure_does_not_break_the_turn(conversational_client, fake_wrapper):
    fake_wrapper.critic_error = RuntimeError("critic caído")
    session_id = new_session(conversational_client)

    response = _estimate_acb(conversational_client, session_id)

    assert response.status_code == 200
    iteration = response.json()["acb"]["iterations"][0]
    assert iteration["verdict"] == "accept"
    assert iteration["confidence_in_review"] == 0                        # "no se pudo revisar"


def test_acb_resolves_the_tier_and_passes_it_to_the_critic(conversational_client, fake_wrapper):
    session_id = new_session(conversational_client)
    _estimate_acb(conversational_client, session_id, "Firmamos un NDA para la app de reservas")

    critic_user = fake_wrapper.calls_for("CriticFeedback")[-1]["messages"][1]["content"]
    assert "<audience_tier>executive</audience_tier>" in critic_user
    state = conversational_client.get(f"/api/v1/sessions/{session_id}").json()
    assert state["last_resolved_tier"] == "executive"


def test_plain_estimate_never_calls_the_critic(conversational_client, fake_wrapper):
    session_id = new_session(conversational_client)
    conversational_client.post(
        f"/api/v1/sessions/{session_id}/estimate", data={"transcript": MSG}
    )
    assert fake_wrapper.calls_for("CriticFeedback") == []


def test_unknown_session_returns_404(conversational_client):
    assert _estimate_acb(conversational_client, "no-existe").status_code == 404
