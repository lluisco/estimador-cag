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
│   ├── loader.py               # render_* de estimación, extractor, resumen y Critic vía Jinja2
│   ├── metadata_extraction/
│   │   └── v1/                 # system.j2 + user.j2 del extractor de project_metadata
│   ├── conversation_summary/
│   │   └── v1/                 # system.j2 + user.j2 del resumen acumulativo (en español)
│   ├── critic/
│   │   └── v1/                 # system.j2 + user.j2 del Critic (flujo ACB)
│   └── estimation/
│       ├── _rates.j2           # Tarifas por rol (compartido por todas las versiones)
│       ├── _response_spec.j2   # Estructura de salida, formato y detalle (compartido)
│       ├── _critic_feedback.j2 # Bloque <critic_feedback> que se añade al user prompt en ACB
│       ├── v1/
│       │   ├── system.j2       # Rol y reglas; incluye _response_spec.j2
│       │   ├── user.j2         # Wrapper de la descripción del proyecto
│       │   └── examples.j2     # Ejemplos few-shot incluidos en system.j2
│       ├── v2/                 # Igual que v1 + tono ejecutivo (ver "Prompts versionados")
│       └── v3/                 # Igual que v1 + bloque <audience> según el tier resuelto
├── sessions.py                # Estado conversacional: ConversationHistory, ProjectMetadata, Session
├── routers/
│   ├── estimations.py         # Endpoint POST /api/v1/estimate
│   └── sessions.py            # POST /sessions, /sessions/{id}/estimate y /estimate-acb (multipart)
└── services/
    ├── llm_service.py         # Orquesta cache + llamada al LLM
    ├── llm_wrapper.py         # litellm.Router (primario + fallback) + Instructor (salida estructurada)
    ├── cache.py                # Cache exact-match en Redis (degrada sin bloquear si no hay Redis)
    ├── attachments.py         # Extracción de texto de PDF/Word (pypdf, python-docx)
    ├── project_memory.py      # Extractor LLM que actualiza el project_metadata de la sesión
    ├── anchors.py             # AnchorDetector: ¿el mensaje del cliente es un compromiso duradero?
    ├── summarizer.py          # CumulativeSummarizer: resumen acumulativo de los turnos expulsados
    ├── compression.py         # CompressionPolicy: decide qué se ancla, qué se resume y qué se olvida
    ├── tier.py                # resolve_tier: tier de audiencia por reglas deterministas
    ├── critic.py              # CriticFeedback (schema) + Critic (auditor sin estado)
    ├── boss.py                # Boss: máquina de estados sin LLM + BossTrace
    └── session_service.py     # Turno de sesión (normal y ACB): tier + LLM + commit atómico
