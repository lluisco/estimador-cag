import streamlit as st
import time

from app.config import settings
from app.context.examples import ESTIMATION_EXAMPLES
from app.services.llm_service import build_system_prompt, generate_estimation, generate_estimation_stream, StreamMetadata

st.title("Estimador CAG")

if "messages" not in st.session_state:
    st.session_state["messages"] = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Pega aquí la transcripción de la reunión...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        metadata = StreamMetadata()
        start_time = time.time()
        try:
            full_response = st.write_stream(
                generate_estimation_stream(st.session_state.messages, metadata)
            )
        except Exception as e:
            st.error(f"Error al generar la estimación: {e}")
            st.stop()
        elapsed_time = time.time() - start_time

    st.session_state.messages.append({"role": "assistant", "content": full_response})
    st.session_state.last_call_metrics = {
        "model": settings.LLM_MODEL,
        "input_tokens": metadata.input_tokens,
        "output_tokens": metadata.output_tokens,
        "truncated": metadata.truncated,
        "elapsed_time": elapsed_time,
    }

with st.sidebar:
    st.header("Contexto CAG")

    with st.expander("System prompt activo"):
        st.text_area(
            "prompt enviado al modelo",
            value=build_system_prompt(),
            height=200,
            disabled=True,
        )

    with st.expander("Ejemplos inyectados (CAG)"):
        for i, example in enumerate(ESTIMATION_EXAMPLES, start=1):
            st.markdown(f"**Ejemplo {i}**")
            st.markdown("\n".join(f"- {line}" for line in example["meeting_summary"]))
            st.markdown(example["estimation"])
            st.divider()

    st.header("Última llamada al LLM")

    if "last_call_metrics" in st.session_state:
        metrics = st.session_state.last_call_metrics
        st.write(f"Modelo: {metrics['model']}")
        st.write(f"Tokens de entrada: {metrics['input_tokens']}")
        st.write(f"Tokens de salida: {metrics['output_tokens']}")
        st.write(f"Truncado: {metrics['truncated']}")
        st.write(f"Tiempo transcurrido: {metrics['elapsed_time']:.2f} segundos")
