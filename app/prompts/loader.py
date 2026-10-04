import hashlib
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.schemas import EstimationRequest, PromptVersion

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)

log = structlog.get_logger()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def render_estimation_prompt(
    request: EstimationRequest, version: PromptVersion = PromptVersion.V1
) -> tuple[str, str]:
    version = PromptVersion(version).value
    context = {
        "description": request.description,
        "project_type": request.project_type.value,
        "detail_level": request.detail_level.value,
        "output_format": request.output_format.value,
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
