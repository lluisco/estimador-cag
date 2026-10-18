"""Boss del patrón Actor-Critic-Boss: máquina de estados sin llamadas al LLM.

Recibe al actor y al critic como funciones, así no sabe nada de prompts, modelos ni
sesiones y se prueba entero con dobles. Decide leyendo campos del CriticFeedback.
"""

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas import LOW_CONFIDENCE_THRESHOLD, EstimationResult
from app.services.critic import CriticFeedback, Issue, Severity, Verdict


class BossOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"                # el Critic rechazó: se sintetiza
    MAX_ITERATIONS = "max_iterations"    # se agotaron las vueltas: se sintetiza


class BossIteration(BaseModel):
    iteration: int
    verdict: Verdict
    issues: list[Issue]
    confidence_in_review: int


class BossTrace(BaseModel):
    max_iterations: int
    iterations: list[BossIteration] = Field(default_factory=list)
    outcome: BossOutcome | None = None

Actor = Callable[[CriticFeedback | None], EstimationResult]
CriticFn = Callable[[EstimationResult], CriticFeedback]


class Boss:
    def __init__(self, max_iterations: int):
        if max_iterations < 1:
            raise ValueError("max_iterations debe ser al menos 1")
        self.max_iterations = max_iterations

    def run(self, actor: Actor, critic: CriticFn) -> tuple[EstimationResult, BossTrace]:
        trace = BossTrace(max_iterations=self.max_iterations)
        feedback: CriticFeedback | None = None

        for i in range(1, self.max_iterations + 1):
            draft = actor(feedback)
            feedback = critic(draft)
            trace.iterations.append(
                BossIteration(
                    iteration=i,
                    verdict=feedback.verdict,
                    issues=feedback.issues,
                    confidence_in_review=feedback.confidence_in_review,
                )
            )

            if feedback.verdict == Verdict.ACCEPT:
                trace.outcome = BossOutcome.ACCEPTED
                return draft, trace
            if feedback.verdict == Verdict.REJECT:
                trace.outcome = BossOutcome.REJECTED
                return _synthesize(draft, feedback), trace
            # needs_iteration: otra vuelta, ahora con feedback

        trace.outcome = BossOutcome.MAX_ITERATIONS
        return _synthesize(draft, feedback), trace


_SYNTHESIS_PENALTY = 20
_SUMMARY_MAX = 1200
_MAX_WARNINGS = 3


def _synthesize(draft: EstimationResult, feedback: CriticFeedback) -> EstimationResult:
    """Último borrador con las advertencias del Critic delante y la confianza reducida.

    Usa LOW_CONFIDENCE_THRESHOLD y no un número fijo: bajar de ese umbral exigiría el
    prefijo OUT OF SCOPE y el resultado violaría el validador de EstimationResult.
    """
    # una estimación ya rechazada por baja confianza lleva su prefijo: no se toca
    if draft.confidence_pct < LOW_CONFIDENCE_THRESHOLD:
        return draft

    serious = [i for i in feedback.issues if i.severity in (Severity.CRITICAL, Severity.MAJOR)]
    warnings = [i.description.rstrip(" .") for i in (serious or feedback.issues)][:_MAX_WARNINGS]
    note = f"Advertencias de la revisión: {'; '.join(warnings)}. " if warnings else ""

    # model_validate (no model_copy) para que los validadores vuelvan a ejecutarse
    return EstimationResult.model_validate(
        {
            **draft.model_dump(),
            "summary": (note + draft.summary)[:_SUMMARY_MAX],
            "confidence_pct": max(LOW_CONFIDENCE_THRESHOLD, draft.confidence_pct - _SYNTHESIS_PENALTY),
        }
    )
