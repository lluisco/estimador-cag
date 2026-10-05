import httpx
import streamlit as st

from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType

API_BASE_URL = "http://localhost:8000/api/v1"

PROJECT_TYPE_LABELS = {
    ProjectType.MOBILE_APP: "Aplicación móvil",
    ProjectType.WEB_SAAS: "Web / SaaS",
    ProjectType.INTERNAL_TOOL: "Herramienta interna",
    ProjectType.DATA_PIPELINE: "Pipeline de datos",
}

DETAIL_LEVEL_LABELS = {
    DetailLevel.SUMMARY: "Resumen",
    DetailLevel.MEDIUM: "Medio",
    DetailLevel.DETAILED: "Detallado",
}

OUTPUT_FORMAT_LABELS = {
    OutputFormat.PHASES_TABLE: "Tabla de fases",
    OutputFormat.LINE_ITEMS: "Partidas (line items)",
    OutputFormat.NARRATIVE: "Narrativo",
}

try:
    context = httpx.get(f"{API_BASE_URL}/context", timeout=10.0).json()
except httpx.ConnectError:
    st.sidebar.error("No se puede conectar con la API. ¿Está arrancado `uvicorn`?")
    context = None


def request_estimation(request: EstimationRequest) -> dict:
    response = httpx.post(
        f"{API_BASE_URL}/estimate", json=request.model_dump(mode="json"), timeout=120.0
    )
    response.raise_for_status()
    return response.json()

# session-05 -- Funciones para interactuar con la API de sesiones

def create_session() -> str:
    response = httpx.post(f"{API_BASE_URL}/sessions", timeout=10.0)
    response.raise_for_status()
    return response.json()["session_id"]

def reset_conversation() -> None:
    st.session_state.session_id = create_session()
    st.session_state.last_estimation = None
    st.session_state.session_state_info = None
    st.session_state.pop("last_call_metrics", None)

