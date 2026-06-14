"""Tests for snapshot sync service placeholders."""
# ruff: noqa: S101

from __future__ import annotations

from services.snapshot_sync_service import (
    google_drive_direct_download_url,
    sync_snapshot_from_env,
)


def test_sync_snapshot_from_env_returns_disabled_default() -> None:
    result = sync_snapshot_from_env()
    assert result == {"enabled": False, "imported": 0}


def test_google_drive_direct_download_url_passthrough() -> None:
    url = "https://drive.google.com/file/d/abc/view?usp=sharing"
    assert google_drive_direct_download_url(url) == url