streamlit_app.py                # Formulario web (Streamlit) sobre la API
docs/
└── transcripcion_ejemplo.md   # Transcripción de ejemplo para inspirar una descripción
tests/
├── conftest.py                # FakeLLMWrapper + fixtures de sesiones (TestClient + dependency_overrides)
├── test_sessions_metadata.py  # project_metadata entre turnos, extractor y fusión
├── test_sessions_attachments.py # Adjuntos PDF/Word: llegan al LLM, influyen y no se arrastran
├── test_sessions_window.py    # La ventana acota el historial; el NDA del turno 1 sigue literal en el 10
├── test_sessions_tier.py      # El tier llega al prompt y se expone en GET /sessions/{id}
├── test_sessions_acb.py       # /estimate-acb: traza, feedback al actor, solo el final en la sesión
├── test_anchors.py            # Detector de anclas: positivos y negativos en español
├── test_compression.py        # Política de compresión y resumidor (sin LLM real)
├── test_tier.py               # Cada regla, precedencia y override
├── test_critic.py             # Schema del CriticFeedback y fallback del Critic
├── test_boss.py               # Boss con actor y critic de mentira, sin LLM
├── test_structure.py          # Valida que la estructura de carpetas es correcta
├── test_api.py                # Valida el flujo completo del endpoint (mockeando el LLM)
├── test_schemas.py            # Valida EstimationResult/Phase (totales, límites, costes > 0)
├── test_llm_service.py        # Valida cache miss/hit y truncado (mockeando wrapper y cache)
├── test_cache.py              # Valida el degradado ante fallos de Redis
└── prompts/
    ├── test_estimation_v1.py  # Valida el render de los templates (sin LLM, milisegundos)
    ├── test_estimation_v2.py  # Valida la variación de v2 frente a v1
    ├── test_estimation_v3.py  # Cada tier pinta solo su bloque <audience>
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
   | `SESSION_MAX_TURNS`               | Turnos que conserva la ventana deslizante del historial de una sesión (6 por defecto) |
   | `MAX_ATTACHMENT_CHARS`            | Caracteres que se conservan de cada adjunto (60.000 por defecto) |
   | `METADATA_EXTRACTOR_MODEL`        | Modelo del extractor de `project_metadata` (por defecto el mismo que `PRIMARY_MODEL`) |
   | `COMPRESSION_MODEL`               | Modelo que escribe el resumen acumulativo de los turnos expulsados |
   | `CRITIC_MODEL`                    | Modelo del Critic en `/estimate-acb` |
   | `BOSS_MAX_ITERATIONS`             | Vueltas máximas actor + critic por turno ACB (3 por defecto) |
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
salida, más un selector de **audiencia (tier)** con la opción "Automático" (no envía
el campo y el servidor decide por reglas) y un interruptor **Revisión independiente
(ACB)** que decide qué endpoint se llama. Al enviarlo hace un `POST
/sessions/{id}/estimate` (o `/estimate-acb`) multipart y después un
`GET /sessions/{id}` para refrescar el panel lateral. No hay hilo de chat: cada
envío reemplaza la estimación mostrada, y la continuidad la aporta la sesión.
Muestra el resumen, la duración, el coste y la confianza totales, la tabla de
fases y un desplegable de supuestos por fase.

El panel lateral muestra:

- el `session_id`, el número de turnos del historial y un botón **Nueva
  conversación** que crea una sesión nueva y limpia el estado;
- el **tier** del último turno y la regla que lo decidió, p. ej. `executive (nda_detected)`;
- el número de **anclas** y la longitud del **resumen acumulativo**;
- la **memoria del proyecto** (`project_metadata`) en JSON, para ver cómo se
  acumulan los hechos entre turnos;
- tras un turno ACB, un desplegable con la **traza**: veredicto, confianza de la
  revisión y principales issues de cada vuelta;
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
| `v2`    | Única variación deliberada: **tono ejecutivo** dirigido a un decisor no técnico (consultor senior, resumen ejecutivo inicial, frases cortas, sin jerga). Reglas, formatos, nivel de detalle, ejemplos, `user.j2` y el bloque `<project_metadata>` son idénticos a v1, para que cualquier diferencia en la salida sea atribuible al tono. |
| `v3`    | Generaliza v2: es **v1 + un bloque `<audience>`** que cambia según el tier resuelto (`executive`: riesgos primero, 3-4 fases, sin jerga, supuestos en términos de negocio; `pm`: hitos y dependencias; `developer`: stack, integraciones y supuestos técnicos verificables; `default`: sin bloque, idéntico a v1). Va al final del system, junto a `<project_metadata>`, para no romper el prefijo cacheable. Además añade un bloque `<partial_definition>`: ante una propuesta con el alcance a medio definir (p. ej. que propone una fase de definición antes de desarrollar), estima esa fase y un MVP orientativo con confianza no inferior al umbral, en vez de responder `OUT OF SCOPE:`. Es la versión por defecto de las sesiones; `/estimate` sigue usando v1/v2, que conservan su regla de rechazo original. |

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

# 3. lo mismo con revisión Actor-Critic-Boss (mismo contrato multipart)
curl -X POST http://localhost:8000/api/v1/sessions/<session_id>/estimate-acb \
  -F "transcript=Firmamos un NDA; el presupuesto está cerrado en 40.000 €"

