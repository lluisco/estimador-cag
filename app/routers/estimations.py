from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.context.examples import ESTIMATION_EXAMPLES
from app.pricing import calculate_cost
from app.services.llm_service import StreamMetadata, build_system_prompt, generate_estimation, generate_estimation_stream

import json
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["estimations"])

class EstimationRequest(BaseModel):
    transcript: str = Field(
        ..., 
        description="Resumen de la reunión con el cliente",
    )

class EstimationResponse(BaseModel):
    estimation: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None
    truncated: bool

class Message(BaseModel):
    role: str
    content: str

class ChatEstimationRequest(BaseModel):
    messages: list[Message] = Field(
        ...,
        description="Historial completo de la conversación (user/assistant)",
    )

class ExampleResponse(BaseModel):
    meeting_summary: list[str]
    estimation: str

class ContextResponse(BaseModel):
    system_prompt: str
    examples: list[ExampleResponse]
    primary_model: str
    fallback_model: str

@router.post("/estimate", response_model=EstimationResponse)
async def estimate(request: EstimationRequest) -> EstimationResponse:
    try:
        result = generate_estimation(request.transcript)
        return EstimationResponse(
            estimation=result.text,
            model=result.model,
            provider=result.provider,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            estimated_cost_usd=calculate_cost(
                result.model, result.input_tokens, result.output_tokens
            ),
            truncated=result.truncated,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/context", response_model=ContextResponse)
def get_context() -> ContextResponse:
    return ContextResponse(
        system_prompt=build_system_prompt(),
        examples=[
            ExampleResponse(
                meeting_summary=list(example["meeting_summary"]),
                estimation=example["estimation"],
            )
            for example in ESTIMATION_EXAMPLES
        ],
        primary_model=settings.PRIMARY_MODEL,
        fallback_model=settings.FALLBACK_MODEL,
    )

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
        }) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")