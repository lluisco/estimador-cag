"""Capa de persistencia de la ingesta (sesión 6).

Contiene el engine de SQLAlchemy, la ``Base`` declarativa y los modelos de fila de
la mapping table de pseudónimos y del seguimiento de jobs. Las capas superiores
usan los repositorios de ``app.persistence.repositories``, nunca tipos de SQLAlchemy.
"""

from app.persistence.database import SessionLocal, create_engine_from_settings, get_session
from app.persistence.models import Base, IngestionJobRow, PseudonymMappingRow

__all__ = [
    "Base",
    "IngestionJobRow",
    "PseudonymMappingRow",
    "SessionLocal",
    "create_engine_from_settings",
    "get_session",
]
