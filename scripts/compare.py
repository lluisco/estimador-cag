#!/usr/bin/env python3
"""Sanity check de embeddings: similitud coseno entre dos textos.

Embebe los dos textos con ``text-embedding-3-small`` (reutilizando
``OpenAIEmbedder``) e imprime su similitud coseno. El coseno se calcula a mano
con ``math`` de la biblioteca estándar: sin numpy ni scikit-learn.

Uso::

    # fuera del contenedor (desde la raíz del repo, con .env presente):
    uv run python scripts/compare.py \
        --text-a "OAuth 2.0 authentication backend for fintech" \
        --text-b "JWT-based authorization service for banking app"

    # dentro del contenedor:
    docker compose exec servicio_ia python scripts/compare.py \
        --text-a "..." --text-b "..."
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

# Permite ejecutar `python scripts/compare.py` desde cualquier directorio.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai import OpenAI  # noqa: E402

from app.config import settings  # noqa: E402
from app.embedding_pipeline.embedder import OpenAIEmbedder  # noqa: E402


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Producto escalar dividido por el producto de las normas."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def main() -> int:
    parser = argparse.ArgumentParser(description="Similitud coseno entre dos textos embebidos.")
    parser.add_argument("--text-a", required=True, help="Primer texto.")
    parser.add_argument("--text-b", required=True, help="Segundo texto.")
    args = parser.parse_args()

    if not settings.OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY no está definida (revisa tu .env).", file=sys.stderr)
        return 1

    embedder = OpenAIEmbedder(
        client=OpenAI(api_key=settings.OPENAI_API_KEY),
        model=settings.EMBEDDING_MODEL,
    )
    similarity = cosine_similarity(embedder.embed_one(args.text_a), embedder.embed_one(args.text_b))

    print(f"Text A: {args.text_a}")
    print(f"Text B: {args.text_b}")
    print(f"Cosine similarity: {similarity:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
