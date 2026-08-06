"""Lightweight beta feedback form for key pages."""

from __future__ import annotations

import streamlit as st

from services.beta_feedback import BetaFeedbackStore
from ui.design_system import render_section_header


def render_beta_feedback(*, page: str, key_suffix: str = "") -> None:
    """Collapsible feedback widget — rating, message, optional email."""
    suffix = f"_{key_suffix}" if key_suffix else ""
    with st.expander("Send beta feedback", expanded=False):
        render_section_header("Share feedback", f"Help us improve · viewing **{page}**")
        rating = st.slider(
            "Rating (1–5)",
            min_value=1,
            max_value=5,
            value=4,
            key=f"beta_feedback_rating{suffix}",
        )
        message = st.text_area(
            "Message",
            placeholder="What worked? What was confusing?",
            key=f"beta_feedback_message{suffix}",
            height=100,
        )

        user = None
        try:
            from auth.user_context import current_user

            user = current_user()
        except Exception:
            user = None

        email = None
        demo_user = False
        if user is not None:
            try:
                from auth.test_user import is_test_user, test_user_session_active

                demo_user = bool(test_user_session_active() and is_test_user(user))
            except Exception:
                demo_user = False

        if user and getattr(user, "email", None) and not demo_user:
            st.caption("Signed in — feedback will be linked to your account (not shown here).")
        elif not user:
            email = st.text_input(
                "Contact (optional)",
                placeholder="Leave blank to stay anonymous",
                key=f"beta_feedback_email{suffix}",
            )

        if st.button("Submit feedback", key=f"beta_feedback_submit{suffix}", type="primary"):
            if not (message or "").strip():
                st.warning("Please enter a message.")
                return
            try:
                store = BetaFeedbackStore()
                store.submit(
                    rating=rating,
                    message=message.strip(),
                    page=page,
                    email=None if demo_user else (email if not user else user.email),
                    user_id=None if demo_user else (getattr(user, "id", None) if user else None),
                )
                st.success("Thank you — your feedback was saved.")
                st.session_state.pop(f"beta_feedback_message{suffix}", None)
            except Exception as exc:
                st.error(f"Could not save feedback: {exc}")
