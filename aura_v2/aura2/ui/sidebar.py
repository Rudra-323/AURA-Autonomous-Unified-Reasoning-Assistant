from __future__ import annotations

import streamlit as st

from ui import api_client


def render_sidebar(token: str) -> str:
    with st.sidebar:
        st.markdown("## AURA")
        st.caption(st.session_state.get("user_email", ""))

        if st.button("＋ New Chat", use_container_width=True):
            conv = api_client.create_conversation(token)
            st.session_state["active_conversation_id"] = conv["conversation_id"]
            st.rerun()

        if st.button("Log out", use_container_width=True):
            st.session_state.clear()
            st.rerun()

        st.divider()

        conversations = api_client.list_conversations(token)
        if "active_conversation_id" not in st.session_state:
            if conversations:
                st.session_state["active_conversation_id"] = conversations[0]["conversation_id"]
            else:
                conv = api_client.create_conversation(token)
                st.session_state["active_conversation_id"] = conv["conversation_id"]
                conversations = api_client.list_conversations(token)

        active_id = st.session_state["active_conversation_id"]
        for conv in conversations:
            is_active = conv["conversation_id"] == active_id
            label = f"{'▸ ' if is_active else ''}{conv['title']}"
            if st.button(label, key=f"conv_{conv['conversation_id']}", use_container_width=True):
                st.session_state["active_conversation_id"] = conv["conversation_id"]
                st.rerun()

    return st.session_state["active_conversation_id"]
