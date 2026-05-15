"""
Data downloaders for public stock data sources.

Supports manual bulk download from:
- StockQuote.io: Dividend history and stock fundamentals
- Nasdaq: Historical price data and company information
"""

import csv
import json
import os
import re
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator
import logging

from .models import StockDocument, PriceHistory, DividendRecord, DataSource

# Import config for default paths
try:
    from config import DOWNLOADS_DIR
    DEFAULT_DOWNLOADS_DIR = str(DOWNLOADS_DIR)
except ImportError:
    DEFAULT_DOWNLOADS_DIR = "data/downloads"

logger = logging.getLogger(__name__)


class BaseDownloader(ABC):
    """Base class for stock data downloaders."""
    
    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir or DEFAULT_DOWNLOADS_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    @abstractmethod
    def parse_file(self, filepath: Path) -> List[StockDocument]:
        """Parse a downloaded file into StockDocuments."""
        pass
    
    @abstractmethod
    def get_source(self) -> DataSource:
        """Return the data source enum."""
        pass
    
    def process_directory(self, subdir: str = "") -> Iterator[StockDocument]:
        """Process all files in the download directory."""
        target_dir = self.data_dir / subdir if subdir else self.data_dir
        
        if not target_dir.exists():
            logger.warning(f"Directory not found: {target_dir}")
            return
        
        for filepath in target_dir.iterdir():
            if filepath.is_file() and self._is_valid_file(filepath):
                try:
                    documents = self.parse_file(filepath)
                    for doc in documents:
                        yield doc
                except Exception as e:
                    logger.error(f"Error processing {filepath}: {e}")
    
    def _is_valid_file(self, filepath: Path) -> bool:
        """Check if file should be processed."""
        return filepath.suffix.lower() in [".csv", ".json", ".txt"]


