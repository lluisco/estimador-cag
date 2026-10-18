"""Contador de consumo por turno.

Un turno hace hasta 3 llamadas al LLM (estimación, extractor de metadata y, si
comprime, resumidor). ``MeteredLLM`` se pone delante del wrapper, reenvía las
llamadas y suma el consumo de todas, sin cambiar las firmas de los servicios
auxiliares. Se crea uno por turno, así que es seguro con varios hilos.

Límite conocido: las llamadas que fallan (y los reintentos internos de litellm)
no devuelven respuesta y por tanto no se contabilizan.
"""

from dataclasses import dataclass

from app.pricing import calculate_cost
from app.services.llm_wrapper import LLMWrapper


@dataclass
class TurnUsage:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    unpriced_calls: int = 0  # llamadas cuyo modelo no está en la tabla de precios


class MeteredLLM:
    def __init__(self, inner: LLMWrapper):
        self._inner = inner
        self.usage = TurnUsage()

    def _record(self, response) -> None:
        u = self.usage
        u.calls += 1
        u.tokens_in += response.input_tokens
        u.tokens_out += response.output_tokens
        u.latency_ms += response.latency_ms
        cost = calculate_cost(response.model, response.input_tokens, response.output_tokens)
        if cost is None:
            u.unpriced_calls += 1  # no se suma 0 en silencio: queda marcado en el evento
        else:
            u.cost_usd += cost

    def complete_structured(self, **kwargs):
        response = self._inner.complete_structured(**kwargs)
        self._record(response)
        return response

    def complete(self, **kwargs):
        response = self._inner.complete(**kwargs)
        self._record(response)
        return response
