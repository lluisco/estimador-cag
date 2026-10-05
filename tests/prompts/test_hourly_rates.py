"""Las tarifas por rol salen de la configuración y llegan a todas las versiones del prompt."""
import pytest

from app.config import settings
from app.prompts.loader import render_estimation_prompt
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType, PromptVersion


def _request() -> EstimationRequest:
    return EstimationRequest(
        description="Cliente necesita un dashboard interno para monitorizar ventas en tiempo real.",
        project_type=ProjectType.INTERNAL_TOOL,
        detail_level=DetailLevel.MEDIUM,
        output_format=OutputFormat.NARRATIVE,
    )


@pytest.mark.parametrize("version", list(PromptVersion))
def test_system_prompt_lists_every_configured_rate(version):
    system, _ = render_estimation_prompt(_request(), version=version)

    assert "<hourly_rates>" in system
    assert "- developer: 60 EUR/hour" in system
    assert "- project_manager: 60 EUR/hour" in system
    assert "- ux_ui: 50 EUR/hour" in system
    assert "- other: 50 EUR/hour" in system


def test_changing_the_configured_rates_changes_the_prompt(monkeypatch):
    monkeypatch.setattr(settings, "HOURLY_RATES_EUR", {"developer": 80, "other": 55})

    system, _ = render_estimation_prompt(_request(), version=PromptVersion.V2)

    assert "- developer: 80 EUR/hour" in system
    assert "- other: 55 EUR/hour" in system
    assert "project_manager" not in system
