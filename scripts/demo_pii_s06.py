#!/usr/bin/env python3
"""Demo de pseudonimización con Presidio (español) + mapping table.

Construye `build_analyzer()` (es_core_news_md + recognizers BUDGET_ID/CLIENT_CODE) y
pasa un `ConsistentPseudonymizer` sobre una transcripción real.

No se muestra el contraste "en inglés falla": forzar el motor por defecto descarga
un modelo de ~382 MB. Esa parte se cuenta; aquí se enseña la corrección funcionando.

    uv run python scripts/demo_pii_s06.py            # store en memoria
    uv run python scripts/demo_pii_s06.py --postgres # mapping table real
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Hace importable `app` cuando el script se ejecuta directamente desde scripts/.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.ingestion.pii import ConsistentPseudonymizer, InMemoryMappingStore, build_analyzer  # noqa: E402

TRANSCRIPT = ROOT / "data" / "seed" / "transcripts" / "transcripcion_2025-02-03_betanorte.txt"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not TRANSCRIPT.exists():
        print(f"ERROR: no existe {TRANSCRIPT}")
        return 1

    if "--postgres" in sys.argv:
        from app.dependencies import build_pseudonymizer
        from app.persistence.database import SessionLocal

        session = SessionLocal()
        pseudo = build_pseudonymizer(session)
    else:
        pseudo = ConsistentPseudonymizer(
            analyzer=build_analyzer(),
            mapping_store=InMemoryMappingStore(),
            salt=settings.PSEUDONYM_HASH_SALT,
            faker_locale=settings.PSEUDONYM_FAKER_LOCALE,
        )
    result = pseudo.pseudonymize(TRANSCRIPT.read_text(encoding="utf-8"))

    print(f"Transcripción: {TRANSCRIPT.name}")
    print("\n--- Texto pseudonimizado (primeros 400 chars) ---")
    print(result.pseudonymized_text[:400])

    print(f"\n--- Mappings aplicados ({len(result.applied)}) ---")
    for m in result.applied[:12]:
        print(f"  {m.entity_type:14} → {m.pseudonym}")
    print("\nMismo valor original → mismo pseudónimo en todo el documento (consistencia por valor, no por chunk).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
