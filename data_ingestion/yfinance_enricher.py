"""
yfinance-based data enricher for StockDocument.

Fetches comprehensive financial data from yfinance to populate
all fields in StockDocument for complete offline operation.
"""

from __future__ import annotations

import contextlib
import logging
import time
from datetime import datetime
from typing import Any, cast

from .models import DataSource, DividendRecord, PriceHistory, StockDocument

logger = logging.getLogger(__name__)

try:
    import yfinance as yf

    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not installed. Install with: pip install yfinance")


class YFinanceEnricher:
    """
    Enriches StockDocument with comprehensive data from yfinance.

    Fetches all available financial metrics to enable complete
    offline operation from the vector database.
    """

    def __init__(self, request_delay: float = 0.5) -> None:
        """
        Initialize the enricher.

        Args:
            request_delay: Seconds to wait between API calls to avoid rate limiting.
        """
        self.request_delay = request_delay
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.time()

    def enrich_document(self, doc: StockDocument) -> StockDocument:  # noqa: C901
        """
        Enrich a StockDocument with yfinance data.

        Merges yfinance data into the existing document, filling in
        missing fields without overwriting existing data.

        Args:
            doc: Existing StockDocument to enrich.

        Returns:
            Enriched StockDocument.
        """
        if not YFINANCE_AVAILABLE:
            logger.warning("yfinance not available, returning original document")
            return doc

        try:
            self._rate_limit()
            ticker = yf.Ticker(doc.symbol)
            info = self._get_info_safe(ticker)

            if not info:
                logger.warning(f"No yfinance data for {doc.symbol}")
                return doc

            # Update basic info if missing
            if doc.name == doc.symbol or not doc.name:
                doc.name = info.get("longName", info.get("shortName", doc.symbol))

            if doc.sector == "Unknown":
                doc.sector = info.get("sector", "Unknown")

            if doc.industry == "Unknown":
                doc.industry = info.get("industry", "Unknown")

            if doc.exchange == "Unknown":
                doc.exchange = info.get("exchange", "Unknown")

            # Dividend fields - use max_reasonable to detect pre-multiplied values
            # Normal dividend yields are < 20%, payout ratios < 200%
            if doc.dividend_yield is None:
                doc.dividend_yield = self._safe_get(
                    info, "dividendYield", multiplier=100, max_reasonable=30
                )

            if doc.annual_dividend is None:
                doc.annual_dividend = info.get("dividendRate")

            if doc.payout_ratio is None:
                doc.payout_ratio = self._safe_get(
                    info, "payoutRatio", multiplier=100, max_reasonable=200
                )

            # Calculate FCF payout ratio
            if doc.fcf_payout_ratio is None:
                fcf = info.get("freeCashflow")
                div_rate = info.get("dividendRate")
                shares = info.get("sharesOutstanding")
                if fcf and div_rate and shares and fcf > 0:
                    total_dividends = div_rate * shares
                    doc.fcf_payout_ratio = (total_dividends / fcf) * 100

            # Dividend coverage (EPS / Dividend)
            if doc.dividend_coverage is None:
                eps = info.get("trailingEps")
                div_rate = info.get("dividendRate")
                if eps and div_rate and div_rate > 0:
                    doc.dividend_coverage = eps / div_rate

            # Ex-dividend date
            if doc.ex_dividend_date is None:
                ex_date = info.get("exDividendDate")
                if ex_date:
                    with contextlib.suppress(ValueError, TypeError, OSError):
                        doc.ex_dividend_date = datetime.fromtimestamp(ex_date).date()

            # Most recently declared dividend
            if getattr(doc, "last_dividend_value", None) is None:
                doc.last_dividend_value = info.get("lastDividendValue")  # type: ignore[attr-defined]
            if getattr(doc, "last_dividend_date", None) is None:
                last_div_ts = info.get("lastDividendDate")
                if last_div_ts:
                    with contextlib.suppress(ValueError, TypeError, OSError):
                        doc.last_dividend_date = datetime.fromtimestamp(last_div_ts).date()  # type: ignore[attr-defined]

            # Price data
            if doc.current_price is None:
                doc.current_price = info.get("currentPrice", info.get("regularMarketPrice"))

            if doc.market_cap is None:
                doc.market_cap = info.get("marketCap")

            if doc.fifty_two_week_high is None:
                doc.fifty_two_week_high = info.get("fiftyTwoWeekHigh")

            if doc.fifty_two_week_low is None:
                doc.fifty_two_week_low = info.get("fiftyTwoWeekLow")

            if doc.beta is None:
                doc.beta = info.get("beta")

            # Valuation metrics
            if doc.pe_ratio is None:
                doc.pe_ratio = info.get("trailingPE")

            if doc.forward_pe is None:
                doc.forward_pe = info.get("forwardPE")

            if doc.peg_ratio is None:
                doc.peg_ratio = info.get("pegRatio")

            if doc.price_to_book is None:
                doc.price_to_book = info.get("priceToBook")

            if doc.price_to_sales is None:
                doc.price_to_sales = info.get("priceToSalesTrailing12Months")

            if doc.ev_ebitda is None:
                doc.ev_ebitda = info.get("enterpriseToEbitda")

            # Financial health
            if doc.debt_to_equity is None:
                de = info.get("debtToEquity")
                if de is not None:
                    # yfinance returns as percentage, convert to ratio
                    doc.debt_to_equity = de / 100 if de > 10 else de

            if doc.current_ratio is None:
                doc.current_ratio = info.get("currentRatio")

            if doc.quick_ratio is None:
                doc.quick_ratio = info.get("quickRatio")

            # Profitability
            if doc.roe is None:
                doc.roe = self._safe_get(info, "returnOnEquity", multiplier=100)

            if doc.roa is None:
                doc.roa = self._safe_get(info, "returnOnAssets", multiplier=100)

            if doc.profit_margin is None:
                doc.profit_margin = self._safe_get(info, "profitMargins", multiplier=100)

            if doc.operating_margin is None:
                doc.operating_margin = self._safe_get(info, "operatingMargins", multiplier=100)

            if doc.gross_margin is None:
                doc.gross_margin = self._safe_get(info, "grossMargins", multiplier=100)

            # Growth
            if doc.revenue_growth is None:
                doc.revenue_growth = self._safe_get(info, "revenueGrowth", multiplier=100)

            if doc.earnings_growth is None:
                doc.earnings_growth = self._safe_get(info, "earningsGrowth", multiplier=100)

            # Analyst data
            if doc.target_price is None:
                doc.target_price = info.get("targetMeanPrice")

            if doc.target_upside is None and doc.target_price and doc.current_price:
                doc.target_upside = ((doc.target_price / doc.current_price) - 1) * 100

            if doc.analyst_rating is None:
                doc.analyst_rating = info.get("recommendationKey")

            if doc.num_analysts is None:
                doc.num_analysts = info.get("numberOfAnalystOpinions")

            # Description
            if not doc.description:
                doc.description = info.get("longBusinessSummary", "")[:500]

            # Fetch dividend history if needed
            if not doc.dividend_history or len(doc.dividend_history) < 10:
                doc = self._enrich_dividend_history(doc, ticker)

            # Calculate dividend growth rates
            doc = self._calculate_dividend_growth(doc)

            # Fetch price history and calculate returns
            doc = self._enrich_price_data(doc, ticker)

            # Update metadata
            doc.source = DataSource.YAHOO
            doc.last_updated = datetime.now()

            # Recalculate data quality
            doc.data_quality = self._calculate_quality(doc)

            logger.info(f"Enriched {doc.symbol}: quality={doc.data_quality}%")
            return doc

        except Exception as e:
            logger.error(f"Error enriching {doc.symbol}: {e}")
            return doc

    def fetch_document(self, symbol: str) -> StockDocument | None:
        """
        Fetch a complete StockDocument from yfinance.

        Creates a new document from scratch using yfinance data.

        Args:
            symbol: Stock ticker symbol.

        Returns:
            StockDocument or None if fetch failed.
        """
        if not YFINANCE_AVAILABLE:
            return None

        try:
            doc = StockDocument(symbol=symbol, name=symbol)
            return self.enrich_document(doc)
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None

    def _get_info_safe(self, ticker: yf.Ticker) -> dict[str, Any]:
        """Safely get ticker info with fallbacks."""
        try:
            info = ticker.info
            if info and isinstance(info, dict) and len(info) > 5:
                return cast(dict[str, Any], info)
        except Exception:  # noqa: S110
            pass

        # Try fast_info as fallback
        try:
            fast_info = ticker.fast_info
            if fast_info:
                return {
                    "currentPrice": getattr(fast_info, "last_price", None),
                    "marketCap": getattr(fast_info, "market_cap", None),
                    "fiftyTwoWeekHigh": getattr(fast_info, "year_high", None),
                    "fiftyTwoWeekLow": getattr(fast_info, "year_low", None),
                }
        except Exception:  # noqa: S110
            pass

        return {}

    def _safe_get(
        self,
        info: dict[str, Any],
        key: str,
        multiplier: float = 1.0,
        max_reasonable: float | None = None,
    ) -> float | None:
        """
        Safely get a value and optionally multiply it.

        Args:
            info: Dictionary with data
            key: Key to retrieve
            multiplier: Multiplier to apply (e.g., 100 for converting 0.05 to 5%)
            max_reasonable: Maximum reasonable value after multiplication.
                           If exceeded, assumes data was already multiplied.
        """
        val = info.get(key)
        if val is not None:
            try:
                result = float(val) * multiplier

                # If we have a max_reasonable limit and the result exceeds it,
                # assume the original value was already in the target format
                if max_reasonable is not None and result > max_reasonable:
                    # Value was probably already multiplied, use original
                    result = float(val)

                return result
            except (ValueError, TypeError):
                pass
        return None

    def _enrich_dividend_history(
        self,
        doc: StockDocument,
        ticker: yf.Ticker,
    ) -> StockDocument:
        """Enrich document with dividend history from yfinance."""
        try:
            dividends = ticker.dividends
            if dividends is None or dividends.empty:
                return doc

            # Convert to DividendRecord list
            existing_dates = {d.ex_date for d in doc.dividend_history}

            for date_idx, amount in dividends.items():
                try:
                    ex_date = date_idx.date() if hasattr(date_idx, "date") else date_idx
                    if ex_date not in existing_dates and amount > 0:
                        doc.dividend_history.append(
                            DividendRecord(
                                ex_date=ex_date,
                                payment_date=None,
                                amount=float(amount),
                            )
                        )
                except Exception:  # noqa: S112
                    continue

            # Sort by date
            doc.dividend_history.sort(key=lambda d: d.ex_date)

            # Update total years
            if doc.dividend_history:
                years = {d.ex_date.year for d in doc.dividend_history}
                doc.dividend_total_years = len(years)

        except Exception as e:
            logger.debug(f"Error getting dividend history for {doc.symbol}: {e}")

        return doc

    def _calculate_dividend_growth(self, doc: StockDocument) -> StockDocument:
        """Calculate dividend CAGR from history."""
        if not doc.dividend_history or len(doc.dividend_history) < 8:
            return doc

        try:
            # Group dividends by year
            yearly: dict[int, float] = {}
            for div in doc.dividend_history:
                year = div.ex_date.year
                yearly[year] = yearly.get(year, 0) + div.amount

            years_sorted = sorted(yearly.keys())
            current_year = datetime.now().year

            # Exclude incomplete current year
            if years_sorted and years_sorted[-1] == current_year:
                years_sorted = years_sorted[:-1]

            if len(years_sorted) < 2:
                return doc

            latest_year = years_sorted[-1]
            latest_div = yearly[latest_year]

            # 5-year CAGR
            if len(years_sorted) >= 6:
                year_5_ago = years_sorted[-6]
                div_5_ago = yearly[year_5_ago]
                if div_5_ago > 0:
                    doc.dividend_cagr_5y = ((latest_div / div_5_ago) ** (1 / 5) - 1) * 100

            # 10-year CAGR
            if len(years_sorted) >= 11:
                year_10_ago = years_sorted[-11]
                div_10_ago = yearly[year_10_ago]
                if div_10_ago > 0:
                    doc.dividend_cagr_10y = ((latest_div / div_10_ago) ** (1 / 10) - 1) * 100

        except Exception as e:
            logger.debug(f"Error calculating dividend growth for {doc.symbol}: {e}")

        return doc

    def _enrich_price_data(  # noqa: C901
        self,
        doc: StockDocument,
        ticker: yf.Ticker,
    ) -> StockDocument:
        """Enrich with price history and calculate returns."""
        try:
            # Get 5 years of price history
            hist = ticker.history(period="5y")
            if hist is None or hist.empty:
                return doc

            # Only add if we don't have much price history
            if len(doc.price_history) < 100:
                existing_dates = {p.date for p in doc.price_history}

                for date_idx, row in hist.iterrows():
                    try:
                        price_date = date_idx.date() if hasattr(date_idx, "date") else date_idx
                        if price_date not in existing_dates:
                            doc.price_history.append(
                                PriceHistory(
                                    date=price_date,
                                    open=float(row.get("Open", 0)),
                                    high=float(row.get("High", 0)),
                                    low=float(row.get("Low", 0)),
                                    close=float(row.get("Close", 0)),
                                    volume=int(row.get("Volume", 0)),
                                    adjusted_close=float(row.get("Adj Close", row.get("Close", 0))),
                                )
                            )
                    except Exception:  # noqa: S112
                        continue

                # Sort by date (newest first)
                doc.price_history.sort(key=lambda p: p.date, reverse=True)

            # Calculate returns using adjusted close
            if len(hist) > 0:
                current_price = (
                    hist["Adj Close"].iloc[-1]
                    if "Adj Close" in hist.columns
                    else hist["Close"].iloc[-1]
                )

                # 1-year return
                if len(hist) >= 252:
                    price_1y_ago = (
                        hist["Adj Close"].iloc[-252]
                        if "Adj Close" in hist.columns
                        else hist["Close"].iloc[-252]
                    )
                    if price_1y_ago > 0:
                        doc.price_return_1y = ((current_price / price_1y_ago) - 1) * 100

                # 5-year return
                if len(hist) >= 1260:
                    price_5y_ago = (
                        hist["Adj Close"].iloc[0]
                        if "Adj Close" in hist.columns
                        else hist["Close"].iloc[0]
                    )
                    if price_5y_ago > 0:
                        doc.price_return_5y = ((current_price / price_5y_ago) - 1) * 100

                # Calculate total return (with dividends)
                if doc.dividend_history and doc.price_return_1y is not None:
                    one_year_ago = datetime.now().date().replace(year=datetime.now().year - 1)
                    yearly_divs = sum(
                        d.amount for d in doc.dividend_history if d.ex_date >= one_year_ago
                    )
                    price_1y_ago = (
                        hist["Close"].iloc[-252] if len(hist) >= 252 else hist["Close"].iloc[0]
                    )
                    if price_1y_ago > 0:
                        div_return = (yearly_divs / price_1y_ago) * 100
                        doc.total_return_1y = doc.price_return_1y + div_return

        except Exception as e:
            logger.debug(f"Error getting price history for {doc.symbol}: {e}")

        return doc

    def _calculate_quality(self, doc: StockDocument) -> float:  # noqa: C901
        """Calculate data quality score (0-100)."""
        score = 0.0

        # Basic identity (10 points)
        if doc.name and doc.name != doc.symbol:
            score += 3
        if doc.sector != "Unknown":
            score += 3
        if doc.industry != "Unknown":
            score += 2
        if doc.exchange != "Unknown":
            score += 2

        # Dividend data (25 points)
        if doc.dividend_yield is not None:
            score += 5
        if doc.annual_dividend is not None:
            score += 5
        if doc.dividend_streak_years is not None:
            score += 5
        if doc.payout_ratio is not None:
            score += 3
        if doc.dividend_cagr_5y is not None:
            score += 4
        if doc.dividend_coverage is not None:
            score += 3

        # Price data (15 points)
        if doc.current_price is not None:
            score += 5
        if doc.market_cap is not None:
            score += 3
        if doc.fifty_two_week_high is not None:
            score += 2
        if doc.fifty_two_week_low is not None:
            score += 2
        if doc.beta is not None:
            score += 3

        # Valuation (15 points)
        if doc.pe_ratio is not None:
            score += 3
        if doc.forward_pe is not None:
            score += 3
        if doc.peg_ratio is not None:
            score += 3
        if doc.price_to_book is not None:
            score += 3
        if doc.ev_ebitda is not None:
            score += 3

        # Financial health (10 points)
        if doc.debt_to_equity is not None:
            score += 4
        if doc.current_ratio is not None:
            score += 3
        if doc.quick_ratio is not None:
            score += 3

        # Profitability (10 points)
        if doc.roe is not None:
            score += 3
        if doc.roa is not None:
            score += 2
        if doc.profit_margin is not None:
            score += 3
        if doc.operating_margin is not None:
            score += 2

        # Performance & Analyst (10 points)
        if doc.price_return_1y is not None:
            score += 3
        if doc.target_price is not None:
            score += 3
        if doc.analyst_rating is not None:
            score += 2
        if doc.num_analysts is not None:
            score += 2

        # Historical data (5 points)
        if len(doc.dividend_history) >= 20:
            score += 2.5
        if len(doc.price_history) >= 100:
            score += 2.5

        return min(100.0, score)

    def enrich_batch(
        self,
        documents: list[StockDocument],
        progress_callback: Any | None = None,
    ) -> list[StockDocument]:
        """
        Enrich multiple documents with yfinance data.

        Args:
            documents: List of documents to enrich.
            progress_callback: Optional callback(current, total) for progress.

        Returns:
            List of enriched documents.
        """
        enriched = []
        total = len(documents)

        for i, doc in enumerate(documents):
            try:
                enriched_doc = self.enrich_document(doc)
                enriched.append(enriched_doc)
            except Exception as e:
                logger.error(f"Error enriching {doc.symbol}: {e}")
                enriched.append(doc)

            if progress_callback:
                progress_callback(i + 1, total)

        return enriched
