"""CLI coverage for ingest_data.py operational flags."""

from __future__ import annotations

import sys

import ingest_data


def _run_cli(monkeypatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["ingest_data.py", *args])
    return ingest_data.main()


def test_sync_history_tables_flag_calls_sync_with_limit(monkeypatch) -> None:
    called: dict[str, int] = {}

    class FakeHistoryStore:
        def sync_pending_from_jsonb(self, *, limit: int) -> dict[str, int]:
            called["limit"] = limit
            return {"pending": 1, "processed": 1, "synced": 1, "skipped": 0}

    monkeypatch.setattr(
        "db.postgres_market_history_store.PostgresMarketHistoryStore",
        lambda: FakeHistoryStore(),
    )

    assert _run_cli(monkeypatch, "--sync-history-tables", "--sync-history-limit", "321") == 0
    assert called["limit"] == 321


def test_sync_history_tables_flag_uses_default_limit(monkeypatch) -> None:
    called: dict[str, int] = {}

    class FakeHistoryStore:
        def sync_pending_from_jsonb(self, *, limit: int) -> dict[str, int]:
            called["limit"] = limit
            return {"pending": 1, "processed": 1, "synced": 1, "skipped": 0}

    monkeypatch.setattr(
        "db.postgres_market_history_store.PostgresMarketHistoryStore",
        lambda: FakeHistoryStore(),
    )

    assert _run_cli(monkeypatch, "--sync-history-tables") == 0
    assert called["limit"] == 500


def test_ensure_sp500_flag_uses_limit(monkeypatch) -> None:
    called: dict[str, int | None] = {}

    def _fake_ensure(
        *,
        limit: int | None = None,
        _request_delay: float = 0.35,
        progress_callback=None,
    ) -> dict[str, int]:
        called["limit"] = limit
        if progress_callback:
            progress_callback("S&P 500: KO", 1, 1)
        return {"created": 1, "already_present": 0, "errors": 0}

    monkeypatch.setattr("services.sp500_peers_service.ensure_sp500_in_vectordb", _fake_ensure)

    assert _run_cli(monkeypatch, "--ensure-sp500", "--limit", "15") == 0
    assert called["limit"] == 15


def test_ensure_sp500_flag_default_limit_is_none(monkeypatch) -> None:
    called: dict[str, int | None] = {}

    def _fake_ensure(*, limit: int | None = None, **kwargs) -> dict[str, int]:
        called["limit"] = limit
        return {"created": 0, "already_present": 500, "errors": 0}

    monkeypatch.setattr("services.sp500_peers_service.ensure_sp500_in_vectordb", _fake_ensure)

    assert _run_cli(monkeypatch, "--ensure-sp500") == 0
    assert called["limit"] is None


def test_backfill_history_flag_uses_limit(monkeypatch) -> None:
    called: dict[str, int] = {}

    def _fake_backfill(*, limit: int = 40, progress_callback=None, **kwargs) -> dict[str, int]:
        called["limit"] = limit
        if progress_callback:
            progress_callback(1.0, "done")
        return {
            "candidates": limit,
            "processed": limit,
            "enriched": limit,
            "ready_after": 0,
            "errors": 0,
        }

    monkeypatch.setattr("services.stock_history_backfill.backfill_thin_history", _fake_backfill)

    assert _run_cli(monkeypatch, "--backfill-history", "--backfill-limit", "9") == 0
    assert called["limit"] == 9


def test_backfill_history_flag_uses_default_limit(monkeypatch) -> None:
    called: dict[str, int] = {}

    def _fake_backfill(*, limit: int = 40, **kwargs) -> dict[str, int]:
        called["limit"] = limit
        return {"candidates": 0, "processed": 0, "enriched": 0, "ready_after": 0, "errors": 0}

    monkeypatch.setattr("services.stock_history_backfill.backfill_thin_history", _fake_backfill)

    assert _run_cli(monkeypatch, "--backfill-history") == 0
    assert called["limit"] == 40


def test_refresh_prices_flag_calls_refresh_service(monkeypatch) -> None:
    called = {"ran": False}

    def _fake_refresh() -> dict[str, int]:
        called["ran"] = True
        return {"total": 2, "updated": 2, "skipped": 0, "errors": 0}

    monkeypatch.setattr("services.db_price_refresh.refresh_market_library_prices", _fake_refresh)

    assert _run_cli(monkeypatch, "--refresh-prices") == 0
    assert called["ran"] is True


def test_ensure_top_dividend_flag_uses_limit(monkeypatch) -> None:
    called: dict[str, int | None] = {}

    def _fake_ensure(
        *,
        limit: int | None = None,
        _request_delay: float = 0.35,
        progress_callback=None,
    ) -> dict[str, int]:
        called["limit"] = limit
        if progress_callback:
            progress_callback("Top dividend: KO", 1, 1)
        return {"created": 1, "already_present": 0, "errors": 0}

    monkeypatch.setattr(
        "services.sp500_peers_service.ensure_top_dividend_in_vectordb",
        _fake_ensure,
    )

    assert _run_cli(monkeypatch, "--ensure-top-dividend", "--limit", "7") == 0
    assert called["limit"] == 7


def test_ensure_top_dividend_flag_default_limit_is_none(monkeypatch) -> None:
    called: dict[str, int | None] = {}

    def _fake_ensure(*, limit: int | None = None, **kwargs) -> dict[str, int]:
        called["limit"] = limit
        return {"created": 0, "already_present": 100, "errors": 0}

    monkeypatch.setattr(
        "services.sp500_peers_service.ensure_top_dividend_in_vectordb",
        _fake_ensure,
    )

    assert _run_cli(monkeypatch, "--ensure-top-dividend") == 0
    assert called["limit"] is None


def test_sync_portfolio_flag_calls_sync_service(monkeypatch) -> None:
    called = {"ran": False}

    def _fake_sync(**kwargs) -> dict[str, object]:
        called["ran"] = True
        assert kwargs == {}
        return {
            "linked": 1,
            "created": 1,
            "stored": 1,
            "still_missing": [],
            "errors": 0,
        }

    monkeypatch.setattr("services.portfolio_vector_sync.sync_portfolio_to_vector_db", _fake_sync)

    assert _run_cli(monkeypatch, "--sync-portfolio") == 0
    assert called["ran"] is True
