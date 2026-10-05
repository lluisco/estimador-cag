"""Valida el flujo completo del servicio: texto -> contexto -> LLM -> respuesta.

Se mockea la llamada al LLM para que el pipeline se pueda validar en CI sin
necesitar credenciales reales de Anthropic/OpenAI.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient
from instructor.core.exceptions import IncompleteOutputException, InstructorRetryException

from app.main import app
from app.schemas import EstimationResult, Phase
from app.services.llm_service import EstimationOutput

client = TestClient(app)

PAYLOAD = {
    "description": "El cliente necesita una web de reservas online.",
    "project_type": "web_saas",
    "detail_level": "medium",
    "output_format": "narrative",
}


def _fake_output(**overrides) -> EstimationOutput:
    result = EstimationResult(
        summary="Plataforma de reservas en 8 semanas por 24.000 EUR.",
        total_duration_weeks=8,
        total_cost_eur=24000,
        confidence_pct=75,
        phases=[
            Phase(name="Diseño", duration_weeks=2, cost_eur=6000, confidence_pct=80, assumptions=["60 EUR/h"]),
            Phase(name="Desarrollo", duration_weeks=6, cost_eur=18000, confidence_pct=70, assumptions=[]),
        ],
    )
    fields = dict(
        result=result, input_tokens=100, output_tokens=50, truncated=False,
        model="gpt-4o-mini", provider="openai", cache_hit=True,
    )
    fields.update(overrides)
    return EstimationOutput(**fields)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_estimate_endpoint_full_flow():
    fake_output = _fake_output()

    with patch(
        "app.routers.estimations.generate_estimation", return_value=fake_output
    ) as mocked:
        response = client.post("/api/v1/estimate", json=PAYLOAD)

    assert mocked.called
    assert response.status_code == 200

    body = response.json()
    assert body["result"] == fake_output.result.model_dump()
    assert body["prompt_version"] == "v1"
    assert body["system_prompt"]
    assert body["input_tokens"] == 100
    assert body["output_tokens"] == 50
    assert body["truncated"] is False
    assert body["model"] == "gpt-4o-mini"
    assert body["provider"] == "openai"
    assert body["cache_hit"] is True


def test_estimate_endpoint_accepts_prompt_version_query_param():
    with patch(
        "app.routers.estimations.generate_estimation", return_value=_fake_output()
    ) as mocked:
        response = client.post("/api/v1/estimate?prompt_version=v2", json=PAYLOAD)

    assert response.status_code == 200
    assert response.json()["prompt_version"] == "v2"
    system_prompt = mocked.call_args.args[0]
    assert "executive summary" in system_prompt


def test_estimate_endpoint_rejects_unknown_prompt_version():
    response = client.post("/api/v1/estimate?prompt_version=v99", json=PAYLOAD)
    assert response.status_code == 422


def test_estimate_endpoint_requires_description():
    response = client.post("/api/v1/estimate", json={})
    assert response.status_code == 422


def test_estimate_endpoint_handles_llm_errors():
    with patch(
        "app.routers.estimations.generate_estimation",
        side_effect=RuntimeError("fallo simulado del proveedor LLM"),
    ):
        response = client.post("/api/v1/estimate", json=PAYLOAD)

    assert response.status_code == 500


def test_estimate_endpoint_returns_502_when_validation_retries_are_exhausted():
    with patch(
        "app.routers.estimations.generate_estimation",
        side_effect=InstructorRetryException(
            "totales incoherentes", n_attempts=3, total_usage=0, messages=[],
        ),
    ):
        response = client.post("/api/v1/estimate", json=PAYLOAD)

    assert response.status_code == 502


def test_estimate_endpoint_returns_502_when_output_hits_token_limit():
    with patch(
        "app.routers.estimations.generate_estimation",
        side_effect=IncompleteOutputException(),
    ):
        response = client.post("/api/v1/estimate", json=PAYLOAD)

    assert response.status_code == 502
    assert "ESTIMATION_MAX_TOKENS" in response.json()["detail"]
