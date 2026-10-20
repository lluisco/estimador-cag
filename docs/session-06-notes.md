## Qué cubre la sesión 06

Preparar el corpus antes de vectorizar: decidir la arquitectura, auditar las fuentes, extraer a un
`Document` canónico, limpiar y validar, y proteger la PII. No hay embeddings ni chunking (sesión 7).
Referencia: rama `session_06_live` de `LIDR-academy-temp/ai-engineering`.

## Piezas

| # | Pieza | Dónde | Cómo verlo |
|---|---|---|---|
| 1 | Decisión CAG / RAG / híbrido | `app/ingestion/architecture.py` | `python -m app.ingestion.architecture` → RAG |
| 2 | Catálogo de fuentes versionado | `app/ingestion/catalog/`, `data/catalog/catalog.yaml` | `python -m app.ingestion.catalog.loader data/catalog/catalog.yaml` |
| 3 | Ingesta + `Document` canónico + API asíncrona | `app/ingestion/{documents,loaders,parsers}/`, `orchestrator.py`, `app/routers/ingestion.py` | `POST /api/v1/ingestion/runs` (202) y `GET /api/v1/ingestion/jobs/{id}` |
| 4 | Limpieza y validación | `app/ingestion/cleaning/` | `python scripts/demo_cleaning_s06.py` |
| 5 | Pseudonimización con Presidio + mapping table | `app/ingestion/pii/`, `app/persistence/` | `python scripts/demo_pii_s06.py --postgres` |

Entorno: `docker compose up -d postgres` y `uv run alembic upgrade head`; `uv run python scripts/preflight_s06.py`
comprueba los 7 puntos críticos.

## Resultados de referencia

- Arquitectura: Proyecto 2 son 250.000 tokens frente a 128.000 de ventana. Restricciones en rojo:
  `context_window`, `latency`, `lost_in_the_middle`. Recomendación: RAG.
- Catálogo: 3 fuentes, 1 `include` (`presupuestos_json`), 1 `review` (transcripciones, la de 2023 sin etiquetas
  de hablante), 1 `exclude` (tarifas, `actuality=1`).
- Ingesta: `presupuestos_json` → job `completed` con 6 documentos. `review` y `exclude` dan 400, desconocida 404.
- Limpieza: 6 ficheros → 5 filas (el dedup se queda con la v2 de `BUDGET-2024-0005`) → 3 válidas, 1 en
  cuarentena (`0002`, fecha `12/03/2024` entre fechas ISO → `NaT`), 1 descartada (`0004`, importe -50.000).
  `dayfirst=True` no repara esa fecha: por eso limpiar y validar son dos pasos.
- PII: transcripción BetaNorte con 14 sustituciones; mismo valor → mismo pseudónimo entre procesos.

## Dónde se aparta este repo de la rama de referencia

- **Entorno.** `unstructured` no está instalado: en Windows `python-magic` falla con segfault sin `libmagic`, y los
  únicos parsers son JSON y TXT. Si aparece un PDF complejo, se instala `python-magic-bin`.
  El modelo `es_core_news_md` se instala como dependencia con URL fija (`[tool.uv.sources]`).
- **Estructura.** Los schemas HTTP de ingesta viven en el router (como en `sessions.py`), no en un paquete
  `app/schemas/`, porque aquí `app/schemas.py` es un módulo. Se usa el singleton `settings`, no `get_settings()`.
- **Limpieza.** `total_amount` se convierte a `float` (con `coerce=False` un entero limpio fallaba el dtype). Se
  valida solo sobre las columnas del contrato. Los fallos de tabla (columna ausente, dtype) quedan en
  `report["table_level_failures"]`; la referencia los ignoraba y una columna ausente dejaba todas las filas como
  válidas sin aviso.
- **PII.** El pseudónimo se deriva del hash del valor (Faker sembrado con el HMAC), no de una secuencia global ni de
  `random`: con la tabla persistente, un reinicio del proceso reasignaba nombres ya usados. Los spans solapados se
  resuelven por score más alto; sustituir ambos corrompía el texto.

## Límites conocidos

- **Falsos positivos del NER en español.** "Quería" se detecta como persona. Se mitiga subiendo el umbral, con una
  deny-list o con `es_core_news_lg`.
- **`ORGANIZATION`** cae en un `REDACTED-xxxx` genérico; no hay generador de organizaciones.
- **Filtración por inferencia** (estilo, jerga, dialecto): la pseudonimización no la frena.
- **Derecho al olvido.** Solo está el paso 4 (`forget`, que borra la entrada de la mapping table). Buscar y borrar los
  chunks del índice y el audit log requieren el índice de la sesión 7.
- **`content_hash`** se calcula en la limpieza pero no se usa para distinguir duplicado exacto de divergencia.
- La mapping table y los jobs no tienen autenticación ni cifrado en reposo: es un entorno de curso.
