from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from instructor.core import IncompleteOutputException, InstructorRetryException
from pydantic import BaseModel

from app.guardrails.input import InputGuardrailViolation
from app.schemas import DetailLevel, EstimationRequest, EstimationResponse, OutputFormat, ProjectType, PromptVersion
from app.services.attachments import UnsupportedAttachment, build_transcript
from app.services.boss import BossTrace
from app.services.llm_service import EstimationOutput, get_llm_wrapper
from app.services.llm_wrapper import LLMWrapper
from app.services.session_service import generate_session_estimation, generate_session_estimation_acb
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
    anchors: int          # turnos anclados (pares user/assistant que nunca se expulsan)
    summary_chars: int    # longitud del resumen acumulativo; 0 si aún no hay


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
        anchors=len(session.history.anchors) // 2,
        summary_chars=len(session.history.summary or ""),
    )


class EstimationACBResponse(EstimationResponse):
    """La respuesta de /estimate más la traza del Boss (veredicto e issues por iteración)."""

    acb: BossTrace


async def _build_request(
    transcript: str,
    attachments: list[UploadFile],
    project_type: ProjectType,
    detail_level: DetailLevel,
    output_format: OutputFormat,
) -> EstimationRequest:
    try:
        full_transcript = await build_transcript(transcript, attachments)
    except UnsupportedAttachment as e:
        raise HTTPException(status_code=400, detail=str(e))

    # El Form ya validó la transcripción. model_construct no revalida: el max_length=2000
    # de EstimationRequest.description es propio de /estimate y aquí entran los adjuntos.
    return EstimationRequest.model_construct(
        description=full_transcript,
        project_type=project_type,
        detail_level=detail_level,
        output_format=output_format,
    )


async def _run_turn(fn, *args, **kwargs):
    """Ejecuta el turno fuera del event loop y traduce los errores a HTTP."""
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
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


def _response_fields(output: EstimationOutput, prompt_version: PromptVersion) -> dict:
    return dict(
        result=output.result, prompt_version=prompt_version.value,
        system_prompt=output.system_prompt, model=output.model,
        provider=output.provider, input_tokens=output.input_tokens,
        output_tokens=output.output_tokens, truncated=output.truncated,
        cache_hit=False,
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
    request = await _build_request(transcript, attachments, project_type, detail_level, output_format)

    output = await _run_turn(
        generate_session_estimation, session, request, transcript,
        [f.filename for f in attachments], prompt_version, tier,
        llm_wrapper=llm_wrapper,
    )
    return EstimationResponse(**_response_fields(output, prompt_version))


@router.post("/{session_id}/estimate-acb", response_model=EstimationACBResponse)
async def estimate_in_session_acb(
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
    """Mismo contrato multipart que /estimate, con revisión Actor-Critic-Boss.

    Endpoint aparte, no el comportamiento por defecto: en el peor caso cuesta hasta
    8 llamadas al LLM por turno frente a 2-3 del flujo normal.
    """
    session = _get_or_404(store, session_id)
    request = await _build_request(transcript, attachments, project_type, detail_level, output_format)

    output, trace = await _run_turn(
        generate_session_estimation_acb, session, request, transcript,
        [f.filename for f in attachments], prompt_version, tier,
        llm_wrapper=llm_wrapper,
    )
    return EstimationACBResponse(**_response_fields(output, prompt_version), acb=trace)
