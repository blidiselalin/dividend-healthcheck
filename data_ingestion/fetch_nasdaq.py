"""
Automated data fetcher for Nasdaq.com historical data.

Downloads historical prices and dividend history from Nasdaq public pages.
Exports to CSV format compatible with the ingestion pipeline.

Note: This uses Nasdaq's public API endpoints which may have rate limits.
"""

from __future__ import annotations

import csv
import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from data_ingestion.base import BaseFetcher

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class NasdaqFetcher(BaseFetcher):
    """
    Fetches historical stock data from Nasdaq.com.

    Uses Nasdaq's public API endpoints for:
    - Historical price data
    - Dividend payment history
    - Company information
    """

    # Nasdaq API endpoints
    BASE_URL = "https://api.nasdaq.com/api"

    ENDPOINTS: ClassVar[dict[str, str]] = {
        "historical": "/quote/{symbol}/historical",
        "dividends": "/quote/{symbol}/dividends",
        "info": "/quote/{symbol}/info",
        "summary": "/quote/{symbol}/summary",
    }

    def __init__(self, output_dir: str = "data/downloads/nasdaq") -> None:
        """
        Initialize fetcher.

        Args:
            output_dir: Directory to save downloaded files.
        """
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests required. Install with: pip install requests")

        super().__init__(request_delay=1.5)

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Add Nasdaq-specific headers
        if self.session:
            self.session.headers.update(
                {
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://www.nasdaq.com",
                    "Referer": "https://www.nasdaq.com/",
                }
            )

    def _fetch_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        retries: int = MAX_RETRIES,
    ) -> dict[str, Any] | None:
        """Fetch JSON data from API."""
        if self.session is None:
            return None
        self._rate_limit()

        for attempt in range(retries):
            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()

                data = response.json()

                # Nasdaq API wraps data in a status/data structure
                if isinstance(data, dict):
                    if data.get("status", {}).get("rCode") == 200:
                        return data.get("data", data)  # type: ignore[no-any-return]
                    elif "data" in data:
                        return data["data"]  # type: ignore[no-any-return]

                return data  # type: ignore[no-any-return]

            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(2**attempt)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error for {url}: {e}")
                return None

        return None

    def fetch_historical_prices(
        self,
        symbol: str,
        years: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Fetch historical price data.

        Args:
            symbol: Stock ticker symbol.
            years: Number of years of history to fetch.

        Returns:
            List of price records.
        """
        url = f"{self.BASE_URL}{self.ENDPOINTS['historical'].format(symbol=symbol.upper())}"

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=years * 365)

        params = {
            "assetclass": "stocks",
            "fromdate": start_date.strftime("%Y-%m-%d"),
            "todate": end_date.strftime("%Y-%m-%d"),
            "limit": 9999,
        }

        logger.info(f"Fetching historical prices for {symbol}")

        data = self._fetch_json(url, params)
        if not data:
            return []

        prices = []

        # Parse response structure
        rows = data.get("tradesTable", {}).get("rows", [])
        if not rows and isinstance(data, dict):
            # Try alternative structure
            rows = data.get("rows", [])

        for row in rows:
            try:
                record = {
                    "date": self._parse_date(row.get("date", "")),
                    "close": self._parse_currency(row.get("close", "")),
                    "volume": self._parse_volume(row.get("volume", "")),
                    "open": self._parse_currency(row.get("open", "")),
                    "high": self._parse_currency(row.get("high", "")),
                    "low": self._parse_currency(row.get("low", "")),
                }

                if record["date"] and record["close"]:
                    prices.append(record)

            except Exception as e:
                logger.debug(f"Error parsing price row: {e}")

        logger.info(f"Found {len(prices)} price records for {symbol}")
        return prices

    def fetch_dividend_history(self, symbol: str) -> list[dict[str, Any]]:
        """
        Fetch dividend payment history.

        Args:
            symbol: Stock ticker symbol.

        Returns:
            List of dividend records.
        """
        url = f"{self.BASE_URL}{self.ENDPOINTS['dividends'].format(symbol=symbol.upper())}"

        params = {
            "assetclass": "stocks",
        }

        logger.info(f"Fetching dividend history for {symbol}")

        data = self._fetch_json(url, params)
        if not data:
            return []

        dividends = []

        # Parse response structure
        rows = data.get("dividends", {}).get("rows", [])
        if not rows:
            rows = data.get("rows", [])

        for row in rows:
            try:
                record = {
                    "symbol": symbol.upper(),
                    "ex_date": self._parse_date(row.get("exOrEffDate", row.get("exDate", ""))),
                    "payment_date": self._parse_date(row.get("paymentDate", "")),
                    "record_date": self._parse_date(row.get("recordDate", "")),
                    "amount": self._parse_currency(row.get("amount", row.get("cash", ""))),
                    "type": row.get("type", "Cash"),
                }

                if record["ex_date"] and record["amount"]:
                    dividends.append(record)

            except Exception as e:
                logger.debug(f"Error parsing dividend row: {e}")

        logger.info(f"Found {len(dividends)} dividend records for {symbol}")
        return dividends

    def fetch_company_info(self, symbol: str) -> dict[str, Any] | None:
        """
        Fetch company information.

        Args:
            symbol: Stock ticker symbol.

        Returns:
            Dict with company data.
        """
        url = f"{self.BASE_URL}{self.ENDPOINTS['info'].format(symbol=symbol.upper())}"

        params = {"assetclass": "stocks"}

        logger.info(f"Fetching company info for {symbol}")

        data = self._fetch_json(url, params)
        if not data:
            return None

        info = {
            "symbol": symbol.upper(),
            "name": data.get("companyName", ""),
            "exchange": data.get("exchange", ""),
            "sector": data.get("sector", ""),
            "industry": data.get("industry", ""),
        }

        # Try to get summary data too
        summary_url = f"{self.BASE_URL}{self.ENDPOINTS['summary'].format(symbol=symbol.upper())}"
        summary = self._fetch_json(summary_url, params)

        if summary:
            summary_data = summary.get("summaryData", {})

            # Extract key metrics
            for key, value in summary_data.items():
                val = value.get("value", "") if isinstance(value, dict) else value

                key_lower = key.lower()
                if "yield" in key_lower:
                    info["dividend_yield"] = self._parse_percent(str(val))
                elif "p/e" in key_lower or "pe ratio" in key_lower:
                    info["pe_ratio"] = self._parse_number(str(val))
                elif "market cap" in key_lower:
                    info["market_cap"] = self._parse_market_cap(str(val))
                elif "eps" in key_lower:
                    info["eps"] = self._parse_currency(str(val))

        return info

    def _parse_date(self, value: str) -> str | None:
        """Parse date to ISO format."""
        if not value or value.lower() in ["n/a", "na", "-", ""]:
            return None

        formats = [
            "%m/%d/%Y",
            "%Y-%m-%d",
            "%b %d, %Y",
            "%B %d, %Y",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(value.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return None

    def _parse_currency(self, value: str) -> float | None:
        """Parse currency value."""
        if not value or str(value).lower() in ["n/a", "na", "-", ""]:
            return None

        cleaned = str(value).replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _parse_number(self, value: str) -> float | None:
        """Parse numeric value."""
        return self._parse_currency(value)

    def _parse_percent(self, value: str) -> float | None:
        """Parse percentage value."""
        if not value:
            return None

        cleaned = str(value).replace("%", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _parse_volume(self, value: str) -> int | None:
        """Parse volume value."""
        if not value or str(value).lower() in ["n/a", "na", "-", ""]:
            return None

        cleaned = str(value).replace(",", "").strip()
        try:
            return int(float(cleaned))
        except ValueError:
            return None

    def _parse_market_cap(self, value: str) -> float | None:
        """Parse market cap with suffix."""
        if not value:
            return None

        value = str(value).upper().strip()

        multipliers = {
            "T": 1e12,
            "B": 1e9,
            "M": 1e6,
            "K": 1e3,
        }

        for suffix, mult in multipliers.items():
            if suffix in value:
                num_str = value.replace(suffix, "").replace("$", "").replace(",", "").strip()
                try:
                    return float(num_str) * mult
                except ValueError:
                    pass

        return self._parse_currency(value)

    def download_stock(
        self,
        symbol: str,
        include_prices: bool = True,
        include_dividends: bool = True,
        include_info: bool = True,
    ) -> dict[str, Any]:
        """
        Download all data for a single stock.

        Args:
            symbol: Stock ticker symbol.
            include_prices: Download historical prices.
            include_dividends: Download dividend history.
            include_info: Download company info.

        Returns:
            Dict with all downloaded data.
        """
        result: dict[str, Any] = {"symbol": symbol.upper()}

        if include_info:
            info = self.fetch_company_info(symbol)
            if info:
                result["info"] = info

        if include_prices:
            prices = self.fetch_historical_prices(symbol)
            if prices:
                result["prices"] = prices
                self._save_prices_csv(symbol, prices)

        if include_dividends:
            dividends = self.fetch_dividend_history(symbol)
            if dividends:
                result["dividends"] = dividends
                self._save_dividends_csv(symbol, dividends)

        return result

    def download_multiple(
        self,
        symbols: list[str],
        include_prices: bool = True,
        include_dividends: bool = True,
        include_info: bool = True,
    ) -> dict[str, int]:
        """
        Download data for multiple stocks.

        Args:
            symbols: List of stock ticker symbols.
            include_prices: Download historical prices.
            include_dividends: Download dividend history.
            include_info: Download company info.

        Returns:
            Stats dict with counts.
        """
        stats = {
            "symbols_processed": 0,
            "prices_downloaded": 0,
            "dividends_downloaded": 0,
            "info_downloaded": 0,
            "errors": 0,
        }

        all_info = []

        for symbol in symbols:
            try:
                logger.info(
                    f"Processing {symbol} ({stats['symbols_processed'] + 1}/{len(symbols)})"
                )

                result = self.download_stock(
                    symbol,
                    include_prices=include_prices,
                    include_dividends=include_dividends,
                    include_info=include_info,
                )

                stats["symbols_processed"] += 1

                if result.get("prices"):
                    stats["prices_downloaded"] += len(result["prices"])

                if result.get("dividends"):
                    stats["dividends_downloaded"] += len(result["dividends"])

                if result.get("info"):
                    all_info.append(result["info"])
                    stats["info_downloaded"] += 1

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                stats["errors"] += 1

        # Save combined info file
        if all_info:
            self._save_info_json(all_info)

        logger.info(f"Download complete: {stats}")
        return stats

    def _save_prices_csv(self, symbol: str, prices: list[dict[str, Any]]) -> None:
        """Save price data to CSV."""
        filepath = self.output_dir / f"{symbol.upper()}_historical.csv"

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["date", "close", "volume", "open", "high", "low"],
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(prices)

        logger.debug(f"Saved {len(prices)} price records to {filepath}")

    def _save_dividends_csv(self, symbol: str, dividends: list[dict[str, Any]]) -> None:
        """Save dividend data to CSV."""
        filepath = self.output_dir / f"{symbol.upper()}_dividends.csv"

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "symbol",
                    "ex_date",
                    "payment_date",
                    "record_date",
                    "amount",
                    "type",
                ],
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(dividends)

        logger.debug(f"Saved {len(dividends)} dividend records to {filepath}")

    def _save_info_json(self, info_list: list[dict[str, Any]]) -> None:
        """Save company info to JSON."""
        filepath = self.output_dir / "company_info.json"

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(info_list, f, indent=2)

        logger.info(f"Saved {len(info_list)} company records to {filepath}")


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Fetch data from Nasdaq.com")
    parser.add_argument(
        "symbols",
        nargs="+",
        help="Stock symbols to download",
    )
    parser.add_argument(
        "--output-dir",
        default="data/downloads/nasdaq",
        help="Output directory for files",
    )
    parser.add_argument(
        "--no-prices",
        action="store_true",
        help="Skip historical prices",
    )
    parser.add_argument(
        "--no-dividends",
        action="store_true",
        help="Skip dividend history",
    )
    parser.add_argument(
        "--no-info",
        action="store_true",
        help="Skip company info",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        fetcher = NasdaqFetcher(output_dir=args.output_dir)

        # Clean symbols
        symbols = [s.upper().strip() for s in args.symbols]

        stats = fetcher.download_multiple(
            symbols,
            include_prices=not args.no_prices,
            include_dividends=not args.no_dividends,
            include_info=not args.no_info,
        )

        print("\nDownload complete!")
        print(f"  Symbols processed: {stats['symbols_processed']}")
        print(f"  Price records: {stats['prices_downloaded']}")
        print(f"  Dividend records: {stats['dividends_downloaded']}")
        print(f"  Company info: {stats['info_downloaded']}")
        if stats["errors"]:
            print(f"  Errors: {stats['errors']}")
        print(f"\nFiles saved to: {args.output_dir}")

    except ImportError as e:
        print(f"Error: {e}")
        print("Install required packages: pip install requests")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