# 4. consultar el estado de la sesión
curl http://localhost:8000/api/v1/sessions/<session_id>
```

Campos del formulario de `/sessions/{id}/estimate` y `/estimate-acb`: `transcript`
(obligatorio), `attachments` (opcional, varios), y los parámetros tipados
`project_type`, `detail_level`, `output_format`, `prompt_version` y `tier`, con valor
por defecto (`web_saas`, `medium`, `phases_table`, `v3` y automático). `tier` acepta
`executive`, `pm`, `developer` o `default`; cualquier otro valor da `422`. La
respuesta de `/estimate` respeta el schema `EstimationResponse`; la de
`/estimate-acb` lo extiende con un campo `acb` (la `BossTrace`).

`GET /sessions/{id}` devuelve `turns`, `max_turns`, `project_metadata`,
`last_resolved_tier`, `last_tier_rule`, `anchors` (turnos anclados) y
`summary_chars` (longitud del resumen acumulativo).

Códigos de error:

| Código | Causa |
|--------|-------|
| `400` | Adjunto que no es `.pdf` o `.docx`, que pesa más de 5 MB, que no se puede leer o que no contiene texto extraíble (p. ej. un PDF escaneado); o entrada rechazada por los guardrails |
| `404` | `session_id` inexistente |
| `422` | Transcripción fuera de rango (menos de 20 o más de 80.000 caracteres), validada en el propio `Form` |
| `502` | El modelo no devolvió una estimación válida tras los reintentos de Instructor, o la salida se cortó por `ESTIMATION_MAX_TOKENS` |

El límite de 2000 caracteres de `description` (propio de `/estimate`) no se aplica
aquí: la transcripción más el texto de los adjuntos puede superarlo. El `Form` valida
la transcripción (20-80.000 caracteres) y el endpoint construye el `EstimationRequest`
con `model_construct`, sin revalidar, con el texto completo.

### Tres memorias, tres políticas de olvido

La ventana deslizante sola olvida a ciegas: en el turno 8, lo dicho en el turno 1
solo sobreviviría si el extractor lo hubiera metido en `project_metadata`, que tiene
cuatro campos. Un "firmamos un NDA" o un "el presupuesto está cerrado en 40.000 €"
desaparecería. Por eso, además de la ventana reciente, hay tres memorias distintas:

| | `project_metadata` | Resumen | Anclas |
|---|---|---|---|
| Qué es | Campos estructurados (nombre, equipo, tecnologías, alcance) | Prosa en español que comprime los turnos viejos | Pares user/assistant **literales** |
| Política de olvido | Se **sobrescribe** campo a campo (fusión en código) | Se **reescribe** entero en cada compresión | **Nunca** se toca |
| Quién escribe | Extractor LLM + `merge_with` | `CumulativeSummarizer` (LLM) | `AnchorDetector` (regex, sin LLM) |
| Dónde va al LLM | Bloque `<project_metadata>` del system | Bloque `<conversation_summary>` del system | Mensajes user/assistant, antes de la ventana |

La **ventana reciente** son los últimos `SESSION_MAX_TURNS` turnos, tal cual. El
array que llega al LLM tiene siempre esta forma y nunca la supera:

    [system (+ project_metadata + resumen)] + anclas + ventana reciente + mensaje nuevo

El system prompt **no se guarda en el historial**: se regenera en cada turno a
partir del `project_metadata` y del resumen actuales, de modo que la ventana nunca
puede descartarlo.

**Datos separados de la política.** `ConversationHistory` solo guarda (`summary`,
`anchors`, ventana) y `add_turn` solo añade. Quien decide qué se olvida es
[`CompressionPolicy.apply`](app/services/compression.py), que se ejecuta tras cada
turno: mientras haya más de `max_turns` pares, saca el más antiguo; si el mensaje del
cliente es un ancla, el par entero va a `anchors`, y si no, se encola. Al final hace
**una sola** llamada al resumidor con todo lo expulsado, aunque sean varios turnos. Es
idempotente: aplicarla dos veces seguidas no cambia nada. Así hay un único punto que
decide qué se borra.

**Detección de anclas.** [`AnchorDetector`](app/services/anchors.py) es heurístico
(regex en español, sin LLM, determinista): NDA o acuerdo de confidencialidad, contrato
firmado, alcance cerrado o congelado, presupuesto cerrado o con tope, regulación
(RGPD, GDPR, HIPAA, ISO 27001, ENS), fecha innegociable y "nos comprometimos a". Es
**conservador a propósito**: un falso negativo solo manda el turno al resumen, pero un
falso positivo lo deja en el prompt para siempre, porque las anclas no se expulsan.
Limitación conocida: una regex no entiende la negación, y "no hay NDA" también
dispara. Un clasificador LLM con fallback al heurístico lo resolvería, a costa de una
llamada más por turno. Tampoco hay tope de anclas: si el cliente repite el mismo
compromiso en varios turnos, se anclan todos.

**Dónde va el resumen: en el system prompt, no como mensaje `user`.** La alternativa
es inyectarlo como un mensaje `user` sintético al principio. Se descartó por tres
razones: sin anclas produce dos mensajes `user` seguidos (el resumen y el primer turno
de la ventana), que algunos proveedores rechazan o fusionan; presenta como dicho por
el cliente algo que escribió el sistema; y el system ya se regenera en cada turno con
el `project_metadata`, así que es el sitio natural para el contexto de fondo. El
coste: el system cambia cuando se comprime, lo que invalida la caché del prompt en ese
turno. Por eso el resumen va al final del system, detrás del metadata.

**Si el resumidor falla**, se conserva el resumen anterior y se registra un warning.
Los turnos expulsados en esa compresión se pierden, y es una decisión consciente:
devolverlos a la ventana haría crecer el prompt sin límite si el modelo de compresión
estuviera caído, y rompería la garantía de tamaño. Mejora futura: señalar al cliente
que la memoria quedó degradada.

**Qué se guarda en el historial.** Por cada turno, el mensaje del usuario se guarda
con el transcript original más una nota `[Adjuntos: nombre.pdf]`, **sin** el texto de
los adjuntos (si no, un PDF largo se reenviaría en cada turno de la ventana). El
mensaje del asistente se guarda como un resumen compacto: resumen, total de semanas y
euros y nombres de fases. Los hechos de los documentos llegan al turno siguiente a
través del `project_metadata`.

**Tamaño de la ventana.** La ventana guarda como máximo `MAX_TURNS` pares
user+assistant tras aplicar la política, y el mensaje en curso viaja aparte: al LLM le
llegan el system prompt (con el resumen), las anclas, hasta `MAX_TURNS` pares previos
y el mensaje nuevo. Se configura con la variable de
entorno `SESSION_MAX_TURNS` (por defecto 6); [`app/sessions.py`](app/sessions.py) la
lee en `MAX_TURNS`. Bajarla a 2 o 3 es la forma más rápida de ver la ventana en acción.

**Atomicidad.** La sesión solo se modifica cuando la estimación tiene éxito. Si el
LLM falla o un guardrail rechaza la entrada, el historial y el `project_metadata`
quedan como estaban.

**Inyección en el prompt.** El bloque `<project_metadata>` está en las plantillas
`v1` y `v2` (va al final del system prompt para mantener estable el prefijo
cacheable). `render_estimation_prompt` acepta el `project_metadata` de la sesión; con
la memoria vacía, o en el endpoint `/estimate` que no usa sesión, el bloque sale vacío.
Junto al bloque, el prompt indica al modelo que trate el historial como contexto ya
establecido (sin pedir que se repita) y que, si llega alcance nuevo, devuelva una
estimación **completa actualizada**, no un delta.

**Volatilidad.** Las sesiones viven en memoria del proceso, dentro de un `SessionStore`
que el router recibe con `Depends(get_session_store)`: se pierden al reiniciar el
servicio y no se comparten entre workers. Es una decisión consciente para esta fase
(sin BBDD ni Redis); el `SessionStore` es la única pieza a sustituir el día que haga
falta persistencia. El wrapper del LLM también se inyecta (`Depends(get_llm_wrapper)`),
lo que permite a los tests sustituir ambos con `dependency_overrides`.

### Adjuntos: camino B (extracción local)

Elegimos **extraer el texto en local** (`pypdf` para PDF, `python-docx` para Word) y
concatenarlo al transcript con un separador claro:

```
<transcript>

