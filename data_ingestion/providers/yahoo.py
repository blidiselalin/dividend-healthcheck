"""
Yahoo Finance provider (via yfinance).

Primary free source; unofficial API — rate limits and gaps are common.
Best for: price, dividends, history, baseline fundamentals.
"""

from __future__ import annotations

import logging
from typing import Any

from data_ingestion.base import BaseFetcher
from data_ingestion.models import DataSource, DividendRecord, PriceHistory
from data_ingestion.providers._numeric import as_float, as_percent, parse_unix_date
from data_ingestion.providers.base import StockDataProvider
from data_ingestion.providers.snapshot import StockSnapshot

logger = logging.getLogger(__name__)

try:
    import yfinance as yf

    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


class YahooFinanceProvider(BaseFetcher, StockDataProvider):
    source = DataSource.YAHOO
    field_groups = frozenset(
        {
            "identity",
            "dividend",
            "price",
            "valuation",
            "health",
            "profitability",
            "growth",
            "analyst",
            "history",
        }
    )
    priority = 10

    def available(self) -> bool:
        return YFINANCE_AVAILABLE

    def fetch(self, symbol: str) -> StockSnapshot | None:
        if not self.available():
            return None

        symbol = symbol.upper().strip()
        self._rate_limit()
        try:
            ticker = yf.Ticker(symbol)
            info = self._info(ticker)
            if not info:
                return None

            snap = StockSnapshot(symbol=symbol, source=self.source)
            snap.name = info.get("longName") or info.get("shortName")
            snap.sector = info.get("sector")
            snap.industry = info.get("industry")
            snap.exchange = info.get("exchange")
            snap.description = info.get("longBusinessSummary")

            snap.dividend_yield = as_percent(info.get("dividendYield"))
            snap.annual_dividend = as_float(info.get("dividendRate"))
            snap.payout_ratio = as_percent(info.get("payoutRatio"))
            snap.pe_ratio = as_float(info.get("trailingPE"))
            snap.forward_pe = as_float(info.get("forwardPE"))
            snap.peg_ratio = as_float(info.get("pegRatio"))
            snap.price_to_book = as_float(info.get("priceToBook"))
            snap.price_to_sales = as_float(info.get("priceToSalesTrailing12Months"))
            snap.ev_ebitda = as_float(info.get("enterpriseToEbitda"))
            snap.current_price = as_float(info.get("currentPrice", info.get("regularMarketPrice")))
            snap.market_cap = as_float(info.get("marketCap"))
            snap.fifty_two_week_high = as_float(info.get("fiftyTwoWeekHigh"))
            snap.fifty_two_week_low = as_float(info.get("fiftyTwoWeekLow"))
            snap.beta = as_float(info.get("beta"))
            snap.debt_to_equity = as_float(info.get("debtToEquity"))
            snap.current_ratio = as_float(info.get("currentRatio"))
            snap.quick_ratio = as_float(info.get("quickRatio"))
            snap.roe = as_percent(info.get("returnOnEquity"))
            snap.roa = as_percent(info.get("returnOnAssets"))
            snap.profit_margin = as_percent(info.get("profitMargins"))
            snap.operating_margin = as_percent(info.get("operatingMargins"))
            snap.gross_margin = as_percent(info.get("grossMargins"))
            snap.revenue_growth = as_percent(info.get("revenueGrowth"))
            snap.earnings_growth = as_percent(info.get("earningsGrowth"))
            snap.target_price = as_float(info.get("targetMeanPrice"))
            snap.num_analysts = int(info.get("numberOfAnalystOpinions") or 0) or None
            snap.analyst_rating = info.get("recommendationKey")

            ex = info.get("exDividendDate")
            if ex:
                snap.ex_dividend_date = parse_unix_date(ex)

            fcf = as_float(info.get("freeCashflow"))
            shares = as_float(info.get("sharesOutstanding"))
            if fcf and snap.annual_dividend and shares and fcf > 0:
                snap.fcf_payout_ratio = (snap.annual_dividend * shares / fcf) * 100

            eps = as_float(info.get("trailingEps"))
            if eps and snap.annual_dividend and snap.annual_dividend > 0:
                snap.dividend_coverage = eps / snap.annual_dividend

            if snap.current_price and snap.target_price and snap.current_price > 0:
                snap.target_upside = ((snap.target_price / snap.current_price) - 1) * 100

            self._attach_history(ticker, snap)
            return snap
        except Exception as exc:
            logger.debug("Yahoo fetch failed for %s: %s", symbol, exc)
            return None

    @staticmethod
    def _info(ticker: Any) -> dict[str, Any] | None:
        try:
            info = ticker.info
            return info if info else None
        except Exception:
            try:
                fast = ticker.fast_info
                return {
                    "regularMarketPrice": getattr(fast, "last_price", None),
                    "currentPrice": getattr(fast, "last_price", None),
                    "marketCap": getattr(fast, "market_cap", None),
                    "fiftyTwoWeekHigh": getattr(fast, "year_high", None),
                    "fiftyTwoWeekLow": getattr(fast, "year_low", None),
                }
            except Exception:
                return None

    @staticmethod
    def _attach_history(ticker: Any, snap: StockSnapshot) -> None:
        try:
            hist = ticker.history(period="10y", auto_adjust=True)
            if hist is not None and not hist.empty:
                from utils.json_safe import finite_float

                for idx, row in hist.tail(252 * 10).iterrows():
                    close = finite_float(row.get("Close"))
                    if close is None or close <= 0:
                        continue
                    open_ = finite_float(row.get("Open"), default=close) or close
                    high = finite_float(row.get("High"), default=close) or close
                    low = finite_float(row.get("Low"), default=close) or close
                    snap.price_history.append(
                        PriceHistory(
                            date=idx.date() if hasattr(idx, "date") else idx,
                            open=open_,
                            high=high,
                            low=low,
                            close=close,
                            volume=int(row.get("Volume", 0) or 0),
                            adjusted_close=finite_float(row.get("Close"), default=close) or close,
                        )
                    )
        except Exception:  # noqa: S110
            pass

        try:
            divs = ticker.dividends
            if divs is not None and not divs.empty:
                for idx, amount in divs.items():
                    ex = idx.date() if hasattr(idx, "date") else None
                    if ex:
                        snap.dividend_history.append(
                            DividendRecord(ex_date=ex, payment_date=None, amount=float(amount))
                        )
        except Exception:  # noqa: S110
            pass
