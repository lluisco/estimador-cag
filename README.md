# Estimador CAG

Servicio que genera estimaciones de proyectos de software a partir de una
descripción del proyecto (tipo, nivel de detalle y formato de salida
deseados), usando un LLM (Anthropic Claude u OpenAI, con fallback automático
entre ambos vía `litellm`) y arquitectura **CAG (Cache-Augmented
Generation)**: estimaciones históricas de referencia se inyectan como
ejemplos few-shot directamente en el prompt del sistema.

La estimación se devuelve como **salida estructurada**: el LLM responde con un
objeto validado (resumen, fases con duración, coste, confianza y supuestos)
gracias a [Instructor](https://python.useinstructor.com/) + Pydantic, no como
texto libre. Si los totales no cuadran con la suma de las fases, la validación
falla y se reintenta con el mensaje de error.

Flujo del servicio:

```
formulario (descripción + tipo + detalle + formato)
  → render de templates Jinja (system + user, con las tarifas por rol)
  → cache exact-match
  → llamada al LLM vía Instructor (esquema EstimationResult + validadores)
  → estimación estructurada
```

Tiene dos interfaces sobre la misma lógica de negocio
(`app/services/llm_service.py`):

- **API REST** (`app/main.py`): endpoint de un solo turno pensado para integraciones.
- **Formulario web con Streamlit** (`streamlit_app.py`): formulario tipado
  (reutiliza los mismos schemas Pydantic que la API) que pinta el resumen, las
  métricas, la tabla de fases y sus supuestos, y muestra el detalle de la última llamada.

## Estructura del proyecto

```
app/
├── main.py                    # App FastAPI y endpoint /health
├── config.py                  # Configuración (variables de entorno)
├── schemas.py                 # Contrato tipado (EstimationRequest/Result/Response, Phase, enums)
├── pricing.py                 # Cálculo de coste estimado por llamada
├── context/
│   └── examples.py            # Ejemplos históricos usados en los templates (CAG)
├── prompts/
│   ├── loader.py               # render_estimation_prompt(request, version) vía Jinja2
│   └── estimation/
│       ├── _rates.j2           # Tarifas por rol (compartido por todas las versiones)
│       ├── _response_spec.j2   # Estructura de salida, formato y detalle (compartido)
│       ├── v1/
│       │   ├── system.j2       # Rol y reglas; incluye _response_spec.j2
│       │   ├── user.j2         # Wrapper de la descripción del proyecto
│       │   └── examples.j2     # Ejemplos few-shot incluidos en system.j2
│       └── v2/                 # Igual que v1 + tono ejecutivo (ver "Prompts versionados")
├── routers/
│   └── estimations.py         # Endpoint POST /api/v1/estimate
└── services/
    ├── llm_service.py         # Orquesta cache + llamada al LLM
    ├── llm_wrapper.py         # litellm.Router (primario + fallback) + Instructor (salida estructurada)
    └── cache.py                # Cache exact-match en Redis (degrada sin bloquear si no hay Redis)
streamlit_app.py                # Formulario web (Streamlit) sobre la API
docs/
└── transcripcion_ejemplo.md   # Transcripción de ejemplo para inspirar una descripción
tests/
├── test_structure.py          # Valida que la estructura de carpetas es correcta
├── test_api.py                # Valida el flujo completo del endpoint (mockeando el LLM)
├── test_schemas.py            # Valida EstimationResult/Phase (totales, límites, costes > 0)
├── test_llm_service.py        # Valida cache miss/hit y truncado (mockeando wrapper y cache)
├── test_cache.py              # Valida el degradado ante fallos de Redis
└── prompts/
    ├── test_estimation_v1.py  # Valida el render de los templates (sin LLM, milisegundos)
    ├── test_estimation_v2.py  # Valida la variación de v2 frente a v1
    └── test_hourly_rates.py   # Valida que las tarifas por rol llegan a los prompts
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
   | `ESTIMATION_MAX_TOKENS`           | Tope de tokens de salida de `/estimate` (4000 por defecto) |
   | `HOURLY_RATES_EUR`                | Tarifa EUR/hora por rol, en JSON (ver abajo)  |

   Las tarifas por defecto son `developer` 60, `project_manager` 60, `ux_ui` 50
   y `other` 50 (cualquier rol no listado). Para cambiarlas, define en `.env`
   `HOURLY_RATES_EUR={"developer": 70, "other": 50}`. Se inyectan en el prompt,
   así que modificarlas cambia la clave de cache.

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

Por defecto se usa la versión `v1` de los prompts. Para usar otra, pásala como
query param (una versión inexistente devuelve `422`):

```bash
curl -X POST "http://localhost:8000/api/v1/estimate?prompt_version=v2"   -H "Content-Type: application/json"   -d '{ ... }'
```

`description` admite entre 20 y 2000 caracteres — la idea es un resumen
acotado, no pegar una transcripción completa (puedes inspirarte en
[`docs/transcripcion_ejemplo.md`](docs/transcripcion_ejemplo.md)).
`project_type`, `detail_level` y `output_format` son los enums definidos en
[`app/schemas.py`](app/schemas.py).

Respuesta de ejemplo:

```json
{
  "result": {
    "summary": "Plataforma de reservas en 8 semanas por 24.000 EUR.",
    "total_duration_weeks": 8,
    "total_cost_eur": 24000,
    "confidence_pct": 75,
    "phases": [
      {
        "name": "Diseño",
        "duration_weeks": 2,
        "cost_eur": 6000,
        "confidence_pct": 80,
        "assumptions": ["Tareas y horas por rol...", "Risk: ..."]
      }
    ]
  },
  "prompt_version": "v1",
  "system_prompt": "You are an expert assistant...",
  "model": "gpt-4o-mini",
  "provider": "openai",
  "input_tokens": 512,
  "output_tokens": 340,
  "truncated": false,
  "cache_hit": false
}
```

Reglas del resultado (validadas en `EstimationResult`): al menos una fase,
costes mayores que 0, `total_duration_weeks` igual a la suma de las fases
(±1 semana) y `total_cost_eur` igual a la suma de las fases (±2 %). Si el modelo
no consigue cumplirlas tras los reintentos, la API responde `502`. También
responde `502` si la salida se corta por `ESTIMATION_MAX_TOKENS`, y `500` para
cualquier otro error del proveedor.

## Formulario web (Streamlit)

```bash
uv run streamlit run streamlit_app.py
```

Se abre en `http://localhost:8501`. El formulario pide descripción, tipo de
proyecto, nivel de detalle y formato de salida — los mismos campos que
`EstimationRequest` — y al enviarlo hace un único `POST /estimate` (sin
streaming ni historial de chat). Muestra el resumen, la duración, el coste y la
confianza totales, la tabla de fases y un desplegable de supuestos por fase.
El panel lateral muestra el resultado de la última llamada: modelo, tokens, si
se sirvió desde cache, y el `system prompt` real que se envió al LLM.

## Prompts versionados

Los templates viven en `app/prompts/estimation/<version>/` (Jinja2, con
`StrictUndefined` para detectar variables no pasadas). `render_estimation_prompt(request, version)`
en [`app/prompts/loader.py`](app/prompts/loader.py) devuelve `(system, user)`
listos para enviar al modelo. Las versiones disponibles se declaran en el enum
`PromptVersion` de [`app/schemas.py`](app/schemas.py), y el endpoint las expone
como `?prompt_version=`. Cada versión tiene su propia copia de `examples.j2`,
pero todas comparten `_rates.j2` (tarifas por rol) y `_response_spec.j2`
(estructura de salida, formato y nivel de detalle), de modo que cambiar esos
dos ficheros afecta a todas las versiones.

Como la respuesta es estructurada, `output_format` y `detail_level` no cambian
el formato del texto sino la forma del resultado: `phases_table` agrupa el
trabajo en fases, `line_items` usa una fase por partida y `narrative` redacta
el resumen como un párrafo; `summary`, `medium` y `detailed` fijan cuántas
fases y supuestos devuelve. Las tareas, las horas por rol y los riesgos (con
prefijo `Risk:`) van dentro de los `assumptions` de cada fase.

| Versión | Variación respecto a la anterior |
|---------|----------------------------------|
| `v1`    | Versión base: asistente experto, tono neutro. |
| `v2`    | Única variación deliberada: **tono ejecutivo** dirigido a un decisor no técnico (consultor senior, resumen ejecutivo inicial, frases cortas, sin jerga). Reglas, formatos, nivel de detalle, ejemplos y `user.j2` son idénticos a v1, para que cualquier diferencia en la salida sea atribuible al tono. |

Para añadir una versión nueva: crea `app/prompts/estimation/vN/` con
`system.j2`, `user.j2` y `examples.j2`, y añade `VN = "vN"` a `PromptVersion`
(`tests/test_structure.py` comprueba que cada versión declarada tiene sus templates).
El cache no necesita cambios: la clave incluye el system prompt renderizado,
así que cada versión cachea por separado.

## Validación y pipeline automático

La suite de tests (`pytest`) se ejecuta automáticamente en cada push/PR
mediante GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

- `tests/test_structure.py`: existencia de ficheros/carpetas esperados y
  que los módulos de la app son importables.
- `tests/test_api.py`: levanta la app con `TestClient` y valida el flujo
  completo del endpoint `/api/v1/estimate` (mockeando la llamada al LLM),
  incluidos los `502` por validación agotada y por límite de tokens.
- `tests/test_schemas.py`: validadores de `EstimationResult` y `Phase`
  (tolerancias de los totales, mensajes de error, costes mayores que 0).
- `tests/test_llm_service.py`: cache miss/hit con el mismo formato guardado y
  marca de truncado (mockeando wrapper y cache).
- `tests/test_cache.py`: valida que el servicio no se rompe si Redis no
  está disponible.
- `tests/prompts/test_estimation_v1.py` / `test_estimation_v2.py`: validan el
  contenido de los templates renderizados (sin llamar al LLM) y que v2 solo
  difiere de v1 en el tono.
- `tests/prompts/test_hourly_rates.py`: las tarifas por rol de la configuración
  llegan a todas las versiones del prompt.

Para ejecutar los tests en local:

```bash
uv sync --all-groups
uv run pytest -v
```
