from uuid import uuid4

import structlog
from fastapi import FastAPI, Request

from app.config import settings
from app.routers import estimations


def configure_logging() -> None:
    """Configura structlog: JSON en producción, consola legible en desarrollo."""
    if settings.APP_ENV == "production":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


configure_logging()

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


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    structlog.contextvars.bind_contextvars(request_id=request_id)
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.unbind_contextvars("request_id")
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "primary_model": settings.PRIMARY_MODEL,
        "fallback_model": settings.FALLBACK_MODEL,
    }
