"""
Data model converters.

Provides conversion functions between different data models
used across the application.
"""

from typing import Optional, List
from datetime import date


def document_to_stock_data(doc: "StockDocument") -> "StockData":
    """
    Convert a StockDocument (vector DB model) to StockData (UI model).
    
    This is the canonical conversion function used by all services
    to ensure consistent data transformation.
    
    Args:
        doc: StockDocument from the vector database.
        
    Returns:
        StockData instance for UI consumption.
    """
    from models.stock import StockData, DividendHistory
    from data_ingestion.models import StockDocument
    
    # Build DividendHistory from document
    div_history = None
    if doc.dividend_streak_years is not None or doc.dividend_history:
        cagr_5y = doc.dividend_cagr_5y or 0.0
        cagr_10y = doc.dividend_cagr_10y or 0.0
        total_years = doc.dividend_total_years or 0
        
        # Calculate total years from history if not set
        if not total_years and doc.dividend_history:
            years = set(d.ex_date.year for d in doc.dividend_history)
            total_years = len(years)
        
        # Get ex-dividend date from history if not set
        ex_date = doc.ex_dividend_date
        if not ex_date and doc.dividend_history:
            sorted_divs = sorted(doc.dividend_history, key=lambda x: x.ex_date, reverse=True)
            if sorted_divs:
                ex_date = sorted_divs[0].ex_date
        
        # Get payment frequency
        payment_freq = doc.payment_frequency
        if not payment_freq and doc.dividend_history:
            payment_freq = _detect_payment_frequency(doc.dividend_history)
        
        div_history = DividendHistory(
            consecutive_years=doc.dividend_streak_years or 0,
            total_years=total_years,
            cagr_5y=cagr_5y,
            cagr_10y=cagr_10y,
            current_annual=doc.annual_dividend or 0.0,
            ex_dividend_date=ex_date,
            payment_frequency=payment_freq,
        )
    
    # Calculate price to 52w high percentage
    price_to_52w_high = None
    if doc.current_price and doc.fifty_two_week_high:
        price_to_52w_high = ((doc.current_price / doc.fifty_two_week_high) - 1) * 100
    
    stock_data = StockData(
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
    
    # Store last updated for freshness checks
    stock_data._last_updated = doc.last_updated
    
    return stock_data


def _detect_payment_frequency(dividend_history: List) -> int:
    """
    Detect dividend payment frequency from history.
    
    Returns payments per year as int (12=monthly, 4=quarterly, 2=semi-annual, 1=annual).
    """
    if not dividend_history or len(dividend_history) < 2:
        return 4  # Default to quarterly
    
    try:
        # Count payments per year
        years: dict = {}
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
