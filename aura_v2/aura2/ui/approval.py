from __future__ import annotations

import streamlit as st


def render_approval(pending: dict) -> tuple[str, dict | None, str | None] | None:
    """Renders the pending-action card. Returns (decision_type, edited_args,
    message) once the user acts, or None while still waiting."""
    tool_name = pending["tool_name"]
    args = pending.get("args", {})
    st.warning(f"⚠️ Approval required: **{tool_name}**")

    edited_args: dict = {}
    changed = False

    if tool_name == "gmail_send":
        st.markdown("AURA wants to send this email:")
        to = st.text_input("To", value=args.get("to", ""), key="approval_to")
        subject = st.text_input("Subject", value=args.get("subject", ""), key="approval_subject")
        body = st.text_area("Body", value=args.get("body", ""), key="approval_body", height=180)
        edited_args = {"to": to, "subject": subject, "body": body}
        changed = edited_args != args
    elif tool_name in ("calendar_delete_event", "drive_delete_file"):
        st.markdown(f"AURA wants to **permanently delete**:")
        st.json(args)
    else:
        st.json(args)

    cols = st.columns(3)
    approve = cols[0].button("✅ Approve", use_container_width=True)
    edit = cols[1].button("✏️ Approve edits", use_container_width=True) if "edit" in pending.get("allowed_decisions", []) else False
    reject = cols[2].button("❌ Reject", use_container_width=True)

    if approve:
        return ("edit", edited_args, None) if changed else ("approve", None, None)
    if edit:
        return "edit", edited_args, None
    if reject:
        return "reject", None, "Rejected by user."
    return None
