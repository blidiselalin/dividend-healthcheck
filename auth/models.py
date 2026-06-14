"""Shared auth types (no Streamlit imports)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    name: Optional[str] = None
    picture_url: Optional[str] = None
    is_admin: bool = False


def sanitize_user_id(subject: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", (subject or "").strip())[:80]
    if safe:
        return safe
    return hashlib.sha256((subject or "user").encode()).hexdigest()[:24]
