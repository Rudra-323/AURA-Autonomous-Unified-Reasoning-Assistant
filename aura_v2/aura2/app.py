"""
AURA v2 — Streamlit entry point. Unlike v1, this file (and everything in
ui/) never imports core/services/tools directly — it only talks to the
FastAPI backend over HTTP/SSE via ui/api_client.py. Run the API separately:

    uvicorn api.main:app --reload

then this UI:

    streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from ui.auth_page import render_auth
from ui.chat import render_chat, render_now_playing
from ui.sidebar import render_sidebar

st.set_page_config(page_title="AURA", page_icon="🤖", layout="centered")


def main() -> None:
    token = st.session_state.get("token")
    if not token:
        render_auth()
        return

    conversation_id = render_sidebar(token)
    render_now_playing()
    render_chat(token, conversation_id)


if __name__ == "__main__":
    main()
