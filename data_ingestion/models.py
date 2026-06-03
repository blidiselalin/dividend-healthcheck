"""
Data models for vector database storage.

These models represent stock market data in a format optimized for
vector embeddings and semantic search.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import hashlib
import json


class DataSource(Enum):
    """Source of the stock data."""
    STOCKQUOTE_IO = "stockquote.io"
    NASDAQ = "nasdaq.com"
    YAHOO = "yahoo"
    FINNHUB = "finnhub"  # legacy stored metadata; no longer in default enrich chain
    FMP = "fmp"  # legacy stored metadata; no longer in default enrich chain
    ALPHAVANTAGE = "alphavantage"
    SEC_EDGAR = "sec_edgar"
    STOOQ = "stooq"
    MANUAL = "manual"


def parse_data_source(value: Optional[str]) -> DataSource:
    """Parse stored source strings; unknown values fall back to MANUAL."""
    if not value:
        return DataSource.MANUAL
    try:
        return DataSource(str(value).strip().lower())
    except ValueError:
        return DataSource.MANUAL


@dataclass
class PriceHistory:
    """Historical price data for a single day."""
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "date": self.date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "adjusted_close": self.adjusted_close,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PriceHistory":
        """Create from dictionary."""
        return cls(
            date=date.fromisoformat(data["date"]),
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            volume=data["volume"],
            adjusted_close=data.get("adjusted_close"),
        )


@dataclass
class DividendRecord:
    """Record of a dividend payment."""
    ex_date: date
    payment_date: Optional[date]
    amount: float
    frequency: str = "quarterly"  # quarterly, monthly, annual, special
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "ex_date": self.ex_date.isoformat(),
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "amount": self.amount,
            "frequency": self.frequency,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DividendRecord":
        """Create from dictionary."""
        return cls(
            ex_date=date.fromisoformat(data["ex_date"]),
            payment_date=date.fromisoformat(data["payment_date"]) if data.get("payment_date") else None,
            amount=data["amount"],
            frequency=data.get("frequency", "quarterly"),
        )


@dataclass
class StockDocument:
    """
    Document representing a stock for vector storage.
    
    This is the primary unit stored in the vector database.
    Each document contains metadata and text content that can be embedded.
    Contains ALL fields needed by the UI for complete offline operation.
    """
    
    # === IDENTITY ===
    symbol: str
    name: str
    
    # === CLASSIFICATION ===
    sector: str = "Unknown"
    industry: str = "Unknown"
    exchange: str = "Unknown"
    
    # === DIVIDEND INFO (core for Dividend Kings) ===
    dividend_yield: Optional[float] = None  # Current yield %
    annual_dividend: Optional[float] = None  # Annual dividend per share
    dividend_streak_years: Optional[int] = None  # Consecutive years of increases
    payout_ratio: Optional[float] = None  # Earnings payout %
    fcf_payout_ratio: Optional[float] = None  # Free cash flow payout %
    dividend_coverage: Optional[float] = None  # EPS / Dividend
    ex_dividend_date: Optional[date] = None  # Last ex-dividend date
    payment_frequency: int = 4  # Payments per year (4=quarterly, 12=monthly)
    
    # === DIVIDEND GROWTH (calculated from history) ===
    dividend_cagr_5y: Optional[float] = None  # 5-year compound annual growth rate
    dividend_cagr_10y: Optional[float] = None  # 10-year compound annual growth rate
    dividend_total_years: Optional[int] = None  # Total years with dividend history
    
    # === PRICE DATA ===
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    beta: Optional[float] = None
    
    # === VALUATION METRICS ===
    pe_ratio: Optional[float] = None  # Trailing P/E
    forward_pe: Optional[float] = None  # Forward P/E
    peg_ratio: Optional[float] = None  # P/E to Growth ratio
    price_to_book: Optional[float] = None  # P/B ratio
    price_to_sales: Optional[float] = None  # P/S ratio
    ev_ebitda: Optional[float] = None  # Enterprise Value / EBITDA
    
    # === FINANCIAL HEALTH ===
    debt_to_equity: Optional[float] = None  # D/E ratio
    debt_to_ebitda: Optional[float] = None  # Debt / EBITDA
    interest_coverage: Optional[float] = None  # EBIT / Interest Expense
    current_ratio: Optional[float] = None  # Current Assets / Current Liabilities
    quick_ratio: Optional[float] = None  # (Current Assets - Inventory) / Current Liabilities
    
    # === PROFITABILITY ===
    roe: Optional[float] = None  # Return on Equity %
    roa: Optional[float] = None  # Return on Assets %
    roic: Optional[float] = None  # Return on Invested Capital %
    profit_margin: Optional[float] = None  # Net Profit Margin %
    operating_margin: Optional[float] = None  # Operating Margin %
    gross_margin: Optional[float] = None  # Gross Margin %
    
    # === GROWTH ===
    revenue_growth: Optional[float] = None  # Year-over-year revenue growth %
    earnings_growth: Optional[float] = None  # Year-over-year earnings growth %
    fcf_growth: Optional[float] = None  # Free cash flow growth %
    
    # === PERFORMANCE ===
    price_return_1y: Optional[float] = None  # 1-year price return %
    total_return_1y: Optional[float] = None  # 1-year total return (price + dividends) %
    price_return_5y: Optional[float] = None  # 5-year price return %
    total_return_5y: Optional[float] = None  # 5-year total return %
    
    # === ANALYST DATA ===
    target_price: Optional[float] = None  # Mean analyst target price
    target_upside: Optional[float] = None  # Upside to target %
    analyst_rating: Optional[str] = None  # Buy/Hold/Sell recommendation
    num_analysts: Optional[int] = None  # Number of analysts covering
    
    # === HISTORICAL DATA ===
    price_history: List[PriceHistory] = field(default_factory=list)
    dividend_history: List[DividendRecord] = field(default_factory=list)
    
    # === METADATA ===
    source: DataSource = DataSource.MANUAL
    last_updated: datetime = field(default_factory=datetime.now)
    data_quality: float = 0.0  # 0-100 completeness score
    
    # === TEXT CONTENT ===
    description: str = ""
    notes: str = ""

    # === PORTFOLIO LINK (synced from portfolio.db) ===
    in_portfolio: bool = False
    portfolio_shares: Optional[float] = None
    portfolio_avg_cost_per_share: Optional[float] = None
    portfolio_acquisition_value: Optional[float] = None
    portfolio_dividends_paid: Optional[float] = None
    portfolio_purchase_count: Optional[int] = None
    
    MAX_HISTORY_YEARS = 10  # Maximum years of historical data to store
    
    @property
    def document_id(self) -> str:
        """Generate unique document ID based on symbol only (ensures no duplicates per symbol)."""
        return f"stock_{self.symbol.upper()}"
    
    def trim_history(self, max_years: int = 10) -> None:
        """
        Trim historical data to max_years.
        
        Keeps only the most recent data within the specified timeframe.
        """
        from datetime import timedelta
        
        cutoff_date = date.today() - timedelta(days=max_years * 365)
        
        if self.price_history:
            self.price_history = [
                p for p in self.price_history
                if p.date >= cutoff_date
            ]
            self.price_history.sort(key=lambda p: p.date, reverse=True)
        
        if self.dividend_history:
            self.dividend_history = [
                d for d in self.dividend_history
                if d.ex_date >= cutoff_date
            ]
            self.dividend_history.sort(key=lambda d: d.ex_date, reverse=True)
    
    @property
    def embedding_text(self) -> str:
        """Generate text content for vector embedding."""
        parts = [
            f"Stock: {self.symbol} - {self.name}",
            f"Sector: {self.sector}",
            f"Industry: {self.industry}",
        ]
        
        if self.dividend_yield:
            parts.append(f"Dividend yield: {self.dividend_yield:.2f}%")
        
        if self.dividend_streak_years:
            parts.append(f"Consecutive dividend increases: {self.dividend_streak_years} years")
            if self.dividend_streak_years >= 50:
                parts.append("Status: Dividend King (50+ years)")
            elif self.dividend_streak_years >= 25:
                parts.append("Status: Dividend Aristocrat (25+ years)")
        
        if self.annual_dividend:
            parts.append(f"Annual dividend: ${self.annual_dividend:.2f}")
        
        if self.payout_ratio:
            parts.append(f"Payout ratio: {self.payout_ratio:.1f}%")
        
        if self.pe_ratio:
            parts.append(f"P/E ratio: {self.pe_ratio:.1f}")
        
        if self.description:
            parts.append(f"Description: {self.description}")
        
        if self.notes:
            parts.append(f"Notes: {self.notes}")

        if self.in_portfolio:
            position_parts = ["Portfolio holding: yes"]
            if self.portfolio_shares is not None:
                position_parts.append(f"{self.portfolio_shares:g} shares")
            if self.portfolio_avg_cost_per_share is not None:
                position_parts.append(
                    f"avg cost ${self.portfolio_avg_cost_per_share:.2f}"
                )
            if self.portfolio_acquisition_value is not None:
                position_parts.append(
                    f"acquisition ${self.portfolio_acquisition_value:,.0f}"
                )
            parts.append(", ".join(position_parts))
        
        return "\n".join(parts)
    
    def to_metadata(self) -> Dict[str, Any]:
        """
        Convert to metadata dict for vector storage.
        
        ChromaDB only accepts str, int, float, bool as metadata values.
        None values must be excluded or converted.
        Lists (like price_history, dividend_history) are JSON-serialized.
        """
        metadata: Dict[str, Any] = {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "industry": self.industry,
            "exchange": self.exchange,
            "source": self.source.value,
            "last_updated": self.last_updated.isoformat(),
            "data_quality": float(self.data_quality) if self.data_quality is not None else 0.0,
            "payment_frequency": self.payment_frequency,
        }
        
        # Helper to add float fields
        def add_float(key: str, val: Optional[float]) -> None:
            if val is not None:
                metadata[key] = float(val)
        
        def add_int(key: str, val: Optional[int]) -> None:
            if val is not None:
                metadata[key] = int(val)
        
        # Dividend fields
        add_float("dividend_yield", self.dividend_yield)
        add_float("annual_dividend", self.annual_dividend)
        add_int("dividend_streak_years", self.dividend_streak_years)
        add_float("payout_ratio", self.payout_ratio)
        add_float("fcf_payout_ratio", self.fcf_payout_ratio)
        add_float("dividend_coverage", self.dividend_coverage)
        add_float("dividend_cagr_5y", self.dividend_cagr_5y)
        add_float("dividend_cagr_10y", self.dividend_cagr_10y)
        add_int("dividend_total_years", self.dividend_total_years)
        
        if self.ex_dividend_date:
            metadata["ex_dividend_date"] = self.ex_dividend_date.isoformat()
        
        # Price data
        add_float("current_price", self.current_price)
        add_float("market_cap", self.market_cap)
        add_float("fifty_two_week_high", self.fifty_two_week_high)
        add_float("fifty_two_week_low", self.fifty_two_week_low)
        add_float("beta", self.beta)
        
        # Valuation metrics
        add_float("pe_ratio", self.pe_ratio)
        add_float("forward_pe", self.forward_pe)
        add_float("peg_ratio", self.peg_ratio)
        add_float("price_to_book", self.price_to_book)
        add_float("price_to_sales", self.price_to_sales)
        add_float("ev_ebitda", self.ev_ebitda)
        
        # Financial health
        add_float("debt_to_equity", self.debt_to_equity)
        add_float("debt_to_ebitda", self.debt_to_ebitda)
        add_float("interest_coverage", self.interest_coverage)
        add_float("current_ratio", self.current_ratio)
        add_float("quick_ratio", self.quick_ratio)
        
        # Profitability
        add_float("roe", self.roe)
        add_float("roa", self.roa)
        add_float("roic", self.roic)
        add_float("profit_margin", self.profit_margin)
        add_float("operating_margin", self.operating_margin)
        add_float("gross_margin", self.gross_margin)
        
        # Growth
        add_float("revenue_growth", self.revenue_growth)
        add_float("earnings_growth", self.earnings_growth)
        add_float("fcf_growth", self.fcf_growth)
        
        # Performance
        add_float("price_return_1y", self.price_return_1y)
        add_float("total_return_1y", self.total_return_1y)
        add_float("price_return_5y", self.price_return_5y)
        add_float("total_return_5y", self.total_return_5y)
        
        # Analyst data
        add_float("target_price", self.target_price)
        add_float("target_upside", self.target_upside)
        add_int("num_analysts", self.num_analysts)
        if self.analyst_rating:
            metadata["analyst_rating"] = self.analyst_rating
        
        # Serialize historical data as JSON strings (ChromaDB only accepts scalars)
        # Limit to MAX_HISTORY_YEARS (10 years) to prevent bloated storage
        from datetime import timedelta
        cutoff_date = date.today() - timedelta(days=self.MAX_HISTORY_YEARS * 365)
        
        if self.price_history:
            trimmed_prices = [p for p in self.price_history if p.date >= cutoff_date]
            trimmed_prices.sort(key=lambda p: p.date, reverse=True)
            metadata["price_history_json"] = json.dumps([p.to_dict() for p in trimmed_prices])
        
        if self.dividend_history:
            trimmed_divs = [d for d in self.dividend_history if d.ex_date >= cutoff_date]
            trimmed_divs.sort(key=lambda d: d.ex_date, reverse=True)
            metadata["dividend_history_json"] = json.dumps([d.to_dict() for d in trimmed_divs])
        
        # Text fields
        if self.description:
            metadata["description"] = self.description
        if self.notes:
            metadata["notes"] = self.notes

        # Portfolio linkage
        metadata["in_portfolio"] = bool(self.in_portfolio)
        add_float("portfolio_shares", self.portfolio_shares)
        add_float("portfolio_avg_cost_per_share", self.portfolio_avg_cost_per_share)
        add_float("portfolio_acquisition_value", self.portfolio_acquisition_value)
        add_float("portfolio_dividends_paid", self.portfolio_dividends_paid)
        add_int("portfolio_purchase_count", self.portfolio_purchase_count)
        
        return metadata
    
    def to_full_dict(self) -> Dict[str, Any]:
        """Convert entire document to dictionary."""
        data = self.to_metadata()
        data["price_history"] = [p.to_dict() for p in self.price_history]
        data["dividend_history"] = [d.to_dict() for d in self.dividend_history]
        data["description"] = self.description
        data["notes"] = self.notes
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StockDocument":
        """Create document from dictionary."""
        price_history = [
            PriceHistory.from_dict(p) 
            for p in data.get("price_history", [])
        ]
        dividend_history = [
            DividendRecord.from_dict(d) 
            for d in data.get("dividend_history", [])
        ]
        
        # Parse ex_dividend_date if present
        ex_div_date = None
        if data.get("ex_dividend_date"):
            try:
                ex_div_date = date.fromisoformat(data["ex_dividend_date"])
            except (ValueError, TypeError):
                pass
        
        return cls(
            symbol=data["symbol"],
            name=data["name"],
            sector=data.get("sector", "Unknown"),
            industry=data.get("industry", "Unknown"),
            exchange=data.get("exchange", "Unknown"),
            # Dividend fields
            dividend_yield=data.get("dividend_yield"),
            annual_dividend=data.get("annual_dividend"),
            dividend_streak_years=data.get("dividend_streak_years"),
            payout_ratio=data.get("payout_ratio"),
            fcf_payout_ratio=data.get("fcf_payout_ratio"),
            dividend_coverage=data.get("dividend_coverage"),
            ex_dividend_date=ex_div_date,
            payment_frequency=data.get("payment_frequency", 4),
            dividend_cagr_5y=data.get("dividend_cagr_5y"),
            dividend_cagr_10y=data.get("dividend_cagr_10y"),
            dividend_total_years=data.get("dividend_total_years"),
            # Price data
            current_price=data.get("current_price"),
            market_cap=data.get("market_cap"),
            fifty_two_week_high=data.get("fifty_two_week_high"),
            fifty_two_week_low=data.get("fifty_two_week_low"),
            beta=data.get("beta"),
            # Valuation
            pe_ratio=data.get("pe_ratio"),
            forward_pe=data.get("forward_pe"),
            peg_ratio=data.get("peg_ratio"),
            price_to_book=data.get("price_to_book"),
            price_to_sales=data.get("price_to_sales"),
            ev_ebitda=data.get("ev_ebitda"),
            # Financial health
            debt_to_equity=data.get("debt_to_equity"),
            debt_to_ebitda=data.get("debt_to_ebitda"),
            interest_coverage=data.get("interest_coverage"),
            current_ratio=data.get("current_ratio"),
            quick_ratio=data.get("quick_ratio"),
            # Profitability
            roe=data.get("roe"),
            roa=data.get("roa"),
            roic=data.get("roic"),
            profit_margin=data.get("profit_margin"),
            operating_margin=data.get("operating_margin"),
            gross_margin=data.get("gross_margin"),
            # Growth
            revenue_growth=data.get("revenue_growth"),
            earnings_growth=data.get("earnings_growth"),
            fcf_growth=data.get("fcf_growth"),
            # Performance
            price_return_1y=data.get("price_return_1y"),
            total_return_1y=data.get("total_return_1y"),
            price_return_5y=data.get("price_return_5y"),
            total_return_5y=data.get("total_return_5y"),
            # Analyst
            target_price=data.get("target_price"),
            target_upside=data.get("target_upside"),
            analyst_rating=data.get("analyst_rating"),
            num_analysts=data.get("num_analysts"),
            # Historical
            price_history=price_history,
            dividend_history=dividend_history,
            # Metadata
            source=parse_data_source(data.get("source")),
            last_updated=datetime.fromisoformat(data["last_updated"]) if data.get("last_updated") else datetime.now(),
            data_quality=data.get("data_quality", 0.0),
            description=data.get("description", ""),
            notes=data.get("notes", ""),
            in_portfolio=bool(data.get("in_portfolio", False)),
            portfolio_shares=data.get("portfolio_shares"),
            portfolio_avg_cost_per_share=data.get("portfolio_avg_cost_per_share"),
            portfolio_acquisition_value=data.get("portfolio_acquisition_value"),
            portfolio_dividends_paid=data.get("portfolio_dividends_paid"),
            portfolio_purchase_count=data.get("portfolio_purchase_count"),
        )


@dataclass
class SearchResult:
    """Result from vector similarity search."""
    document: StockDocument
    score: float  # Similarity score (0-1, higher = more similar)
    
    def __repr__(self) -> str:
        return f"SearchResult({self.document.symbol}, score={self.score:.3f})"
