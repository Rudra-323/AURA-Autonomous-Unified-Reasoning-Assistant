from __future__ import annotations

import httpx
import streamlit as st

from ui import api_client


def render_auth() -> None:
    st.markdown("## AURA")
    st.caption("Sign in to continue.")

    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Log in", use_container_width=True):
            try:
                result = api_client.login(email, password)
            except httpx.HTTPStatusError as exc:
                st.error(exc.response.json().get("detail", "Login failed."))
            else:
                st.session_state["token"] = result["access_token"]
                st.session_state["user_email"] = email
                st.rerun()

    with tab_signup:
        email_s = st.text_input("Email", key="signup_email")
        name_s = st.text_input("Display name (optional)", key="signup_name")
        password_s = st.text_input("Password", type="password", key="signup_password")
        if st.button("Create account", use_container_width=True):
            try:
                api_client.signup(email_s, password_s, name_s)
            except httpx.HTTPStatusError as exc:
                st.error(exc.response.json().get("detail", "Sign-up failed."))
            else:
                st.success("Account created — log in on the other tab.")
