from app.config import settings
from app.guardrails.input import validate_input
from app.guardrails.output import enforce_scope_response
from app.prompts.loader import render_estimation_prompt
from app.schemas import EstimationRequest, EstimationResult, PromptVersion
from app.services.llm_service import EstimationOutput, _wrapper
from app.services.project_memory import update_project_metadata
from app.sessions import Session


def _history_user_text(transcript: str, attachment_names: list[str]) -> str:
    if not attachment_names:
        return transcript
    return f"{transcript}\n[Adjuntos: {', '.join(attachment_names)}]"


def _history_assistant_text(result: EstimationResult) -> str:
    phases = ", ".join(p.name for p in result.phases)
    return (
        f"{result.summary}\n"
        f"Total: {result.total_duration_weeks} semanas, {result.total_cost_eur} EUR. "
        f"Fases: {phases}."
    )


def generate_session_estimation(
    session: Session,
    request: EstimationRequest,   # description = transcript + texto de adjuntos
    transcript: str,              # solo lo que escribió el cliente
    attachment_names: list[str],
    version: PromptVersion = PromptVersion.V2,
) -> EstimationOutput:
    # los adjuntos son input no confiable: se validan junto con el transcript
    validate_input(request.description)

    system_prompt, user_prompt = render_estimation_prompt(
        request, version, project_metadata=session.project_metadata
    )
    messages = session.history.to_messages_list(system_prompt, user_prompt)

    response = _wrapper.complete_structured(
        messages=messages,
        max_tokens=settings.ESTIMATION_MAX_TOKENS,
        response_model=EstimationResult,
    )
    result = enforce_scope_response(response.parsed)

    # solo tras el éxito se muta la sesión
    session.history.add_turn(
        _history_user_text(transcript, attachment_names),
        _history_assistant_text(result),
    )
    session.project_metadata = update_project_metadata(
        session.project_metadata, request.description, result.summary
    )

    return EstimationOutput(
        result=result,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        truncated=response.finish_reason == "length",
        model=response.model,
        provider=response.provider,
        system_prompt=system_prompt,
    )
