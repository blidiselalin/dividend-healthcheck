"""
Read authentication settings from Streamlit secrets and environment variables.
"""

from __future__ import annotations

import os
from typing import FrozenSet, List, Optional

_AUTH_SECTION = "auth"


def _auth_section() -> dict:
    try:
        import streamlit as st

        raw = st.secrets.get(_AUTH_SECTION, {})
        return dict(raw) if raw else {}
    except Exception:
        return {}


def auth_disabled() -> bool:
    flag = os.environ.get("DIVIDENDSCOPE_AUTH_DISABLE", "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    section = _auth_section()
    return bool(section.get("disable"))


def _valid_oauth_value(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    upper = text.upper()
    if upper.startswith("YOUR_") or upper.startswith("REPLACE_"):
        return False
    if "xxxx" in text.lower() or text == "YOUR_CLIENT_SECRET":
        return False
    return True


def auth_configured() -> bool:
    """True when Google OIDC client credentials are available."""
    if auth_disabled():
        return False
    section = _auth_section()
    if _valid_oauth_value(section.get("client_id")) and _valid_oauth_value(
        section.get("client_secret")
    ):
        return True
    if _valid_oauth_value(os.environ.get("GOOGLE_OAUTH_CLIENT_ID")) and _valid_oauth_value(
        os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    ):
        return True
    return False


def auth_required() -> bool:
    """App should show the login screen before any portfolio data."""
    if auth_disabled():
        return False
    section = _auth_section()
    if section.get("require_login") is False:
        return False
    return auth_configured()


def dev_bypass_email() -> Optional[str]:
    """Local-only sign-in without Google (secrets auth.dev_email)."""
    if auth_configured() and not auth_disabled():
        return None
    section = _auth_section()
    email = (section.get("dev_email") or os.environ.get("DIVIDENDSCOPE_DEV_EMAIL") or "").strip()
    return email or None


def cookie_secret() -> str:
    section = _auth_section()
    return str(
        section.get("cookie_secret")
        or os.environ.get("DIVIDENDSCOPE_AUTH_COOKIE_SECRET")
        or "change-me-in-streamlit-secrets"
    )


def redirect_uri() -> str:
    section = _auth_section()
    return str(
        section.get("redirect_uri")
        or os.environ.get("DIVIDENDSCOPE_AUTH_REDIRECT_URI")
        or "http://localhost:8501/oauth2callback"
    )


def _split_emails(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = str(value).replace(";", ",").split(",")
    return [item.strip().lower() for item in items if str(item).strip()]


def allowed_emails() -> FrozenSet[str]:
    section = _auth_section()
    raw = section.get("allowed_emails") or os.environ.get("DIVIDENDSCOPE_ALLOWED_EMAILS")
    return frozenset(_split_emails(raw))


def admin_emails() -> FrozenSet[str]:
    section = _auth_section()
    raw = section.get("admin_emails") or os.environ.get("DIVIDENDSCOPE_ADMIN_EMAILS")
    return frozenset(_split_emails(raw))


def is_email_allowed(email: str) -> bool:
    """Static allowlist (secrets) plus admin-approved access requests."""
    normalized = email.strip().lower()
    if not normalized:
        return False

    try:
        from auth.access_requests import AccessRequestStore

        if AccessRequestStore().is_approved(normalized):
            return True
    except Exception:
        pass

    allow = allowed_emails()
    if not allow:
        return True
    return normalized in allow


def invite_only_signup() -> bool:
    """When true, only emails in allowed_emails may register (invite list)."""
    return bool(allowed_emails())


def google_signup_enabled() -> bool:
    """Allow new accounts via Google OAuth (first successful login creates the user)."""
    if auth_disabled() or not auth_configured():
        return False
    section = _auth_section()
    if section.get("allow_signup") is False:
        return False
    return True


def is_admin_email(email: str) -> bool:
    return email.strip().lower() in admin_emails()
