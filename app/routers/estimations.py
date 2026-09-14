from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.pricing import calculate_cost
from app.services.llm_service import generate_estimation

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

@router.post("/estimate", response_model=EstimationResponse)
async def estimate(request: EstimationRequest) -> EstimationResponse:
    try:
        result = generate_estimation(request.transcript)
        return EstimationResponse(
            estimation=result.text,
            model=settings.LLM_MODEL,
            provider=settings.LLM_PROVIDER,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            estimated_cost_usd=calculate_cost(
                settings.LLM_MODEL, result.input_tokens, result.output_tokens
            ),
            truncated=result.truncated,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))