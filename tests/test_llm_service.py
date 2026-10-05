import pytest
from unittest.mock import MagicMock, patch

from app.guardrails.input import InputGuardrailViolation
from app.schemas import DetailLevel, EstimationRequest, EstimationResult, OutputFormat, Phase, ProjectType
from app.services import llm_service
from app.services.llm_wrapper import LLMStructuredResponse


def _request(description: str = "El cliente necesita una web de reservas online.") -> EstimationRequest:
    return EstimationRequest(
        description=description,
        project_type=ProjectType.WEB_SAAS,
        detail_level=DetailLevel.MEDIUM,
        output_format=OutputFormat.NARRATIVE,
    )


@pytest.fixture(autouse=True)
def _no_moderation_call():
    with patch.object(llm_service, "validate_input"):
        yield


def _result() -> EstimationResult:
    return EstimationResult(
        summary="Resumen",
        total_duration_weeks=2,
        total_cost_eur=5000,
        confidence_pct=80,
        phases=[Phase(name="Única", duration_weeks=2, cost_eur=5000, confidence_pct=80, assumptions=[])],
    )


def _structured_response(finish_reason: str = "stop") -> LLMStructuredResponse:
    return LLMStructuredResponse(
        parsed=_result(), model="gpt-4o-mini", provider="openai",
        input_tokens=10, output_tokens=5, finish_reason=finish_reason, latency_ms=1,
    )


def test_cache_miss_calls_llm_and_stores_json_serializable_payload():
    cache = MagicMock()
    cache.get.return_value = None
    wrapper = MagicMock()
    wrapper.complete_structured.return_value = _structured_response()

    with patch.object(llm_service, "_cache", cache), patch.object(llm_service, "_wrapper", wrapper):
        output = llm_service.generate_estimation(_request())

    assert output.cache_hit is False
    assert output.result == _result()
    wrapper.complete_structured.assert_called_once()
    stored = cache.set.call_args.args[1]
    assert stored["result"] == _result().model_dump()


def test_cache_hit_skips_llm_and_roundtrips_the_stored_payload():
    stored = {}
    cache = MagicMock()
    cache.get.side_effect = lambda key: stored.get("v")
    cache.set.side_effect = lambda key, value: stored.update(v=value)
    wrapper = MagicMock()
    wrapper.complete_structured.return_value = _structured_response()

    with patch.object(llm_service, "_cache", cache), patch.object(llm_service, "_wrapper", wrapper):
        first = llm_service.generate_estimation(_request())
        second = llm_service.generate_estimation(_request())

    assert wrapper.complete_structured.call_count == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.result == first.result
    assert second.model == "gpt-4o-mini"


def test_truncated_flag_follows_finish_reason():
    cache = MagicMock()
    cache.get.return_value = None
    wrapper = MagicMock()
    wrapper.complete_structured.return_value = _structured_response(finish_reason="length")

    with patch.object(llm_service, "_cache", cache), patch.object(llm_service, "_wrapper", wrapper):
        output = llm_service.generate_estimation(_request())

    assert output.truncated is True


def test_guardrail_violation_blocks_before_cache_and_llm():
    cache = MagicMock()
    wrapper = MagicMock()
    violation = InputGuardrailViolation("bloqueado", reason="prompt_injection")

    with patch.object(llm_service, "_cache", cache), patch.object(llm_service, "_wrapper", wrapper),          patch.object(llm_service, "validate_input", side_effect=violation):
        with pytest.raises(InputGuardrailViolation):
            llm_service.generate_estimation(_request())

    cache.get.assert_not_called()
    wrapper.complete_structured.assert_not_called()


def test_guardrail_validates_description_not_rendered_prompt():
    cache = MagicMock()
    cache.get.return_value = None
    wrapper = MagicMock()
    wrapper.complete_structured.return_value = _structured_response()
    request = _request()

    with patch.object(llm_service, "_cache", cache), patch.object(llm_service, "_wrapper", wrapper),          patch.object(llm_service, "validate_input") as validate:
        output = llm_service.generate_estimation(request)

    validate.assert_called_once_with(request.description)
    assert output.system_prompt
