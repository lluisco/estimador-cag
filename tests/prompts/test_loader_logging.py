"""Tests del evento de log emitido en cada render del prompt."""
from structlog.testing import capture_logs

from app.prompts.loader import render_estimation_prompt
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType, PromptVersion

DESCRIPTION = "Cliente necesita un dashboard interno para monitorizar ventas en tiempo real."


def _build_request() -> EstimationRequest:
    return EstimationRequest(
        description=DESCRIPTION,
        project_type=ProjectType.INTERNAL_TOOL,
        detail_level=DetailLevel.MEDIUM,
        output_format=OutputFormat.NARRATIVE,
    )


def _render_and_capture(version: PromptVersion) -> dict:
    with capture_logs() as logs:
        render_estimation_prompt(_build_request(), version=version)
    events = [e for e in logs if e["event"] == "prompt_rendered"]
    assert len(events) == 1
    return events[0]


def test_render_emits_event_with_version_and_hashes():
    event = _render_and_capture(PromptVersion.V2)

    assert event["log_level"] == "info"
    assert event["prompt_version"] == "v2"
    assert len(event["system_hash"]) == 12
    assert len(event["user_hash"]) == 12
    assert event["system_chars"] > 0 and event["user_chars"] > 0


def test_render_event_does_not_leak_prompt_content():
    event = _render_and_capture(PromptVersion.V1)

    assert DESCRIPTION not in str(event)


def test_hashes_are_stable_and_track_content_changes():
    v1_first = _render_and_capture(PromptVersion.V1)
    v1_second = _render_and_capture(PromptVersion.V1)
    v2 = _render_and_capture(PromptVersion.V2)

    assert v1_first["system_hash"] == v1_second["system_hash"]
    assert v2["system_hash"] != v1_first["system_hash"]
    assert v2["user_hash"] == v1_first["user_hash"]
