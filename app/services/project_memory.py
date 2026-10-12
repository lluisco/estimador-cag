"""Segunda llamada al LLM de cada turno: extrae el ``ProjectMetadata`` actualizado.

Corre DESPUÉS de que la estimación haya pasado la validación. La fusión con lo ya
conocido se hace en código (``ProjectMetadata.merge_with``), no en el LLM. Si la
extracción falla, se registra y se conserva el metadata anterior: perder un
refresco de memoria es aceptable, romper la petición del usuario no.
"""

import structlog

from app.prompts.loader import render_metadata_extraction_prompt
from app.schemas import EstimationResult
from app.services.llm_wrapper import LLMWrapper
from app.sessions import ProjectMetadata

log = structlog.get_logger()


def update_project_metadata(
    *,
    previous: ProjectMetadata,
    transcript: str,
    result: EstimationResult,
    llm_wrapper: LLMWrapper,
    model: str,
) -> ProjectMetadata:
    system_prompt, user_message = render_metadata_extraction_prompt(
        previous=previous, transcript=transcript, result=result
    )
    try:
        response = llm_wrapper.complete_structured(
            system_prompt=system_prompt,
            user_message=user_message,
            response_model=ProjectMetadata,
            model=model,
            max_tokens=1000,
        )
    except Exception as exc:
        log.warning("metadata_extraction_failed", error_type=type(exc).__name__, error=str(exc)[:200])
        return previous
    return previous.merge_with(response.parsed)
