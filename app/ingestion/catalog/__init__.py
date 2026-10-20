"""Catálogo versionado de fuentes de datos.

Un ``DataCatalog`` es código (Pydantic + YAML en git), no documentación. Cada
``CatalogSource`` declara lo que sabemos de una fuente (owners, refresco,
calidad, sensibilidad, linaje) y una ``decision`` explícita (include / review /
exclude) con motivo obligatorio si no es ``include``.
"""

from app.ingestion.catalog.loader import load_catalog
from app.ingestion.catalog.models import (
    CatalogDecision,
    CatalogSource,
    DataCatalog,
    QualityScore,
    Sensitivity,
)

__all__ = [
    "CatalogDecision",
    "CatalogSource",
    "DataCatalog",
    "QualityScore",
    "Sensitivity",
    "load_catalog",
]
