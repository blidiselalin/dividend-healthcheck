"""
Move legacy single-user portfolio files into the first Google account's folder.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from config import DATA_DIR
from utils.logging_config import get_logger
from utils.portfolio_db import holding_count as _holding_count_fn

logger = get_logger("dividendscope.migration")

LEGACY_PORTFOLIO_DB = DATA_DIR / "portfolio.db"
LEGACY_SESSION_CACHE = DATA_DIR / "portfolio_ui_session.pkl"
MIGRATION_MARKER = DATA_DIR / ".legacy_portfolio_migrated"


def _holding_count(db_path: Path) -> int:
    return _holding_count_fn(db_path)


def _postgres_only() -> bool:
    try:
        from db.connection import use_cloud_sql

        return use_cloud_sql()
    except Exception:
        return False


def _copy_legacy_files(user_dir: Path) -> bool:
    """Copy legacy portfolio.db and UI cache into a user directory."""
    user_dir.mkdir(parents=True, exist_ok=True)
    copied = False
    target_db = user_dir / "portfolio.db"
    if LEGACY_PORTFOLIO_DB.is_file():
        shutil.copy2(LEGACY_PORTFOLIO_DB, target_db)
        copied = True
        logger.info("Copied legacy portfolio.db to %s", user_dir)

    target_cache = user_dir / "portfolio_ui_session.pkl"
    if LEGACY_SESSION_CACHE.is_file() and not target_cache.exists():
        shutil.copy2(LEGACY_SESSION_CACHE, target_cache)

    return copied


def restore_owner_portfolio(user_id: str, user_dir: Path) -> bool:
    """
    Attach the original on-disk portfolio to an owner account.

    Runs when the user's DB is empty but the legacy shared portfolio still has holdings.
    """
    if _postgres_only():
        return False
    legacy_count = _holding_count(LEGACY_PORTFOLIO_DB)
    if legacy_count == 0:
        return False

    target_db = user_dir / "portfolio.db"
    user_count = _holding_count(target_db)
    if user_count >= legacy_count:
        return False

    if target_db.exists() and user_count == 0:
        backup = user_dir / "portfolio.empty.bak"
        try:
            shutil.copy2(target_db, backup)
        except OSError:
            pass

    copied = _copy_legacy_files(user_dir)
    if copied:
        MIGRATION_MARKER.write_text(user_id, encoding="utf-8")
    return copied


def migrate_legacy_portfolio(user_id: str, user_dir: Path) -> bool:
    """
    Copy the old shared portfolio.db (and UI cache) into this user's directory once.

    Returns True when a legacy database was copied.
    """
    if _postgres_only():
        return False
    user_dir.mkdir(parents=True, exist_ok=True)
    target_db = user_dir / "portfolio.db"
    legacy_count = _holding_count(LEGACY_PORTFOLIO_DB)
    user_count = _holding_count(target_db)

    if legacy_count == 0:
        return False

    if user_count >= legacy_count:
        if not MIGRATION_MARKER.exists():
            MIGRATION_MARKER.write_text(user_id, encoding="utf-8")
        return False

    if MIGRATION_MARKER.exists() and user_count > 0:
        return False

    copied = _copy_legacy_files(user_dir)
    if copied:
        MIGRATION_MARKER.write_text(user_id, encoding="utf-8")
    return copied


def migrate_user_data_dir(old_user_id: str, new_user_id: str) -> bool:
    """
    Move per-user portfolio files when the canonical user id changes (e.g. dev → Google).

    Returns True when files were moved or merged into the new directory.
    """
    if _postgres_only():
        return False
    if not old_user_id or not new_user_id or old_user_id == new_user_id:
        return False

    old_dir = DATA_DIR / "users" / old_user_id
    new_dir = DATA_DIR / "users" / new_user_id
    if not old_dir.is_dir():
        return False

    new_dir.mkdir(parents=True, exist_ok=True)
    moved = False
    for name in ("portfolio.db", "portfolio_ui_session.pkl"):
        source = old_dir / name
        target = new_dir / name
        if not source.is_file():
            continue
        if target.exists():
            continue
        shutil.move(str(source), str(target))
        moved = True
        logger.info("Moved %s from user %s to %s", name, old_user_id, new_user_id)

    try:
        if old_dir.is_dir() and not any(old_dir.iterdir()):
            old_dir.rmdir()
    except OSError:
        pass

    return moved
