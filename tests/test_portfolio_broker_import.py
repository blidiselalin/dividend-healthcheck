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
    assert result.deposits_imported == 12

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
    assert len(deposits) == 12
    march = next(item for item in deposits if item.period.month == 3)
    assert march.deposit_usd == 1500.0
    december = next(item for item in deposits if item.period.month == 12)
    assert december.portfolio_eur == pytest.approx(3220.0)


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
    aapl_holding = next(h for h in ctx.portfolio.list_holdings() if h.symbol == "AAPL")
    assert net == pytest.approx(aapl_holding.shares)


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
    assert not any(item.period_key == "2025-01" for item in deposits)
    feb_2025 = next(item for item in deposits if item.period_key == "2025-02")
    assert feb_2025.deposit_eur == pytest.approx(1840.0)


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
    assert aapl_net == pytest.approx(10.0)
    assert aapl.shares == pytest.approx(10.0)
    open_rows = [
        p
        for p in ctx.journal.list_purchases(portfolio_only=False)
        if p.symbol == "AAPL" and p.source == "ibkr-open"
    ]
    assert len(open_rows) == 1
    assert open_rows[0].shares == pytest.approx(3.0)
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
    assert result.trades_imported == 1

    ctx = create_portfolio_context(db_path=db)
    symbols = {h.symbol for h in ctx.portfolio.list_holdings()}
    assert symbols == {"MSFT"}
    aapl_trades = [
        p for p in ctx.journal.list_purchases(portfolio_only=False) if p.symbol == "AAPL"
    ]
    assert len(aapl_trades) == 3
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


def test_merge_second_year_keeps_first_year_trades(tmp_path: Path) -> None:
    csv_2023 = (
        "Statement,Data,Title,Activity Statement\n"
        'Statement,Data,Period,"January 1, 2023 - December 31, 2023"\n'
        "Open Positions,Data,Summary,Stocks,USD,AAPL,10,150,150,1500\n"
        'Trades,Data,Order,Stocks,USD,AAPL,"2023-06-01, 09:30:00",10,150,1500,USD,-1.00\n'
    )
    csv_2024 = (
        "Statement,Data,Title,Activity Statement\n"
        'Statement,Data,Period,"January 1, 2024 - December 31, 2024"\n'
        "Open Positions,Data,Summary,Stocks,USD,AAPL,15,160,160,2400\n"
        'Trades,Data,Order,Stocks,USD,AAPL,"2024-06-01, 09:30:00",5,160,800,USD,-1.00\n'
    )
    db = tmp_path / "portfolio.db"
    apply_import(csv_2023, mode=ImportMode.REPLACE, db_path=db)
    apply_import(csv_2024, mode=ImportMode.MERGE, db_path=db)

    ctx = create_portfolio_context(db_path=db)
    aapl_trades = [
        p for p in ctx.journal.list_purchases(portfolio_only=False) if p.symbol == "AAPL"
    ]
    assert len(aapl_trades) == 2
    dates = sorted(p.purchase_date.isoformat() for p in aapl_trades if p.source == "ibkr")
    assert dates == ["2023-06-01", "2024-06-01"]
    holding = next(h for h in ctx.portfolio.list_holdings() if h.symbol == "AAPL")
    assert holding.shares == pytest.approx(15.0)


def test_merge_multiple_statements_same_year_without_double_count(tmp_path: Path) -> None:
    """H1 then full-year merge: overlapping months use the larger total, not a sum."""
    h1_csv = (
        "Statement,Data,Title,Activity Statement\n"
        'Statement,Data,Period,"January 1, 2025 - June 30, 2025"\n'
        "Account Information,Data,Base Currency,EUR\n"
        "Deposits & Withdrawals,Header,Currency,Settle Date,Description,Amount\n"
        "Deposits & Withdrawals,Data,EUR,2025-02-13,Electronic Fund Transfer,2500\n"
        "Deposits & Withdrawals,Data,Total,,,2500\n"
    )
    full_csv = (
        "Statement,Data,Title,Activity Statement\n"
        'Statement,Data,Period,"January 1, 2025 - December 31, 2025"\n'
        "Account Information,Data,Base Currency,EUR\n"
        "Deposits & Withdrawals,Header,Currency,Settle Date,Description,Amount\n"
        "Deposits & Withdrawals,Data,EUR,2025-02-13,Electronic Fund Transfer,2500\n"
        "Deposits & Withdrawals,Data,EUR,2025-02-17,Electronic Fund Transfer,5300\n"
        "Deposits & Withdrawals,Data,EUR,2025-07-08,Electronic Fund Transfer,1500\n"
        "Deposits & Withdrawals,Data,Total,,,9300\n"
    )
    db = tmp_path / "portfolio.db"
    apply_import(h1_csv, mode=ImportMode.MERGE, db_path=db)
    apply_import(full_csv, mode=ImportMode.MERGE, db_path=db)

    ctx = create_portfolio_context(db_path=db)
    deposits = ctx.deposits.list_deposits()
    assert len(deposits) == 2
    feb = next(item for item in deposits if item.period_key == "2025-02")
    jul = next(item for item in deposits if item.period_key == "2025-07")
    assert feb.deposit_eur == pytest.approx(7800.0)
    assert jul.deposit_eur == pytest.approx(1500.0)


