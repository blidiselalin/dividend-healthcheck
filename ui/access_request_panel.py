"""
User-facing access request UI and admin approval controls.
"""

from __future__ import annotations

import logging

import streamlit as st

from auth.access_requests import AccessRequestStatus, AccessRequestStore
from auth.settings import invite_only_signup
from auth.user_context import google_identity
from ui.theme import render_notice, sidebar_heading

logger = logging.getLogger(__name__)


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
            "Access approved for your Google account. Click below to open your portfolio.",
            kind="success",
        )
        if st.button("Enter DividendScope", type="primary", use_container_width=True):
            st.rerun()
        return

    if record and record.status == AccessRequestStatus.PENDING:
        st.warning(
            "Your access request is waiting for admin approval. "
            "You will be able to sign in once the owner approves your Google account."
        )
        st.caption(f"Requested {record.requested_at.strftime('%Y-%m-%d %H:%M')} UTC")
        if st.button("Check again", use_container_width=True, key="access_check_again"):
            st.rerun()
    elif record and record.status == AccessRequestStatus.REJECTED:
        st.error(
            "Access for this Google account was declined. "
            "You may send a new request with a short note for the admin."
        )
        _render_request_form(identity, store, allow_resubmit=True)
    else:
        if invite_only_signup():
            st.error(
                "This Google account is not on the invite list yet. "
                "Request access below — the app owner reviews pending requests in the sidebar."
            )
        else:
            st.error("Your account is not allowed to use this app. Contact the owner for access.")
        _render_request_form(identity, store, allow_resubmit=False)

    st.divider()
    if st.button(
        "Use a different Google account", use_container_width=True, key="access_try_other_google"
    ):
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
        try:
            store.submit_request(
                email=identity.email,
                user_id=identity.id,
                name=identity.name,
                picture_url=identity.picture_url,
                message=note.strip() or None,
            )
        except Exception as exc:
            logger.exception("Failed to submit access request for %s", identity.email)
            st.error(f"Could not save your access request. Please try again. ({exc})")
            return
        st.session_state["access_request_just_sent"] = identity.email
        st.rerun()

    if st.session_state.get("access_request_just_sent") == identity.email:
        render_notice(
            "Request sent. When the owner signs in, they will see it under "
            "**Access requests** in the sidebar (and Account menu).",
            kind="success",
        )


def render_admin_access_requests(
    *,
    in_sidebar: bool = False,
    key_prefix: str = "options",
) -> None:
    """Admin block for pending Google access requests (Options menu or sidebar)."""
    try:
        store = AccessRequestStore()
        pending = store.list_pending()
    except Exception as exc:
        logger.exception("Failed to load access requests")
        target = st.sidebar if in_sidebar else st
        target.error(f"Could not load access requests: {exc}")
        return

    count = len(pending)
    panel = st.sidebar if in_sidebar else st

    if in_sidebar:
        sidebar_heading("Access requests")
    else:
        st.markdown("**Access requests**")

    if count == 0:
        panel.caption("No pending requests.")
        return

    panel.warning(f"{count} pending — approve or reject below")

    for item in pending:
        panel.markdown(f"**{item.email}**")
        if item.name:
            panel.caption(item.name)
        panel.caption(item.requested_at.strftime("%Y-%m-%d %H:%M UTC"))
        if item.message:
            panel.caption(f"“{item.message[:200]}”")

        approve_key = f"{key_prefix}_approve_access_{item.email}"
        reject_key = f"{key_prefix}_reject_access_{item.email}"
        col_a, col_b = panel.columns(2)
        admin_email = ""
        try:
            from auth.user_context import current_user

            user = current_user()
            admin_email = user.email if user else ""
        except ImportError as exc:
            logger.debug("Could not resolve admin email for access approval: %s", exc)
        with col_a:
            if st.button(
                "Approve", key=approve_key, use_container_width=True, type="primary"
            ) and store.approve(item.email, reviewer_email=admin_email):
                st.session_state.pop("access_request_just_sent", None)
                st.success(f"Approved {item.email}")
                st.rerun()
        with col_b:
            if st.button("Reject", key=reject_key, use_container_width=True) and store.reject(
                item.email, reviewer_email=admin_email
            ):
                st.warning(f"Rejected {item.email}")
                st.rerun()
        panel.divider()
