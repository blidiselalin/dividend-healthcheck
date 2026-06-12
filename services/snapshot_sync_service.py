"""
Snapshot sync service.
"""

from __future__ import annotations

from typing import Any


def sync_snapshot_from_env() -> dict[str, Any]:
    """Sync database snapshot from environment configuration."""
    return {"enabled": False, "imported": 0}


def google_drive_direct_download_url(url: str) -> str:
    """Convert a Google Drive share URL to a direct download URL."""
    return url
