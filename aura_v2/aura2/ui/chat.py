from __future__ import annotations

import hashlib
import json

import httpx
import streamlit as st

from ui import api_client
from ui.approval import render_approval

_LANGUAGES = {"English": "en", "Hindi": "hi", "Odia": "or"}


def render_chat(token: str, conversation_id: str) -> None:
    st.markdown("### AURA")

    with st.expander("📎 Upload a document (RAG)", expanded=False):
        uploaded = st.file_uploader("PDF, DOCX, or XLSX", type=["pdf", "docx", "xlsx"])
        if uploaded and st.button("Ingest document"):
            result = api_client.upload_document(token, uploaded.read(), uploaded.name, uploaded.type)
            status = result.get("status")
            if status == "processing":
                st.success(f"Uploading in the background (job {result['job_id']}) — it'll be searchable shortly.")
            elif status == "already_processed":
                st.info(result.get("message", "This file was already processed and is searchable."))
            else:
                st.warning(result.get("message", "Upload finished with an unexpected response."))

    language_label = st.selectbox("Voice language", list(_LANGUAGES.keys()), index=0)
    language = _LANGUAGES[language_label]

    for message in api_client.get_history(token, conversation_id):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # A pending approval from a prior turn takes priority over new input.
    if st.session_state.get("pending_approval"):
        decision = render_approval(st.session_state["pending_approval"])
        if decision is not None:
            decision_type, edited_args, reject_message = decision
            pending = st.session_state.pop("pending_approval")
            result = api_client.resume_decision(
                token, conversation_id, pending["tool_name"], decision_type, edited_args, reject_message,
            )
            if result.get("pending_approval"):
                st.session_state["pending_approval"] = result["pending_approval"]
            elif result.get("reply"):
                with st.chat_message("assistant"):
                    st.markdown(result["reply"])
            st.rerun()
        return

    # A pending camera request — show the widget, save on capture.
    if st.session_state.get("pending_camera"):
        label = st.session_state["pending_camera"]
        st.info(f"📷 {label}")
        photo = st.camera_input("Camera")
        if photo is not None:
            api_client.save_photo(token, photo.getvalue())
            st.session_state.pop("pending_camera")
            st.success("Photo saved.")
            st.rerun()
        return

    col_text, col_voice = st.columns([4, 1])
    with col_text:
        user_input = st.chat_input("Ask AURA...")
    with col_voice:
        audio = st.audio_input("🎙️", label_visibility="collapsed")

    if audio is not None:
        audio_bytes = audio.getvalue()
        audio_hash = hashlib.sha256(audio_bytes).hexdigest()
        if audio_hash != st.session_state.get("_last_audio_hash"):
            st.session_state["_last_audio_hash"] = audio_hash
            _handle_voice_turn(token, conversation_id, audio_bytes, language)
            return

    if user_input:
        with st.chat_message("user"):
            st.markdown(user_input)
        _handle_stream(token, conversation_id, user_input, language)


def _handle_stream(token: str, conversation_id: str, message: str, language: str) -> None:
    placeholder = st.chat_message("assistant").empty()
    buffer = ""
    try:
        for event, data in api_client.stream_chat(token, conversation_id, message, language):
            if event == "token":
                buffer += json.loads(data)["content"]
                placeholder.markdown(buffer)
            elif event in ("approval_required", "play_media", "request_camera", "error"):
                _handle_special_event(event, data)
    except httpx.HTTPError as exc:
        # Covers both HTTP-status errors and connection-level failures
        # (RemoteProtocolError/ConnectError etc. all inherit from HTTPError) —
        # e.g. the API process crashing or being restarted mid-stream.
        st.error("Lost connection to AURA mid-reply. Check that the API server "
                  f"is running, then try again. ({type(exc).__name__})")
    st.rerun()


def _handle_voice_turn(token: str, conversation_id: str, audio_bytes: bytes, language: str) -> None:
    with st.chat_message("assistant"):
        placeholder = st.empty()
        buffer = ""
        try:
            for event, data in api_client.voice_message(token, conversation_id, audio_bytes, language):
                if event == "transcript":
                    with st.chat_message("user"):
                        st.markdown(json.loads(data)["text"])
                elif event == "token":
                    buffer += json.loads(data)["content"]
                    placeholder.markdown(buffer)
                elif event == "audio_chunk":
                    st.audio(json.loads(data)["audio_path"], autoplay=True)
                elif event in ("approval_required", "play_media", "request_camera", "error"):
                    _handle_special_event(event, data)
        except httpx.HTTPError as exc:
            st.error("Lost connection to AURA mid-reply. Check that the API server "
                      f"is running, then try again. ({type(exc).__name__})")
    st.rerun()


def _handle_special_event(event: str, data: str) -> None:
    payload = json.loads(data)
    if event == "approval_required":
        st.session_state["pending_approval"] = payload
    elif event == "play_media":
        st.session_state["_now_playing"] = payload
    elif event == "request_camera":
        st.session_state["pending_camera"] = payload.get("label", "Take a photo")
    elif event == "error":
        st.error(payload.get("message", "Something went wrong."))


def render_now_playing() -> None:
    playing = st.session_state.get("_now_playing")
    if playing:
        st.markdown(f"**Now playing:** {playing['title']}")
        # autoplay=True: previously missing entirely — the tool
        # (tools/youtube.py) already built an embed_url with ?autoplay=1,
        # but this function was reconstructing a plain watch URL from
        # scratch instead of using it, so the flag never reached the
        # player and every video required a manual click.
        # Note: browsers still block autoplay WITH SOUND in some cases
        # unless the page already had user interaction — which is true
        # here (the user just sent a chat message), so this should work
        # in most browsers, but isn't 100% guaranteed everywhere.
        st.video(f"https://www.youtube.com/watch?v={playing['video_id']}", autoplay=True)
