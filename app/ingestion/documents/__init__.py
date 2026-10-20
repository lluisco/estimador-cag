"""Contrato canónico ``Document``.

Todo parser produce ``Document``; todo consumidor posterior (limpieza, PII, RAG)
acepta ``Document``. El modelo es plano a propósito: es trivial de falsear en
tests y homogéneo entre formatos.
"""

from app.ingestion.documents.models import Document, DocumentMetadata

__all__ = ["Document", "DocumentMetadata"]
