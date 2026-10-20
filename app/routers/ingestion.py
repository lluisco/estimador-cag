"""POST /ingestion/runs  +  GET /ingestion/jobs/{job_id}  (bajo /api/v1).

El router es fino a propósito: valida la fuente contra el catálogo, registra el
job, lanza el orquestador como BackgroundTask y devuelve 202 al instante. La
ingesta es offline (indexar tarda minutos), por eso es 202 + polling; la consulta
de la sesión 7 sí será síncrona. Toda la lógica vive en ``app.ingestion.orchestrator``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.dependencies import get_catalog, get_filesystem_loader, get_parser_registry
from app.ingestion.catalog.models import CatalogDecision, DataCatalog
from app.ingestion.loaders.filesystem import FileSystemLoader
from app.ingestion.orchestrator import ingest_source
from app.ingestion.parsers.registry import ParserRegistry
from app.persistence.database import SessionLocal, get_session
from app.persistence.repositories.jobs import JobsRepository

log = structlog.get_logger()

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

JobStatus = Literal["pending", "running", "completed", "failed"]


class IngestionRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(
        min_length=1,
        max_length=128,
        description="Nombre de una fuente `include` del catálogo; cualquier otra se rechaza con 400/404.",
    )


class IngestionRunResponse(BaseModel):
    job_id: uuid.UUID
    source_name: str
    status: JobStatus


class IngestionJobView(BaseModel):
    job_id: uuid.UUID
    source_name: str
    status: JobStatus
    documents_count: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


def _run_in_background(
    *,
    job_id: uuid.UUID,
    source_name: str,
    catalog: DataCatalog,
    loader: FileSystemLoader,
    registry: ParserRegistry,
) -> None:
    """Cuerpo del BackgroundTask. Abre su propia Session: la de la petición ya está cerrada."""
    session = SessionLocal()
    try:
        ingest_source(
            catalog=catalog,
            source_name=source_name,
            loader=loader,
            registry=registry,
            jobs_repo=JobsRepository(session),
            job_id=job_id,
        )
    except Exception as exc:  # noqa: BLE001
        # El orquestador ya dejó el job en `failed`; aquí solo se deja constancia en el log.
        log.error("ingestion_background_failed", job_id=str(job_id), source_name=source_name, error=str(exc)[:400])
    finally:
        session.close()


@router.post("/runs", response_model=IngestionRunResponse, status_code=202)
def create_ingestion_run(
    request: IngestionRunRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    catalog: DataCatalog = Depends(get_catalog),
    loader: FileSystemLoader = Depends(get_filesystem_loader),
    registry: ParserRegistry = Depends(get_parser_registry),
) -> IngestionRunResponse:
    source = catalog.find(request.source_name)
    if source is None:
        raise HTTPException(
            status_code=404,
            detail={"reason": "unknown_source", "source_name": request.source_name},
        )
    if source.decision is not CatalogDecision.INCLUDE:
        raise HTTPException(
            status_code=400,
            detail={
                "reason": "source_not_included",
                "source_name": request.source_name,
                "decision": source.decision.value,
                "decision_reason": source.decision_reason,
            },
        )

    job = JobsRepository(session).create(source_name=request.source_name)
    background.add_task(
        _run_in_background,
        job_id=job.job_id,
        source_name=request.source_name,
        catalog=catalog,
        loader=loader,
        registry=registry,
    )
    return IngestionRunResponse(job_id=job.job_id, source_name=job.source_name, status=job.status)


@router.get("/jobs/{job_id}", response_model=IngestionJobView)
def get_ingestion_job(job_id: uuid.UUID, session: Session = Depends(get_session)) -> IngestionJobView:
    job = JobsRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return IngestionJobView(
        job_id=job.job_id,
        source_name=job.source_name,
        status=job.status,
        documents_count=job.documents_count,
        error_message=job.error_message,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
