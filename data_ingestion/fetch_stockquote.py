"""
Automated data fetcher for dividend stock data.

Downloads dividend fundamentals, streaks, and history from public sources
and exports to CSV format.

Sources:
- yfinance - Detailed stock data and history
- Central config for stock lists
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

# Import stock lists from central config
try:
    from config import DIVIDEND_KINGS, DIVIDEND_ARISTOCRATS
except ImportError:
    DIVIDEND_KINGS = []
    DIVIDEND_ARISTOCRATS = []

from data_ingestion.base import BaseFetcher

logger = logging.getLogger(__name__)


class StockQuoteFetcher(BaseFetcher):
    """
    Fetches dividend data from public sources.
    
    Data available:
    - Dividend Kings list with streaks
    - Dividend Aristocrats list  
    - Individual stock dividend history
    - Stock fundamentals (yield, payout ratio, etc.)
    """
    
    def __init__(self, output_dir: str = "data/downloads/stockquote"):
        """
        Initialize fetcher.
        
        Args:
            output_dir: Directory to save downloaded files.
        """
        super().__init__()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _symbols_to_stock_list(
        self, 
        symbols: List[str], 
        category: str
    ) -> List[Dict[str, Any]]:
        """
        Convert symbol list to stock metadata list.
        
        Metadata (name, sector) is fetched from yfinance if available.
        """
        stocks = []
        for symbol in symbols:
            stock = {
                "symbol": symbol,
                "name": symbol,
                "streak": None,
                "sector": "",
                "category": category,
                "fetched_at": datetime.now().isoformat(),
            }
            stocks.append(stock)
        return stocks
    
    def fetch_dividend_kings(self) -> List[Dict[str, Any]]:
        """
        Fetch list of Dividend Kings with streak data.
        
        Returns:
            List of dicts with symbol, name, streak, etc.
        """
        logger.info("Fetching Dividend Kings list from config...")
        stocks = self._symbols_to_stock_list(list(DIVIDEND_KINGS), "King")
        logger.info(f"Loaded {len(stocks)} Dividend Kings")
        return stocks
    
    def fetch_dividend_aristocrats(self) -> List[Dict[str, Any]]:
        """Fetch list of Dividend Aristocrats from config."""
        logger.info("Fetching Dividend Aristocrats list from config...")
        stocks = self._symbols_to_stock_list(list(DIVIDEND_ARISTOCRATS), "Aristocrat")
        logger.info(f"Loaded {len(stocks)} Dividend Aristocrats")
        return stocks
    
    def fetch_stock_details(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch detailed data for a single stock using yfinance.
        
        Args:
            symbol: Stock ticker symbol.
            
        Returns:
            Dict with fundamentals and dividend data.
        """
        if not YFINANCE_AVAILABLE:
            logger.warning("yfinance not available, skipping stock details")
            return None
        
        self._rate_limit()
        logger.info(f"Fetching details for {symbol}")
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            if not info:
                return None
            
            data = {
                "symbol": symbol.upper(),
                "name": info.get("longName", info.get("shortName", symbol)),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "dividend_yield": info.get("dividendYield"),
                "annual_dividend": info.get("dividendRate"),
                "payout_ratio": info.get("payoutRatio"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "market_cap": info.get("marketCap"),
                "price": info.get("currentPrice", info.get("regularMarketPrice")),
                "52_week_high": info.get("fiftyTwoWeekHigh"),
                "52_week_low": info.get("fiftyTwoWeekLow"),
                "beta": info.get("beta"),
                "fetched_at": datetime.now().isoformat(),
            }
            
            return data
            
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None
    
    def fetch_dividend_history(
        self, 
        symbol: str, 
        years: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetch dividend payment history for a stock.
        
        Args:
            symbol: Stock ticker symbol.
            years: Years of history to fetch.
            
        Returns:
            List of dividend payment records.
        """
        if not YFINANCE_AVAILABLE:
            logger.warning("yfinance not available, skipping dividend history")
            return []
        
        self._rate_limit()
        logger.info(f"Fetching dividend history for {symbol}")
        
        try:
            ticker = yf.Ticker(symbol)
            dividends = ticker.dividends
            
            if dividends is None or dividends.empty:
                return []
            
            history = []
            for dt, amount in dividends.items():
                history.append({
                    "symbol": symbol.upper(),
                    "ex_date": dt.strftime("%Y-%m-%d"),
                    "amount": float(amount),
                    "year": dt.year,
                })
            
            # Filter to requested years
            cutoff_year = datetime.now().year - years
            history = [h for h in history if h["year"] >= cutoff_year]
            
            return history
            
        except Exception as e:
            logger.error(f"Error fetching dividend history for {symbol}: {e}")
            return []
    
    def save_kings_to_csv(self, stocks: List[Dict[str, Any]]) -> str:
        """Save Dividend Kings to CSV."""
        filepath = self.output_dir / "dividend_kings.csv"
        
        if not stocks:
            logger.warning("No stocks to save")
            return ""
        
        fieldnames = ["symbol", "name", "streak", "sector", "category", "fetched_at"]
        
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(stocks)
        
        logger.info(f"Saved {len(stocks)} stocks to {filepath}")
        return str(filepath)
    
    def save_aristocrats_to_csv(self, stocks: List[Dict[str, Any]]) -> str:
        """Save Dividend Aristocrats to CSV."""
        filepath = self.output_dir / "dividend_aristocrats.csv"
        
        if not stocks:
            return ""
        
        fieldnames = ["symbol", "name", "streak", "sector", "category", "fetched_at"]
        
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(stocks)
        
        logger.info(f"Saved {len(stocks)} stocks to {filepath}")
        return str(filepath)
    
    def save_stock_details_to_csv(self, stocks: List[Dict[str, Any]]) -> str:
        """Save stock details to CSV."""
        filepath = self.output_dir / "stock_fundamentals.csv"
        
        if not stocks:
            return ""
        
        fieldnames = [
            "symbol", "name", "sector", "industry", "dividend_yield",
            "annual_dividend", "payout_ratio", "pe_ratio", "forward_pe",
            "market_cap", "price", "52_week_high", "52_week_low", "beta",
            "fetched_at"
        ]
        
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(stocks)
        
        logger.info(f"Saved {len(stocks)} stock details to {filepath}")
        return str(filepath)
    
    def save_dividend_history_to_csv(
        self, 
        history: List[Dict[str, Any]], 
        symbol: Optional[str] = None
    ) -> str:
        """Save dividend history to CSV."""
        if symbol:
            filepath = self.output_dir / f"dividends_{symbol.lower()}.csv"
        else:
            filepath = self.output_dir / "dividend_history.csv"
        
        if not history:
            return ""
        
        fieldnames = ["symbol", "ex_date", "amount", "year"]
        
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(history)
        
        logger.info(f"Saved {len(history)} dividend records to {filepath}")
        return str(filepath)
    
    def download_all(
        self,
        symbols: Optional[List[str]] = None,
        include_history: bool = True,
    ) -> Dict[str, Any]:
        """
        Download all available data.
        
        Args:
            symbols: Specific symbols to download details for.
                    If None, downloads Kings and Aristocrats.
            include_history: Whether to download dividend history.
            
        Returns:
            Dict with download statistics.
        """
        stats = {
            "kings": 0,
            "aristocrats": 0,
            "stock_details": 0,
            "dividend_records": 0,
            "files_created": [],
        }
        
        # Fetch lists
        kings = self.fetch_dividend_kings()
        stats["kings"] = len(kings)
        if kings:
            filepath = self.save_kings_to_csv(kings)
            if filepath:
                stats["files_created"].append(filepath)
        
        aristocrats = self.fetch_dividend_aristocrats()
        stats["aristocrats"] = len(aristocrats)
        if aristocrats:
            filepath = self.save_aristocrats_to_csv(aristocrats)
            if filepath:
                stats["files_created"].append(filepath)
        
        # Determine symbols to fetch details for
        if symbols is None:
            all_symbols = set(s["symbol"] for s in kings + aristocrats)
            symbols = list(all_symbols)
        
        # Fetch stock details
        stock_details = []
        all_history = []
        
        for i, symbol in enumerate(symbols):
            logger.info(f"Processing {symbol} ({i+1}/{len(symbols)})")
            
            # Get details
            details = self.fetch_stock_details(symbol)
            if details:
                stock_details.append(details)
            
            # Get dividend history
            if include_history:
                history = self.fetch_dividend_history(symbol)
                all_history.extend(history)
        
        stats["stock_details"] = len(stock_details)
        if stock_details:
            filepath = self.save_stock_details_to_csv(stock_details)
            if filepath:
                stats["files_created"].append(filepath)
        
        stats["dividend_records"] = len(all_history)
        if all_history:
            filepath = self.save_dividend_history_to_csv(all_history)
            if filepath:
                stats["files_created"].append(filepath)
        
        logger.info(f"Download complete: {stats}")
        return stats


def main():
    """CLI entry point for testing."""
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    parser = argparse.ArgumentParser(description="Download dividend stock data")
    parser.add_argument(
        "--output", "-o",
        default="data/downloads/stockquote",
        help="Output directory"
    )
    parser.add_argument(
        "--symbols", "-s",
        nargs="+",
        help="Specific symbols to download"
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Skip dividend history download"
    )
    
    args = parser.parse_args()
    
    fetcher = StockQuoteFetcher(output_dir=args.output)
    stats = fetcher.download_all(
        symbols=args.symbols,
        include_history=not args.no_history,
    )
    
    print(f"\nDownload Statistics:")
    print(f"  Dividend Kings: {stats['kings']}")
    print(f"  Dividend Aristocrats: {stats['aristocrats']}")
    print(f"  Stock Details: {stats['stock_details']}")
    print(f"  Dividend Records: {stats['dividend_records']}")
    print(f"\nFiles created:")
    for f in stats["files_created"]:
        print(f"  - {f}")


if __name__ == "__main__":
    main()
