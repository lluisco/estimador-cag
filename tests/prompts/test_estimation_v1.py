"""Tests del template v1: verifican el texto renderizado, no llaman al LLM."""
from app.prompts.loader import render_estimation_prompt
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType

DESCRIPTION = "Cliente necesita un dashboard interno para monitorizar ventas en tiempo real."


def _build_request(
    *, detail_level: DetailLevel = DetailLevel.MEDIUM, output_format: OutputFormat = OutputFormat.NARRATIVE
) -> EstimationRequest:
    return EstimationRequest(
        description=DESCRIPTION,
        project_type=ProjectType.INTERNAL_TOOL,
        detail_level=detail_level,
        output_format=output_format,
    )


def test_user_prompt_wraps_description_in_project_description_block():
    _, user = render_estimation_prompt(_build_request())

    start = user.index("<descripcion_proyecto>")
    end = user.index("</descripcion_proyecto>")

    assert start < user.index(DESCRIPTION) < end


def test_system_prompt_varies_by_output_format():
    system_phases, _ = render_estimation_prompt(_build_request(output_format=OutputFormat.PHASES_TABLE))
    system_narrative, _ = render_estimation_prompt(_build_request(output_format=OutputFormat.NARRATIVE))

    assert "tabla markdown" in system_phases
    assert "tabla markdown" not in system_narrative


def test_system_prompt_varies_by_detail_level():
    system_detailed, _ = render_estimation_prompt(_build_request(detail_level=DetailLevel.DETAILED))
    system_summary, _ = render_estimation_prompt(_build_request(detail_level=DetailLevel.SUMMARY))

    assert "supuestos" in system_detailed
    assert "supuestos" not in system_summary
