"""El Boss se prueba sin LLM: actor y critic son dobles con respuestas guionizadas."""

import pytest

from app.schemas import LOW_CONFIDENCE_THRESHOLD, OUT_OF_SCOPE_PREFIX, EstimationResult
from app.services.boss import Boss, BossOutcome
from app.services.critic import CriticFeedback, Issue, IssueCategory, Severity, Verdict
from tests.conftest import make_canned_result


def _feedback(verdict: Verdict, severity: Severity = Severity.MAJOR) -> CriticFeedback:
    issues = [] if verdict == Verdict.ACCEPT else [
        Issue(category=IssueCategory.SCOPE_MISREAD, severity=severity,
              field_path="phases[0]", description="falta el módulo de pagos")
    ]
    return CriticFeedback(verdict=verdict, issues=issues, confidence_in_review=80)


class ScriptedActor:
    """Devuelve siempre el mismo borrador y apunta qué feedback recibió en cada vuelta."""

    def __init__(self, draft: EstimationResult | None = None):
        self.draft = draft or make_canned_result()
        self.received: list[CriticFeedback | None] = []

    def __call__(self, feedback: CriticFeedback | None) -> EstimationResult:
        self.received.append(feedback)
        return self.draft


def scripted_critic(*verdicts: Verdict):
    queue = [_feedback(v) for v in verdicts]
    return lambda _draft: queue.pop(0)


def test_accepts_on_first_try():
    actor = ScriptedActor()
    result, trace = Boss(3).run(actor, scripted_critic(Verdict.ACCEPT))
    assert result == actor.draft
    assert trace.outcome == BossOutcome.ACCEPTED
    assert actor.received == [None]                                  # una vuelta, sin feedback


def test_iterates_then_accepts():
    actor = ScriptedActor()
    _, trace = Boss(3).run(actor, scripted_critic(Verdict.NEEDS_ITERATION, Verdict.ACCEPT))
    assert trace.outcome == BossOutcome.ACCEPTED
    assert len(trace.iterations) == 2
    assert actor.received[0] is None
    assert actor.received[1].verdict == Verdict.NEEDS_ITERATION      # el feedback llega al actor


def test_exhausts_iterations_and_synthesizes():
    actor = ScriptedActor()
    result, trace = Boss(2).run(
        actor, scripted_critic(Verdict.NEEDS_ITERATION, Verdict.NEEDS_ITERATION)
    )
    assert trace.outcome == BossOutcome.MAX_ITERATIONS
    assert result.summary.startswith("Advertencias de la revisión: falta el módulo de pagos")
    assert result.confidence_pct < actor.draft.confidence_pct


def test_reject_synthesizes_without_iterating():
    actor = ScriptedActor()
    result, trace = Boss(3).run(actor, scripted_critic(Verdict.REJECT))
    assert trace.outcome == BossOutcome.REJECTED
    assert len(trace.iterations) == 1
    assert result.summary.startswith("Advertencias de la revisión:")


def test_reject_with_only_minor_issues_still_warns():
    critic = lambda _draft: _feedback(Verdict.REJECT, Severity.MINOR)
    result, _ = Boss(1).run(ScriptedActor(), critic)
    assert "falta el módulo de pagos" in result.summary


def test_synthesis_note_has_no_double_period():
    critic = lambda _draft: CriticFeedback(
        verdict=Verdict.REJECT, confidence_in_review=80,
        issues=[Issue(category=IssueCategory.OTHER, severity=Severity.MAJOR,
                      field_path="summary", description="Falta el alcance.")],
    )
    result, _ = Boss(1).run(ScriptedActor(), critic)
    assert result.summary.startswith("Advertencias de la revisión: Falta el alcance. ")
    assert ".." not in result.summary


def test_one_trace_entry_per_iteration():
    _, trace = Boss(3).run(ScriptedActor(), scripted_critic(
        Verdict.NEEDS_ITERATION, Verdict.NEEDS_ITERATION, Verdict.ACCEPT))
    assert [it.iteration for it in trace.iterations] == [1, 2, 3]
    assert trace.max_iterations == 3


@pytest.mark.parametrize("bad", [0, -1])
def test_max_iterations_below_one_fails(bad):
    with pytest.raises(ValueError):
        Boss(bad)


def test_synthesis_never_drops_below_threshold():
    # el bug latente: 55 - 20 = 35 quedaría bajo el umbral sin el prefijo OUT OF SCOPE
    draft = make_canned_result().model_copy(update={"confidence_pct": 55})
    result, _ = Boss(1).run(ScriptedActor(draft), scripted_critic(Verdict.REJECT))
    assert result.confidence_pct == LOW_CONFIDENCE_THRESHOLD


def test_synthesis_keeps_out_of_scope_drafts_untouched():
    draft = make_canned_result().model_copy(
        update={"confidence_pct": 30, "summary": f"{OUT_OF_SCOPE_PREFIX} demasiado vago"}
    )
    result, _ = Boss(1).run(ScriptedActor(draft), scripted_critic(Verdict.REJECT))
    assert result == draft


def test_synthesis_respects_summary_max_length():
    draft = make_canned_result().model_copy(update={"summary": "x" * 1200})
    result, _ = Boss(1).run(ScriptedActor(draft), scripted_critic(Verdict.REJECT))
    assert len(result.summary) == 1200
