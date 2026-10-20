"""Loader de filesystem.

Resuelve ``CatalogSource.location`` contra ``INGESTION_DATA_ROOT`` y entrega un
``LoadedBlob`` por cada fichero cuya extensión coincide con el formato de la
fuente. Una ruta inexistente es un error duro: un catálogo que apunta a la nada
es un fallo silencioso, el peor tipo.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LoadedBlob:
    """Los bytes de un fichero y su ruta relativa a la raíz de datos."""

    relative_path: str
    bytes_: bytes


class FileSystemLoader:
    def __init__(self, data_root: Path | str) -> None:
        self._data_root = Path(data_root)

    def iter_blobs(self, location: str, formats: set[str]) -> Iterator[LoadedBlob]:
        path = self._data_root / location
        if not path.exists():
            raise FileNotFoundError(
                f"La ubicación del catálogo {location!r} no existe ({path!s} no encontrada)"
            )
        candidates = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for candidate in candidates:
            if candidate.suffix.lower().lstrip(".") not in formats:
                continue
            yield LoadedBlob(
                # as_posix: el id del Document no debe depender del sistema operativo
                relative_path=candidate.relative_to(self._data_root).as_posix(),
                bytes_=candidate.read_bytes(),
            )
