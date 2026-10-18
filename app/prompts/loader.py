import hashlib
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.config import settings
from app.schemas import (
    LOW_CONFIDENCE_THRESHOLD,
    OUT_OF_SCOPE_PREFIX,
    EstimationRequest,
    EstimationResult,
    PromptVersion,
)
from app.sessions import ProjectMetadata

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
)

log = structlog.get_logger()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def render_estimation_prompt(
    request: EstimationRequest, 
    version: PromptVersion = PromptVersion.V1,
    project_metadata: ProjectMetadata | None = None,
    tier: str | None = None,
) -> tuple[str, str]:
    version = PromptVersion(version).value
    context = {
        "description": request.description,
        "project_type": request.project_type.value,
        "detail_level": request.detail_level.value,
        "output_format": request.output_format.value,
        "hourly_rates": settings.HOURLY_RATES_EUR,
        "out_of_scope_prefix": OUT_OF_SCOPE_PREFIX,
        "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
        "project_metadata": (project_metadata or ProjectMetadata()).model_dump(),
        "tier": str(tier) if tier else "default"
    }

    system = _env.get_template(f"estimation/{version}/system.j2").render(context)
    user = _env.get_template(f"estimation/{version}/user.j2").render(context)

    # Solo hashes y longitudes: el contenido incluye la descripción del cliente.
    log.info(
        "prompt_rendered",
        prompt_version=version,
        system_hash=_content_hash(system),
        user_hash=_content_hash(user),
        system_chars=len(system),
        user_chars=len(user),
    )

    return system, user


def render_metadata_extraction_prompt(
    *,
    previous: ProjectMetadata,
    transcript: str,
    result: EstimationResult,
    version: str = "v1",
) -> tuple[str, str]:
    """Prompts del extractor de project_metadata (segunda llamada de cada turno)."""
    context = {
        "previous": previous.model_dump(),
        "previous_is_empty": previous.is_empty(),
        "transcript": transcript,
        "result": result.model_dump(),
    }
    system = _env.get_template(f"metadata_extraction/{version}/system.j2").render(context)
    user = _env.get_template(f"metadata_extraction/{version}/user.j2").render(context)
    return system, user

def render_conversation_summary_prompts(
    previous: str | None,
    turns: list[tuple[dict, dict]],
    version: str = "v1",
) -> tuple[str, str]:
    context = {
        "previous_summary": previous or "",
        "turns": [{"user": u["content"], "assistant": a["content"]} for u, a in turns],
    }
    system = _env.get_template(f"conversation_summary/{version}/system.j2").render(context)
    user = _env.get_template(f"conversation_summary/{version}/user.j2").render(context)
    return system, user
