import json
from typing import NamedTuple

from app.config import settings
from app.context.examples import ESTIMATION_EXAMPLES

from app.services.llm_wrapper import LLMWrapper

from app.services.cache import EstimationCache

_wrapper = LLMWrapper(
    primary_model=settings.PRIMARY_MODEL,
    fallback_model=settings.FALLBACK_MODEL,
    open_api_key=settings.OPENAI_API_KEY,
    anthropic_api_key=settings.ANTHROPIC_API_KEY,
    timeout=settings.LLM_TIMEOUT_SECONDS,
    num_retries=settings.LLM_NUM_RETRIES,
)

_cache = EstimationCache(
    redis_url=settings.REDIS_URL,
    ttl_seconds=settings.CACHE_TTL_SECONDS,
)


class EstimationResult(NamedTuple):
    text: str
    input_tokens: int
    output_tokens: int
    truncated: bool
    model: str = ""
    provider: str = ""
    cache_hit: bool = False

class StreamMetadata:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.truncated = False
        self.model = ""
        self.provider = ""
        self.cache_hit = False

SYSTEM_INSTRUCTIONS = """
Eres un asistente experto en estimaciones de proyectos de software.
Recibes un resumen de la reunión con el cliente y debes generar una estimación detallada de las tareas, el tiempo requerido, el equipo recomendado y la duración estimada del proyecto.

Reglas:
- Básate en los ejemplos proporcionados en ESTIMATION_EXAMPLES para generar tus estimaciones.
- Desglosa el trabajo en tareas concretas con horas asignadas.
- Si el cliente menciona funcionalidades nice to have o que acepta posponer, sepáralo en tu estimación.
- No des una ciffra global sin un desglose.
- No inventes requisitos que no hayan sido mencionados por el cliente.
- Responde en español y en formato markdown.
"""

def _build_examples_block() -> str:
    blocks = []
    for example in ESTIMATION_EXAMPLES:
        meeting_summary = "\n".join(f"- {line}" for line in example["meeting_summary"])
        estimation = example["estimation"]
        blocks.append(f"{meeting_summary}\n{estimation}")
    return "\n\n".join(blocks)

def build_system_prompt() -> str:
    return (
        f"{SYSTEM_INSTRUCTIONS}\n\n"
        f"A continuación tienes estimaciones previas realizadas por la consultora. "
        f"Úsalas como referencia de criterio y formato:\n\n"
        f"<estimaciones_previas>\n{_build_examples_block()}\n</estimaciones_previas>"
    )

def generate_estimation(transcript: str) -> EstimationResult:
    system_prompt = build_system_prompt()
    cache_key = EstimationCache.make_key(
        system_prompt=system_prompt, user_message=transcript, model=settings.PRIMARY_MODEL, max_tokens=2000
    )

    cached = _cache.get(cache_key)
    if cached:
        return EstimationResult(**cached)._replace(cache_hit=True)

    response = _wrapper.complete(system_prompt=system_prompt, user_message=transcript, max_tokens=2000)
    result = EstimationResult(
        text=response.text,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        truncated=response.finish_reason == "length",
        model=response.model,
        provider=response.provider,
    )
    _cache.set(cache_key, result._asdict())
    return result

def generate_estimation_stream(messages: list[dict], metadata: StreamMetadata):
    system_prompt = build_system_prompt()
    cache_key = EstimationCache.make_key(
        system_prompt=system_prompt,
        user_message=json.dumps(messages, sort_keys=True),
        model=settings.PRIMARY_MODEL,
        max_tokens=8000,
    )

    cached = _cache.get(cache_key)
    if cached:
        metadata.input_tokens = cached["input_tokens"]
        metadata.output_tokens = cached["output_tokens"]
        metadata.truncated = cached["truncated"]
        metadata.model = cached["model"]
        metadata.provider = cached["provider"]
        metadata.cache_hit = True
        yield cached["text"]
        return

    chunks = []
    for chunk in _wrapper.complete_stream(
        system_prompt=system_prompt, messages=messages, max_tokens=8000, metadata=metadata
    ):
        chunks.append(chunk)
        yield chunk

    _cache.set(cache_key, {
        "text": "".join(chunks),
        "input_tokens": metadata.input_tokens,
        "output_tokens": metadata.output_tokens,
        "truncated": metadata.truncated,
        "model": metadata.model,
        "provider": metadata.provider,
    })