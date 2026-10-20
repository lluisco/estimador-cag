"""Fábricas de dependencias de FastAPI para los singletons de la ingesta."""

from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.ingestion.catalog import DataCatalog, load_catalog
from app.ingestion.loaders.filesystem import FileSystemLoader
from app.ingestion.parsers.registry import ParserRegistry, default_registry


@lru_cache
def get_catalog() -> DataCatalog:
    """Carga y cachea el catálogo de fuentes.

    Se lee una sola vez al arrancar: releerlo invalidaría las decisiones ya
    aplicadas por el pipeline en marcha, así que una versión nueva exige reiniciar.
    """
    return load_catalog(settings.CATALOG_PATH)


@lru_cache
def get_filesystem_loader() -> FileSystemLoader:
    return FileSystemLoader(data_root=settings.INGESTION_DATA_ROOT)


@lru_cache
def get_parser_registry() -> ParserRegistry:
    return default_registry()
