from fastapi import APIRouter, File, Form, HTTPException, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.guardrails.input import InputGuardrailViolation
from app.schemas import DetailLevel, EstimationRequest, EstimationResponse, OutputFormat, ProjectType, PromptVersion
from app.services.attachments import UnsupportedAttachment, build_transcript
from app.services.session_service import generate_session_estimation
from app.sessions import ProjectMetadata, create_session, get_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreated(BaseModel):
    session_id: str

class SessionState(BaseModel):
    session_id: str
    turns: int
    project_metadata: ProjectMetadata


@router.post("", response_model=SessionCreated, status_code=201)
def new_session() -> SessionCreated:
    session = create_session()
    return SessionCreated(session_id=session.session_id)

@router.get("/{session_id}", response_model=SessionState)
def read_session(session_id: str) -> SessionState:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return SessionState(
        session_id=session.session_id,
        turns=session.history.turns,
        project_metadata=session.project_metadata,
    )

@router.post("/{session_id}/estimate", response_model=EstimationResponse)
async def estimate_in_session(
    session_id: str,
    transcript: str = Form(...),
    project_type: ProjectType = Form(ProjectType.WEB_SAAS),
    detail_level: DetailLevel = Form(DetailLevel.MEDIUM),
    output_format: OutputFormat = Form(OutputFormat.PHASES_TABLE),
    prompt_version: PromptVersion = Form(PromptVersion.V2),
    attachments: list[UploadFile] = File(default=[]),
):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    try:
        full_transcript = await build_transcript(transcript, attachments)
    except UnsupportedAttachment as e:
        raise HTTPException(status_code=400, detail=str(e))

    request = EstimationRequest(
        description=transcript,
        project_type=project_type,
        detail_level=detail_level,
        output_format=output_format,
    ).model_copy(update={"description": full_transcript})

    try:
        output = await run_in_threadpool(
            generate_session_estimation, session, request, transcript,
            [f.filename for f in attachments], prompt_version,
        )
    except InputGuardrailViolation as e:
        raise HTTPException(status_code=400, detail={"reason": e.reason, "message": e.message})
    # (aquí van los mismos except de IncompleteOutputException / InstructorRetryException del router de estimations)

    return EstimationResponse(
        result=output.result, prompt_version=prompt_version.value,
        system_prompt=output.system_prompt, model=output.model,
        provider=output.provider, input_tokens=output.input_tokens,
        output_tokens=output.output_tokens, truncated=output.truncated,
        cache_hit=False,
    )