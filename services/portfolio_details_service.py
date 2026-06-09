"""
Build the full portfolio details table from holdings and market data.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import yfinance as yf

from data_ingestion.models import StockDocument
from data_ingestion.portfolio_store import PortfolioHolding, PortfolioStore
from models.stock import StockData
from services.live_price import fetch_latest_market_price, fetch_previous_close
from services.scoring import ScoringService
from services.stock_analysis_service import load_portfolio_statistics_stock
from services.portfolio_analysis_preload import PortfolioAnalysisPreload, preload_portfolio_analysis
from utils.logging_config import get_logger

logger = get_logger("dividendscope.portfolio")


@dataclass(frozen=True)
class PriceSnapshot:
    """Historical price metrics for a symbol."""

    medium_price_365d: Optional[float]
    price_180d: Optional[float]
    price_365d: Optional[float]
    change_180d_pct: Optional[float]
    change_365d_pct: Optional[float]


@dataclass(frozen=True)
class PortfolioDetailRow:
    """One row in the portfolio details table."""

    company: str
    ticker: str
    market_cap: Optional[float]
    pe_ratio: Optional[float]
    shares: float
    current_price: Optional[float]
    current_value: Optional[float]
    avg_cost_per_share: float
    acquisition_value: float
    profit: Optional[float]
    profit_pct: Optional[float]
    estimated_avg_price: float
    medium_price_365d: Optional[float]
    price_180d: Optional[float]
    price_365d: Optional[float]
    change_180d_pct: Optional[float]
    change_365d_pct: Optional[float]
    weight_pct: Optional[float]
    dividend_yield_pct: Optional[float]
    dividend_per_share: Optional[float]
    annual_income: Optional[float]
    dividend_weight_pct: Optional[float]
    income_weight_pct: Optional[float]
    dividends_paid: float
    growth_years: Optional[int]
    commission: float
    sector: str
    acquisition_share_pct: Optional[float]
    analyst_rating: str
    price_to_fcf: Optional[float]
    computed_dividend: str
    ex_dividend_date: Optional[date]
    dividend_pay_date: Optional[date]
    data_source: str
    previous_close: Optional[float] = None


class PortfolioDetailsService:
    """Merge portfolio holdings with market data for the details page."""

    def __init__(self, store: Optional[PortfolioStore] = None) -> None:
        self.store = store or PortfolioStore(seed=False)

    def build_rows(self) -> List[PortfolioDetailRow]:
        rows, _ = self.build_rows_with_cache()
        return rows

    def build_rows_with_cache(
        self,
        *,
        use_live_prices: bool = False,
        preload_analysis: bool = True,
    ) -> Tuple[List[PortfolioDetailRow], PortfolioAnalysisPreload]:
        holdings = self.store.list_holdings()
        symbols = [holding.symbol for holding in holdings]
        if use_live_prices:
            logger.info(
                "Reloading portfolio market data (%d holdings): %s",
                len(symbols),
                ", ".join(symbols[:12]) + ("…" if len(symbols) > 12 else ""),
            )
        elif not symbols:
            logger.info("Portfolio empty (no holdings in database)")
        documents = self._load_documents(symbols)
        stats_cache: Dict[str, Optional[StockData]] = {}
        live_prices: Dict[str, Optional[float]] = {}
        previous_closes: Dict[str, Optional[float]] = {}
        price_cache: Dict[str, PriceSnapshot] = {}
        market_cache: Dict[str, Tuple[Optional[float], Optional[date], Optional[date]]] = {}

        with ThreadPoolExecutor(max_workers=8) as executor:
            stats_futures = {
                executor.submit(
                    load_portfolio_statistics_stock,
                    symbol,
                    documents.get(symbol),
                ): symbol
                for symbol in symbols
            }
            price_futures = {}
            previous_close_futures = {}
            if use_live_prices:
                price_futures = {
                    executor.submit(fetch_latest_market_price, symbol): symbol
                    for symbol in symbols
                }
                previous_close_futures = {
                    executor.submit(fetch_previous_close, symbol): symbol
                    for symbol in symbols
                }
            for future in as_completed(stats_futures):
                symbol = stats_futures[future]
                try:
                    stats_cache[symbol] = future.result()
                except Exception:
                    stats_cache[symbol] = None
            if use_live_prices:
                for future in as_completed(price_futures):
                    symbol = price_futures[future]
                    try:
                        live_prices[symbol] = future.result()
                    except Exception:
                        live_prices[symbol] = None
                for future in as_completed(previous_close_futures):
                    symbol = previous_close_futures[future]
                    try:
                        previous_closes[symbol] = future.result()
                    except Exception:
                        previous_closes[symbol] = None

        if not use_live_prices:
            for symbol in symbols:
                document = documents.get(symbol)
                stats = stats_cache.get(symbol)
                price = None
                if document and document.current_price is not None:
                    price = float(document.current_price)
                elif stats and stats.price is not None:
                    price = float(stats.price)
                live_prices[symbol] = price
                previous_closes[symbol] = None

        for symbol in symbols:
            document = documents.get(symbol)
            price_cache[symbol] = self._get_price_snapshot(
                symbol,
                live_prices.get(symbol),
                document,
            )
            market_cache[symbol] = self._get_market_extras(
                symbol,
                stats_cache.get(symbol),
                document,
            )

        total_value = sum(
            (live_prices[h.symbol] or 0.0) * h.shares
            for h in holdings
            if live_prices.get(h.symbol) is not None
        )
        total_acquisition = sum(h.acquisition_value for h in holdings)
        total_income = sum(
            income
            for h in holdings
            for income in [
                self._annual_income(
                    h,
                    stats_cache.get(h.symbol),
                    documents.get(h.symbol),
                )
            ]
            if income is not None
        )

        rows: List[PortfolioDetailRow] = []
        resolved_stock_cache: Dict[str, StockData] = {}
        for holding in holdings:
            stats = stats_cache.get(holding.symbol)
            live_price = live_prices.get(holding.symbol)
            if stats is not None:
                if live_price is not None:
                    stats.price = live_price
                document = documents.get(holding.symbol)
                if document is not None and not getattr(stats, "_yield_source", None):
                    from utils.stock_history_enrichment import enrich_stock_data_from_history

                    stats, yield_source = enrich_stock_data_from_history(stats, document)
                    stats._yield_source = yield_source  # type: ignore[attr-defined]
                resolved_stock_cache[holding.symbol] = stats
            prices = price_cache[holding.symbol]
            pfcf, pay_date, ex_date_override = market_cache[holding.symbol]
            rows.append(
                self._build_row(
                    holding=holding,
                    stats=stats,
                    document=documents.get(holding.symbol),
                    live_price=live_price,
                    prices=prices,
                    total_value=total_value,
                    total_acquisition=total_acquisition,
                    total_income=total_income,
                    price_to_fcf=pfcf,
                    dividend_pay_date=pay_date,
                    ex_dividend_date=ex_date_override,
                    has_db_stats=holding.symbol in documents,
                    use_live_prices=use_live_prices,
                    previous_close=previous_closes.get(holding.symbol),
                )
            )

        if preload_analysis:
            preload = preload_portfolio_analysis(
                symbols,
                resolved_stock_cache,
                documents,
            )
        else:
            preload = PortfolioAnalysisPreload(
                stock_data=dict(resolved_stock_cache),
                yield_channels={},
                vector_docs=dict(documents),
            )
        return rows, preload

    def _load_documents(self, symbols: List[str]) -> Dict[str, StockDocument]:
        from services.shared_market_db import load_documents

        return load_documents(symbols)

    def _build_row(
        self,
        holding: PortfolioHolding,
        stats: Optional[StockData],
        document: Optional[StockDocument],
        live_price: Optional[float],
        prices: PriceSnapshot,
        total_value: float,
        total_acquisition: float,
        total_income: float,
        price_to_fcf: Optional[float],
        dividend_pay_date: Optional[date],
        ex_dividend_date: Optional[date],
        has_db_stats: bool,
        *,
        use_live_prices: bool = False,
        previous_close: Optional[float] = None,
    ) -> PortfolioDetailRow:
        current_price = live_price
        current_value = current_price * holding.shares if current_price is not None else None
        profit = (
            current_value - holding.acquisition_value
            if current_value is not None
            else None
        )
        profit_pct = (
            (profit / holding.acquisition_value) * 100
            if profit is not None and holding.acquisition_value
            else None
        )
        annual_income = self._annual_income(holding, stats, document)
        dividend_per_share = self._dividend_per_share(stats, document)
        dividend_yield = stats.dividend_yield_pct if stats else None
        weight_pct = (
            (current_value / total_value) * 100
            if current_value is not None and total_value
            else None
        )
        dividend_weight_pct = (
            (annual_income / total_income) * 100
            if annual_income is not None and total_income
            else None
        )
        acquisition_share_pct = (
            (holding.acquisition_value / total_acquisition) * 100
            if total_acquisition
            else None
        )
        growth_years = (
            stats.dividend_history.consecutive_years
            if stats and stats.dividend_history
            else None
        )
        ex_date = ex_dividend_date
        if ex_date is None and stats and stats.dividend_history:
            ex_date = stats.dividend_history.ex_dividend_date

        score = ScoringService.calculate_score(stats) if stats else 0
        analyst_rating = self._format_analyst_rating(stats, score)
        computed_dividend = self._format_computed_dividend(dividend_per_share, dividend_yield)
        price_label = "live market price" if use_live_prices else "cached price (analysed stocks)"
        if has_db_stats:
            data_source = f"{price_label}; statistics from analysed stocks"
        elif stats and stats.data_sources:
            data_source = f"{price_label}; statistics from {', '.join(stats.data_sources)}"
        else:
            data_source = f"{price_label}; statistics from public api"

        return PortfolioDetailRow(
            company=stats.name if stats and stats.name else holding.symbol,
            ticker=holding.symbol,
            market_cap=stats.market_cap if stats else None,
            pe_ratio=stats.trailing_pe if stats else None,
            shares=holding.shares,
            current_price=current_price,
            current_value=current_value,
            avg_cost_per_share=holding.avg_cost_per_share,
            acquisition_value=holding.acquisition_value,
            profit=profit,
            profit_pct=profit_pct,
            estimated_avg_price=holding.estimated_avg_price,
            medium_price_365d=prices.medium_price_365d,
            price_180d=prices.price_180d,
            price_365d=prices.price_365d,
            change_180d_pct=prices.change_180d_pct,
            change_365d_pct=prices.change_365d_pct,
            weight_pct=weight_pct,
            dividend_yield_pct=dividend_yield,
            dividend_per_share=dividend_per_share,
            annual_income=annual_income,
            dividend_weight_pct=dividend_weight_pct,
            income_weight_pct=dividend_weight_pct,
            dividends_paid=holding.dividends_paid,
            growth_years=growth_years,
            commission=holding.commission,
            sector=stats.sector if stats and stats.sector else "Unknown",
            acquisition_share_pct=acquisition_share_pct,
            analyst_rating=analyst_rating,
            price_to_fcf=price_to_fcf,
            computed_dividend=computed_dividend,
            ex_dividend_date=ex_date,
            dividend_pay_date=dividend_pay_date,
            data_source=data_source,
            previous_close=previous_close,
        )

    @staticmethod
    def _annual_income(
        holding: PortfolioHolding,
        stock: Optional[StockData],
        document: Optional[StockDocument] = None,
    ) -> Optional[float]:
        dividend_per_share = PortfolioDetailsService._dividend_per_share(
            stock, document
        )
        if dividend_per_share is None:
            return None
        return dividend_per_share * holding.shares

    @staticmethod
    def _dividend_per_share(
        stock: Optional[StockData],
        document: Optional[StockDocument] = None,
    ) -> Optional[float]:
        from utils.dividend_amounts import resolve_annual_dividend_per_share

        records = document.dividend_history if document and document.dividend_history else []
        return resolve_annual_dividend_per_share(records, document, stock)

    @staticmethod
    def _format_computed_dividend(
        dividend_per_share: Optional[float],
        dividend_yield_pct: Optional[float],
    ) -> str:
        if dividend_per_share is None and dividend_yield_pct is None:
            return "N/A"
        if dividend_per_share is None:
            return f"N/A ({dividend_yield_pct:.2f}%)"
        if dividend_yield_pct is None:
            return f"{dividend_per_share:.2f}"
        return f"{dividend_per_share:.2f} ({dividend_yield_pct:.2f}%)"

    @staticmethod
    def _format_analyst_rating(stock: Optional[StockData], score: int) -> str:
        if stock and stock.analyst_rating:
            rating = stock.analyst_rating.strip().upper()
            if rating in {"BUY", "STRONG_BUY", "STRONG BUY"}:
                return "BUY"
            if rating in {"SELL", "STRONG_SELL", "STRONG SELL"}:
                return "AVOID"
            if rating in {"HOLD", "NEUTRAL"}:
                return "HOLD/WATCH" if score >= 50 else "WEAK HOLD"
            return rating.replace("_", " ")

        recommendation = ScoringService.get_recommendation(score).label
        mapping = {
            "STRONG BUY": "BUY",
            "BUY": "BUY",
            "ACCUMULATE": "CONSIDER",
            "HOLD": "HOLD/WATCH" if score >= 50 else "WEAK HOLD",
            "AVOID": "AVOID",
        }
        return mapping.get(recommendation, recommendation)

    def _get_price_snapshot(
        self,
        symbol: str,
        live_price: Optional[float],
        document: Optional[StockDocument],
    ) -> PriceSnapshot:
        if document and document.price_history:
            snapshot = self._price_snapshot_from_history(
                document.price_history,
                live_price,
            )
            if snapshot is not None:
                return snapshot

        return self._fetch_price_snapshot(symbol)

    @staticmethod
    def _price_snapshot_from_history(
        price_history,
        current_price: Optional[float],
    ) -> Optional[PriceSnapshot]:
        if not price_history:
            return None

        closes = sorted(price_history, key=lambda point: point.date)
        if not closes:
            return None

        latest = closes[-1]
        current = current_price if current_price is not None else latest.close
        today = latest.date
        close_values = [point.close for point in closes if point.close is not None]
        if not close_values:
            return None

        medium_365 = PortfolioDetailsService._mean_close_from_points(closes, today, 365)
        price_180 = PortfolioDetailsService._close_on_or_before_points(closes, today - timedelta(days=180))
        price_365 = PortfolioDetailsService._close_on_or_before_points(closes, today - timedelta(days=365))

        return PriceSnapshot(
            medium_price_365d=medium_365,
            price_180d=price_180,
            price_365d=price_365,
            change_180d_pct=PortfolioDetailsService._pct_change(current, price_180),
            change_365d_pct=PortfolioDetailsService._pct_change(current, price_365),
        )

    @staticmethod
    @lru_cache(maxsize=128)
    def _fetch_price_snapshot(symbol: str) -> PriceSnapshot:
        try:
            history = yf.Ticker(symbol).history(period="2y", auto_adjust=True)
        except Exception:
            return PriceSnapshot(None, None, None, None, None)

        if history is None or history.empty or "Close" not in history.columns:
            return PriceSnapshot(None, None, None, None, None)

        closes = history["Close"].dropna()
        if closes.empty:
            return PriceSnapshot(None, None, None, None, None)

        current_price = float(closes.iloc[-1])
        today = closes.index[-1].date()
        medium_365 = PortfolioDetailsService._mean_close(closes, today, 365)
        price_180 = PortfolioDetailsService._close_on_or_before(closes, today - timedelta(days=180))
        price_365 = PortfolioDetailsService._close_on_or_before(closes, today - timedelta(days=365))

        return PriceSnapshot(
            medium_price_365d=medium_365,
            price_180d=price_180,
            price_365d=price_365,
            change_180d_pct=PortfolioDetailsService._pct_change(current_price, price_180),
            change_365d_pct=PortfolioDetailsService._pct_change(current_price, price_365),
        )

    def _get_market_extras(
        self,
        symbol: str,
        stats: Optional[StockData],
        document: Optional[StockDocument],
    ) -> Tuple[Optional[float], Optional[date], Optional[date]]:
        pay_date = None
        ex_date = None
        if document and document.dividend_history:
            latest = max(document.dividend_history, key=lambda record: record.ex_date)
            pay_date = latest.payment_date
            ex_date = latest.ex_date
        if stats and stats.dividend_history and stats.dividend_history.ex_dividend_date:
            ex_date = stats.dividend_history.ex_dividend_date

        price_to_fcf = None
        if pay_date is None or ex_date is None:
            fetched_pfcf, fetched_pay, fetched_ex = self._fetch_market_extras(symbol, ex_date)
            return fetched_pfcf, pay_date or fetched_pay, ex_date or fetched_ex

        return price_to_fcf, pay_date, ex_date

    @staticmethod
    @lru_cache(maxsize=128)
    def _fetch_market_extras(
        symbol: str,
        ex_date: Optional[date],
    ) -> Tuple[Optional[float], Optional[date], Optional[date]]:
        try:
            info = yf.Ticker(symbol).info or {}
        except Exception:
            return None, ex_date, ex_date

        price_to_fcf = info.get("priceToFreeCashFlows")
        if price_to_fcf is None:
            market_cap = info.get("marketCap")
            free_cashflow = info.get("freeCashflow")
            if market_cap and free_cashflow:
                price_to_fcf = market_cap / free_cashflow

        pay_date = PortfolioDetailsService._parse_timestamp(info.get("dividendDate"))
        fetched_ex = PortfolioDetailsService._parse_timestamp(info.get("exDividendDate"))
        return price_to_fcf, pay_date, ex_date or fetched_ex

    @staticmethod
    def _mean_close_from_points(points, end_date: date, window_days: int) -> Optional[float]:
        start_date = end_date - timedelta(days=window_days)
        window = [point.close for point in points if start_date <= point.date <= end_date]
        if not window:
            return None
        return float(sum(window) / len(window))

    @staticmethod
    def _close_on_or_before_points(points, target_date: date) -> Optional[float]:
        eligible = [point for point in points if point.date <= target_date]
        if not eligible:
            return None
        return float(eligible[-1].close)

    @staticmethod
    def _mean_close(closes, end_date: date, window_days: int) -> Optional[float]:
        start_date = end_date - timedelta(days=window_days)
        window = closes[closes.index.date >= start_date]
        if window.empty:
            return None
        return float(window.mean())

    @staticmethod
    def _close_on_or_before(closes, target_date: date) -> Optional[float]:
        eligible = closes[closes.index.date <= target_date]
        if eligible.empty:
            return None
        return float(eligible.iloc[-1])

    @staticmethod
    def _pct_change(current: float, prior: Optional[float]) -> Optional[float]:
        if prior is None or prior == 0:
            return None
        return ((current / prior) - 1) * 100

    @staticmethod
    def _parse_timestamp(value) -> Optional[date]:
        if value in (None, 0, "0"):
            return None
        try:
            return datetime.fromtimestamp(value).date()
        except (TypeError, ValueError, OSError):
            return None
