import structlog

from pydantic import BaseModel, Field

from app.prompts.loader import render_conversation_summary_prompts
from app.services.llm_wrapper import LLMWrapper

log = structlog.get_logger()

class ConversationSummary(BaseModel):
    """Module for summarizing conversations. Es una clase porque instructor solo trabaja con modelos. 
    max_length=4000 es un guardrail para evitar resúmenes demasiado largos."""
    summary: str = Field(max_length=4000)

class CumulativeSummarizer:
    def __init__(self, llm_wrapper: LLMWrapper, model: str):
        self._llm = llm_wrapper
        self.model = model

    def summarize(self, previous: str | None, expelled: list[tuple[dict, dict]]) -> str | None:
        try:
            system_prompt, user_message = render_conversation_summary_prompts(
                previous=previous, 
                turns=expelled
            )
        except Exception as e:
            log.warning("summary_failed", error_type=type(e).__name__, error=str(e)[:200])
            return previous # Return the previous summary if summarization fails.
        try:
            response = self._llm.complete_structured(
                system_prompt=system_prompt,
                user_message=user_message,
                response_model=ConversationSummary,
                model=self.model,
                max_tokens=1500,
            )
        except Exception as e:
            log.warning("summary_failed", error_type=type(e).__name__, error=str(e)[:200])
            return previous # Return the previous summary if summarization fails.

        return response.parsed.summary