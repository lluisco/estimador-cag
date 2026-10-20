"""Modelo canónico ``Document``.

Plano a propósito: un único ``DocumentMetadata`` con los campos que necesita todo
consumidor, y lo específico de cada formato en ``extra``. Esa válvula de escape
mantiene el contrato uniforme entre JSON, TXT, XLSX y formatos futuros.

El ``id`` es determinista y estable entre reingestas, para que el índice pueda
deduplicar. Con ``extra="forbid"``, si un parser cuela un campo no declarado,
Pydantic falla: mejor un error fuerte que uno silencioso.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    source_version: str  # ``DataCatalog.version`` vigente en la ingesta
    ingested_at: datetime
    lineage: list[str] = Field(default_factory=list)
    sensitivity_pii_flags: list[str] = Field(default_factory=list)
    sensitivity_access_level: str = "internal"
    location: str = ""  # ruta o URL de origen
    extra: dict[str, Any] = Field(default_factory=dict)


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    metadata: DocumentMetadata
