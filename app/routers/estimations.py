from fastapi import APIRouter, HTTPException, Query
from instructor.core.exceptions import IncompleteOutputException, InstructorRetryException
from pydantic import BaseModel, Field

from app.prompts.loader import render_estimation_prompt
from app.schemas import EstimationRequest, EstimationResponse, PromptVersion
from app.services.llm_service import StreamMetadata, generate_estimation, generate_estimation_stream

import json
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["estimations"])

class Message(BaseModel):
    role: str
    content: str

class ChatEstimationRequest(BaseModel):
    messages: list[Message] = Field(
        ...,
        description="Historial completo de la conversación (user/assistant)",
    )

@router.post("/estimate", response_model=EstimationResponse)
async def estimate(
    request: EstimationRequest,
    prompt_version: PromptVersion = Query(
        PromptVersion.V1, description="Versión de los templates de app/prompts/estimation/"
    ),
) -> EstimationResponse:
    try:
        system_prompt, user_prompt = render_estimation_prompt(request, version=prompt_version)
        output = generate_estimation(system_prompt, user_prompt)
        return EstimationResponse(
            result=output.result,
            prompt_version=prompt_version.value,
            system_prompt=system_prompt,
            model=output.model,
            provider=output.provider,
            input_tokens=output.input_tokens,
            output_tokens=output.output_tokens,
            truncated=output.truncated,
            cache_hit=output.cache_hit,
        )
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/estimate/stream")
def estimate_stream(request: ChatEstimationRequest):
    messages = [m.model_dump() for m in request.messages]
    metadata = StreamMetadata()

    def event_generator():
        try:
            for chunk in generate_estimation_stream(messages, metadata):
                yield json.dumps({"type": "delta", "text": chunk}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "detail": str(e)}) + "\n"
            return

        yield json.dumps({
            "type": "metadata",
            "model": metadata.model,
            "provider": metadata.provider,
            "input_tokens": metadata.input_tokens,
            "output_tokens": metadata.output_tokens,
            "truncated": metadata.truncated,
            "cache_hit": metadata.cache_hit,
        }) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")