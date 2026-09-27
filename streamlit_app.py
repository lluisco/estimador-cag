import json
import time

import httpx
import streamlit as st

API_BASE_URL = "http://localhost:8000/api/v1"

try:
    context = httpx.get(f"{API_BASE_URL}/context", timeout=10.0).json()
except httpx.ConnectError:
    st.sidebar.error("No se puede conectar con la API. ¿Está arrancado `uvicorn`?")
    context = None


def stream_estimation(messages: list[dict], metrics_holder: dict):
    payload = {"messages": messages}
    with httpx.stream(
        "POST", f"{API_BASE_URL}/estimate/stream", json=payload, timeout=120.0
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            event = json.loads(line)
            if event["type"] == "delta":
                yield event["text"]
            elif event["type"] == "metadata":
                metrics_holder.update(event)
            elif event["type"] == "error":
                raise RuntimeError(event["detail"])


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
        metrics_holder = {}
        start_time = time.time()
        try:
            full_response = st.write_stream(
                stream_estimation(st.session_state.messages, metrics_holder)
            )
        except httpx.ConnectError:
            st.error("No se puede conectar con la API. ¿Está arrancado `uvicorn`?")
            st.stop()
        except Exception as e:
            st.error(f"Error al generar la estimación: {e}")
            st.stop()
        elapsed_time = time.time() - start_time

    st.session_state.messages.append({"role": "assistant", "content": full_response})
    st.session_state.last_call_metrics = {
        "model": metrics_holder.get("model", "desconocido"),
        "input_tokens": metrics_holder.get("input_tokens", 0),
        "output_tokens": metrics_holder.get("output_tokens", 0),
        "truncated": metrics_holder.get("truncated", False),
        "cache_hit": metrics_holder.get("cache_hit", False),
        "elapsed_time": elapsed_time,
    }

with st.sidebar:
    st.header("Contexto CAG")

    if context:
        with st.expander("System prompt activo"):
            st.text_area(
                "Prompt enviado al modelo",
                value=context["system_prompt"],
                height=200,
                disabled=True,
            )

        with st.expander("Ejemplos inyectados (CAG)"):
            for i, example in enumerate(context["examples"], start=1):
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
        st.write(f"Servido desde cache: {metrics['cache_hit']}")
        st.write(f"Tiempo transcurrido: {metrics['elapsed_time']:.2f} segundos")
