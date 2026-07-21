"""Tests for IBKR broker import apply logic."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from services.portfolio_broker_import_service import ImportMode, apply_import, preview_import
from services.portfolio_context import create_portfolio_context

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ibkr_activity_sample.csv"


@pytest.fixture
def sample_csv() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_preview_sample(sample_csv: str) -> None:
    preview = preview_import(sample_csv)
    assert preview.position_count == 2
    assert not preview.blocking


def test_replace_import_loads_holdings_and_receipts(tmp_path: Path, sample_csv: str) -> None:
    db = tmp_path / "portfolio.db"
    result = apply_import(sample_csv, mode=ImportMode.REPLACE, db_path=db)
    assert result.holdings_upserted == 2
    assert result.trades_imported == 3
    assert result.dividends_imported == 2

    ctx = create_portfolio_context(db_path=db)
    symbols = {h.symbol for h in ctx.portfolio.list_holdings()}
    assert symbols == {"AAPL", "MSFT"}
    aapl = next(h for h in ctx.portfolio.list_holdings() if h.symbol == "AAPL")
    assert aapl.shares == 10
    receipts = ctx.receipts.list_for_symbol("AAPL")
    assert len(receipts) == 1
    assert receipts[0].source == "ibkr"
    assert receipts[0].gross_usd == 2.50


def test_merge_leaves_untouched_symbols(tmp_path: Path, sample_csv: str) -> None:
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    ctx.portfolio.upsert_holding("VZ", shares=20, avg_cost_per_share=40.0)
    ctx.journal.add_purchase("VZ", date(2024, 1, 1), 40.0, shares=20, source="manual")

    apply_import(sample_csv, mode=ImportMode.MERGE, db_path=db)

    ctx = create_portfolio_context(db_path=db)
    symbols = {h.symbol for h in ctx.portfolio.list_holdings()}
    assert "VZ" in symbols
    assert "AAPL" in symbols
    vz_lots = [p for p in ctx.journal.list_purchases(portfolio_only=False) if p.symbol == "VZ"]
    assert len(vz_lots) == 1
    assert vz_lots[0].source == "manual"


def test_computed_sync_does_not_overwrite_ibkr_receipts(tmp_path: Path, sample_csv: str) -> None:
    db = tmp_path / "portfolio.db"
    apply_import(sample_csv, mode=ImportMode.REPLACE, db_path=db)
    ctx = create_portfolio_context(db_path=db)
    before = ctx.receipts.list_for_symbol("AAPL")[0]

    outcome = ctx.receipts.sync_receipt(
        "AAPL",
        ex_date=before.ex_date,
        pay_date=before.pay_date,
        per_share_usd=before.per_share_usd,
        shares_held=999.0,
        gross_usd=999.0,
        source="computed",
    )
    assert outcome == "unchanged"
    after = ctx.receipts.list_for_symbol("AAPL")[0]
    assert after.gross_usd == before.gross_usd
    assert after.source == "ibkr"


def test_sell_lots_produce_negative_estimated_shares(tmp_path: Path, sample_csv: str) -> None:
    db = tmp_path / "portfolio.db"
    apply_import(sample_csv, mode=ImportMode.REPLACE, db_path=db)
    ctx = create_portfolio_context(db_path=db)
    lots = ctx.journal_service.build_estimated_lots()
    aapl_lots = [lot for lot in lots if lot.symbol == "AAPL"]
    assert any(lot.estimated_shares < 0 for lot in aapl_lots)
    net = sum(lot.estimated_shares for lot in aapl_lots)
    assert net == pytest.approx(7.0)


def test_import_stores_dividends_for_closed_positions(tmp_path: Path) -> None:
    """Dividends for sold symbols (not in Open Positions) are still persisted."""
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        "Open Positions,Data,Summary,Stocks,USD,KO,10,60,60,600\n"
        "Dividends,Data,USD,2025-03-15,"
        '"AMCR(US001) Cash Dividend USD 0.12 (Ordinary Dividend)",1.20\n'
    )
    db = tmp_path / "portfolio.db"
    result = apply_import(csv_text, mode=ImportMode.REPLACE, db_path=db)
    assert result.dividends_imported == 1

    ctx = create_portfolio_context(db_path=db)
    assert {h.symbol for h in ctx.portfolio.list_holdings()} == {"KO"}
    amcr = ctx.receipts.list_for_symbol("AMCR")
    assert len(amcr) == 1
    assert amcr[0].source == "ibkr"
    assert amcr[0].gross_usd == 1.20


def test_merge_import_stores_dividends_for_closed_positions(tmp_path: Path) -> None:
    """Merge mode also keeps dividends for symbols no longer held."""
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        "Open Positions,Data,Summary,Stocks,USD,KO,10,60,60,600\n"
        "Dividends,Data,USD,2025-03-15,"
        '"AMCR(US001) Cash Dividend USD 0.12 (Ordinary Dividend)",1.20\n'
    )
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    ctx.portfolio.upsert_holding("VZ", shares=5, avg_cost_per_share=40.0)

    result = apply_import(csv_text, mode=ImportMode.MERGE, db_path=db)
    assert result.dividends_imported == 1

    ctx = create_portfolio_context(db_path=db)
    assert {h.symbol for h in ctx.portfolio.list_holdings()} == {"KO", "VZ"}
    assert len(ctx.receipts.list_for_symbol("AMCR")) == 1


def test_replace_import_validates_against_open_positions(tmp_path: Path, sample_csv: str) -> None:
    db = tmp_path / "portfolio.db"
    apply_import(sample_csv, mode=ImportMode.REPLACE, db_path=db)
    ctx = create_portfolio_context(db_path=db)

    from services.ibkr_activity_parser import parse_activity_statement_csv

    stmt = parse_activity_statement_csv(sample_csv)
    for position in stmt.open_positions:
        holding = next(h for h in ctx.portfolio.list_holdings() if h.symbol == position.symbol)
        assert holding.shares == pytest.approx(position.shares)
        assert holding.avg_cost_per_share == pytest.approx(position.cost_price)
