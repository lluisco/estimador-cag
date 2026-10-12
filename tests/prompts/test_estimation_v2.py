"""Tests del template v2: misma estructura que v1, con el tono ejecutivo como única variación."""
import pytest

from app.prompts.loader import render_estimation_prompt
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType, PromptVersion
from app.sessions import ProjectMetadata

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


def test_v2_system_prompt_adds_executive_tone():
    system_v1, _ = render_estimation_prompt(_build_request(), version=PromptVersion.V1)
    system_v2, _ = render_estimation_prompt(_build_request(), version=PromptVersion.V2)

    assert "executive summary" in system_v2
    assert "executive summary" not in system_v1


def test_v2_keeps_same_user_prompt_and_examples_as_v1():
    system_v1, user_v1 = render_estimation_prompt(_build_request(), version=PromptVersion.V1)
    system_v2, user_v2 = render_estimation_prompt(_build_request(), version=PromptVersion.V2)

    assert user_v2 == user_v1
    # solo hasta el cierre: tras </estimation_examples> v2 añade el bloque <project_metadata>
    closing = "</estimation_examples>"
    examples_v1 = system_v1[system_v1.rindex("<estimation_examples>"):system_v1.rindex(closing)]
    examples_v2 = system_v2[system_v2.rindex("<estimation_examples>"):system_v2.rindex(closing)]
    assert examples_v2 == examples_v1


@pytest.mark.parametrize("version", [PromptVersion.V1, PromptVersion.V2])
def test_project_metadata_block_is_empty_without_facts(version):
    system, _ = render_estimation_prompt(_build_request(), version=version)

    # con la memoria vacía el bloque existe pero no contiene ningún hecho
    assert "<project_metadata>\n</project_metadata>" in system


@pytest.mark.parametrize("version", [PromptVersion.V1, PromptVersion.V2])
def test_project_metadata_block_renders_known_facts(version):
    metadata = ProjectMetadata(
        project_name="Atlas",
        assumed_team_size=3,
        mentioned_technologies=["MAUI", "FastAPI"],
        agreed_scope="MVP con bandeja de tareas",
    )
    system, _ = render_estimation_prompt(_build_request(), version=version, project_metadata=metadata)

    assert "- Project name: Atlas" in system
    assert "- Assumed team size: 3" in system
    assert "- Technologies mentioned: MAUI, FastAPI" in system
    assert "- Agreed scope: MVP con bandeja de tareas" in system


def test_v2_system_prompt_varies_by_output_format_and_detail_level():
    system_phases, _ = render_estimation_prompt(
        _build_request(output_format=OutputFormat.PHASES_TABLE), version=PromptVersion.V2
    )
    system_detailed, _ = render_estimation_prompt(
        _build_request(detail_level=DetailLevel.DETAILED), version=PromptVersion.V2
    )

    assert "group the work into phases" in system_phases
    assert "subtask level" in system_detailed


def test_unknown_version_is_rejected():
    with pytest.raises(ValueError):
        render_estimation_prompt(_build_request(), version="../v1")
