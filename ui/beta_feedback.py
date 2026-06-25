"""Lightweight beta feedback form for key pages."""

from __future__ import annotations

import streamlit as st

from services.beta_feedback import BetaFeedbackStore


def render_beta_feedback(*, page: str, key_suffix: str = "") -> None:
    """Collapsible feedback widget — rating, message, optional email."""
    suffix = f"_{key_suffix}" if key_suffix else ""
    with st.expander("Send beta feedback", expanded=False):
        st.caption(f"Page: **{page}**")
        rating = st.slider(
            "Rating",
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
        if user and getattr(user, "email", None):
            st.caption(f"Signed in as **{user.email}** — we will attach your account.")
        else:
            email = st.text_input(
                "Email (optional)",
                placeholder="you@example.com",
                key=f"beta_feedback_email{suffix}",
            )

        if st.button("Submit feedback", key=f"beta_feedback_submit{suffix}"):
            if not (message or "").strip():
                st.warning("Please enter a message.")
                return
            try:
                store = BetaFeedbackStore()
                store.submit(
                    rating=rating,
                    message=message.strip(),
                    page=page,
                    email=email if not user else user.email,
                    user_id=getattr(user, "id", None) if user else None,
                )
                st.success("Thank you — your feedback was saved.")
                st.session_state.pop(f"beta_feedback_message{suffix}", None)
            except Exception as exc:
                st.error(f"Could not save feedback: {exc}")
