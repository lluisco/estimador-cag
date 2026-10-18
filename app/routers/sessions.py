from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from instructor.core import IncompleteOutputException, InstructorRetryException
from pydantic import BaseModel

from app.guardrails.input import InputGuardrailViolation
from app.schemas import DetailLevel, EstimationRequest, EstimationResponse, OutputFormat, ProjectType, PromptVersion
from app.services.attachments import UnsupportedAttachment, build_transcript
from app.services.llm_service import get_llm_wrapper
from app.services.llm_wrapper import LLMWrapper
from app.services.session_service import generate_session_estimation
from app.services.tier import Tier
from app.sessions import ProjectMetadata, Session, SessionStore, get_session_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreated(BaseModel):
    session_id: str


class SessionState(BaseModel):
    session_id: str
    turns: int
    max_turns: int
    project_metadata: ProjectMetadata
    last_resolved_tier: str | None
    last_tier_rule: str | None


def _get_or_404(store: SessionStore, session_id: str) -> Session:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return session


@router.post("", response_model=SessionCreated, status_code=201)
def new_session(store: SessionStore = Depends(get_session_store)) -> SessionCreated:
    session = store.create()
    return SessionCreated(session_id=session.session_id)


@router.get("/{session_id}", response_model=SessionState)
def read_session(session_id: str, store: SessionStore = Depends(get_session_store)) -> SessionState:
    session = _get_or_404(store, session_id)
    return SessionState(
        session_id=session.session_id,
        turns=session.history.turns,
        max_turns=session.history.max_turns,
        project_metadata=session.project_metadata,
        last_resolved_tier=session.last_resolved_tier,
        last_tier_rule=session.last_tier_rule,
    )


@router.post("/{session_id}/estimate", response_model=EstimationResponse)
async def estimate_in_session(
    session_id: str,
    transcript: str = Form(..., min_length=20, max_length=80_000),
    project_type: ProjectType = Form(ProjectType.WEB_SAAS),
    detail_level: DetailLevel = Form(DetailLevel.MEDIUM),
    output_format: OutputFormat = Form(OutputFormat.PHASES_TABLE),
    prompt_version: PromptVersion = Form(PromptVersion.V3),
    tier: Tier | None = Form(None),
    attachments: list[UploadFile] = File(default=[]),
    store: SessionStore = Depends(get_session_store),
    llm_wrapper: LLMWrapper = Depends(get_llm_wrapper),
):
    session = _get_or_404(store, session_id)

    try:
        full_transcript = await build_transcript(transcript, attachments)
    except UnsupportedAttachment as e:
        raise HTTPException(status_code=400, detail=str(e))

    # El Form ya validó la transcripción. model_construct no revalida: el max_length=2000
    # de EstimationRequest.description es propio de /estimate y aquí entran los adjuntos.
    request = EstimationRequest.model_construct(
        description=full_transcript,
        project_type=project_type,
        detail_level=detail_level,
        output_format=output_format,
    )

    try:
        output = await run_in_threadpool(
            generate_session_estimation, session, request, transcript,
            [f.filename for f in attachments], prompt_version, tier,
            llm_wrapper=llm_wrapper,
        )
    except InputGuardrailViolation as e:
        raise HTTPException(status_code=400, detail={"reason": e.reason, "message": e.message})
    except IncompleteOutputException:
        raise HTTPException(
            status_code=502,
            detail="La estimación se cortó por el límite de tokens de salida. "
            "Prueba con un nivel de detalle menor o sube ESTIMATION_MAX_TOKENS.",
        )
    except InstructorRetryException as e:
        raise HTTPException(
            status_code=502,
            detail=f"El modelo no devolvió una estimación válida tras varios intentos: {e}",
        )

    return EstimationResponse(
        result=output.result, prompt_version=prompt_version.value,
        system_prompt=output.system_prompt, model=output.model,
        provider=output.provider, input_tokens=output.input_tokens,
        output_tokens=output.output_tokens, truncated=output.truncated,
        cache_hit=False,
    )
