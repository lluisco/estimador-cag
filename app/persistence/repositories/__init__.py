"""Repositorios estrechos sobre la capa de persistencia.

Cada repositorio envuelve una ``Session`` y expone solo lo que su consumidor
necesita; ningún tipo ORM cruza esta frontera.
"""

from app.persistence.repositories.jobs import JobsRepository
from app.persistence.repositories.mappings import MappingsRepository

__all__ = ["JobsRepository", "MappingsRepository"]
