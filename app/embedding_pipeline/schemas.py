"""Modelos Pydantic del pipeline de embeddings.

La entrada refleja el JSON de presupuestos históricos ya normalizados (un
presupuesto con su lista de componentes). La salida lleva los chunks listos para
embeber y, una vez embebidos, sus vectores más las estadísticas agregadas.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Universo cerrado de valores presentes en el dataset de ejemplo: un valor
# inesperado debe fallar la validación (422) en vez de colarse en la metadata.
Sector = Literal["finance", "ecommerce", "healthcare", "industrial"]
Complexity = Literal["low", "medium", "high"]


class ClientMetadata(BaseModel):
    """Cliente del presupuesto. Viaja como contexto filtrable."""

    name: str = Field(description="Nombre de la empresa cliente.")
    sector: Sector = Field(description="Sector de negocio del cliente.")
    country: str = Field(description="Código de país, p. ej. 'ES'.")


class BudgetComponent(BaseModel):
    """Una partida de un presupuesto histórico."""

    component_id: str = Field(description="Id estable dentro del presupuesto, p. ej. 'AUTH-001'.")
    name: str = Field(description="Nombre corto del componente.")
    description: str = Field(description="Descripción detallada del trabajo.")
    tech_stack: list[str] = Field(default_factory=list, description="Tecnologías implicadas.")
    estimated_hours: int = Field(ge=0, description="Horas estimadas del componente.")
    complexity: Complexity = Field(description="Cubo de complejidad.")
    dependencies: list[str] = Field(
        default_factory=list, description="component_id de los que depende."
    )


class Budget(BaseModel):
    """Un presupuesto histórico completo."""

    budget_id: str = Field(description="Id estable del presupuesto, p. ej. 'BUD-2024-014'.")
    client_metadata: ClientMetadata
    project_summary: str = Field(description="Resumen de una línea del proyecto.")
    main_technology: str = Field(description="Tecnología principal del proyecto.")
    year: int = Field(ge=2000, le=2100, description="Año del presupuesto.")
    total_estimated_hours: int = Field(ge=0, description="Horas totales registradas.")
    components: list[BudgetComponent] = Field(min_length=1, description="Partidas del presupuesto.")


class Chunk(BaseModel):
    """Fragmento listo para embeber.

    ``text`` es lo que se envía a la API de embeddings; ``metadata`` son campos
    filtrables que viajan con el chunk pero NO se embeben.
    """

    chunk_id: str = Field(description="Id trazable: '{budget_id}::{component_id}'.")
    text: str = Field(description="Texto a embeber: contexto del padre + detalle del componente.")
    metadata: dict = Field(default_factory=dict, description="Campos filtrables, no embebidos.")
    token_count: int = Field(ge=0, description="Tokens de ``text`` según tiktoken.")


class EmbeddedChunk(Chunk):
    """Un :class:`Chunk` con su vector de embedding."""

    embedding: list[float] = Field(
        description="Vector denso (1536 dimensiones con text-embedding-3-small)."
    )


class IngestRequest(BaseModel):
    """Cuerpo de ``POST /embeddings/ingest``."""

    budgets: list[Budget] = Field(min_length=1, description="Presupuestos a trocear y embeber.")


class IngestStats(BaseModel):
    """Contadores agregados de una ingesta."""

    total_budgets: int = Field(ge=0)
    total_chunks: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0.0)


class IngestResponse(BaseModel):
    """Respuesta de ``POST /embeddings/ingest``."""

    chunks: list[EmbeddedChunk]
    stats: IngestStats
