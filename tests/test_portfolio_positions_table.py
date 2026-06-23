"""Home positions table — sort order and dataframe shape."""

from __future__ import annotations

from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_holdings_summary import sort_positions_worst_first
from ui.portfolio_positions_table import build_positions_table_df


def _row(
    ticker: str,
    *,
    profit_pct: float | None,
    current_value: float = 1000.0,
) -> PortfolioDetailRow:
    return PortfolioDetailRow(
        company=f"{ticker} Co",
        ticker=ticker,
        market_cap=None,
        pe_ratio=None,
        shares=10.0,
        current_price=100.0,
        current_value=current_value,
        avg_cost_per_share=90.0,
        acquisition_value=900.0,
        profit=(current_value - 900.0) if profit_pct is not None else None,
        profit_pct=profit_pct,
        estimated_avg_price=90.0,
        medium_price_365d=None,
        price_180d=None,
        price_365d=None,
        change_180d_pct=None,
        change_365d_pct=None,
        weight_pct=10.0,
        dividend_yield_pct=3.0,
        dividend_per_share=3.0,
        annual_income=30.0,
        dividend_weight_pct=10.0,
        income_weight_pct=10.0,
        dividends_paid=0.0,
        growth_years=5,
        commission=0.0,
        sector="Consumer",
        acquisition_share_pct=10.0,
        analyst_rating="Hold",
        price_to_fcf=None,
        computed_dividend="Yes",
        ex_dividend_date=None,
        dividend_pay_date=None,
        data_source="test",
    )


def test_sort_positions_worst_first() -> None:
    rows = [
        _row("WIN", profit_pct=25.0),
        _row("LOSS", profit_pct=-12.0),
        _row("FLAT", profit_pct=0.0),
        _row("UNK", profit_pct=None),
    ]
    ordered = [row.ticker for row in sort_positions_worst_first(rows)]
    assert ordered == ["LOSS", "FLAT", "WIN", "UNK"]


def test_build_positions_table_df_columns() -> None:
    df = build_positions_table_df([_row("KO", profit_pct=-5.0)])
    assert list(df.columns) == [
        "Signal",
        "Ticker",
        "Company",
        "Value $",
        "Weight %",
        "P/L %",
        "P/L $",
        "Yield %",
        "Income/yr $",
        "Price $",
    ]
    assert df.iloc[0]["Ticker"] == "KO"
    assert df.iloc[0]["P/L %"] == -5.0
