"""
Enhanced stock service with vector database as primary source.

This service prioritizes data from the local vector database and only
falls back to public API sources when necessary (missing data, stale data).
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging

from models.stock import StockData, DividendHistory
from services.stock_service import StockService
from data_ingestion.vector_store import VectorStore
from data_ingestion.models import StockDocument

# Import config for default paths
try:
    from config import VECTORDB_DIR
    DEFAULT_VECTORDB_DIR = str(VECTORDB_DIR)
except ImportError:
    DEFAULT_VECTORDB_DIR = "data/vectordb"

logger = logging.getLogger(__name__)


class EnhancedStockService:
    """
    Stock service that prioritizes vector database over API calls.
    
    Data Source Priority:
    1. Vector database (local, fast, no rate limits)
    2. Public API (yfinance) - only for:
       - Stocks not in vector DB
       - Real-time price updates (if requested)
       - Data older than staleness threshold
    
    This approach:
    - Reduces API calls and rate limiting issues
    - Provides faster response times
    - Works offline with cached data
    - Only hits public sources when necessary
    """
    
    # How old data can be before fetching from API (in days)
    STALENESS_THRESHOLD_DAYS = 7
    
    # Whether to update prices from API (set False for pure DB mode)
    FETCH_REALTIME_PRICES = True
    
    def __init__(
        self, 
        vectordb_dir: str = None,
        staleness_days: int = 7,
        fetch_realtime_prices: bool = True,
    ):
        """
        Initialize enhanced service.
        
        Args:
            vectordb_dir: Path to vector database. Defaults to ~/.dividendscope/data/vectordb.
            staleness_days: Days before data is considered stale.
            fetch_realtime_prices: Whether to fetch real-time prices from API.
        """
        self._vector_store: Optional[VectorStore] = None
        self._vectordb_dir = vectordb_dir or DEFAULT_VECTORDB_DIR
        self._vector_db_available = False
        self._staleness_threshold = timedelta(days=staleness_days)
        self._fetch_realtime = fetch_realtime_prices
        
        self._init_vector_store()
    
    def _init_vector_store(self) -> None:
        """Initialize vector store if available."""
        try:
            self._vector_store = VectorStore(persist_directory=self._vectordb_dir)
            count = self._vector_store.count()
            if count > 0:
                self._vector_db_available = True
                logger.info(f"Vector DB initialized: {count} documents (primary source)")
            else:
                logger.warning("Vector DB empty - will use API as primary source")
        except Exception as e:
            logger.warning(f"Vector store not available: {e}")
            self._vector_db_available = False
    
    def fetch(self, symbol: str) -> Optional[StockData]:
        """
        Fetch stock data, prioritizing complete vector database data.
        
        Strategy:
        1. Try to get from vector DB first
        2. If found, fresh, AND complete - use it (optionally update price)
        3. If incomplete/stale/missing - fetch from API and enhance with DB data
        
        Args:
            symbol: Stock ticker symbol.
            
        Returns:
            StockData or None.
        """
        symbol = symbol.upper().strip()
        
        db_data = None
        
        # === Check Vector Database ===
        if self._vector_db_available:
            db_data = self._fetch_from_vector_db(symbol)
            
            if db_data and self._is_data_complete(db_data) and self._is_data_fresh(db_data):
                logger.debug(f"{symbol}: Using complete vector DB data")
                
                # Optionally update real-time price only
                if self._fetch_realtime:
                    db_data = self._update_realtime_price(db_data)
                
                return db_data
        
        # === Fetch from API (primary source when DB data incomplete) ===
        logger.info(f"{symbol}: Fetching from API (DB data missing or incomplete)")
        api_data = StockService.fetch(symbol)
        
        if api_data:
            api_data.data_sources = ["Public API"]
            
            # Enhance API data with any useful DB data
            if db_data:
                api_data = self._enhance_with_db_data(api_data, db_data)
            
            return api_data
        
        # === FALLBACK: Return incomplete DB data if API fails ===
        if db_data:
            logger.warning(f"{symbol}: API failed, using incomplete DB data")
            db_data.data_sources = ["Vector DB (incomplete)"]
            return db_data
        
        return None
    
    def _is_data_complete(self, data: StockData) -> bool:
        """
        Check if stock data has the essential fields populated.
        
        Essential fields for dividend analysis:
        - Price
        - Dividend yield or dividend rate
        - Either PE ratio or payout ratio
        """
        # Must have price
        has_price = data.price is not None and data.price > 0
        
        # Must have dividend info
        has_dividend = (
            (data.dividend_yield_pct is not None and data.dividend_yield_pct > 0) or
            (data.dividend_rate is not None and data.dividend_rate > 0)
        )
        
        # Should have some valuation metric
        has_valuation = (
            (data.trailing_pe is not None and data.trailing_pe > 0) or
            (data.forward_pe is not None and data.forward_pe > 0) or
            (data.payout_ratio_pct is not None and data.payout_ratio_pct > 0)
        )
        
        # Data quality check (if score exists and is high enough)
        quality_ok = (
            data.data_quality_score is None or 
            data.data_quality_score >= 50
        )
        
        is_complete = has_price and has_dividend and (has_valuation or quality_ok)
        
        if not is_complete:
            logger.debug(
                f"{data.symbol}: Incomplete - price={has_price}, "
                f"dividend={has_dividend}, valuation={has_valuation}, "
                f"quality={data.data_quality_score}"
            )
        
        return is_complete
    
    def _enhance_with_db_data(self, api_data: StockData, db_data: StockData) -> StockData:
        """Enhance API data with useful fields from DB data."""
        # Add dividend streak if DB has better data
        if db_data.dividend_history and db_data.dividend_history.consecutive_years:
            if not api_data.dividend_history or api_data.dividend_history.consecutive_years == 0:
                api_data.dividend_history = db_data.dividend_history
            elif db_data.dividend_history.consecutive_years > api_data.dividend_history.consecutive_years:
                api_data.dividend_history = DividendHistory(
                    consecutive_years=db_data.dividend_history.consecutive_years,
                    total_years=api_data.dividend_history.total_years,
                    cagr_5y=api_data.dividend_history.cagr_5y or db_data.dividend_history.cagr_5y,
                    cagr_10y=api_data.dividend_history.cagr_10y or db_data.dividend_history.cagr_10y,
                    current_annual=api_data.dividend_history.current_annual,
                    ex_dividend_date=api_data.dividend_history.ex_dividend_date,
                )
        
        # Track sources
        api_data.data_sources = ["Public API", "Enhanced: Vector DB"]
        
        return api_data
    
    def fetch_from_db_only(self, symbol: str) -> Optional[StockData]:
        """
        Fetch stock data from vector DB only (no API calls).
        
        Args:
            symbol: Stock ticker symbol.
            
        Returns:
            StockData or None.
        """
        if not self._vector_db_available:
            return None
        
        return self._fetch_from_vector_db(symbol)
    
    def _fetch_from_vector_db(self, symbol: str) -> Optional[StockData]:
        """Get stock data from vector database."""
        if not self._vector_store:
            return None
        
        doc = self._vector_store.get_by_symbol(symbol)
        if not doc:
            return None
        
        return self._document_to_stock_data(doc)
    
    def _is_data_fresh(self, data: StockData) -> bool:
        """Check if stock data is fresh enough."""
        # If no timestamp info, assume it's fresh
        if not hasattr(data, "_last_updated") or data._last_updated is None:
            return True
        
        age = datetime.now() - data._last_updated
        return age < self._staleness_threshold
    
    def _update_realtime_price(self, data: StockData) -> StockData:
        """Update only the real-time price from API (minimal API call)."""
        try:
            import yfinance as yf
            
            ticker = yf.Ticker(data.symbol)
            info = ticker.fast_info
            
            if hasattr(info, "last_price") and info.last_price:
                data.price = info.last_price
                
                if "Vector DB" in str(data.data_sources):
                    data.data_sources.append("Price: Live")
                else:
                    data.data_sources = ["Vector DB", "Price: Live"]
                    
        except Exception as e:
            logger.debug(f"Could not update real-time price for {data.symbol}: {e}")
        
        return data
    
    def _document_to_stock_data(self, doc: StockDocument) -> StockData:
        """Convert vector DB document to StockData."""
        div_history = None
        
        if doc.dividend_streak_years or doc.dividend_history:
            # Calculate CAGR from dividend history if available
            cagr_5y = self._calculate_cagr(doc.dividend_history, years=5)
            cagr_10y = self._calculate_cagr(doc.dividend_history, years=10)
            current_annual = doc.annual_dividend or 0.0
            
            # Get ex-dividend date from history
            ex_date = None
            if doc.dividend_history:
                sorted_divs = sorted(doc.dividend_history, key=lambda x: x.ex_date, reverse=True)
                if sorted_divs:
                    # ex_date should be a date object, not string
                    ex_date = sorted_divs[0].ex_date.date() if hasattr(sorted_divs[0].ex_date, 'date') else sorted_divs[0].ex_date
            
            div_history = DividendHistory(
                consecutive_years=doc.dividend_streak_years or 0,
                total_years=len(set(d.ex_date.year for d in doc.dividend_history)) if doc.dividend_history else 0,
                cagr_5y=cagr_5y,
                cagr_10y=cagr_10y,
                current_annual=current_annual,
                ex_dividend_date=ex_date,
                payment_frequency=self._detect_frequency(doc.dividend_history),
            )
        
        # Build StockData from document
        stock_data = StockData(
            symbol=doc.symbol,
            name=doc.name,
            sector=doc.sector,
            industry=doc.industry,
            price=doc.current_price,
            market_cap=doc.market_cap,
            trailing_pe=doc.pe_ratio,
            dividend_yield_pct=doc.dividend_yield,
            dividend_rate=doc.annual_dividend,
            payout_ratio_pct=doc.payout_ratio,
            dividend_history=div_history,
            data_sources=[f"Vector DB ({doc.source.value})"],
            data_quality_score=doc.data_quality,
        )
        
        # Store last updated for freshness check
        stock_data._last_updated = doc.last_updated
        
        return stock_data
    
    def _calculate_cagr(self, dividend_history: list, years: int) -> float:
        """Calculate compound annual growth rate from dividend history."""
        if not dividend_history or len(dividend_history) < 4:
            return 0.0
        
        try:
            # Sort by date
            sorted_divs = sorted(dividend_history, key=lambda x: x.ex_date)
            
            # Get annual totals
            annual_totals = {}
            for div in sorted_divs:
                year = div.ex_date.year
                annual_totals[year] = annual_totals.get(year, 0) + div.amount
            
            if len(annual_totals) < 2:
                return 0.0
            
            years_list = sorted(annual_totals.keys())
            
            # Calculate CAGR for requested period
            target_years = min(years, len(years_list) - 1)
            if target_years < 1:
                return 0.0
            
            end_year = years_list[-1]
            start_year = years_list[-(target_years + 1)]
            
            end_value = annual_totals[end_year]
            start_value = annual_totals[start_year]
            
            if start_value <= 0:
                return 0.0
            
            cagr = ((end_value / start_value) ** (1 / target_years) - 1) * 100
            return round(cagr, 2)
            
        except Exception as e:
            logger.debug(f"Error calculating CAGR: {e}")
            return 0.0
    
    def _detect_frequency(self, dividend_history: list) -> int:
        """
        Detect dividend payment frequency from history.
        
        Returns payments per year as int (12=monthly, 4=quarterly, 2=semi-annual, 1=annual).
        """
        if not dividend_history or len(dividend_history) < 2:
            return 4  # Default to quarterly
        
        try:
            # Count payments per year
            years: dict[int, int] = {}
            for div in dividend_history:
                year = div.ex_date.year
                years[year] = years.get(year, 0) + 1
            
            if not years:
                return 4
            
            avg_per_year = sum(years.values()) / len(years)
            
            if avg_per_year >= 11:
                return 12  # Monthly
            elif avg_per_year >= 3.5:
                return 4   # Quarterly
            elif avg_per_year >= 1.5:
                return 2   # Semi-annual
            else:
                return 1   # Annual
                
        except Exception:
            return 4
    
    # === Batch Operations (DB-first) ===
    
    def fetch_multiple(self, symbols: List[str]) -> Dict[str, Optional[StockData]]:
        """
        Fetch multiple stocks, using DB for complete data only.
        
        Args:
            symbols: List of stock symbols.
            
        Returns:
            Dict mapping symbol to StockData.
        """
        import time
        
        results = {}
        api_needed = []
        db_cache = {}  # Cache DB data for enhancement
        
        # First pass: check DB for complete data
        for symbol in symbols:
            symbol = symbol.upper().strip()
            
            if self._vector_db_available:
                db_data = self._fetch_from_vector_db(symbol)
                if db_data:
                    db_cache[symbol] = db_data  # Cache for potential enhancement
                    
                    if self._is_data_complete(db_data) and self._is_data_fresh(db_data):
                        if self._fetch_realtime:
                            db_data = self._update_realtime_price(db_data)
                        results[symbol] = db_data
                        continue
            
            api_needed.append(symbol)
        
        logger.info(f"Complete DB hits: {len(results)}, API needed: {len(api_needed)}")
        
        # Second pass: fetch from API for incomplete/missing data
        for symbol in api_needed:
            api_data = StockService.fetch(symbol)
            if api_data:
                api_data.data_sources = ["Public API"]
                
                # Enhance with DB data if available
                if symbol in db_cache:
                    api_data = self._enhance_with_db_data(api_data, db_cache[symbol])
                
                results[symbol] = api_data
            else:
                # Fallback to incomplete DB data
                if symbol in db_cache:
                    db_cache[symbol].data_sources = ["Vector DB (incomplete)"]
                    results[symbol] = db_cache[symbol]
                else:
                    results[symbol] = None
            
            # Small delay to avoid rate limiting
            time.sleep(0.1)
        
        return results
    
    def get_all_from_db(self) -> List[StockData]:
        """Get all stocks from vector DB (no API calls)."""
        if not self._vector_db_available or not self._vector_store:
            return []
        
        try:
            # Get all documents
            results = self._vector_store.search("dividend stock", n_results=1000)
            return [self._document_to_stock_data(r.document) for r in results]
        except Exception as e:
            logger.error(f"Error getting all from DB: {e}")
            return []
    
    def get_dividend_kings_from_db(self) -> List[StockData]:
        """Get all Dividend Kings from vector DB (no API calls)."""
        if not self._vector_db_available or not self._vector_store:
            return []
        
        docs = self._vector_store.get_dividend_kings(min_streak=50)
        return [self._document_to_stock_data(doc) for doc in docs]
    
    def get_sector_from_db(self, sector: str) -> List[StockData]:
        """Get all stocks in a sector from vector DB (no API calls)."""
        if not self._vector_db_available or not self._vector_store:
            return []
        
        docs = self._vector_store.get_by_sector(sector)
        return [self._document_to_stock_data(doc) for doc in docs]
    
    def search(
        self,
        query: str,
        n_results: int = 10,
        min_streak: Optional[int] = None,
        sector: Optional[str] = None,
    ) -> List[StockData]:
        """
        Semantic search in vector DB (no API calls).
        
        Args:
            query: Natural language query.
            n_results: Maximum results.
            min_streak: Minimum dividend streak filter.
            sector: Filter by sector.
            
        Returns:
            List of matching StockData.
        """
        if not self._vector_db_available or not self._vector_store:
            logger.warning("Vector DB not available for search")
            return []
        
        where = {}
        if min_streak:
            where["dividend_streak_years"] = {"$gte": min_streak}
        if sector:
            where["sector"] = sector
        
        results = self._vector_store.search(
            query, 
            n_results=n_results, 
            where=where if where else None,
        )
        
        return [self._document_to_stock_data(r.document) for r in results]
    
    # === Status & Info ===
    
    @property
    def has_vector_data(self) -> bool:
        """Check if vector database has data."""
        return self._vector_db_available and self._vector_store.count() > 0
    
    @property
    def document_count(self) -> int:
        """Get number of documents in vector DB."""
        if not self._vector_store:
            return 0
        return self._vector_store.count()
    
    @property
    def is_db_primary(self) -> bool:
        """Check if DB is being used as primary source."""
        return self._vector_db_available and self.document_count > 0
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status information."""
        return {
            "vector_db_available": self._vector_db_available,
            "document_count": self.document_count,
            "is_db_primary": self.is_db_primary,
            "staleness_threshold_days": self._staleness_threshold.days,
            "fetch_realtime_prices": self._fetch_realtime,
            "mode": "DB-first" if self.is_db_primary else "API-only",
        }
