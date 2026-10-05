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

- **API REST** (`app/main.py`): endpoint de un solo turno (`/estimate`) para
  integraciones y endpoints de **sesión** multi-turno con adjuntos
  (ver "Sesiones conversacionales").
- **Formulario web con Streamlit** (`streamlit_app.py`): formulario tipado
  (reutiliza los mismos schemas Pydantic que la API) que trabaja dentro de una
  sesión, pinta el resumen, las métricas, la tabla de fases y sus supuestos, y
  muestra la memoria del proyecto y el detalle de la última llamada.

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
├── sessions.py                # Estado conversacional: ConversationHistory, ProjectMetadata, Session
├── routers/
│   ├── estimations.py         # Endpoint POST /api/v1/estimate
│   └── sessions.py            # POST /api/v1/sessions y /sessions/{id}/estimate (multipart)
└── services/
    ├── llm_service.py         # Orquesta cache + llamada al LLM
    ├── llm_wrapper.py         # litellm.Router (primario + fallback) + Instructor (salida estructurada)
    ├── cache.py                # Cache exact-match en Redis (degrada sin bloquear si no hay Redis)
    ├── attachments.py         # Extracción de texto de PDF/Word (pypdf, python-docx)
    ├── project_memory.py      # Extractor LLM que actualiza el project_metadata de la sesión
    └── session_service.py     # Estimación dentro de una sesión: historial + metadata + LLM
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

Se abre en `http://localhost:8501`. Al cargar la página crea una sesión
(`POST /sessions`) y guarda el `session_id` en `st.session_state`. El formulario
pide la transcripción (o la nueva información del cliente), un selector múltiple
de adjuntos (PDF y Word), el tipo de proyecto, el nivel de detalle y el formato de
salida. Al enviarlo hace un `POST /sessions/{id}/estimate` multipart y después un
`GET /sessions/{id}` para refrescar el panel lateral. No hay hilo de chat: cada
envío reemplaza la estimación mostrada, y la continuidad la aporta la sesión.
Muestra el resumen, la duración, el coste y la confianza totales, la tabla de
fases y un desplegable de supuestos por fase.

El panel lateral muestra:

- el `session_id`, el número de turnos del historial y un botón **Nueva
  conversación** que crea una sesión nueva y limpia el estado;
- la **memoria del proyecto** (`project_metadata`) en JSON, para ver cómo se
  acumulan los hechos entre turnos;
- el resultado de la última llamada: modelo, tokens, si se sirvió desde cache, y
  el `system prompt` real que se envió al LLM.

Como las sesiones viven en memoria del servidor, si se reinicia uvicorn (por
ejemplo con `--reload` al guardar un archivo) el `session_id` que conserva
Streamlit deja de existir y la API responde `404`: pulsa "Nueva conversación".

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

## Sesiones conversacionales (sesión 05)

El endpoint `/estimate` es transaccional. Para iterar sobre un mismo proyecto
(refinar alcance, añadir documentos) hay un modelo de **sesión**:

```bash
# 1. crear sesión -> {"session_id": "<uuid>"}
curl -X POST http://localhost:8000/api/v1/sessions

# 2. estimar dentro de la sesión (multipart/form-data, adjuntos opcionales)
curl -X POST http://localhost:8000/api/v1/sessions/<session_id>/estimate \
  -F "transcript=Quiero una app de reservas para mi academia" \
  -F "attachments=@spec.pdf" -F "attachments=@propuesta.docx"

# 3. consultar el estado de la sesión (turnos y project_metadata)
curl http://localhost:8000/api/v1/sessions/<session_id>
```

Campos del formulario de `/sessions/{id}/estimate`: `transcript` (obligatorio),
`attachments` (opcional, varios), y los parámetros tipados `project_type`,
`detail_level`, `output_format` y `prompt_version`, todos con valor por defecto
(`web_saas`, `medium`, `phases_table` y `v2`). La respuesta respeta el mismo
schema `EstimationResponse` que `/estimate`.

Códigos de error: un `session_id` inexistente devuelve `404`; un adjunto que no sea
`.pdf` o `.docx`, o que pese más de 5 MB, devuelve `400`; una entrada rechazada por
los guardrails también `400`.

El límite de 2000 caracteres de `description` (propio de `/estimate`) no se aplica
aquí: la transcripción más el texto de los adjuntos puede superarlo, así que el
endpoint valida la transcripción original y después sustituye `description` por el
texto completo sin revalidar.

### Historial frente a memoria

Son dos cosas distintas y viven separadas en [`app/sessions.py`](app/sessions.py):

| | Historial | Memoria (`project_metadata`) |
|---|---|---|
| Qué es | El array `messages` que viaja a la API en cada llamada | Hechos del proyecto: nombre, equipo asumido, tecnologías, alcance acordado |
| Duración | Ventana deslizante: solo los últimos `MAX_TURNS` (6) turnos (par user+assistant) | Se acumula durante toda la sesión |
| Dónde va al LLM | Como mensajes user/assistant | Dentro del system prompt, en el bloque `<project_metadata>` |