def request_session_estimation(session_id, transcript, project_type, detail_level, output_format, files) -> dict:
    response = httpx.post(
        f"{API_BASE_URL}/sessions/{session_id}/estimate",
        data={
            "transcript": transcript,
            "project_type": project_type.value,
            "detail_level": detail_level.value,
            "output_format": output_format.value,
        },
        files=[("attachments", (f.name, f.getvalue(), f.type)) for f in files],
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()

def fetch_session_info(session_id: str) -> dict:
    response = httpx.get(f"{API_BASE_URL}/sessions/{session_id}", timeout=10.0)
    response.raise_for_status()
    return response.json()

## end session-05


def render_estimation(estimation: dict) -> None:
    st.subheader("Resumen ejecutivo")
    st.write(estimation["summary"])

    col_weeks, col_cost, col_confidence = st.columns(3)
    col_weeks.metric("Duración total", f"{estimation['total_duration_weeks']} semanas")
    col_cost.metric("Coste total", f"{estimation['total_cost_eur']:,} €".replace(",", "."))
    col_confidence.metric("Confianza", f"{estimation['confidence_pct']} %")

    st.subheader("Fases")
    st.dataframe(
        [
            {
                "Fase": phase["name"],
                "Semanas": phase["duration_weeks"],
                "Coste (€)": phase["cost_eur"],
                "Confianza (%)": phase["confidence_pct"],
            }
            for phase in estimation["phases"]
        ],
        hide_index=True,
        use_container_width=True,
    )

    for phase in estimation["phases"]:
        if phase["assumptions"]:
            with st.expander(f"Supuestos: {phase['name']}"):
                for assumption in phase["assumptions"]:
                    st.markdown(f"- {assumption}")


st.title("Estimador CAG")

if "session_id" not in st.session_state:
    try:
        reset_conversation()
    except httpx.ConnectError:
        st.error("No se puede conectar con la API. ¿Está arrancado `uvicorn`?")
        st.stop()

with st.form("estimation_form"):
    description = st.text_area(
        "Descripción del proyecto",
        placeholder="Resume la reunión con el cliente: qué necesita, alcance, restricciones...",
        height=200,
    )
    attachments = st.file_uploader(
        "Adjuntar archivos (pdf o word)",
        accept_multiple_files=True,
        type=["pdf", "docx"],
    )
    project_type = st.selectbox(
        "Tipo de proyecto",
        options=list(ProjectType),
        format_func=lambda pt: PROJECT_TYPE_LABELS[pt],
    )
    detail_level = st.selectbox(
        "Nivel de detalle",
        options=list(DetailLevel),
        format_func=lambda dl: DETAIL_LEVEL_LABELS[dl],
    )
    output_format = st.selectbox(
        "Formato de salida",
        options=list(OutputFormat),
        format_func=lambda of: OUTPUT_FORMAT_LABELS[of],
    )
    submitted = st.form_submit_button("Generar estimación")

# if submitted:
#     try:
#         request = EstimationRequest(
#             description=description,
#             project_type=project_type,
#             detail_level=detail_level,
#             output_format=output_format,
#         )
#     except ValueError as e:
#         st.error(f"Datos del formulario inválidos: {e}")
#         st.stop()

#     try:
#         result = request_estimation(request)
#     except httpx.ConnectError:
#         st.error("No se puede conectar con la API. ¿Está arrancado `uvicorn`?")
#         st.stop()
#     except httpx.HTTPStatusError as e:
#         st.error(f"Error al generar la estimación: {e.response.text}")
#         st.stop()

#     render_estimation(result["result"])
#     st.session_state.last_call_metrics = {
#         "model": result.get("model", "desconocido"),
#         "input_tokens": result.get("input_tokens", 0),
#         "output_tokens": result.get("output_tokens", 0),
#         "truncated": result.get("truncated", False),
#         "cache_hit": result.get("cache_hit", False),
#         "prompt_version": result.get("prompt_version", "unknown"),
#         "system_prompt": result.get("system_prompt", ""),
#     }

if submitted:
    try:
        result = request_session_estimation(
            st.session_state.session_id, description, project_type, detail_level, output_format, attachments
        )
        st.session_state.session_state_info = fetch_session_info(st.session_state.session_id)
    except httpx.ConnectError:
        st.error("No se puede conectar con la API. ¿Está arrancado `uvicorn`?")
        st.stop()
    except httpx.HTTPStatusError as e:
        st.error(f"Error al generar la estimación: {e.response.text}")
        st.stop()

    st.session_state.last_estimation = result["result"]
    st.session_state.last_call_metrics = {
        "model": result.get("model", "desconocido"),
        "input_tokens": result.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
        "truncated": result.get("truncated", False),
        "cache_hit": result.get("cache_hit", False),
        "prompt_version": result.get("prompt_version", "unknown"),
        "system_prompt": result.get("system_prompt", ""),
    }

    if st.session_state.get("last_estimation"):
        render_estimation(st.session_state.last_estimation)

with st.sidebar:
    st.header("Conversación")
    st.caption(f"Sesión: {st.session_state.session_id}")
    st.button("Nueva conversación", on_click=reset_conversation)

    info = st.session_state.get("session_state_info")
    if info:
        st.write(f"Turnos en el historial: {info['turns']}")
        with st.expander("Memoria del proyecto (project_metadata)", expanded=True):
            st.json(info["project_metadata"])

    st.header("Contexto CAG")

    if "last_call_metrics" in st.session_state:
        with st.expander("System prompt del último envío"):
            st.text_area(
                "Prompt enviado al modelo",
                value=st.session_state.last_call_metrics.get("system_prompt", ""),
                height=200,
                disabled=True,
            )

    st.header("Última llamada al LLM")

    if "last_call_metrics" in st.session_state:
        metrics = st.session_state.last_call_metrics
        st.write(f"Modelo: {metrics['model']}")
        st.write(f"Tokens de entrada: {metrics['input_tokens']}")
        st.write(f"Tokens de salida: {metrics['output_tokens']}")
        st.write(f"Truncado: {metrics['truncated']}")
        st.write(f"Servido desde cache: {metrics['cache_hit']}")
        st.write(f"Versión del prompt: {metrics['prompt_version']}")
