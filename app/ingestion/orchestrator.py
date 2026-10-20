"""Orquestador: une catálogo + loader + parser en una ejecución de ingesta.

    ingest_source(catalog=, source_name=, loader=, registry=, jobs_repo=, job_id=)
      → list[Document]

Tres garantías:

1. La fuente existe en el catálogo y tiene ``decision == include``; si no, lanza
   ``IngestionRejected`` (el router lo traduce a 400).
2. ``jobs_repo`` se actualiza durante la ejecución: pending → running → completed
   o failed, y el endpoint GET puede consultarlo.
3. Es síncrona: la invoca un BackgroundTask de FastAPI con su propia sesión de BD.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

from app.ingestion.catalog.models import CatalogDecision, DataCatalog
from app.ingestion.documents.models import Document
from app.ingestion.loaders.filesystem import FileSystemLoader
from app.ingestion.parsers.protocol import ParseContext
from app.ingestion.parsers.registry import ParserRegistry
from app.persistence.repositories.jobs import JobsRepository

log = structlog.get_logger(__name__)


class IngestionRejected(Exception):
    """La fuente es desconocida o está en exclude/review: la run no puede empezar."""


def ingest_source(
    *,
    catalog: DataCatalog,
    source_name: str,
    loader: FileSystemLoader,
    registry: ParserRegistry,
    jobs_repo: JobsRepository,
    job_id: uuid.UUID,
) -> list[Document]:
    """Ingiere una fuente ``include`` y deja trazado el estado en ``ingestion_jobs``."""
    bound = log.bind(job_id=str(job_id), source_name=source_name)

    source = catalog.find(source_name)
    if source is None:
        raise IngestionRejected(f"la fuente {source_name!r} no está en el catálogo")
    if source.decision is not CatalogDecision.INCLUDE:
        raise IngestionRejected(
            f"la fuente {source_name!r} tiene decision={source.decision.value!r}; "
            "solo se ingieren las 'include'"
        )

    jobs_repo.mark_running(job_id)
    bound.info("ingestion.started", format=source.format)

    parser = registry.get(source.format)
    context = ParseContext(
        source=source,
        source_version=catalog.version,
        ingested_at=datetime.now(timezone.utc),
    )

    documents: list[Document] = []
    try:
        for blob in loader.iter_blobs(source.location, {source.format}):
            documents.extend(parser.parse(blob, context))
    except Exception as exc:
        bound.error("ingestion.failed", error=str(exc))
        jobs_repo.mark_failed(job_id, error_message=str(exc))
        raise

    jobs_repo.mark_completed(job_id, documents_count=len(documents))
    bound.info("ingestion.completed", documents_count=len(documents))
    return documents
