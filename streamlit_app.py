import httpx
import streamlit as st

from app.schemas import OUT_OF_SCOPE_PREFIX, DetailLevel, OutputFormat, ProjectType
from app.services.tier import Tier

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

# None = "Automático": no se envía el campo y el servidor resuelve el tier por reglas
TIER_LABELS = {
    None: "Automático",
    Tier.EXECUTIVE: "Dirección (executive)",
    Tier.PM: "Responsable de proyecto (pm)",
    Tier.DEVELOPER: "Equipo técnico (developer)",
    Tier.DEFAULT: "Neutro (default)",
}

VERDICT_LABELS = {
    "accept": "✅ accept",
    "needs_iteration": "🔁 needs_iteration",
    "reject": "⛔ reject",
}

# session-05 -- Funciones para interactuar con la API de sesiones

def create_session() -> str:
    response = httpx.post(f"{API_BASE_URL}/sessions", timeout=10.0)
    response.raise_for_status()
    return response.json()["session_id"]

def reset_conversation() -> None:
    st.session_state.session_id = create_session()
    st.session_state.last_estimation = None
    st.session_state.session_state_info = None
    st.session_state.last_acb_trace = None
    st.session_state.pop("last_call_metrics", None)

def request_session_estimation(
    session_id, transcript, project_type, detail_level, output_format, files,
    *, tier: Tier | None = None, use_acb: bool = False,
) -> dict:
    data = {
        "transcript": transcript,
        "project_type": project_type.value,
        "detail_level": detail_level.value,
        "output_format": output_format.value,
    }
    if tier is not None:
        data["tier"] = tier.value
    endpoint = "estimate-acb" if use_acb else "estimate"
    response = httpx.post(
        f"{API_BASE_URL}/sessions/{session_id}/{endpoint}",
        data=data,
        files=[("attachments", (f.name, f.getvalue(), f.type)) for f in files],
        # ACB puede encadenar hasta 3 vueltas actor+critic: más margen que el flujo normal
        timeout=300.0 if use_acb else 120.0,
    )
    response.raise_for_status()
    return response.json()

def fetch_session_info(session_id: str) -> dict:
    response = httpx.get(f"{API_BASE_URL}/sessions/{session_id}", timeout=10.0)
    response.raise_for_status()
    return response.json()

## end session-05


def render_out_of_scope(estimation: dict) -> None:
    """Una negativa no es un presupuesto: sin métricas ni fases de relleno (1 semana, 1 €)."""
    reason = estimation["summary"].removeprefix(OUT_OF_SCOPE_PREFIX).strip()
    st.warning(f"**No se ha podido estimar el proyecto.** {reason}")
    st.caption(
        "Añade más detalle en el siguiente mensaje (procesos concretos, usuarios, "
        "integraciones) o pide una estimación parcial, por ejemplo de la fase de definición."
    )


def render_estimation(estimation: dict) -> None:
    if estimation["summary"].startswith(OUT_OF_SCOPE_PREFIX):
        render_out_of_scope(estimation)
        return

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
    tier = st.selectbox(
        "Audiencia (tier)",
        options=list(TIER_LABELS),
        format_func=lambda t: TIER_LABELS[t],
        help="Automático: el servidor decide por reglas (NDA o regulación → executive, "
        "lenguaje técnico → developer, equipo pequeño → pm).",
    )
    use_acb = st.toggle(
        "Revisión independiente (ACB)",
        help="Un Critic audita la estimación y el Boss decide si iterar. "
        "Hasta 8 llamadas al LLM por turno frente a 2-3: más lento y más caro.",
    )
    submitted = st.form_submit_button("Generar estimación")

if submitted:
    try:
        result = request_session_estimation(
            st.session_state.session_id, description, project_type, detail_level, output_format,
            attachments, tier=tier, use_acb=use_acb,
        )
        st.session_state.session_state_info = fetch_session_info(st.session_state.session_id)
    except httpx.ConnectError:
        st.error("No se puede conectar con la API. ¿Está arrancado `uvicorn`?")
        st.stop()
    except httpx.HTTPStatusError as e:
        st.error(f"Error al generar la estimación: {e.response.text}")
        st.stop()

    st.session_state.last_estimation = result["result"]
    st.session_state.last_acb_trace = result.get("acb")    # None en el flujo normal
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
        if info.get("last_resolved_tier"):
            st.write(f"Tier: **{info['last_resolved_tier']}** ({info['last_tier_rule']})")
        st.write(f"Anclas: {info.get('anchors', 0)}")
        st.write(f"Resumen acumulativo: {info.get('summary_chars', 0)} caracteres")
        with st.expander("Memoria del proyecto (project_metadata)", expanded=True):
            st.json(info["project_metadata"])

    trace = st.session_state.get("last_acb_trace")
    if trace:
        with st.expander(f"Traza ACB: {trace['outcome']} en {len(trace['iterations'])} vuelta(s)"):
            for it in trace["iterations"]:
                st.markdown(
                    f"**Vuelta {it['iteration']}**: {VERDICT_LABELS.get(it['verdict'], it['verdict'])} "
                    f"(confianza de la revisión: {it['confidence_in_review']})"
                )
                if it["confidence_in_review"] == 0:
                    st.caption("El Critic no pudo revisar esta vuelta.")
                for issue in it["issues"][:3]:
                    st.markdown(
                        f"- `{issue['severity']}` {issue['category']} en "
                        f"`{issue['field_path']}`: {issue['description']}"
                    )

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
