from enum import StrEnum

from pydantic import BaseModel, Field, model_validator
import structlog

from app.prompts.loader import render_critic_prompt
from app.schemas import EstimationResult
from app.services.llm_wrapper import LLMWrapper
from app.sessions import ProjectMetadata

log = structlog.get_logger()

class Verdict(StrEnum):
    ACCEPT = "accept"
    NEEDS_ITERATION = "needs_iteration"
    REJECT = "reject"


class Severity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class IssueCategory(StrEnum):
    INVENTED_DATA = "invented_data"      # datos que el cliente no dijo
    SCOPE_MISREAD = "scope_misread"      # alcance mal interpretado
    UNBALANCED_PHASES = "unbalanced_phases"
    TONE_MISMATCH = "tone_mismatch"      # el tono no encaja con el tier
    MATH_ERROR = "math_error"
    OTHER = "other"


class Issue(BaseModel):
    category: IssueCategory
    severity: Severity
    field_path: str = Field(description="Ruta del campo afectado, p. ej. 'phases[2].assumptions'")
    description: str = Field(max_length=500)


class CriticFeedback(BaseModel):
    verdict: Verdict
    issues: list[Issue] = Field(default_factory=list)
    confidence_in_review: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _check_verdict_matches_issues(self):
        if self.verdict == Verdict.NEEDS_ITERATION and not any(
            i.severity in (Severity.CRITICAL, Severity.MAJOR) for i in self.issues
        ):
            raise ValueError("needs_iteration exige al menos una issue critical o major")
        if self.verdict == Verdict.REJECT and not self.issues:
            raise ValueError("reject exige al menos una issue")
        return self

class Critic:
    """Auditor sin estado. Si falla, acepta con confianza 0: el auditor nunca rompe la petición."""

    def __init__(self, llm_wrapper: LLMWrapper, model: str):
        self._llm = llm_wrapper
        self._model = model

    def review(
        self,
        transcript: str,
        metadata: ProjectMetadata,
        tier: str,
        result: EstimationResult,
    ) -> CriticFeedback:
        try:
            system_prompt, user_message = render_critic_prompt(
                transcript=transcript, metadata=metadata, tier=tier, result=result
            )
            response = self._llm.complete_structured(
                system_prompt=system_prompt,
                user_message=user_message,
                response_model=CriticFeedback,
                model=self._model,
                max_tokens=1500,
            )
        except Exception as exc:
            log.warning("critic_failed", error_type=type(exc).__name__, error=str(exc)[:200])
            return CriticFeedback(verdict=Verdict.ACCEPT, confidence_in_review=0)
        return response.parsed

