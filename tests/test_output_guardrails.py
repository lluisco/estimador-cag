from app.guardrails.output import enforce_scope_response
from app.schemas import LOW_CONFIDENCE_THRESHOLD, OUT_OF_SCOPE_PREFIX, EstimationResult, Phase


def _build(confidence_pct: int, summary: str) -> EstimationResult:
    # model_construct skips validators, needed to build a low-confidence
    # result without the prefix (the schema validator would reject it).
    return EstimationResult.model_construct(
        summary=summary,
        confidence_pct=confidence_pct,
        phases=[Phase(name="Discovery", duration_weeks=1, cost_eur=2500, confidence_pct=50, assumptions=[])],
        total_duration_weeks=1,
        total_cost_eur=2500,
    )


def test_high_confidence_passes_through_untouched():
    original = _build(80, "Solid build.")
    assert enforce_scope_response(original) is original


def test_threshold_boundary_is_not_low_confidence():
    original = _build(LOW_CONFIDENCE_THRESHOLD, "Borderline build.")
    assert enforce_scope_response(original) is original


def test_low_confidence_with_prefix_passes_through():
    original = _build(10, f"{OUT_OF_SCOPE_PREFIX} too vague.")
    assert enforce_scope_response(original) is original


def test_low_confidence_without_prefix_is_rewritten():
    original = _build(LOW_CONFIDENCE_THRESHOLD - 1, "A standard SaaS around 30k.")
    out = enforce_scope_response(original)

    assert out is not original
    assert out.summary.startswith(OUT_OF_SCOPE_PREFIX)
    assert "A standard SaaS around 30k." in out.summary
    assert out.confidence_pct == original.confidence_pct
    assert len(out.phases) == 1
    assert out.phases[0].name == "not_estimated"


def test_rewrite_is_idempotent_and_valid_with_long_summary():
    out = enforce_scope_response(_build(0, "x" * 1000))
    EstimationResult.model_validate(out.model_dump())
    assert enforce_scope_response(out) is out
