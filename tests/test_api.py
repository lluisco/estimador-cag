"""Valida el flujo completo del servicio: texto -> contexto -> LLM -> respuesta.

Se mockea la llamada al LLM para que el pipeline se pueda validar en CI sin
necesitar credenciales reales de Anthropic/OpenAI.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.llm_service import EstimationResult

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_estimate_endpoint_full_flow():
    fake_result = EstimationResult(
        text="## Estimación\n- Tarea de ejemplo: 10 horas",
        input_tokens=100,
        output_tokens=50,
        truncated=False,
        model="gpt-4o-mini",
        provider="openai",
        cache_hit=True,
    )

    with patch(
        "app.routers.estimations.generate_estimation", return_value=fake_result
    ) as mocked:
        response = client.post(
            "/api/v1/estimate",
            json={
                "description": "El cliente necesita una web de reservas online.",
                "project_type": "web_saas",
                "detail_level": "medium",
                "output_format": "narrative",
            },
        )

    assert mocked.called
    assert response.status_code == 200

    body = response.json()
    assert body["text"] == fake_result.text
    assert body["prompt_version"] == "v1"
    assert body["system_prompt"]
    assert body["input_tokens"] == 100
    assert body["output_tokens"] == 50
    assert body["truncated"] is False
    assert body["model"] == "gpt-4o-mini"
    assert body["cache_hit"] is True


def test_estimate_endpoint_requires_description():
    response = client.post("/api/v1/estimate", json={})
    assert response.status_code == 422


def test_estimate_endpoint_handles_llm_errors():
    with patch(
        "app.routers.estimations.generate_estimation",
        side_effect=RuntimeError("fallo simulado del proveedor LLM"),
    ):
        response = client.post(
            "/api/v1/estimate",
            json={
                "description": "Reunión de ejemplo con el cliente.",
                "project_type": "internal_tool",
                "detail_level": "summary",
                "output_format": "line_items",
            },
        )

    assert response.status_code == 500
