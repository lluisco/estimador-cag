#!/usr/bin/env python3
"""Preflight de la sesión 06: detecta los fallos de entorno típicos antes de ingerir.

Modelo spaCy español ausente, catálogo inválido, Postgres sin migrar, etc.
Imprime ✅ / ❌ por check y sale con código distinto de 0 si alguno falla.

Uso::

    uv run python scripts/preflight_s06.py
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

OK = "✅"
FAIL = "❌"

ROOT = Path(__file__).resolve().parent.parent
# Hace importable `app` cuando el script se ejecuta directamente desde scripts/.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Check:
    def __init__(self, name: str, fn: Callable[[], str | None]) -> None:
        self.name = name
        self._fn = fn

    def run(self) -> bool:
        try:
            detail = self._fn()
        except Exception as exc:  # noqa: BLE001
            print(f"{FAIL}  {self.name}: {type(exc).__name__}: {exc}")
            return False
        print(f"{OK}  {self.name}" + (f": {detail}" if detail else ""))
        return True


def check_python_version() -> str:
    major, minor, micro = sys.version_info[:3]
    if (major, minor) < (3, 11):
        raise RuntimeError(f"se necesita Python 3.11+, hay {major}.{minor}")
    return f"{major}.{minor}.{micro}"


# unstructured no está: en Windows python-magic revienta sin libmagic, y el repo
# solo usa parsers nativos (JSON, TXT). Volverá si aparece un formato que lo pida.
_MIN_VERSIONS = {
    "pandas": "2.2.0",
    "pandera": "0.20.0",
    "pyyaml": "6.0",
    "sqlalchemy": "2.0.0",
    "psycopg": "3.1.0",
    "alembic": "1.13.0",
    "openpyxl": "3.1.0",
    "presidio-analyzer": "2.2.0",
    "presidio-anonymizer": "2.2.0",
    "spacy": "3.7.0",
    "faker": "24.0.0",
}


def _parse_version(s: str) -> tuple[int, ...]:
    parts = []
    for chunk in s.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def check_packages() -> str:
    missing, too_old = [], []
    for pkg, minimum in _MIN_VERSIONS.items():
        try:
            installed = importlib_metadata.version(pkg)
        except importlib_metadata.PackageNotFoundError:
            missing.append(pkg)
            continue
        if _parse_version(installed) < _parse_version(minimum):
            too_old.append(f"{pkg} {installed} < {minimum}")
    if missing or too_old:
        raise RuntimeError(f"faltan={','.join(missing)} antiguos={','.join(too_old)}")
    return f"{len(_MIN_VERSIONS)} paquetes OK"


def check_spacy_model() -> str:
    import spacy

    from app.config import settings

    nlp = spacy.load(settings.PRESIDIO_SPACY_MODEL)
    doc = nlp("Laura Fernández firmó en Madrid.")
    labels = {(e.text, e.label_) for e in doc.ents}
    if ("Laura Fernández", "PER") not in labels or ("Madrid", "LOC") not in labels:
        raise RuntimeError(f"{settings.PRESIDIO_SPACY_MODEL} no detecta PER + LOC: {labels}")
    return f"{settings.PRESIDIO_SPACY_MODEL}: {sorted(labels)}"


def check_corpus_seed() -> str:
    seed = ROOT / "data" / "seed"
    budgets = list((seed / "budgets").glob("*.json"))
    transcripts = list((seed / "transcripts").glob("*.txt"))
    xlsx = list(seed.glob("*.xlsx"))
    if not budgets or not transcripts or not xlsx:
        raise RuntimeError(
            f"corpus incompleto: budgets={len(budgets)}, "
            f"transcripts={len(transcripts)}, xlsx={len(xlsx)}"
        )
    return f"{len(budgets)} json + {len(transcripts)} txt + {len(xlsx)} xlsx"


def check_catalog() -> str:
    from app.ingestion.catalog import load_catalog

    catalog = load_catalog(ROOT / "data" / "catalog" / "catalog.yaml")
    return f"versión {catalog.version}, {len(catalog.included_sources())} incluidas"


def check_health_endpoint() -> str:
    try:
        with urllib.request.urlopen("http://localhost:8000/health", timeout=2) as r:
            return f"{r.status} OK"
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"GET /health falla: ¿está uvicorn levantado? ({exc})") from exc


def check_postgres() -> str:
    """Conecta a Postgres y confirma que la migración está aplicada."""
    from sqlalchemy import inspect

    from app.persistence.database import create_engine_from_settings

    tables = set(inspect(create_engine_from_settings()).get_table_names())
    expected = {"pseudonym_mappings", "ingestion_jobs", "alembic_version"}
    missing = expected - tables
    if missing:
        raise RuntimeError(f"faltan tablas {missing}: ejecuta `alembic upgrade head`")
    return f"tablas OK: {sorted(expected)}"


CHECKS = [
    Check("Versión de Python", check_python_version),
    Check("Paquetes requeridos", check_packages),
    Check("spaCy en español", check_spacy_model),
    Check("Corpus seed", check_corpus_seed),
    Check("Catálogo válido", check_catalog),
    Check("Estimador /health", check_health_endpoint),
    Check("Postgres + migración", check_postgres),
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("Preflight sesión 06\n")
    failed = sum(not check.run() for check in CHECKS)
    print()
    if failed:
        print(f"{FAIL}  {failed} check(s) fallan")
        return 1
    print(f"{OK}  Todo OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
