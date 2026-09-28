from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.prompts.loader import render_estimation_prompt
from app.schemas import EstimationRequest, EstimationResponse
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
async def estimate(request: EstimationRequest, version: str = "v1") -> EstimationResponse:
    try:
        system_prompt, user_prompt = render_estimation_prompt(request, version=version)
        result = generate_estimation(system_prompt, user_prompt)
        return EstimationResponse(
            text=result.text,
            prompt_version=version,
            system_prompt=system_prompt,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            truncated=result.truncated,
            cache_hit=result.cache_hit,
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