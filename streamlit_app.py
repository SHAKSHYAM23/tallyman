"""Tallyman: Streamlit chat UI.

Streamlit Cloud runs a single process, so this entrypoint starts the FastAPI
backend in a background thread (once per server process) and then talks to it
over localhost HTTP. The agent launches the MCP server as a stdio subprocess.

API contract this file relies on:
    GET  /health -> 200
    POST /chat   {"session_id": str, "message": str}
              -> {"reply": str,
                  "status": "awaiting_input" | "done" | "gave_up",
                  "tool_results": {tool_name: {...}}}
"""

import os
import threading
import time
import uuid

import httpx
import streamlit as st

APP_NAME = "Tallyman"  
API_PORT = int(os.getenv("API_PORT", "8000"))
API_URL = f"http://127.0.0.1:{API_PORT}"

EXAMPLES = [
    "I earn 12 LPA. Can I afford a 40 lakh home loan?",
    "Old vs new tax regime for 18 LPA with 1.5 lakh in deductions?",
    "I have 10,000 extra per month. Should I prepay my loan or invest?",
]

st.set_page_config(page_title=APP_NAME, page_icon="₹", layout="centered")


def _load_secrets_into_env() -> None:
    """On Streamlit Cloud, keys live in st.secrets; locally they come from .env."""
    try:
        for key in ("GROQ_API_KEY", "GROQ_MODEL"):
            if key in st.secrets:
                os.environ.setdefault(key, str(st.secrets[key]))
    except Exception:
     
        pass


@st.cache_resource(show_spinner="Starting backend...")
def start_backend() -> bool:
    """Start FastAPI once per server process (cache_resource survives reruns)."""
    _load_secrets_into_env()

    import uvicorn

    from app.api.main import app as fastapi_app

    config = uvicorn.Config(
        fastapi_app, host="127.0.0.1", port=API_PORT, log_level="warning"
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if httpx.get(f"{API_URL}/health", timeout=1).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    raise RuntimeError("Backend did not start within 30 seconds")


def call_api(session_id: str, message: str) -> dict:
    response = httpx.post(
        f"{API_URL}/chat",
        json={"session_id": session_id, "message": message},
        timeout=90,  
    )
    response.raise_for_status()
    return response.json()


def render_tool_results(tool_results: dict) -> None:
    if not tool_results:
        return
    with st.expander("Calculations used"):
        for tool_name, output in tool_results.items():
            st.markdown(f"**{tool_name}**")
            st.json(output)


def reset_chat() -> None:
    st.session_state.session_id = uuid.uuid4().hex
    st.session_state.messages = []



start_backend()

if "session_id" not in st.session_state:
    reset_chat()


with st.sidebar:
    st.header(APP_NAME)
    st.caption(
        "Describe a money decision in plain words. The assistant asks for "
        "anything missing, and all numbers come from calculator tools, "
        "not from the language model."
    )
    if st.button("New chat", use_container_width=True):
        reset_chat()
        st.rerun()
    st.divider()
    st.caption("Try an example")
    for i, example in enumerate(EXAMPLES):
        if st.button(example, key=f"example_{i}", use_container_width=True):
            st.session_state.queued = example


st.title(f"{APP_NAME}: money decision copilot")
st.caption("Educational estimates only, not financial advice.")

if not st.session_state.messages:
    st.info("Ask something like: 'Can I afford a 40 lakh loan if I earn 1 lakh a month?'")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        render_tool_results(msg.get("tool_results", {}))

prompt = st.chat_input("Describe a money decision...") or st.session_state.pop(
    "queued", None
)

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Working on it..."):
                data = call_api(st.session_state.session_id, prompt)
        except httpx.HTTPError as exc:
            st.error(f"Could not reach the backend: {exc}")
            st.stop()

        st.markdown(data["reply"])
        render_tool_results(data.get("tool_results", {}))

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": data["reply"],
            "tool_results": data.get("tool_results", {}),
        }
    )