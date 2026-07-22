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
    assert preview.deposit_month_count == 2
    assert not preview.blocking


def test_preview_without_open_positions_is_not_blocking() -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        'Trades,Data,Order,Stocks,USD,AAPL,"2025-02-13, 09:30:00",10,150,1500,USD,-1.25\n'
        'Dividends,Data,USD,2025-03-15,"AAPL(US0378331005) Cash Dividend USD 0.25 per Share",2.50\n'
        "Deposits & Withdrawals,Data,USD,2025-02-01,Electronic Fund Transfer,1000.00\n"
    )
    preview = preview_import(csv_text)
    assert preview.position_count == 0
    assert preview.trade_count == 1
    assert preview.dividend_count == 1
    assert preview.deposit_month_count == 1
    assert preview.symbols == ["AAPL"]
    assert not preview.blocking


def test_apply_import_without_open_positions(tmp_path: Path) -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        'Trades,Data,Order,Stocks,USD,AAPL,"2025-02-13, 09:30:00",10,150,1500,USD,-1.25\n'
        'Trades,Data,Order,Stocks,USD,AAPL,"2025-08-01, 10:00:00",-10,170,1700,USD,-1.00\n'
        'Dividends,Data,USD,2025-03-15,"AAPL(US0378331005) Cash Dividend USD 0.25 per Share",2.50\n'
        "Deposits & Withdrawals,Data,USD,2025-02-01,Electronic Fund Transfer,1000.00\n"
    )
    db = tmp_path / "portfolio.db"
    result = apply_import(csv_text, mode=ImportMode.REPLACE, db_path=db)
    assert result.holdings_upserted == 0
    assert result.trades_imported == 2
    assert result.dividends_imported == 1
    assert result.deposits_imported == 1
    assert result.wrote_data

    ctx = create_portfolio_context(db_path=db)
    assert ctx.portfolio.list_holdings() == []
    assert len(ctx.journal.list_purchases(portfolio_only=False)) == 2
    assert len(ctx.receipts.list_for_symbol("AAPL")) == 1
    assert len(ctx.deposits.list_deposits()) == 1


