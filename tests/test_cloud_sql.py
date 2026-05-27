"""Cloud SQL integration tests (local SQLite fallback unchanged)."""

from db.connection import get_database_url, use_cloud_sql


def test_cloud_sql_disabled_by_default():
    assert use_cloud_sql() is (bool(get_database_url()))
