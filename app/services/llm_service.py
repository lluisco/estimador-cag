from typing import NamedTuple

from anthropic import Anthropic
from openai import OpenAI

from app.config import settings
from app.context.examples import ESTIMATION_EXAMPLES


class EstimationResult(NamedTuple):
    text: str
    input_tokens: int
    output_tokens: int
    truncated: bool

class StreamMetadata:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.truncated = False

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

def _generate_anthropic(system_prompt: str, transcript: str) -> EstimationResult:
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=2000,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": transcript
            }
        ]
    )
    return EstimationResult(
        text=response.content[0].text,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        truncated=response.stop_reason == "max_tokens",
    )

def _generate_anthropic_stream(system_prompt: str, messages: list[dict], metadata: StreamMetadata):
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    with client.messages.stream(
        model=settings.LLM_MODEL,
        max_tokens=8000,
        system=system_prompt,
        messages=messages
    ) as stream:
       for text in stream.text_stream:
           yield text

    final_message = stream.get_final_message()
    metadata.input_tokens = final_message.usage.input_tokens
    metadata.output_tokens = final_message.usage.output_tokens
    metadata.truncated = final_message.stop_reason == "max_tokens"

def _generate_openai(system_prompt: str, transcript: str) -> EstimationResult:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.responses.create(
        model=settings.LLM_MODEL,
        max_output_tokens=2000,
        instructions=system_prompt,
        input=[
            {
                "role": "user",
                "content": transcript
            }
        ]
    )
    return EstimationResult(
        text=response.output_text,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        truncated=response.incomplete_details is not None
        and response.incomplete_details.reason == "max_output_tokens",
    )

def _generate_openai_stream(system_prompt: str, messages: list[dict], metadata: StreamMetadata):
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    with client.responses.stream(
        model=settings.LLM_MODEL,
        max_output_tokens=2000,
        instructions=system_prompt,
        input=messages
    ) as stream:
        for event in stream:
            if event.type == "response.output_text.delta":
                yield event.delta

        final_response = stream.get_final_response()
        metadata.input_tokens = final_response.usage.input_tokens
        metadata.output_tokens = final_response.usage.output_tokens
        metadata.truncated = (
            final_response.incomplete_details is not None
            and final_response.incomplete_details.reason == "max_output_tokens"
        )

def generate_estimation(transcript: str) -> EstimationResult:
    system_prompt = build_system_prompt()

    if settings.LLM_PROVIDER == "anthropic":
        return _generate_anthropic(system_prompt, transcript)
    if settings.LLM_PROVIDER == "openai":
        return _generate_openai(system_prompt, transcript)

    raise ValueError(f"Proveedor LLM no soportado: {settings.LLM_PROVIDER}")

def generate_estimation_stream(messages: list[dict], metadata: StreamMetadata):
    system_prompt = build_system_prompt()

    if settings.LLM_PROVIDER == "anthropic":
        return _generate_anthropic_stream(system_prompt, messages, metadata)
    if settings.LLM_PROVIDER == "openai":
        return _generate_openai_stream(system_prompt, messages, metadata)

    raise ValueError(f"Proveedor LLM no soportado para streaming: {settings.LLM_PROVIDER}")