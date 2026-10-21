"""Embedder de OpenAI.

Envuelve el modelo ``text-embedding-3-small``. ``embed_many`` agrupa los chunks
en lotes y hace una sola llamada a la API por lote (el endpoint acepta listas),
mucho más barato en latencia que una petición por chunk.
"""

from __future__ import annotations

import time

import structlog
from openai import OpenAI, RateLimitError

from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk

log = structlog.get_logger()

# Dimensión por defecto del modelo (sin recorte Matryoshka: se discute en el directo).
EMBEDDING_DIM = 1536

# Chunks por llamada a la API: evita martillear el endpoint con peticiones en serie.
BATCH_SIZE = 100

# PRECIO — CAMBIA CON EL TIEMPO. text-embedding-3-small cuesta 0,02 USD por millón
# de tokens de entrada. Actualizar cuando OpenAI revise tarifas.
PRICE_PER_MILLION_TOKENS_USD = 0.02

# Esperas (s) del reintento exponencial simple ante RateLimitError.
_RETRY_BACKOFF_SECONDS = (1, 2, 4)


def estimated_cost_usd(total_tokens: int) -> float:
    """Coste en USD de embeber ``total_tokens`` tokens de entrada."""
    return total_tokens / 1_000_000 * PRICE_PER_MILLION_TOKENS_USD


class OpenAIEmbedder:
    """Envoltorio fino de ``client.embeddings.create`` con lotes y reintentos."""

    def __init__(self, client: OpenAI, model: str = "text-embedding-3-small") -> None:
        self._client = client
        self._model = model

    def embed_one(self, text: str) -> list[float]:
        """Embebe un único texto (lo usa el script compare.py)."""
        return self._create([text])[0]

    def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        """Embebe todos los chunks en orden, en lotes de ``BATCH_SIZE``."""
        embedded: list[EmbeddedChunk] = []
        for start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[start : start + BATCH_SIZE]
            batch_tokens = sum(chunk.token_count for chunk in batch)

            t0 = time.perf_counter()
            vectors = self._create([chunk.text for chunk in batch])
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)

            log.info(
                "embedding_batch_done",
                chunks=len(batch),
                tokens=batch_tokens,
                latency_ms=latency_ms,
                model=self._model,
            )
            embedded.extend(
                EmbeddedChunk(**chunk.model_dump(), embedding=vector)
                for chunk, vector in zip(batch, vectors)
            )
        return embedded

    def _create(self, texts: list[str]) -> list[list[float]]:
        """Llama a la API; reintenta con backoff solo ante RateLimitError.

        Cualquier otro error se propaga al llamador.
        """
        for attempt, wait in enumerate((*_RETRY_BACKOFF_SECONDS, None)):
            try:
                response = self._client.embeddings.create(model=self._model, input=texts)
                return [item.embedding for item in response.data]
            except RateLimitError:
                if wait is None:
                    raise
                log.warning("embedding_rate_limited", attempt=attempt + 1, retry_in_s=wait)
                time.sleep(wait)
        raise AssertionError("unreachable")
