import pytest
from pydantic import ValidationError

from app.services.critic import Critic, CriticFeedback, Issue, IssueCategory, Severity, Verdict
from app.sessions import ProjectMetadata
from tests.conftest import make_canned_result


def _issue(severity: Severity) -> Issue:
    return Issue(
        category=IssueCategory.OTHER,
        severity=severity,
        field_path="summary",
        description="detalle",
    )


def test_accept_without_issues_is_valid():
    feedback = CriticFeedback(verdict=Verdict.ACCEPT, confidence_in_review=90)
    assert feedback.issues == []


def test_needs_iteration_requires_a_serious_issue():
    with pytest.raises(ValidationError):
        CriticFeedback(
            verdict=Verdict.NEEDS_ITERATION,
            issues=[_issue(Severity.MINOR)],
            confidence_in_review=80,
        )


@pytest.mark.parametrize("severity", [Severity.CRITICAL, Severity.MAJOR])
def test_needs_iteration_accepts_critical_or_major(severity):
    feedback = CriticFeedback(
        verdict=Verdict.NEEDS_ITERATION, issues=[_issue(severity)], confidence_in_review=80
    )
    assert feedback.verdict == Verdict.NEEDS_ITERATION


def test_reject_requires_at_least_one_issue():
    with pytest.raises(ValidationError):
        CriticFeedback(verdict=Verdict.REJECT, issues=[], confidence_in_review=80)


def test_confidence_is_bounded():
    with pytest.raises(ValidationError):
        CriticFeedback(verdict=Verdict.ACCEPT, confidence_in_review=101)

def _review(fake_wrapper, tier="executive"):
    critic = Critic(fake_wrapper, "modelo-critic")
    return critic.review("quiero una app de reservas", ProjectMetadata(), tier, make_canned_result())


def test_review_returns_the_llm_feedback(fake_wrapper):
    expected = CriticFeedback(
        verdict=Verdict.NEEDS_ITERATION, issues=[_issue(Severity.MAJOR)], confidence_in_review=70
    )
    fake_wrapper.critic_queue = [expected]
    assert _review(fake_wrapper) == expected


def test_review_failure_accepts_with_zero_confidence(fake_wrapper):
    fake_wrapper.critic_error = RuntimeError("caído")
    feedback = _review(fake_wrapper)
    assert feedback.verdict == Verdict.ACCEPT
    assert feedback.confidence_in_review == 0
    assert feedback.issues == []


def test_review_uses_its_own_model(fake_wrapper):
    _review(fake_wrapper)
    assert fake_wrapper.calls_for("CriticFeedback")[-1]["model"] == "modelo-critic"


def test_review_prompt_carries_the_tier(fake_wrapper):
    _review(fake_wrapper, tier="developer")
    user = fake_wrapper.calls_for("CriticFeedback")[-1]["messages"][1]["content"]
    assert "<audience_tier>developer</audience_tier>" in user