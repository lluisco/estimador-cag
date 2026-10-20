"""Repositorio de la mapping table de pseudónimos.

``lookup_or_create`` es lo que el pseudonimizador llama por cada entidad. Debe ser
idempotente bajo concurrencia: dos llamadas paralelas con el mismo
``(entity_type, original_hash)`` tienen que converger al mismo pseudónimo, o el
corpus acabaría con dos pseudónimos para la misma persona.

Lo garantiza el UNIQUE de Postgres: se intenta insertar y, si choca, se lee la
fila ganadora. Es más barato que SELECT-luego-INSERT y no necesita locks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.persistence.models import PseudonymMappingRow


@dataclass(frozen=True)
class Mapping:
    """Vista en memoria de una fila; los repositorios no filtran tipos de SQLAlchemy."""

    entity_type: str
    original_hash: str
    pseudonym: str
    created_at: datetime


class MappingsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lookup(self, entity_type: str, original_hash: str) -> Mapping | None:
        row = self._session.execute(
            select(PseudonymMappingRow).where(
                PseudonymMappingRow.entity_type == entity_type,
                PseudonymMappingRow.original_hash == original_hash,
            )
        ).scalar_one_or_none()
        return _to_mapping(row) if row is not None else None

    def lookup_or_create(
        self, entity_type: str, original_hash: str, new_pseudonym_factory: Callable[[], str]
    ) -> Mapping:
        """Devuelve el mapping existente o inserta uno nuevo.

        La factory solo se invoca si no hay mapping previo: generar el valor con
        Faker es barato pero inútil cuando ya existe.
        """
        existing = self.lookup(entity_type, original_hash)
        if existing is not None:
            return existing

        stmt = (
            pg_insert(PseudonymMappingRow)
            .values(
                entity_type=entity_type,
                original_hash=original_hash,
                pseudonym=new_pseudonym_factory(),
            )
            .on_conflict_do_nothing(index_elements=["entity_type", "original_hash"])
            .returning(PseudonymMappingRow)
        )
        row = self._session.execute(stmt).scalar_one_or_none()
        self._session.commit()
        if row is not None:
            return _to_mapping(row)

        # Otro escritor ganó la carrera: leemos su fila.
        winner = self.lookup(entity_type, original_hash)
        assert winner is not None, "el UNIQUE garantiza que existe una fila ganadora"
        return winner

    def forget(self, entity_type: str, original_hash: str) -> bool:
        """Borra un mapping. Devuelve True si existía."""
        deleted = self._session.execute(
            PseudonymMappingRow.__table__.delete().where(
                PseudonymMappingRow.entity_type == entity_type,
                PseudonymMappingRow.original_hash == original_hash,
            )
        )
        self._session.commit()
        return deleted.rowcount > 0


def _to_mapping(row: PseudonymMappingRow) -> Mapping:
    return Mapping(
        entity_type=row.entity_type,
        original_hash=row.original_hash,
        pseudonym=row.pseudonym,
        created_at=row.created_at,
    )