--- attachment: spec.pdf ---
<texto extraído, recortado a MAX_ATTACHMENT_CHARS>
--- end attachment ---
```

Además del límite de 5 MB por archivo, el texto extraído de cada adjunto se recorta a
`MAX_ATTACHMENT_CHARS` (60.000 por defecto) para no reventar la ventana de contexto.

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
mensaje del cliente y la estimación recién generada, y devuelve un `ProjectMetadata`
validado por Instructor/Pydantic (con límites: nombre de hasta 120 caracteres, equipo
de 1 a 50 personas, alcance de hasta 2000 caracteres). El prompt vive en plantillas
Jinja versionadas (`app/prompts/metadata_extraction/v1/`) y el modelo se configura
con `METADATA_EXTRACTOR_MODEL`: si coincide con `PRIMARY_MODEL` pasa por el Router (con
fallback); si es otro, se llama directamente.

La fusión con lo ya conocido se hace **en código** (`ProjectMetadata.merge_with`), no
en el LLM: las tecnologías se unen sin duplicados y sin distinguir mayúsculas
(`React` y `react` son la misma), y el resto de campos solo se sobrescriben si hay un
valor nuevo, así el modelo no puede borrar un hecho por error. Por eso el prompt le
pide devolver `null` ante la duda. Si la extracción falla, se conserva el metadata
anterior y se registra un warning: la memoria es auxiliar y no debe romper la petición.

Por qué un extractor LLM y no una heurística (regex): los hechos llegan en lenguaje
natural libre ("el proyecto se llamará Atlas", "somos tres desarrolladores"), y un
regex sobre la respuesta del modelo es frágil. El coste es una llamada pequeña extra
por turno (máx. 1000 tokens de salida).

### Tier de audiencia: por reglas, no por LLM

[`resolve_tier(transcript, metadata, override)`](app/services/tier.py) devuelve
`(tier, regla)`. El override de quien llama (campo `tier` del formulario) siempre
gana; si no hay, gana la **primera** regla que se cumpla:

| Orden | Regla | Tier |
|---|---|---|
| 1 | `nda_detected` | `executive` |
| 2 | `regulation_detected` (RGPD, GDPR, HIPAA, ISO 27001, ENS) | `executive` |
| 3 | `technical_language` (2 o más términos técnicos distintos) | `developer` |
| 4 | `small_team` (equipo de 2 personas o menos) | `pm` |
| - | `no_rule_matched` | `default` |

**Por qué reglas y no un LLM.** Son explicables (el panel muestra
"executive (nda_detected)"), deterministas (un test fija cada regla y la precedencia:
un NDA gana a un equipo pequeño por estar antes en la tabla) y no cuestan una llamada.
Una regla que lanza una excepción se registra y se salta, sin romper la petición.

**Mira el metadata acumulado, no solo el último mensaje.** El texto que evalúan las
reglas es el transcript (con adjuntos) más el `agreed_scope` y las tecnologías del
`project_metadata`. Un NDA dicho en el turno 1 y guardado en `agreed_scope` sigue
activando `executive` en el turno 5. Limitación: si el extractor no copia el NDA al
metadata, el tier lo pierde aunque el turno siga en las anclas.

El tier se guarda en la sesión con el resto de mutaciones, solo si el turno tiene
éxito, y se expone en `GET /sessions/{id}` (`last_resolved_tier`, `last_tier_rule`).

### Actor-Critic-Boss (`/estimate-acb`)

Tres papeles separados: el **Actor** genera (la llamada de estimación de siempre), el
**Critic** audita y el **Boss** decide.

- **Critic** ([`app/services/critic.py`](app/services/critic.py)). Devuelve un
  `CriticFeedback` con `verdict` (`accept`, `needs_iteration`, `reject`), `issues`
  (categoría, severidad, `field_path` y descripción) y `confidence_in_review`. Los
  validadores imponen coherencia: `needs_iteration` exige al menos una issue
  `critical` o `major`, y `reject` exige al menos una issue. **Schema y no prosa**
  porque el Boss decide leyendo campos; con texto libre habría que interpretarlo. Es
  sin estado y, si falla, devuelve `accept` con confianza 0: la petición nunca se rompe
  por el auditor, y la traza distingue "revisado" de "no se pudo revisar". Como
  `EstimationResult` ya valida en código que los totales cuadran, un `math_error`
  indicaría una regresión; el valor del Critic está en lo que Pydantic no ve: datos
  inventados, alcance mal interpretado, fases desequilibradas y tono que no encaja con
  el tier (por eso recibe el tier). Su prompt insiste en "ante la duda, minor" y "ante
  la duda, accept": un Critic quisquilloso multiplica las llamadas sin mejorar nada.
- **Boss** ([`app/services/boss.py`](app/services/boss.py)). Máquina de estados **sin
  llamadas al LLM**: recibe `actor(feedback | None) -> EstimationResult` y
  `critic(result) -> CriticFeedback` como funciones, y por eso se prueba entero con
  dobles. Si el Critic acepta, devuelve el borrador; si pide iterar y quedan vueltas,
  vuelve a llamar al actor con el feedback; si rechaza o se agotan las vueltas,
  **sintetiza**: el último borrador con las advertencias del Critic delante del
  resumen y la confianza reducida. La confianza nunca baja de
  `LOW_CONFIDENCE_THRESHOLD` (50): por debajo, el validador de `EstimationResult`
  exigiría el prefijo `OUT OF SCOPE:` y la síntesis sería incoherente. Por eso se usa
  la constante y no un número fijo. Todo queda en una `BossTrace` (una entrada por
  vuelta) que viaja en el campo `acb` de la respuesta.
- **Actor.** Reconstruye el prompt en cada vuelta y añade el feedback del Critic en un
  bloque `<critic_feedback>` al final del user prompt (parcial
  `estimation/_critic_feedback.j2`, igual para todas las versiones, así v1 y v2 no se
  tocan y el system no cambia).

**Regla de sesión:** solo el resultado final se guarda en la sesión; los borradores
intermedios se descartan. Para el usuario, un turno sigue siendo una respuesta.

**Coste por turno.** Cada llamada añade latencia, y casi todas son secuenciales:

| Flujo | Llamadas al LLM por turno |
|---|---|
| `/estimate` (sesión) | 1 estimación + 1 extractor (+ 1 resumidor si la ventana se desborda) = **2-3** |
| `/estimate-acb`, mejor caso | 1 actor + 1 critic + 1 extractor (+ 1 resumidor) = **3-4** |
| `/estimate-acb`, peor caso (`BOSS_MAX_ITERATIONS=3`) | 3 actor + 3 critic + 1 extractor + 1 resumidor = **hasta 8** |

Por eso ACB es un endpoint aparte y no el comportamiento por defecto. Los tokens que
devuelve la respuesta suman todas las llamadas del actor; los del Critic no se
contabilizan todavía.

### Estado

Completo: modelo de sesión con `SessionStore` inyectable, `POST /sessions` y
`GET /sessions/{id}`, endpoint multipart con extracción y recorte de adjuntos,
estimación con historial + `project_metadata`, bloque `<project_metadata>` y reglas de
conversación en las plantillas v1 y v2, extractor con prompt versionado y modelo
propio, ventana configurable con `SESSION_MAX_TURNS`, manejo de errores
(400/404/422/502), cliente Streamlit adaptado y tests de integración (ver abajo).
Memoria híbrida (anclas, resumen acumulativo y `CompressionPolicy`), tier por reglas
con plantilla v3, y flujo Actor-Critic-Boss en `/estimate-acb` con su traza en el
cliente.

Limitación conocida, heredada de `/estimate`: el validador de `EstimationResult`
exige que los totales coincidan con la suma de las fases y el modelo a veces falla la
suma en transcripciones complejas. Tras los reintentos de Instructor la petición
falla y la sesión queda intacta. Una solución más robusta sería calcular los totales
en código en lugar de pedírselos al modelo.

## Validación y pipeline automático

La suite de tests (`pytest`) se ejecuta automáticamente en cada push/PR
mediante GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

- `tests/test_sessions_*.py`: tests de integración de las sesiones con `TestClient`.
  Un `FakeLLMWrapper` (en `tests/conftest.py`) sustituye al wrapper real vía
  `dependency_overrides`, registra los `messages` de cada llamada y distingue la
  estimación del extractor por `response_model`. Cubren: dos turnos enlazados que
  actualizan el `project_metadata`; adjuntos PDF/Word cuyo texto llega al LLM y cambia
  la estimación, pero no se arrastra por el historial; y 8 turnos con una ventana de 3
  en los que el historial nunca supera el límite mientras la memoria sobrevive.
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

## Ingesta de datos (sesión 06)

La sesión 06 añade el subsistema `app/ingestion/` (catálogo, parsers, limpieza, PII) y Postgres para los jobs y la
mapping table de pseudónimos. Detalle, resultados y diferencias con la rama de clase en
[docs/session-06-notes.md](docs/session-06-notes.md).

```bash
docker compose up -d postgres
uv run alembic upgrade head
uv run python scripts/preflight_s06.py
```

## Pipeline de embeddings (sesión 07)

El módulo `app/embedding_pipeline/` convierte los presupuestos históricos (JSON normalizado) en vectores:

- `chunker.py`: `JSONStructuralChunker`, un componente del presupuesto = un chunk, con la cabecera de contexto del
  presupuesto padre. Sin overlap ni troceado de descripciones largas.
- `embedder.py`: `OpenAIEmbedder` (`text-embedding-3-small`, 1536 dimensiones, lotes de 100, reintentos 1 s/2 s/4 s
  ante `RateLimitError`). El precio por millón de tokens es una constante del módulo: cambia con el tiempo.
- `router.py`: `POST /embeddings/ingest` (sin el prefijo `/api/v1`).

Los vectores se generan en memoria y se devuelven por HTTP; la persistencia llega en la sesión 08. Resultados del
sanity check en [app/embedding_pipeline/SANITY_CHECK.md](app/embedding_pipeline/SANITY_CHECK.md).

### Arrancar el servicio

Con Docker (servicio `servicio_ia`, necesita `OPENAI_API_KEY` en `.env`):

```bash
docker compose build servicio_ia
docker compose up -d servicio_ia
```

O en local, sin contenedor: `uv run uvicorn app.main:app --reload`. En ambos casos queda en `http://localhost:8000`
(Swagger en `/docs`). Tras `up -d`, uvicorn tarda unos segundos en responder.

