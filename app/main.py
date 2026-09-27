from fastapi import FastAPI

from app.config import settings
from app.routers import estimations

app = FastAPI(
    title="Estimador CAG",
    description=(
        "Genera estimaciones de proyectos de software a partir de la transcripción "
        "de una reunión con el cliente.\n\n"
        "Usa una arquitectura CAG (Cache-Augmented Generation): las estimaciones "
        "históricas de referencia viajan en el propio prompt, sin recuperación previa "
        "ni base de datos vectorial."
    ),
    version="0.1.0",
)

app.include_router(estimations.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "primary_model": settings.PRIMARY_MODEL,
        "fallback_model": settings.FALLBACK_MODEL,
    }