def test_apply_import_reports_progress(sample_csv: str, tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    steps: list[tuple[str, float]] = []

    apply_import(
        sample_csv,
        mode=ImportMode.REPLACE,
        db_path=db,
        progress=lambda message, fraction: steps.append((message, fraction)),
    )

    assert steps
    assert steps[0][0].startswith("Parsing")
    assert steps[-1] == ("Import complete", 1.0)
    assert all(0.0 <= fraction <= 1.0 for _, fraction in steps)


def test_replace_import_loads_holdings_and_receipts(tmp_path: Path, sample_csv: str) -> None:
    db = tmp_path / "portfolio.db"
    result = apply_import(sample_csv, mode=ImportMode.REPLACE, db_path=db)
    assert result.holdings_upserted == 2
    assert result.trades_imported == 3
    assert result.dividends_imported == 2
    assert result.deposits_imported == 2

    ctx = create_portfolio_context(db_path=db)
    symbols = {h.symbol for h in ctx.portfolio.list_holdings()}
    assert symbols == {"AAPL", "MSFT"}
    aapl = next(h for h in ctx.portfolio.list_holdings() if h.symbol == "AAPL")
    assert aapl.shares == 10
    receipts = ctx.receipts.list_for_symbol("AAPL")
    assert len(receipts) == 1
    assert receipts[0].source == "ibkr"
    assert receipts[0].gross_usd == 2.50
    deposits = ctx.deposits.list_deposits()
    assert len(deposits) == 2
    march = next(item for item in deposits if item.period.month == 3)
    assert march.deposit_usd == 1500.0
    assert march.portfolio_eur == pytest.approx(3220.0)


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
    assert result.symbols_touched == ["AMCR", "KO"]


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


def test_merge_import_updates_deposit_months_without_wiping_manual_months(
    tmp_path: Path,
    sample_csv: str,
) -> None:
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    ctx.deposits.upsert_deposit(
        year=2024,
        month=12,
        label="December 2024",
        deposit_eur=4500.0,
        deposit_usd=4729.10,
        portfolio_eur=65006.66,
    )

    apply_import(sample_csv, mode=ImportMode.MERGE, db_path=db)

    ctx = create_portfolio_context(db_path=db)
    deposits = ctx.deposits.list_deposits()
    assert len(deposits) == 3
    assert any(item.period_key == "2024-12" for item in deposits)
    assert any(item.period_key == "2025-02" for item in deposits)
    assert any(item.period_key == "2025-03" for item in deposits)


def test_replace_import_journal_net_shares_match_open_position(
    tmp_path: Path,
    sample_csv: str,
) -> None:
    db = tmp_path / "portfolio.db"
    result = apply_import(sample_csv, mode=ImportMode.REPLACE, db_path=db)
    ctx = create_portfolio_context(db_path=db)

    aapl = next(h for h in ctx.portfolio.list_holdings() if h.symbol == "AAPL")
    lots = ctx.journal_service.build_estimated_lots()
    aapl_net = sum(lot.estimated_shares for lot in lots if lot.symbol == "AAPL")
    assert aapl_net == pytest.approx(7.0)
    assert aapl.shares == pytest.approx(10.0)
    assert result.symbols_touched == ["AAPL", "MSFT"]


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


def test_merge_drops_fully_sold_holding_keeps_history(tmp_path: Path) -> None:
    """Merge removes open positions that were fully sold but keeps journal + receipts."""
    sold_csv = (
        "Statement,Data,Title,Activity Statement\n"
        "Open Positions,Data,Summary,Stocks,USD,MSFT,5,400,400,2000\n"
        'Trades,Data,Order,Stocks,USD,AAPL,"2025-02-13, 09:30:00",10,150,1500,USD,-1.25\n'
        'Trades,Data,Order,Stocks,USD,AAPL,"2025-08-01, 10:00:00",-10,170,1700,USD,-1.00\n'
        'Trades,Data,Order,Stocks,USD,MSFT,"2025-03-01, 11:00:00",5,400,2000,USD,-1.50\n'
        'Dividends,Data,USD,2025-03-15,"AAPL(US0378331005) Cash Dividend USD 0.25 per Share",2.50\n'
    )
    db = tmp_path / "portfolio.db"
    apply_import(FIXTURE.read_text(encoding="utf-8"), mode=ImportMode.REPLACE, db_path=db)

    result = apply_import(sold_csv, mode=ImportMode.MERGE, db_path=db)
    assert result.trades_imported == 3

    ctx = create_portfolio_context(db_path=db)
    symbols = {h.symbol for h in ctx.portfolio.list_holdings()}
    assert symbols == {"MSFT"}
    aapl_trades = [
        p for p in ctx.journal.list_purchases(portfolio_only=False) if p.symbol == "AAPL"
    ]
    assert len(aapl_trades) == 2
    assert {p.side for p in aapl_trades} == {"buy", "sell"}
    assert len(ctx.receipts.list_for_symbol("AAPL")) == 1


def test_merge_imports_trades_for_symbols_not_in_open_positions(tmp_path: Path) -> None:
    """Closed-position trades in the statement are still written on merge."""
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        "Open Positions,Data,Summary,Stocks,USD,KO,10,60,60,600\n"
        'Trades,Data,Order,Stocks,USD,AMCR,"2025-04-01, 09:30:00",20,10,200,USD,-1.00\n'
        'Trades,Data,Order,Stocks,USD,AMCR,"2025-05-01, 10:00:00",-20,11,220,USD,-1.00\n'
        "Dividends,Data,USD,2025-03-15,"
        '"AMCR(US001) Cash Dividend USD 0.12 (Ordinary Dividend)",1.20\n'
    )
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    ctx.portfolio.upsert_holding("AMCR", shares=5, avg_cost_per_share=10.0)

    apply_import(csv_text, mode=ImportMode.MERGE, db_path=db)

    ctx = create_portfolio_context(db_path=db)
    assert "AMCR" not in {h.symbol for h in ctx.portfolio.list_holdings()}
    amcr_trades = [
        p for p in ctx.journal.list_purchases(portfolio_only=False) if p.symbol == "AMCR"
    ]
    assert len(amcr_trades) == 2
    assert len(ctx.receipts.list_for_symbol("AMCR")) == 1


def test_apply_import_invalidates_cache_and_syncs_vector(
    tmp_path: Path,
    sample_csv: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "portfolio.db"
    invalidate_calls: list[bool] = []
    sync_calls: list[bool] = []

    monkeypatch.setattr(
        "services.portfolio_session.invalidate_holdings_cache",
        lambda: invalidate_calls.append(True),
    )

    def _sync(**kwargs: object) -> dict[str, int]:
        sync_calls.append(True)
        return {"linked": 2}

    monkeypatch.setattr(
        "services.portfolio_vector_sync.sync_portfolio_to_vector_db",
        _sync,
    )

    apply_import(sample_csv, mode=ImportMode.REPLACE, db_path=db)

    assert invalidate_calls
    assert sync_calls


def test_merge_import_never_calls_clear_user_portfolio(
    tmp_path: Path,
    sample_csv: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    ctx.portfolio.upsert_holding("VZ", shares=5, avg_cost_per_share=40.0)

    clear_calls: list[bool] = []

    def _fail_clear(**kwargs: object) -> None:
        clear_calls.append(True)
        raise AssertionError("merge must not clear portfolio tables")

    monkeypatch.setattr(
        "services.portfolio_broker_import_service.clear_user_portfolio",
        _fail_clear,
    )

    apply_import(sample_csv, mode=ImportMode.MERGE, db_path=db)

    assert not clear_calls
    symbols = {h.symbol for h in create_portfolio_context(db_path=db).portfolio.list_holdings()}
    assert "VZ" in symbols
