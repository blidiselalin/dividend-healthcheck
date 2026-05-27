"""Tests for PostgreSQL migration SQL parsing."""

from pathlib import Path

from db.connection import _migration_path, _migration_statements


def test_migration_statements_include_users_table():
    statements = _migration_statements()
    assert statements, "migration file should produce statements"
    first = statements[0].upper()
    assert "CREATE TABLE" in first and "USERS" in first


def test_migration_file_exists():
    assert _migration_path().is_file()
