import pytest
from app.prompts.loader import render_estimation_prompt
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType, PromptVersion
from tests.prompts.test_estimation_v1 import DESCRIPTION

MARKERS = {
    "executive": 'tier="executive"',
    "pm": 'tier="pm"',
    "developer": 'tier="developer"',
}

@pytest.fixture
def request_fixture() -> EstimationRequest:
    return EstimationRequest(
        description=DESCRIPTION,
        project_type=ProjectType.INTERNAL_TOOL,
        detail_level=DetailLevel.MEDIUM,
        output_format=OutputFormat.NARRATIVE,
    )


@pytest.mark.parametrize("tier", ["executive", "pm", "developer"])
def test_v3_contains_only_its_own_marker(request_fixture, tier):
    system, _ = render_estimation_prompt(request_fixture, PromptVersion.V3, tier=tier)
    assert MARKERS[tier] in system
    for other, marker in MARKERS.items():
        if other != tier:
            assert marker not in system

@pytest.mark.parametrize("tier", ["executive", "pm", "developer"])
def test_v3_contains_only_its_own_marker(request_fixture, tier):
    system, _ = render_estimation_prompt(request_fixture, PromptVersion.V3, tier=tier)
    assert MARKERS[tier] in system
    for other, marker in MARKERS.items():
        if other != tier:
            assert marker not in system

def test_v3_default_has_no_audience_block(request_fixture):
    system, _ = render_estimation_prompt(request_fixture, PromptVersion.V3, tier="default")
    assert "<audience" not in system

def test_v3_without_tier_equals_default(request_fixture):
    a, _ = render_estimation_prompt(request_fixture, PromptVersion.V3)
    b, _ = render_estimation_prompt(request_fixture, PromptVersion.V3, tier="default")
    assert a == b

def test_v1_and_v2_ignore_the_tier(request_fixture):
    for v in (PromptVersion.V1, PromptVersion.V2):
        system, _ = render_estimation_prompt(request_fixture, v, tier="executive")
        assert "<audience" not in system


def test_v3_tells_the_model_not_to_refuse_partial_definitions(request_fixture):
    system, _ = render_estimation_prompt(request_fixture, PromptVersion.V3)
    assert "<partial_definition>" in system
    assert "no lower than 50" in system                              # el umbral viene de la constante


def test_v1_and_v2_keep_their_refusal_rules_unchanged(request_fixture):
    for v in (PromptVersion.V1, PromptVersion.V2):
        system, _ = render_estimation_prompt(request_fixture, v)
        assert "<partial_definition>" not in system
