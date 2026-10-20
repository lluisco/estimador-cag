"""El protocolo ``Parser`` y el ``ParseContext`` que recibe.

¿Protocol y no clase base abstracta? Los parsers no comparten implementación (no
hay nada útil que heredar) y el tipado estructural permite meter un fake en un
test sin heredar de nada: vale cualquier clase con ``supported_formats`` y ``parse``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Protocol, runtime_checkable

from app.ingestion.catalog.models import CatalogSource
from app.ingestion.documents.models import Document
from app.ingestion.loaders.filesystem import LoadedBlob


@dataclass(frozen=True)
class ParseContext:
    """Lo que un parser necesita y no vive en el blob.

    El orquestador lo construye una vez por ejecución, así ``ingested_at`` y
    ``source_version`` son constantes en toda la run.
    """

    source: CatalogSource
    source_version: str
    ingested_at: datetime


@runtime_checkable
class Parser(Protocol):
    supported_formats: ClassVar[set[str]]

    def parse(self, blob: LoadedBlob, context: ParseContext) -> Iterable[Document]: ...