### Invocar el endpoint

Desde Swagger (`/docs` > `POST /embeddings/ingest` > *Try it out*) o con curl, usando `data/budgets_sample.json`
(15 presupuestos, 52 componentes):

```bash
python -c "import json; print(json.dumps({'budgets': json.load(open('data/budgets_sample.json', encoding='utf-8'))}))"   | curl -s -X POST localhost:8000/embeddings/ingest -H "Content-Type: application/json" -d @-   | python -c "import json,sys; print(json.load(sys.stdin)['stats'])"
```

Respuesta: `{"chunks": [...], "stats": {total_budgets, total_chunks, total_tokens, estimated_cost_usd}}`.
422 si el body no valida (p. ej. un `sector` fuera de `finance|ecommerce|healthcare|industrial`) y 500 con mensaje
genérico si falla la API de embeddings (el detalle va al log).

### Comparar dos textos (`scripts/compare.py`)

Similitud coseno entre dos textos, calculada a mano con la biblioteca estándar:

```bash
# Dentro del contenedor
docker compose exec servicio_ia python scripts/compare.py   --text-a "OAuth 2.0 authentication backend for fintech"   --text-b "JWT-based authorization service for banking app"

# Fuera del contenedor (con el .env cargado)
uv run python scripts/compare.py   --text-a "OAuth 2.0 authentication backend for fintech"   --text-b "JWT-based authorization service for banking app"
```

Fuera del contenedor, ejecútalo desde la raíz del repo: `Settings` busca el `.env` en el directorio de trabajo.
