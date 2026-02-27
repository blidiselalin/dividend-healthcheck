"""
VectorDB-first service layer for stock data.

Provides stock data from the vector database, converting
StockDocument to StockData for UI consumption.

This service is designed to be the primary data source for the UI,
eliminating the need for live API calls when the database is populated.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import date, datetime

from models.stock import StockData, DividendHistory

logger = logging.getLogger(__name__)

# Import config for default paths
try:
    from config import VECTORDB_DIR
    DEFAULT_VECTORDB_DIR = str(VECTORDB_DIR)
except ImportError:
    DEFAULT_VECTORDB_DIR = "data/vectordb"

# Try to import vector store
try:
    from data_ingestion.vector_store import VectorStore
    from data_ingestion.models import StockDocument
    VECTOR_DB_AVAILABLE = True
except ImportError:
    VECTOR_DB_AVAILABLE = False
    logger.warning("VectorStore not available")


class VectorDBService:
    """
    Service for fetching stock data from the vector database.
    
    Converts StockDocument to StockData format expected by UI.
    Provides a complete offline data source when the DB is populated.
    """
    
    def __init__(self, db_path: str = None):
        """
        Initialize the service.
        
        Args:
            db_path: Path to the vector database directory. Defaults to ~/.dividendscope/data/vectordb.
        """
        self._store: Optional["VectorStore"] = None
        self._db_path = db_path or DEFAULT_VECTORDB_DIR
        
        if VECTOR_DB_AVAILABLE:
            try:
                self._store = VectorStore(persist_directory=db_path)
                logger.info(f"VectorDBService initialized with {self._store.count()} documents")
            except Exception as e:
                logger.error(f"Failed to initialize VectorStore: {e}")
    
    @property
    def is_available(self) -> bool:
        """Check if the vector database is available and has data."""
        return self._store is not None and self._store.count() > 0
    
    def get_stock(self, symbol: str) -> Optional[StockData]:
        """
        Get stock data for a symbol.
        
        Args:
            symbol: Stock ticker symbol.
            
        Returns:
            StockData or None if not found.
        """
        if not self._store:
            return None
        
        doc = self._store.get_by_symbol(symbol)
        if not doc:
            return None
        
        return self._document_to_stock_data(doc)
    
    def get_stocks(self, symbols: List[str]) -> Dict[str, StockData]:
        """
        Get stock data for multiple symbols.
        
        Args:
            symbols: List of ticker symbols.
            
        Returns:
            Dict mapping symbol to StockData.
        """
        result = {}
        for symbol in symbols:
            data = self.get_stock(symbol)
            if data:
                result[symbol] = data
        return result
    
    def get_dividend_kings(self, min_streak: int = 50) -> List[StockData]:
        """
        Get all Dividend Kings from the database.
        
        Args:
            min_streak: Minimum consecutive years (default 50 for Kings).
            
        Returns:
            List of StockData for Dividend Kings.
        """
        if not self._store:
            return []
        
        docs = self._store.get_dividend_kings(min_streak=min_streak)
        return [self._document_to_stock_data(d) for d in docs]
    
    def get_all_stocks(self) -> List[StockData]:
        """
        Get all stocks from the database.
        
        Returns:
            List of all StockData.
        """
        if not self._store:
            return []
        
        # Use get_dividend_kings with min_streak=0 to get all
        docs = self._store.get_dividend_kings(min_streak=0)
        return [self._document_to_stock_data(d) for d in docs]
    
    def search(self, query: str, n_results: int = 10) -> List[StockData]:
        """
        Search for stocks matching a query.
        
        Args:
            query: Search query string.
            n_results: Maximum number of results.
            
        Returns:
            List of matching StockData.
        """
        if not self._store:
            return []
        
        results = self._store.search(query, n_results=n_results)
        return [self._document_to_stock_data(r.document) for r in results]
    
    def get_by_sector(self, sector: str) -> List[StockData]:
        """
        Get all stocks in a sector.
        
        Args:
            sector: Sector name.
            
        Returns:
            List of StockData in the sector.
        """
        all_stocks = self.get_all_stocks()
        return [s for s in all_stocks if s.sector.lower() == sector.lower()]
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.
        
        Returns:
            Dict with database stats.
        """
        if not self._store:
            return {"available": False}
        
        return self._store.get_stats()
    
    def _document_to_stock_data(self, doc: "StockDocument") -> StockData:
        """
        Convert StockDocument to StockData.
        
        Maps all fields from the vector DB model to the UI model.
        """
        # Build DividendHistory from document
        div_history = None
        if doc.dividend_streak_years is not None:
            # Calculate values from dividend_history if available
            cagr_5y = doc.dividend_cagr_5y or 0.0
            cagr_10y = doc.dividend_cagr_10y or 0.0
            total_years = doc.dividend_total_years or 0
            
            if not total_years and doc.dividend_history:
                years = set(d.ex_date.year for d in doc.dividend_history)
                total_years = len(years)
            
            div_history = DividendHistory(
                consecutive_years=doc.dividend_streak_years,
                total_years=total_years,
                cagr_5y=cagr_5y,
                cagr_10y=cagr_10y,
                current_annual=doc.annual_dividend or 0.0,
                ex_dividend_date=doc.ex_dividend_date,
                payment_frequency=doc.payment_frequency,
            )
        
        # Calculate price to 52w high percentage
        price_to_52w_high = None
        if doc.current_price and doc.fifty_two_week_high:
            price_to_52w_high = ((doc.current_price / doc.fifty_two_week_high) - 1) * 100
        
        return StockData(
            # Identity
            symbol=doc.symbol,
            name=doc.name,
            sector=doc.sector,
            industry=doc.industry,
            
            # Dividend metrics
            dividend_yield_pct=doc.dividend_yield,
            dividend_rate=doc.annual_dividend,
            payout_ratio_pct=doc.payout_ratio,
            dividend_history=div_history,
            fcf_payout_ratio_pct=doc.fcf_payout_ratio,
            dividend_coverage=doc.dividend_coverage,
            
            # Price & Valuation
            price=doc.current_price,
            market_cap=doc.market_cap,
            trailing_pe=doc.pe_ratio,
            forward_pe=doc.forward_pe,
            peg_ratio=doc.peg_ratio,
            price_to_book=doc.price_to_book,
            price_to_sales=doc.price_to_sales,
            ev_ebitda=doc.ev_ebitda,
            fifty_two_week_high=doc.fifty_two_week_high,
            fifty_two_week_low=doc.fifty_two_week_low,
            price_to_52w_high_pct=price_to_52w_high,
            
            # Financial Health
            debt_to_equity=doc.debt_to_equity,
            debt_to_ebitda=doc.debt_to_ebitda,
            interest_coverage=doc.interest_coverage,
            current_ratio=doc.current_ratio,
            quick_ratio=doc.quick_ratio,
            
            # Profitability
            roe_pct=doc.roe,
            roa_pct=doc.roa,
            roic_pct=doc.roic,
            profit_margin_pct=doc.profit_margin,
            operating_margin_pct=doc.operating_margin,
            gross_margin_pct=doc.gross_margin,
            
            # Growth
            revenue_growth_pct=doc.revenue_growth,
            earnings_growth_pct=doc.earnings_growth,
            fcf_growth_pct=doc.fcf_growth,
            
            # Performance
            price_return_1y=doc.price_return_1y,
            total_return_1y=doc.total_return_1y,
            price_return_5y=doc.price_return_5y,
            
            # Analyst
            beta=doc.beta,
            target_price=doc.target_price,
            target_upside_pct=doc.target_upside,
            analyst_rating=doc.analyst_rating,
            num_analysts=doc.num_analysts,
            
            # Metadata
            data_sources=[doc.source.value],
            data_quality_score=doc.data_quality,
        )
    
    def is_data_complete(self, data: StockData) -> bool:
        """
        Check if stock data is complete enough for UI display.
        
        A stock is considered complete if it has:
        - Basic identity info
        - Dividend yield and streak
        - Current price
        - At least some valuation metrics
        
        Args:
            data: StockData to check.
            
        Returns:
            True if data is complete enough.
        """
        # Must have basic identity
        if not data.symbol or not data.name:
            return False
        
        # Must have dividend info
        if data.dividend_yield_pct is None:
            return False
        
        if data.dividend_history is None:
            return False
        
        # Must have price
        if data.price is None:
            return False
        
        # Should have some valuation
        if data.trailing_pe is None and data.forward_pe is None:
            return False
        
        return True


# Singleton instance for convenience
_service_instance: Optional[VectorDBService] = None


def get_vectordb_service() -> VectorDBService:
    """Get or create the global VectorDBService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = VectorDBService()
    return _service_instance
