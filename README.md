# Estimador CAG

Servicio que genera estimaciones de proyectos de software a partir de la
transcripción de una reunión con el cliente, usando un LLM (Anthropic Claude
u OpenAI) y arquitectura **CAG (Cache-Augmented Generation)**: las
estimaciones históricas de referencia se inyectan directamente en el prompt
del sistema (`app/context/examples.py`), sirviendo como ejemplos de criterio
y formato para el modelo.

Flujo del servicio:

```
transcripción → inyección de contexto (ejemplos previos) → llamada al LLM → estimación
```

## Estructura del proyecto

```
app/
├── main.py                    # App FastAPI y endpoint /health
├── config.py                  # Configuración (variables de entorno)
├── pricing.py                 # Cálculo de coste estimado por llamada
├── context/
│   └── examples.py            # Ejemplos históricos usados como contexto (CAG)
├── routers/
│   └── estimations.py         # Endpoint POST /api/v1/estimate
└── services/
    └── llm_service.py         # Construcción del prompt y llamada al LLM
docs/
└── transcripcion_ejemplo.md   # Transcripción de ejemplo para probar el servicio
tests/
├── test_structure.py          # Valida que la estructura de carpetas es correcta
└── test_api.py                # Valida el flujo completo (mockeando el LLM)
.github/workflows/ci.yml       # Pipeline que ejecuta los tests automáticamente
```

## Requisitos

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) como gestor de dependencias

## Configuración

1. Copia `.env.example` a `.env` y rellena las claves necesarias:

   ```bash
   cp .env.example .env
   ```

   Variables disponibles:

   | Variable            | Descripción                                      |
   |---------------------|---------------------------------------------------|
   | `LLM_PROVIDER`      | `anthropic` u `openai`                             |
   | `LLM_MODEL`         | Nombre del modelo a usar                           |
   | `ANTHROPIC_API_KEY` | API key de Anthropic (si `LLM_PROVIDER=anthropic`) |
   | `OPENAI_API_KEY`    | API key de OpenAI (si `LLM_PROVIDER=openai`)       |

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

Usa el texto de [`docs/transcripcion_ejemplo.md`](docs/transcripcion_ejemplo.md)
como referencia de entrada, o el tuyo propio:

```bash
curl -X POST http://localhost:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{"transcript": "El cliente necesita una plataforma web de reservas de aulas para una academia de idiomas con tres sedes..."}'
```

Respuesta de ejemplo:

```json
{
  "estimation": "## Estimación...",
  "model": "claude-haiku-4-5",
  "provider": "anthropic",
  "input_tokens": 512,
  "output_tokens": 340,
  "estimated_cost_usd": 0.002,
  "truncated": false
}
```

## Validación y pipeline automático

La estructura de carpetas y el funcionamiento del servicio se validan con una
suite de tests (`pytest`), que se ejecuta automáticamente en cada push/PR
mediante GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

- `tests/test_structure.py`: comprueba que existen los ficheros y carpetas
  esperados y que los módulos de la app son importables.
- `tests/test_api.py`: levanta la app con `TestClient` y valida el flujo
  completo del endpoint `/api/v1/estimate` (mockeando la llamada al LLM para
  no depender de credenciales reales en CI).

Para ejecutar los tests en local:

```bash
uv sync --all-groups
uv run pytest -v
```
