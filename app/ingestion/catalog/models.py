"""Modelos Pydantic v2 del catálogo de fuentes.

El catálogo es el contrato entre lo que existe en la empresa y lo que el pipeline
de ingesta da por bueno. Hay tres decisiones válidas:

* ``include``: la fuente entra en el pipeline.
* ``review``: problemas conocidos a la espera del visto bueno de su owner. Se
  conserva en disco pero no se ingiere (evita el binario incluir/excluir).
* ``exclude``: fuera de forma explícita. El motivo es obligatorio: excluir es una
  decisión defendible, no una omisión silenciosa.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CatalogDecision(str, Enum):
    INCLUDE = "include"
    REVIEW = "review"
    EXCLUDE = "exclude"


class QualityScore(BaseModel):
    """Puntuación 1..5 por dimensión, anclada en hechos concretos."""

    model_config = ConfigDict(extra="forbid")

    completeness: int = Field(ge=1, le=5)
    consistency: int = Field(ge=1, le=5)
    actuality: int = Field(ge=1, le=5)
    reliability: int = Field(ge=1, le=5)


class Sensitivity(BaseModel):
    """Si la fuente contiene PII y de qué tipos.

    El orquestador lo usa para decidir si los documentos pasan por la
    pseudonimización antes de indexarse.
    """

    model_config = ConfigDict(extra="forbid")

    has_pii: bool
    pii_flags: list[str] = Field(default_factory=list)
    access_level: Literal["public", "internal", "confidential"] = "internal"


class CatalogSource(BaseModel):
    """Una fuente de datos auditada."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    location: str  # ruta o URL; la resuelve el loader, no este modelo
    owners: list[str] = Field(default_factory=list)
    format: Literal["json", "txt", "xlsx", "docx", "pdf", "csv"]
    volume_estimate: str = ""  # texto libre, p. ej. "≈ 6 ficheros, 250 KB"
    refresh_declared: str = ""  # lo que dice el owner: "semanal"
    refresh_observed: str = ""  # lo que midió el inspector
    quality: QualityScore
    sensitivity: Sensitivity
    lineage: list[str] = Field(default_factory=list)
    decision: CatalogDecision
    decision_reason: str = ""
    last_audited: datetime | None = None

    @field_validator("name")
    @classmethod
    def _name_is_snake_case(cls, value: str) -> str:
        if not value or not all(c.islower() or c.isdigit() or c == "_" for c in value):
            raise ValueError(
                "CatalogSource.name debe ir en snake_case minúscula "
                "(es el identificador que usa el endpoint de ingesta)"
            )
        return value

    @model_validator(mode="after")
    def _decision_requires_reason_when_not_include(self) -> "CatalogSource":
        if self.decision is not CatalogDecision.INCLUDE and not self.decision_reason:
            raise ValueError(f"decision={self.decision.value} exige un decision_reason no vacío")
        return self


class DataCatalog(BaseModel):
    """El catálogo completo, versionado en git junto al código."""

    model_config = ConfigDict(extra="forbid")

    version: str
    description: str = ""
    sources: list[CatalogSource]

    @field_validator("sources")
    @classmethod
    def _names_are_unique(cls, sources: list[CatalogSource]) -> list[CatalogSource]:
        seen: set[str] = set()
        for src in sources:
            if src.name in seen:
                raise ValueError(f"Nombre de fuente duplicado en el catálogo: {src.name}")
            seen.add(src.name)
        return sources

    def included_sources(self) -> list[CatalogSource]:
        return [s for s in self.sources if s.decision is CatalogDecision.INCLUDE]

    def find(self, name: str) -> CatalogSource | None:
        return next((s for s in self.sources if s.name == name), None)
