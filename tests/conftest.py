"""Fakes y fixtures compartidos por los tests de integración de las sesiones."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import EstimationResult, Phase
from app.services.llm_service import get_llm_wrapper
from app.services.llm_wrapper import LLMStructuredResponse
from app.sessions import ProjectMetadata, SessionStore, get_session_store


def make_canned_result(*, total_cost_eur: int = 24_000) -> EstimationResult:
    return EstimationResult(
        summary="Plataforma de reservas en 8 semanas.",
        confidence_pct=75,
        phases=[
            Phase(name="Diseño", duration_weeks=2, cost_eur=6_000, confidence_pct=80, assumptions=[]),
            Phase(name="Desarrollo", duration_weeks=6, cost_eur=total_cost_eur - 6_000,
                  confidence_pct=70, assumptions=[]),
        ],
        total_duration_weeks=8,
        total_cost_eur=total_cost_eur,
    )


class FakeLLMWrapper:
    """Doble de ``LLMWrapper`` para los tests de sesiones.

    Registra cada llamada a ``complete_structured`` (``response_model``, ``messages``
    y ``model``) y responde según el schema pedido:

    - ``EstimationResult``: lo que devuelva ``estimation_factory(messages)``.
    - ``ProjectMetadata`` (extractor): el siguiente de ``metadata_queue``, o vacío.
      Si ``metadata_error`` está definido, lo lanza en su lugar.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.metadata_queue: list[ProjectMetadata] = []
        self.metadata_error: Exception | None = None
        self.estimation_factory: Callable[[list[dict]], EstimationResult] = lambda _: make_canned_result()

    def complete_structured(
        self, *, response_model, system_prompt=None, user_message=None,
        messages=None, model=None, **_,
    ) -> LLMStructuredResponse:
        if messages is None:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
        self.calls.append({"response_model": response_model.__name__, "messages": messages, "model": model})

        if response_model is EstimationResult:
            parsed = self.estimation_factory(messages)
        elif response_model is ProjectMetadata:
            if self.metadata_error is not None:
                raise self.metadata_error
            parsed = self.metadata_queue.pop(0) if self.metadata_queue else ProjectMetadata()
        else:
            raise AssertionError(f"response_model inesperado: {response_model.__name__}")

        return LLMStructuredResponse(
            parsed=parsed, model="gpt-4o-mini", provider="openai",
            input_tokens=10, output_tokens=5, finish_reason="stop", latency_ms=1,
        )

    def calls_for(self, schema: str) -> list[dict]:
        return [c for c in self.calls if c["response_model"] == schema]


@pytest.fixture
def fake_wrapper() -> FakeLLMWrapper:
    return FakeLLMWrapper()


@pytest.fixture
def session_store() -> SessionStore:
    """Store aislado por test. Un módulo puede sobrescribir esta fixture (p. ej. ventana pequeña)."""
    return SessionStore()


@pytest.fixture
def conversational_client(fake_wrapper, session_store, monkeypatch):
    app.dependency_overrides[get_session_store] = lambda: session_store
    app.dependency_overrides[get_llm_wrapper] = lambda: fake_wrapper
    # los checks locales de guardrails tienen sus propios tests; aquí evitamos la red (moderation)
    monkeypatch.setattr("app.services.session_service.validate_input", lambda _: None)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def new_session(client: TestClient) -> str:
    response = client.post("/api/v1/sessions")
    assert response.status_code == 201
    return response.json()["session_id"]


def estimate(client: TestClient, session_id: str, transcript: str, files=None):
    return client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        data={"transcript": transcript},
        files=files or [],
    )
