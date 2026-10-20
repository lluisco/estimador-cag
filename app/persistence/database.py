"""Engine de SQLAlchemy, fábrica de sesiones y helper por petición.

API síncrona de SQLAlchemy 2.0: la ingesta no está en el camino caliente de las
peticiones (corre como BackgroundTask o tarea puntual), así que se prefiere la
simplicidad a la ergonomía async.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


@lru_cache
def create_engine_from_settings() -> Engine:
    """Engine global a partir de ``settings.DATABASE_URL`` (singleton, conexión perezosa)."""
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)


SessionLocal = sessionmaker(
    bind=create_engine_from_settings(),
    autoflush=False,
    expire_on_commit=False,
)


def get_session() -> Iterator[Session]:
    """Dependencia de FastAPI: entrega una Session y la cierra al salir."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
