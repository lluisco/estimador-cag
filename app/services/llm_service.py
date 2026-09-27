from typing import NamedTuple

from app.config import settings
from app.context.examples import ESTIMATION_EXAMPLES

from app.services.llm_wrapper import LLMWrapper

_wrapper = LLMWrapper(
    primary_model=settings.PRIMARY_MODEL,
    fallback_model=settings.FALLBACK_MODEL,
    open_api_key=settings.OPENAI_API_KEY,
    anthropic_api_key=settings.ANTHROPIC_API_KEY,
    timeout=settings.LLM_TIMEOUT_SECONDS,
    num_retries=settings.LLM_NUM_RETRIES,
)


class EstimationResult(NamedTuple):
    text: str
    input_tokens: int
    output_tokens: int
    truncated: bool
    model: str = ""
    provider: str = ""

class StreamMetadata:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.truncated = False
        self.model = ""
        self.provider = ""

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
    response = _wrapper.complete(system_prompt=system_prompt, user_message=transcript, max_tokens=2000)
    return EstimationResult(
        text=response.text,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        truncated=response.finish_reason == "length",
        model=response.model,
        provider=response.provider,
    )

def generate_estimation_stream(messages: list[dict], metadata: StreamMetadata):
    system_prompt = build_system_prompt()
    return _wrapper.complete_stream(
        system_prompt=system_prompt, messages=messages, max_tokens=8000, metadata=metadata
    )