El system prompt **no se guarda en el historial**: se regenera en cada turno a
partir del `project_metadata` actual, de modo que la ventana nunca puede
descartarlo. Cuando un turno antiguo sale de la ventana, sus hechos siguen
disponibles porque ya están en el `project_metadata`.

**Qué se guarda en el historial.** Por cada turno, el mensaje del usuario se guarda
con el transcript original más una nota `[Adjuntos: nombre.pdf]`, **sin** el texto de
los adjuntos (si no, un PDF largo se reenviaría en cada turno de la ventana). El
mensaje del asistente se guarda como un resumen compacto: resumen, total de semanas y
euros y nombres de fases. Los hechos de los documentos llegan al turno siguiente a
través del `project_metadata`.

**Tamaño de la ventana.** El mensaje en curso cuenta como un turno: al LLM viajan
como máximo `MAX_TURNS - 1` pares guardados más el mensaje nuevo, de modo que el total
de turnos de usuario en la llamada es `MAX_TURNS`. `MAX_TURNS` es de momento una
constante de [`app/sessions.py`](app/sessions.py), no una variable de entorno.

**Atomicidad.** La sesión solo se modifica cuando la estimación tiene éxito. Si el
LLM falla o un guardrail rechaza la entrada, el historial y el `project_metadata`
quedan como estaban.

**Inyección en el prompt.** El bloque `<project_metadata>` está en la plantilla `v2`
(va al final del system prompt para mantener estable el prefijo cacheable).
La plantilla `v1` no lo usa. Con la memoria vacía, el bloque sale vacío.

**Volatilidad.** Las sesiones viven en un diccionario en memoria del proceso: se
pierden al reiniciar el servicio y no se comparten entre workers. Es una decisión
consciente para esta fase (sin BBDD ni Redis); el patrón es lo que importa aquí,
no la durabilidad.

### Adjuntos: camino B (extracción local)

Elegimos **extraer el texto en local** (`pypdf` para PDF, `python-docx` para Word) y
concatenarlo al transcript con un separador claro:

```
<transcript>

--- attachment: spec.pdf ---
<texto extraído>
```

Por qué no enviar el archivo directamente al LLM (camino A, Files API):

- El servicio usa `litellm.Router` con **fallback entre proveedores**. Un archivo
  subido a la Files API queda ligado a un proveedor, y el fallback dejaría de
  funcionar con adjuntos.
- La Files API no cubre bien Word.
- El texto extraído es la base del chunking de RAG del módulo 3.

Limitaciones asumidas: se pierden los diagramas y las imágenes, y un PDF
escaneado (sin capa de texto) produce texto vacío porque no hay OCR. Los adjuntos
se tratan como **input no confiable**: los guardrails de entrada deben ejecutarse
sobre el texto completo (transcript + adjuntos), no solo sobre el transcript.

### Cómo se extrae el `project_metadata`

Tras cada respuesta, [`app/services/project_memory.py`](app/services/project_memory.py)
hace una **segunda llamada al LLM** (extractor) que recibe los hechos conocidos, el
mensaje del cliente y el resumen de la estimación, y devuelve un `ProjectMetadata`
validado por Instructor/Pydantic. La fusión con lo ya conocido se hace **en código**,
no en el LLM: las tecnologías se acumulan sin duplicados y el resto de campos solo se
sobrescriben si hay un valor nuevo, así el modelo no puede borrar un hecho por error.
Si la extracción falla, se conserva el metadata anterior y se registra un warning: la
memoria es auxiliar y no debe romper la petición.

Por qué un extractor LLM y no una heurística (regex): los hechos llegan en lenguaje
natural libre ("el proyecto se llamará Atlas", "somos tres desarrolladores"), y un
regex sobre la respuesta del modelo es frágil. El coste es una llamada pequeña extra
por turno (máx. 500 tokens de salida).

### Estado

Hecho: modelo de sesión, `POST /sessions` y `GET /sessions/{id}`, endpoint multipart
con extracción de adjuntos y estimación con historial + `project_metadata`, bloque
`<project_metadata>` en la plantilla v2, extractor y cliente Streamlit adaptado.

Pendiente (trabajo en curso):

- Tests de integración con `pytest` y `httpx.AsyncClient`: dos peticiones enlazadas
  que actualizan el `project_metadata`, una petición con PDF adjunto y 8 turnos que
  verifican el límite de la ventana.
- Manejo de errores del LLM en `/sessions/{id}/estimate`: las excepciones de
  validación agotada (`InstructorRetryException`) y de salida truncada
  (`IncompleteOutputException`) aún no se traducen a `502` como en `/estimate`, así
  que hoy llegan como `500`. Tampoco se traduce a `422` una transcripción de menos de
  20 caracteres.
- `MAX_TURNS` como variable de entorno (`SESSION_MAX_TURNS`).

Limitación conocida, heredada de `/estimate`: el validador de `EstimationResult`
exige que los totales coincidan con la suma de las fases y el modelo a veces falla la
suma en transcripciones complejas. Tras los reintentos de Instructor la petición
falla y la sesión queda intacta. Una solución más robusta sería calcular los totales
en código en lugar de pedírselos al modelo.

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
