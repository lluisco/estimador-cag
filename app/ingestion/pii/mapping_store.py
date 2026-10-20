"""Mapping store: el respaldo persistente de la pseudonimización consistente.

Dos implementaciones:

* ``PostgresMappingStore``: la de producción. A la BD llega el HMAC del valor
  original, nunca el valor. Esa asimetría hace auditable el derecho al olvido:
  borrar la fila por hash mata la reversibilidad sin haber guardado el original.
* ``InMemoryMappingStore``: para tests y scripts. Mismo contrato, sin BD.

Ambas son idempotentes: consultar dos veces el mismo ``(entity_type, hash)`` da el
mismo pseudónimo, sea cual sea el orden. Los llamadores concurrentes convergen
gracias al UNIQUE de la tabla.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.persistence.repositories.mappings import MappingsRepository


@runtime_checkable
class MappingStore(Protocol):
    def lookup_or_create(
        self, entity_type: str, original_hash: str, new_pseudonym_factory: Callable[[], str]
    ) -> str: ...

    def forget(self, entity_type: str, original_hash: str) -> bool: ...


class PostgresMappingStore:
    def __init__(self, session: Session) -> None:
        self._repo = MappingsRepository(session)

    def lookup_or_create(
        self, entity_type: str, original_hash: str, new_pseudonym_factory: Callable[[], str]
    ) -> str:
        return self._repo.lookup_or_create(entity_type, original_hash, new_pseudonym_factory).pseudonym

    def forget(self, entity_type: str, original_hash: str) -> bool:
        return self._repo.forget(entity_type, original_hash)


class InMemoryMappingStore:
    def __init__(self) -> None:
        self._mappings: dict[tuple[str, str], str] = {}

    def lookup_or_create(
        self, entity_type: str, original_hash: str, new_pseudonym_factory: Callable[[], str]
    ) -> str:
        key = (entity_type, original_hash)
        if key not in self._mappings:
            self._mappings[key] = new_pseudonym_factory()
        return self._mappings[key]

    def forget(self, entity_type: str, original_hash: str) -> bool:
        return self._mappings.pop((entity_type, original_hash), None) is not None
