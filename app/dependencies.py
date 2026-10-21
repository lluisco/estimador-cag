"""Fábricas de dependencias de FastAPI para los singletons de la ingesta."""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from app.config import settings
from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.ingestion.catalog import DataCatalog, load_catalog
from app.ingestion.loaders.filesystem import FileSystemLoader
from app.ingestion.parsers.registry import ParserRegistry, default_registry


def build_pseudonymizer(session):
    """Pseudonimizador respaldado por Postgres.

    No es singleton: la store envuelve una Session, así que scripts, BackgroundTasks
    y tests aportan la suya. El analyzer sí es singleton y la sal sale de settings.
    """
    from app.ingestion.pii import ConsistentPseudonymizer, PostgresMappingStore, build_analyzer

    return ConsistentPseudonymizer(
        analyzer=build_analyzer(),
        mapping_store=PostgresMappingStore(session),
        salt=settings.PSEUDONYM_HASH_SALT,
        faker_locale=settings.PSEUDONYM_FAKER_LOCALE,
        language="es",
    )


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


@lru_cache
def get_chunker() -> JSONStructuralChunker:
    return JSONStructuralChunker()


@lru_cache
def get_embedder() -> OpenAIEmbedder | None:
    """Embedder de la sesión 7; ``None`` si no hay OPENAI_API_KEY (el router responde 500)."""
    if not settings.OPENAI_API_KEY:
        return None
    return OpenAIEmbedder(
        client=OpenAI(api_key=settings.OPENAI_API_KEY),
        model=settings.EMBEDDING_MODEL,
    )
