"""Output guardrails: safety net on top of the Pydantic model_validators.

The schema validator (``low_confidence_requires_out_of_scope_prefix``) is the
first line: when it raises, Instructor re-prompts the LLM. This filter is the
second line: it never raises, it rewrites a low-confidence answer that does not
declare itself out of scope (edge cases, or a future loosening of the validator).
"""

import structlog

from app.schemas import EstimationResult, Phase, LOW_CONFIDENCE_THRESHOLD, OUT_OF_SCOPE_PREFIX

log = structlog.get_logger()

# Phase.cost_eur and total_cost_eur must be > 0 in the schema, so the
# placeholder uses the minimum value; it is not a real estimate.
_NOT_ESTIMATED_PHASE = Phase(
    name="not_estimated",
    duration_weeks=1,
    cost_eur=1,
    confidence_pct=0,
    assumptions=["Cannot be sized without more information"],
)


def enforce_scope_response(result: EstimationResult) -> EstimationResult:
    """Rewrite the result if confidence is low and the summary does not declare it."""
    is_low_confidence = result.confidence_pct < LOW_CONFIDENCE_THRESHOLD
    already_marked = result.summary.startswith(OUT_OF_SCOPE_PREFIX)

    if not is_low_confidence or already_marked:
        return result

    log.info(
        "low_confidence_marked_out_of_scope",
        confidence_pct=result.confidence_pct,
        original_summary_chars=len(result.summary),
    )

    new_summary = (
        f"{OUT_OF_SCOPE_PREFIX} not enough information to estimate confidently. "
        f"Original model rationale: {result.summary[:400]}"
    )

    return EstimationResult(
        summary=new_summary,
        confidence_pct=result.confidence_pct,
        phases=[_NOT_ESTIMATED_PHASE],
        total_duration_weeks=1,
        total_cost_eur=1,
    )