class StockQuoteDownloader(BaseDownloader):
    """
    Downloader for StockQuote.io data.
    
    Expected file formats:
    
    1. Dividend History CSV (dividend_history.csv):
       Symbol,Ex-Date,Payment-Date,Amount,Yield
       KO,2024-03-14,2024-04-01,0.485,3.12
       
    2. Stock Fundamentals CSV (fundamentals.csv):
       Symbol,Name,Sector,Industry,MarketCap,PE,DivYield,PayoutRatio
       KO,Coca-Cola,Consumer Defensive,Beverages,265000000000,25.4,3.12,75.2
       
    3. Dividend Streak CSV (dividend_streaks.csv):
       Symbol,Name,ConsecutiveYears,Category
       KO,Coca-Cola,62,King
    """
    
    def __init__(self, data_dir: str = None):
        super().__init__(data_dir or f"{DEFAULT_DOWNLOADS_DIR}/stockquote")
        self._documents: Dict[str, StockDocument] = {}
    
    def get_source(self) -> DataSource:
        return DataSource.STOCKQUOTE_IO
    
    def parse_file(self, filepath: Path) -> List[StockDocument]:
        """Parse a StockQuote.io file."""
        filename = filepath.name.lower()
        
        if "dividend_history" in filename or "dividends" in filename:
            return self._parse_dividend_history(filepath)
        elif "fundamental" in filename or "stocks" in filename:
            return self._parse_fundamentals(filepath)
        elif "streak" in filename or "kings" in filename or "aristocrats" in filename:
            return self._parse_dividend_streaks(filepath)
        else:
            logger.info(f"Unknown file type: {filename}, attempting auto-detect")
            return self._auto_parse(filepath)
    
    def _parse_dividend_history(self, filepath: Path) -> List[StockDocument]:
        """Parse dividend history CSV."""
        documents: Dict[str, StockDocument] = {}
        
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                symbol = self._clean_symbol(row.get("Symbol", row.get("symbol", "")))
                if not symbol:
                    continue
                
                # Get or create document
                if symbol not in documents:
                    documents[symbol] = StockDocument(
                        symbol=symbol,
                        name=row.get("Name", row.get("name", symbol)),
                        source=self.get_source(),
                    )
                
                # Parse dividend record
                try:
                    ex_date = self._parse_date(row.get("Ex-Date", row.get("ex_date", row.get("ExDate", ""))))
                    payment_date = self._parse_date(row.get("Payment-Date", row.get("payment_date", row.get("PaymentDate", ""))))
                    amount = self._parse_float(row.get("Amount", row.get("amount", row.get("Dividend", "0"))))
                    
                    if ex_date and amount:
                        documents[symbol].dividend_history.append(
                            DividendRecord(
                                ex_date=ex_date,
                                payment_date=payment_date,
                                amount=amount,
                            )
                        )
                except Exception as e:
                    logger.debug(f"Error parsing dividend row: {e}")
        
        return list(documents.values())
    
    def _parse_fundamentals(self, filepath: Path) -> List[StockDocument]:
        """Parse stock fundamentals CSV."""
        documents = []
        
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                symbol = self._clean_symbol(row.get("Symbol", row.get("symbol", row.get("Ticker", ""))))
                if not symbol:
                    continue
                
                doc = StockDocument(
                    symbol=symbol,
                    name=row.get("Name", row.get("name", row.get("Company", symbol))),
                    sector=row.get("Sector", row.get("sector", "Unknown")),
                    industry=row.get("Industry", row.get("industry", "Unknown")),
                    exchange=row.get("Exchange", row.get("exchange", "Unknown")),
                    dividend_yield=self._parse_float(row.get("DivYield", row.get("Yield", row.get("dividend_yield")))),
                    annual_dividend=self._parse_float(row.get("AnnualDividend", row.get("annual_dividend"))),
                    payout_ratio=self._parse_payout_ratio(row.get("PayoutRatio", row.get("payout_ratio"))),
                    current_price=self._parse_float(row.get("Price", row.get("price", row.get("LastPrice")))),
                    market_cap=self._parse_float(row.get("MarketCap", row.get("market_cap"))),
                    pe_ratio=self._parse_float(row.get("PE", row.get("pe_ratio", row.get("P/E")))),
                    source=self.get_source(),
                )
                
                documents.append(doc)
        
        return documents
    
    def _parse_dividend_streaks(self, filepath: Path) -> List[StockDocument]:
        """Parse dividend streak CSV."""
        documents = []
        
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                symbol = self._clean_symbol(row.get("Symbol", row.get("symbol", row.get("Ticker", ""))))
                if not symbol:
                    continue
                
                streak = self._parse_int(row.get("ConsecutiveYears", row.get("Years", row.get("Streak", row.get("streak", "0")))))
                
                doc = StockDocument(
                    symbol=symbol,
                    name=row.get("Name", row.get("name", symbol)),
                    sector=row.get("Sector", row.get("sector", "Unknown")),
                    industry=row.get("Industry", row.get("industry", "Unknown")),
                    dividend_streak_years=streak,
                    source=self.get_source(),
                )
                
                # Set category in notes
                category = row.get("Category", row.get("category", ""))
                if category:
                    doc.notes = f"Category: {category}"
                
                documents.append(doc)
        
        return documents
    
    def _auto_parse(self, filepath: Path) -> List[StockDocument]:
        """Auto-detect file format and parse."""
        with open(filepath, "r", encoding="utf-8") as f:
            first_line = f.readline().lower()
            
            if "ex-date" in first_line or "ex_date" in first_line or "exdate" in first_line:
                f.seek(0)
                return self._parse_dividend_history(filepath)
            elif "streak" in first_line or "consecutive" in first_line:
                f.seek(0)
                return self._parse_dividend_streaks(filepath)
            else:
                f.seek(0)
                return self._parse_fundamentals(filepath)
    
    def _clean_symbol(self, symbol: str) -> str:
        """Clean and validate stock symbol."""
        if not symbol:
            return ""
        return symbol.strip().upper().replace("$", "")
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date from various formats."""
        if not date_str or date_str.lower() in ["n/a", "null", "-", ""]:
            return None
        
        date_str = date_str.strip()
        
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%b %d, %Y",
            "%B %d, %Y",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        return None
    
    def _parse_float(self, value: Any) -> Optional[float]:
        """Parse float from various formats."""
        if value is None or value == "" or str(value).lower() in ["n/a", "null", "-"]:
            return None
        
        try:
            # Remove currency symbols, commas, percent signs
            cleaned = re.sub(r"[$,%]", "", str(value).strip())
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    
    def _parse_int(self, value: Any) -> Optional[int]:
        """Parse integer from various formats."""
        float_val = self._parse_float(value)
        return int(float_val) if float_val is not None else None
    
    def _parse_payout_ratio(self, value: Any) -> Optional[float]:
        """Parse payout ratio and convert to percentage if needed."""
        float_val = self._parse_float(value)
        if float_val is None:
            return None
        
        # Payout ratios from data sources can be in different formats:
        # - Decimal ratio: 0.67 means 67%, 1.5 means 150%, 2.78 means 278%
        # - Percentage: 67 means 67%, 150 means 150%
        #
        # Heuristic: if value < 10, assume it's a ratio and multiply by 100
        # (ratios typically range from 0.2 to 3.0, percentages from 20 to 300)
        if float_val < 10:
            return float_val * 100
        return float_val


class NasdaqDownloader(BaseDownloader):
    """
    Downloader for Nasdaq.com historical data.
    
    Expected file formats:
    
    1. Historical Prices CSV (KO_historical.csv):
       Date,Close/Last,Volume,Open,High,Low
       03/14/2024,$60.12,12345678,$59.85,$60.45,$59.72
       
    2. Dividend History CSV (KO_dividends.csv):
       Ex/EFF DATE,TYPE,CASH AMOUNT,DECLARATION DATE,RECORD DATE,PAYMENT DATE
       03/14/2024,CASH,$0.485,02/15/2024,03/15/2024,04/01/2024
       
    3. Company Info JSON (KO_info.json):
       {"symbol": "KO", "name": "Coca-Cola", "sector": "Consumer Defensive", ...}
    """
    
    def __init__(self, data_dir: str = None):
        super().__init__(data_dir or f"{DEFAULT_DOWNLOADS_DIR}/nasdaq")
    
    def get_source(self) -> DataSource:
        return DataSource.NASDAQ
    
    def parse_file(self, filepath: Path) -> List[StockDocument]:
        """Parse a Nasdaq file."""
        filename = filepath.name.lower()
        
        if filepath.suffix == ".json":
            return self._parse_company_info(filepath)
        elif "dividend" in filename:
            return self._parse_dividend_history(filepath)
        elif "historical" in filename or "price" in filename:
            return self._parse_price_history(filepath)
        else:
            # Try to infer from content
            return self._auto_parse(filepath)
    
    def _parse_price_history(self, filepath: Path) -> List[StockDocument]:
        """Parse Nasdaq historical price CSV."""
        # Extract symbol from filename (e.g., KO_historical.csv -> KO)
        symbol = self._extract_symbol_from_filename(filepath)
        if not symbol:
            logger.warning(f"Could not extract symbol from {filepath.name}")
            return []
        
        price_history: List[PriceHistory] = []
        
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    # Handle various date column names (Date/date)
                    date_str = row.get("Date", row.get("date", ""))
                    price_date = self._parse_date(date_str)
                    if not price_date:
                        continue
                    
                    # Handle price values - support both Nasdaq format and our fetch format
                    close = self._parse_price(row.get("Close/Last", row.get("Close", row.get("close", "0"))))
                    open_price = self._parse_price(row.get("Open", row.get("open", "0")))
                    high = self._parse_price(row.get("High", row.get("high", "0")))
                    low = self._parse_price(row.get("Low", row.get("low", "0")))
                    volume = self._parse_int(row.get("Volume", row.get("volume", "0")))
                    
                    if close > 0:
                        price_history.append(PriceHistory(
                            date=price_date,
                            open=open_price,
                            high=high,
                            low=low,
                            close=close,
                            volume=volume or 0,
                        ))
                except Exception as e:
                    logger.debug(f"Error parsing price row: {e}")
        
        if not price_history:
            return []
        
        # Sort by date (newest first for latest price)
        price_history.sort(key=lambda x: x.date, reverse=True)
        
        doc = StockDocument(
            symbol=symbol,
            name=symbol,
            current_price=price_history[0].close if price_history else None,
            price_history=price_history,
            source=self.get_source(),
        )
        
        return [doc]
    
    def _parse_dividend_history(self, filepath: Path) -> List[StockDocument]:
        """Parse Nasdaq dividend history CSV."""
        symbol = self._extract_symbol_from_filename(filepath)
        if not symbol:
            return []
        
        dividend_history: List[DividendRecord] = []
        
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    # Support various column naming conventions
                    ex_date = self._parse_date(row.get("Ex/EFF DATE", row.get("Ex-Date", row.get("ex_date", ""))))
                    payment_date = self._parse_date(row.get("PAYMENT DATE", row.get("Payment-Date", row.get("payment_date", ""))))
                    amount = self._parse_price(row.get("CASH AMOUNT", row.get("Amount", row.get("amount", "0"))))
                    
                    if ex_date and amount > 0:
                        dividend_history.append(DividendRecord(
                            ex_date=ex_date,
                            payment_date=payment_date,
                            amount=amount,
                        ))
                except Exception as e:
                    logger.debug(f"Error parsing dividend row: {e}")
        
        if not dividend_history:
            return []
        
        # Sort by date (oldest first for streak calculation)
        dividend_history.sort(key=lambda x: x.ex_date)
        
        # Calculate annual dividend and streak
        annual_dividend = sum(d.amount for d in dividend_history[-4:])  # Last 4 quarters
        streak = self._calculate_dividend_streak(dividend_history)
        
        doc = StockDocument(
            symbol=symbol,
            name=symbol,
            annual_dividend=annual_dividend,
            dividend_streak_years=streak,
            dividend_history=dividend_history,
            source=self.get_source(),
        )
        
        return [doc]
    
    def _parse_company_info(self, filepath: Path) -> List[StockDocument]:
        """Parse company info JSON."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if isinstance(data, list):
                return [self._json_to_document(item) for item in data if item]
            else:
                doc = self._json_to_document(data)
                return [doc] if doc else []
        except Exception as e:
            logger.error(f"Error parsing JSON {filepath}: {e}")
            return []
    
    def _json_to_document(self, data: Dict[str, Any]) -> Optional[StockDocument]:
        """Convert JSON data to StockDocument."""
        symbol = data.get("symbol", data.get("Symbol", ""))
        if not symbol:
            return None
        
        return StockDocument(
            symbol=symbol.upper(),
            name=data.get("name", data.get("companyName", symbol)),
            sector=data.get("sector", "Unknown"),
            industry=data.get("industry", "Unknown"),
            exchange=data.get("exchange", "NASDAQ"),
            dividend_yield=data.get("dividendYield"),
            annual_dividend=data.get("annualDividend"),
            pe_ratio=data.get("peRatio", data.get("PE")),
            market_cap=data.get("marketCap"),
            description=data.get("description", ""),
            source=self.get_source(),
        )
    
    def _auto_parse(self, filepath: Path) -> List[StockDocument]:
        """Auto-detect and parse file."""
        with open(filepath, "r", encoding="utf-8") as f:
            first_line = f.readline().lower()
            
            if "close/last" in first_line or "open" in first_line and "high" in first_line:
                return self._parse_price_history(filepath)
            elif "cash amount" in first_line or "ex/eff" in first_line:
                return self._parse_dividend_history(filepath)
            else:
                logger.warning(f"Could not auto-detect format for {filepath}")
                return []
    
    def _extract_symbol_from_filename(self, filepath: Path) -> str:
        """Extract stock symbol from filename."""
        name = filepath.stem.upper()
        # Remove common suffixes
        for suffix in ["_HISTORICAL", "_DIVIDENDS", "_INFO", "_PRICES", "_DIVIDEND"]:
            name = name.replace(suffix, "")
        # Clean up
        name = re.sub(r"[^A-Z.]", "", name)
        return name if len(name) <= 5 else ""
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date from various formats."""
        if not date_str or date_str.lower() in ["n/a", "null", "-", ""]:
            return None
        
        date_str = date_str.strip()
        formats = [
            "%m/%d/%Y",
            "%Y-%m-%d",
            "%m-%d-%Y",
            "%b %d, %Y",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        return None
    
    def _parse_price(self, value: str) -> float:
        """Parse price value (may have $ prefix)."""
        if not value:
            return 0.0
        cleaned = re.sub(r"[$,]", "", str(value).strip())
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    
    def _parse_int(self, value: Any) -> Optional[int]:
        """Parse integer."""
        if not value:
            return None
        try:
            cleaned = re.sub(r"[,]", "", str(value).strip())
            return int(float(cleaned))
        except (ValueError, TypeError):
            return None
    
    def _calculate_dividend_streak(self, dividends: List[DividendRecord]) -> int:
        """Calculate consecutive years of dividend increases from payment history."""
        if not dividends:
            return 0

        year_to_payments: dict[int, list[float]] = {}
        for dividend in dividends:
            year_to_payments.setdefault(dividend.ex_date.year, []).append(dividend.amount)

        from utils.dividend_streak import (
            annual_totals_from_payments,
            calculate_consecutive_increase_years,
        )

        annual_totals = annual_totals_from_payments(year_to_payments)
        return calculate_consecutive_increase_years(annual_totals)