def test_merge_accumulates_complementary_deposits_same_month(tmp_path: Path) -> None:
    eur_csv = (
        "Statement,Data,Title,Activity Statement\n"
        'Statement,Data,Period,"May 1, 2026 - May 31, 2026"\n'
        "Account Information,Data,Base Currency,EUR\n"
        "Deposits & Withdrawals,Header,Currency,Settle Date,Description,Amount\n"
        "Deposits & Withdrawals,Data,EUR,2026-05-11,Electronic Fund Transfer,700.07\n"
        "Deposits & Withdrawals,Data,Total,,,700.07\n"
    )
    usd_csv = (
        "Statement,Data,Title,Activity Statement\n"
        'Statement,Data,Period,"May 1, 2026 - May 31, 2026"\n'
        "Account Information,Data,Base Currency,EUR\n"
        "Deposits & Withdrawals,Header,Currency,Settle Date,Description,Amount\n"
        "Deposits & Withdrawals,Data,USD,2026-05-06,Electronic Fund Transfer,4000\n"
        "Deposits & Withdrawals,Data,Total,,,4000\n"
        "Deposits & Withdrawals,Data,Total in EUR,,,16752\n"
        "Deposits & Withdrawals,Data,Total Deposits & Withdrawals in EUR,,,17452.07\n"
    )
    db = tmp_path / "portfolio.db"
    apply_import(eur_csv, mode=ImportMode.REPLACE, db_path=db)
    apply_import(usd_csv, mode=ImportMode.MERGE, db_path=db)

    ctx = create_portfolio_context(db_path=db)
    may = next(item for item in ctx.deposits.list_deposits() if item.period_key == "2026-05")
    assert may.deposit_eur == pytest.approx(17452.07)
    assert may.deposit_usd == pytest.approx(4000.0)


def test_merge_same_file_twice_is_idempotent(tmp_path: Path, sample_csv: str) -> None:
    db = tmp_path / "portfolio.db"
    first = apply_import(sample_csv, mode=ImportMode.MERGE, db_path=db)
    ctx = create_portfolio_context(db_path=db)
    trades_after_first = len(ctx.journal.list_purchases(portfolio_only=False))
    deposits_after_first = len(ctx.deposits.list_deposits())

    second = apply_import(sample_csv, mode=ImportMode.MERGE, db_path=db)
    ctx = create_portfolio_context(db_path=db)

    assert second.trades_imported == 0
    assert second.dividends_imported == 0
    assert second.deposits_imported == 0
    assert len(ctx.journal.list_purchases(portfolio_only=False)) == trades_after_first
    assert len(ctx.deposits.list_deposits()) == deposits_after_first
    assert first.trades_imported > 0


def test_merge_does_not_overwrite_manual_journal_row(tmp_path: Path) -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        "Open Positions,Data,Summary,Stocks,USD,AAPL,10,150,150,1500\n"
        'Trades,Data,Order,Stocks,USD,AAPL,"2025-02-13, 09:30:00",10,150,1500,USD,-1.25\n'
    )
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    ctx.journal.add_purchase(
        "AAPL",
        date(2025, 2, 13),
        150.0,
        shares=99.0,
        commission_usd=0.0,
        side="buy",
        source="manual",
    )

    apply_import(csv_text, mode=ImportMode.MERGE, db_path=db)

    manual_rows = [
        p
        for p in create_portfolio_context(db_path=db).journal.list_purchases(portfolio_only=False)
        if p.symbol == "AAPL" and p.source == "manual"
    ]
    assert len(manual_rows) == 1
    assert manual_rows[0].shares == pytest.approx(99.0)


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
