"""project_metadata: se actualiza entre turnos, viaja en el system prompt y se fusiona en código."""

from app.config import settings
from app.sessions import ProjectMetadata
from tests.conftest import estimate, new_session


def test_two_turns_in_one_session_update_project_metadata(conversational_client, fake_wrapper):
    fake_wrapper.metadata_queue = [
        ProjectMetadata(project_name="Atlas", mentioned_technologies=["MAUI"]),
        ProjectMetadata(assumed_team_size=3, mentioned_technologies=["FastAPI"]),
    ]
    session_id = new_session(conversational_client)
    state = conversational_client.get(f"/api/v1/sessions/{session_id}").json()
    assert state["project_metadata"]["project_name"] is None

    first = estimate(conversational_client, session_id, "Quiero una app de reservas llamada Atlas con MAUI")
    assert first.status_code == 200, first.text
    state = conversational_client.get(f"/api/v1/sessions/{session_id}").json()
    assert state["turns"] == 1
    assert state["project_metadata"]["project_name"] == "Atlas"

    second = estimate(conversational_client, session_id, "Seremos un equipo de tres y usaremos FastAPI")
    assert second.status_code == 200, second.text
    metadata = conversational_client.get(f"/api/v1/sessions/{session_id}").json()["project_metadata"]
    assert metadata["project_name"] == "Atlas"                       # no se olvida entre turnos
    assert metadata["assumed_team_size"] == 3                        # hecho nuevo
    assert metadata["mentioned_technologies"] == ["MAUI", "FastAPI"]

    # el turno 2 viaja con la memoria en el system prompt y con el turno 1 en el historial
    second_call = fake_wrapper.calls_for("EstimationResult")[1]["messages"]
    assert second_call[0]["role"] == "system"
    assert "- Project name: Atlas" in second_call[0]["content"]
    assert any("llamada Atlas" in m["content"] for m in second_call if m["role"] == "user")


def test_extractor_uses_its_own_model(conversational_client, fake_wrapper):
    session_id = new_session(conversational_client)
    estimate(conversational_client, session_id, "Quiero una app de reservas para mi academia")

    (extractor_call,) = fake_wrapper.calls_for("ProjectMetadata")
    assert extractor_call["model"] == settings.METADATA_EXTRACTOR_MODEL


def test_extractor_failure_keeps_previous_metadata(conversational_client, fake_wrapper):
    fake_wrapper.metadata_queue = [ProjectMetadata(project_name="Atlas")]
    session_id = new_session(conversational_client)
    estimate(conversational_client, session_id, "Quiero una app de reservas llamada Atlas")

    fake_wrapper.metadata_error = RuntimeError("timeout simulado del extractor")
    response = estimate(conversational_client, session_id, "Añadimos un módulo de facturación")

    assert response.status_code == 200                               # la petición no se rompe
    state = conversational_client.get(f"/api/v1/sessions/{session_id}").json()
    assert state["project_metadata"]["project_name"] == "Atlas"
    assert state["turns"] == 2


def test_merge_unions_technologies_case_insensitively():
    previous = ProjectMetadata(project_name="Atlas", mentioned_technologies=["React", "Postgres"])
    update = ProjectMetadata(assumed_team_size=4, mentioned_technologies=["react", "AWS Lambda"])

    merged = previous.merge_with(update)

    assert merged.project_name == "Atlas"                            # null no sobrescribe
    assert merged.assumed_team_size == 4
    assert merged.mentioned_technologies == ["React", "Postgres", "AWS Lambda"]


def test_unknown_session_returns_404(conversational_client):
    response = estimate(conversational_client, "no-existe", "Quiero una app de reservas online")
    assert response.status_code == 404


def test_short_transcript_returns_422(conversational_client):
    session_id = new_session(conversational_client)
    response = estimate(conversational_client, session_id, "muy corto")
    assert response.status_code == 422
