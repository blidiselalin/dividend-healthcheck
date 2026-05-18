"""
User-facing access request UI and admin approval controls.
"""

from __future__ import annotations

import streamlit as st

from auth.access_requests import AccessRequestStatus, AccessRequestStore
from auth.settings import invite_only_signup
from auth.user_context import google_identity
from ui.theme import render_notice, sidebar_heading


def render_access_denied_panel() -> None:
    """Shown when Google login succeeded but the email is not allowed yet."""
    identity = google_identity()
    if identity is None:
        st.error("Your account is not allowed to use this app. Contact the owner for access.")
        return

    store = AccessRequestStore()
    record = store.get_by_email(identity.email)

    if record and record.status == AccessRequestStatus.APPROVED:
        render_notice(
            f"Access approved for **{identity.email}**. Click below to open your portfolio.",
            kind="success",
        )
        if st.button("Enter DividendScope", type="primary", use_container_width=True):
            st.rerun()
        return

    if record and record.status == AccessRequestStatus.PENDING:
        st.warning(
            f"Your access request for **{identity.email}** is waiting for admin approval. "
            "You will be able to sign in once the owner approves your Google account."
        )
        st.caption(f"Requested {record.requested_at.strftime('%Y-%m-%d %H:%M')} UTC")
        if st.button("Check again", use_container_width=True, key="access_check_again"):
            st.rerun()
    elif record and record.status == AccessRequestStatus.REJECTED:
        st.error(
            f"Access for **{identity.email}** was declined. "
            "You may send a new request with a short note for the admin."
        )
        _render_request_form(identity, store, allow_resubmit=True)
    else:
        if invite_only_signup():
            st.error(
                "This Google account is not on the invite list yet. "
                "Request access below — the app owner will be notified in the admin panel."
            )
        else:
            st.error("Your account is not allowed to use this app. Contact the owner for access.")
        _render_request_form(identity, store, allow_resubmit=False)

    st.divider()
    if st.button("Use a different Google account", use_container_width=True, key="access_try_other_google"):
        st.logout()


def _render_request_form(identity, store: AccessRequestStore, *, allow_resubmit: bool) -> None:
    default_msg = ""
    if allow_resubmit:
        default_msg = "I would like access to track my dividend portfolio."

    note = st.text_area(
        "Message to admin (optional)",
        value=default_msg,
        placeholder="e.g. I'm investing for long-term dividend income.",
        key="access_request_message",
    )
    label = "Send new request" if allow_resubmit else "Request access from admin"
    if st.button(label, type="primary", use_container_width=True, key="access_submit_request"):
        store.submit_request(
            email=identity.email,
            user_id=identity.id,
            name=identity.name,
            picture_url=identity.picture_url,
            message=note.strip() or None,
        )
        st.session_state["access_request_just_sent"] = identity.email
        st.rerun()

    if st.session_state.get("access_request_just_sent") == identity.email:
        render_notice(
            "Request sent. The admin will see it in the **Access requests** panel and can approve your Google email.",
            kind="success",
        )


def render_admin_access_requests() -> None:
    """Sidebar block for admins — pending Google access requests."""
    store = AccessRequestStore()
    pending = store.list_pending()
    count = len(pending)

    sidebar_heading("Access requests")
    if count == 0:
        st.sidebar.caption("No pending requests.")
        return

    st.sidebar.warning(f"{count} pending — new user(s) waiting for approval")

    for item in pending:
        st.sidebar.markdown(f"**{item.email}**")
        if item.name:
            st.sidebar.caption(item.name)
        st.sidebar.caption(item.requested_at.strftime("%Y-%m-%d %H:%M UTC"))
        if item.message:
            st.sidebar.caption(f"“{item.message[:200]}”")

        approve_key = f"approve_access_{item.email}"
        reject_key = f"reject_access_{item.email}"
        col_a, col_b = st.sidebar.columns(2)
        admin_email = ""
        try:
            from auth.user_context import current_user

            user = current_user()
            admin_email = user.email if user else ""
        except Exception:
            pass

        with col_a:
            if st.button("Approve", key=approve_key, use_container_width=True, type="primary"):
                if store.approve(item.email, reviewer_email=admin_email):
                    st.session_state.pop("access_request_just_sent", None)
                    st.success(f"Approved {item.email}")
                    st.rerun()
        with col_b:
            if st.button("Reject", key=reject_key, use_container_width=True):
                if store.reject(item.email, reviewer_email=admin_email):
                    st.warning(f"Rejected {item.email}")
                    st.rerun()
        st.sidebar.divider()
