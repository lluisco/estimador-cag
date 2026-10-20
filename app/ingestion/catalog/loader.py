"""Carga y valida el catálogo YAML.

Todo el peso (reglas de decisión, duplicados) vive en el modelo; el loader es
deliberadamente trivial.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from app.ingestion.catalog.models import DataCatalog


def load_catalog(path: str | Path) -> DataCatalog:
    """Lee ``path`` como YAML y lo valida como ``DataCatalog``."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return DataCatalog.model_validate(raw)


def _main(argv: list[str]) -> int:
    """CLI: ``python -m app.ingestion.catalog.loader data/catalog/catalog.yaml``."""
    if len(argv) != 2:
        print("uso: python -m app.ingestion.catalog.loader <ruta.yaml>")
        return 1
    catalog = load_catalog(argv[1])
    included = catalog.included_sources()
    print(f"Versión del catálogo: {catalog.version}")
    print(f"Sources total: {len(catalog.sources)} · Sources included: {len(included)}")
    for src in included:
        print(f"  - {src.name} ({src.format})")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
