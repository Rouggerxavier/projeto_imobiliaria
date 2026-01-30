import uuid
from typing import List, Dict

import requests
import streamlit as st


st.set_page_config(page_title="Chat Imobiliário", page_icon="🏠", layout="centered")
st.title("Chat Imobiliário 🏠")
st.caption("Converse com o agente que está rodando em http://localhost:8000/webhook")

# Keep a stable session id per browser session.
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# Conversation history: list of {"role": "user" | "agent", "text": str}
if "history" not in st.session_state:
    st.session_state.history: List[Dict[str, str]] = []


def send_message(message: str, name: str | None = None) -> str:
    """Send a message to the FastAPI backend and return the agent reply."""
    payload = {
        "session_id": st.session_state.session_id,
        "message": message,
        "name": name,
    }
    try:
        resp = requests.post("http://localhost:8000/webhook", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        # Backend returns {"reply": "..."}; fall back to common keys.
        if isinstance(data, dict):
            return data.get("reply") or data.get("response") or data.get("message") or str(data)
        return str(data)
    except Exception as exc:
        return f"Erro ao contatar o backend: {exc}"


# Render chat history (newest last). Streamlit keeps input anchored at the bottom via chat_input.
for turn in st.session_state.history:
    with st.chat_message("user" if turn["role"] == "user" else "assistant"):
        st.markdown(turn["text"])

# Input stays fixed at the bottom of the viewport.
prompt = st.chat_input("Digite sua mensagem")
if prompt:
    st.session_state.history.append({"role": "user", "text": prompt})
    reply = send_message(prompt)
    st.session_state.history.append({"role": "agent", "text": reply})
    # Rerun to display the new messages immediately.
    st.rerun()

st.divider()
st.markdown(
    """
**Como rodar o frontend localmente**
1) Instale dependências: `pip install streamlit requests`
2) Inicie: `streamlit run frontend.py`
3) Abra o navegador no endereço mostrado pelo Streamlit (ex.: http://localhost:8501)
Certifique-se de que o backend FastAPI está rodando em http://localhost:8000.
"""
)
