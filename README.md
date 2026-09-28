# Estimador CAG

Servicio que genera estimaciones de proyectos de software a partir de una
descripción del proyecto (tipo, nivel de detalle y formato de salida
deseados), usando un LLM (Anthropic Claude u OpenAI, con fallback automático
entre ambos vía `litellm`) y arquitectura **CAG (Cache-Augmented
Generation)**: estimaciones históricas de referencia se inyectan como
ejemplos few-shot directamente en el prompt del sistema.

Flujo del servicio:

```
formulario (descripción + tipo + detalle + formato)
  → render de templates Jinja (system + user)
  → llamada al LLM (con cache exact-match)
  → estimación
```

Tiene dos interfaces sobre la misma lógica de negocio
(`app/services/llm_service.py`):

- **API REST** (`app/main.py`): endpoint de un solo turno pensado para integraciones.
- **Formulario web con Streamlit** (`streamlit_app.py`): formulario tipado
  (reutiliza los mismos schemas Pydantic que la API) para generar una
  estimación y ver el detalle de la última llamada.

## Estructura del proyecto

```
app/
├── main.py                    # App FastAPI y endpoint /health
├── config.py                  # Configuración (variables de entorno)
├── schemas.py                 # Contrato tipado (EstimationRequest/Response, enums)
├── pricing.py                 # Cálculo de coste estimado por llamada
├── context/
│   └── examples.py            # Ejemplos históricos usados en los templates (CAG)
├── prompts/
│   ├── loader.py               # render_estimation_prompt(request, version) vía Jinja2
│   └── estimation/v1/
│       ├── system.j2           # Rol, reglas y bloques condicionales (formato/detalle)
│       ├── user.j2              # Wrapper de la descripción del proyecto
│       └── examples.j2          # Ejemplos few-shot incluidos en system.j2
├── routers/
│   └── estimations.py         # Endpoint POST /api/v1/estimate
└── services/
    ├── llm_service.py         # Orquesta cache + llamada al LLM
    ├── llm_wrapper.py         # Wrapper sobre litellm.Router (primario + fallback)
    └── cache.py                # Cache exact-match en Redis (degrada sin bloquear si no hay Redis)
streamlit_app.py                # Formulario web (Streamlit) sobre la API
docs/
└── transcripcion_ejemplo.md   # Transcripción de ejemplo para inspirar una descripción
tests/
├── test_structure.py          # Valida que la estructura de carpetas es correcta
├── test_api.py                # Valida el flujo completo del endpoint (mockeando el LLM)
├── test_cache.py              # Valida el degradado ante fallos de Redis
└── prompts/
    └── test_estimation_v1.py  # Valida el render de los templates (sin LLM, milisegundos)
.github/workflows/ci.yml       # Pipeline que ejecuta los tests automáticamente
```

## Requisitos

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) como gestor de dependencias
- Redis, opcional: si no está disponible, el cache falla en silencio y el
  servicio sigue funcionando sin cachear (ver `app/services/cache.py`)

## Configuración

1. Copia `.env.example` a `.env` y rellena al menos las API keys:

   ```bash
   cp .env.example .env
   ```

   Variables principales (ver `.env.example` para el resto):

   | Variable                         | Descripción                                  |
   |-----------------------------------|-----------------------------------------------|
   | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Credenciales del/los proveedor/es LLM   |
   | `PRIMARY_MODEL` / `FALLBACK_MODEL`     | Modelos usados por `litellm.Router`     |
   | `REDIS_URL`                       | Cache exact-match; opcional en local          |

2. Instala las dependencias:

   ```bash
   uv sync
   ```

## Ejecutar el servicio

```bash
uv run uvicorn app.main:app --reload
```

El servicio queda disponible en `http://localhost:8000`. Documentación
interactiva (Swagger) en `http://localhost:8000/docs`.

## Uso

### Comprobar estado del servicio

```bash
curl http://localhost:8000/health
```

### Generar una estimación

```bash
curl -X POST http://localhost:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "description": "El cliente necesita una plataforma web de reservas de aulas para una academia de idiomas con tres sedes.",
    "project_type": "web_saas",
    "detail_level": "medium",
    "output_format": "phases_table"
  }'
```

`description` admite entre 20 y 2000 caracteres — la idea es un resumen
acotado, no pegar una transcripción completa (puedes inspirarte en
[`docs/transcripcion_ejemplo.md`](docs/transcripcion_ejemplo.md)).
`project_type`, `detail_level` y `output_format` son los enums definidos en
[`app/schemas.py`](app/schemas.py).

Respuesta de ejemplo:

```json
{
  "text": "## Estimación...",
  "prompt_version": "v1",
  "system_prompt": "Eres un asistente experto...",
  "model": "gpt-4o-mini",
  "input_tokens": 512,
  "output_tokens": 340,
  "truncated": false,
  "cache_hit": false
}
```

## Formulario web (Streamlit)

```bash
uv run streamlit run streamlit_app.py
```

Se abre en `http://localhost:8501`. El formulario pide descripción, tipo de
proyecto, nivel de detalle y formato de salida — los mismos campos que
`EstimationRequest` — y al enviarlo hace un único `POST /estimate` (sin
streaming ni historial de chat). El panel lateral muestra el resultado de la
última llamada: modelo, tokens, si se sirvió desde cache, y el `system
prompt` real que se envió al LLM.

## Prompts versionados

Los templates viven en `app/prompts/estimation/<version>/` (Jinja2, con
`StrictUndefined` para detectar variables no pasadas). `render_estimation_prompt(request, version="v1")`
en [`app/prompts/loader.py`](app/prompts/loader.py) devuelve `(system, user)`
listos para enviar al modelo; cambiar de versión es cuestión de crear una
carpeta `v2/` nueva y pasar `version="v2"`, sin tocar el resto del código.

## Validación y pipeline automático

La suite de tests (`pytest`) se ejecuta automáticamente en cada push/PR
mediante GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

- `tests/test_structure.py`: existencia de ficheros/carpetas esperados y
  que los módulos de la app son importables.
- `tests/test_api.py`: levanta la app con `TestClient` y valida el flujo
  completo del endpoint `/api/v1/estimate` (mockeando la llamada al LLM).
- `tests/test_cache.py`: valida que el servicio no se rompe si Redis no
  está disponible.
- `tests/prompts/test_estimation_v1.py`: valida el contenido de los
  templates renderizados (sin llamar al LLM).

Para ejecutar los tests en local:

```bash
uv sync --all-groups
uv run pytest -v
```
