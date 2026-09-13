from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
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

@router.post("/estimate", response_model=EstimationResponse)
async def estimate(request: EstimationRequest) -> EstimationResponse:
    try:
        estimation = generate_estimation(request.transcript)
        return EstimationResponse(
            estimation=estimation,
            model=settings.LLM_MODEL,
            provider=settings.LLM_PROVIDER
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))