"""Inspección de una carpeta de datos: solo hechos.

Produce los hechos (nº de ficheros, MB, última modificación, formatos) que
respaldan las entradas del catálogo. No puntúa calidad ni escribe el catálogo:
las opiniones viven en el YAML, los hechos en el código.

    python -m app.ingestion.catalog.inspect data/seed
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class FolderFacts:
    folder: Path
    file_count: int = 0
    total_size_mb: float = 0.0
    latest_modified: datetime | None = None
    formats_detected: set[str] = field(default_factory=set)

    def add_file(self, path: Path) -> None:
        stat = path.stat()
        self.file_count += 1
        self.total_size_mb += stat.st_size / (1024 * 1024)
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        if self.latest_modified is None or modified > self.latest_modified:
            self.latest_modified = modified
        if path.suffix:
            self.formats_detected.add(path.suffix.lower().lstrip("."))

    def as_table_row(self) -> str:
        ts = self.latest_modified.date().isoformat() if self.latest_modified else "-"
        formats = ",".join(sorted(self.formats_detected)) or "-"
        return (
            f"{self.folder.name:<12} {self.file_count:>3} files  "
            f"{self.total_size_mb:>6.2f} MB  latest={ts}  formats={formats}"
        )


def _facts_for(folder: Path, files: Iterable[Path]) -> FolderFacts:
    facts = FolderFacts(folder=folder)
    for path in files:
        facts.add_file(path)
    return facts


def inspect_folder(folder: Path) -> FolderFacts:
    if not folder.exists():
        return FolderFacts(folder=folder)
    return _facts_for(folder, (p for p in folder.rglob("*") if p.is_file()))


def inspect_root(root: Path) -> list[FolderFacts]:
    """Inspecciona cada subcarpeta directa de ``root`` y los ficheros sueltos de ``root``."""
    if not root.exists():
        return []
    results = [inspect_folder(p) for p in sorted(root.iterdir()) if p.is_dir()]
    # Ficheros directamente bajo root (p. ej. el XLSX de tarifas).
    loose = [p for p in root.iterdir() if p.is_file()]
    if loose:
        results.append(_facts_for(root, loose))
    return results


def _main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("uso: python -m app.ingestion.catalog.inspect <carpeta-raíz>")
        return 1
    root = Path(argv[1])
    if not root.exists():
        print(f"ERROR: {root} no existe")
        return 2
    facts = inspect_root(root)
    if not facts:
        print(f"(sin ficheros en {root})")
        return 0
    for entry in facts:
        print(entry.as_table_row())
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
