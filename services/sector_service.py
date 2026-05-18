"""
Sector comparison service.

This module provides functionality for comparing stocks within sectors,
including Dividend Kings, Aristocrats, and external competitors.

Implements the "Dividends Don't Lie" philosophy (Geraldine Weiss, 1988):
A company's dividend policy is a more honest indicator of its financial 
health than reported earnings. High-quality dividend payers with consistent
histories are prioritized in comparisons.
"""

import time
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd

from config import DIVIDEND_KINGS, DIVIDEND_ARISTOCRATS, API_DELAY_SECONDS
from models.stock import StockData
from services.stock_service import StockService
from services.scoring import ScoringService

# Top PUBLIC dividend-paying stocks by sector for external reference
# These are well-known dividend payers NOT in the config list for comparison
# Prioritizes stocks with long dividend histories (Dividends Don't Lie philosophy)
SECTOR_REFERENCE_STOCKS: Dict[str, List[str]] = {
    "Technology": ["AAPL", "MSFT", "AVGO", "TXN", "INTC", "HPQ", "KLAC", "LRCX"],
    "Healthcare": ["PFE", "MRK", "LLY", "AMGN", "GILD", "CVS", "UNH", "AZN"],
    "Consumer Staples": ["WMT", "COST", "PG", "CL", "GIS", "K", "SJM", "CAG"],
    "Consumer Defensive": ["WMT", "COST", "PG", "CL", "GIS", "K", "SJM", "CAG"],
    "Consumer Discretionary": ["HD", "LOW", "MCD", "TGT", "DG", "ROST", "TJX", "YUM"],
    "Consumer Cyclical": ["HD", "LOW", "MCD", "TGT", "DG", "ROST", "TJX", "YUM"],
    "Financials": ["JPM", "WFC", "USB", "PNC", "TFC", "SCHW", "BLK", "MS"],
    "Financial Services": ["JPM", "WFC", "USB", "PNC", "TFC", "SCHW", "BLK", "MS"],
    "Industrials": ["CAT", "DE", "HON", "UNP", "LMT", "RTX", "GD", "WM"],
    "Energy": ["CVX", "COP", "EOG", "SLB", "PSX", "VLO", "MPC", "OXY"],
    "Utilities": ["DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL", "WEC"],
    "Real Estate": ["PLD", "CCI", "EQIX", "PSA", "SPG", "AVB", "EQR", "DLR"],
    "Communication Services": ["CMCSA", "DIS", "OMC", "IPG", "WBD"],
    "Telecommunications": ["CMCSA", "DIS", "OMC", "IPG"],
    "Basic Materials": ["LIN", "APD", "SHW", "ECL", "DD", "NEM", "FCX", "DOW"],
    "Materials": ["LIN", "APD", "SHW", "ECL", "DD", "NEM", "FCX", "DOW"],
}


class SectorService:
    """Service for sector-based stock analysis and comparison."""
    
    _sector_cache: Dict[str, List[Dict[str, Any]]] = {}
    _external_cache: Dict[str, List[Dict[str, Any]]] = {}
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached sector data."""
        cls._sector_cache = {}
        cls._external_cache = {}
    
    @staticmethod
    def _build_peer_dict(
        symbol: str,
        name: str,
        score: int,
        dividend_yield_pct: Optional[float] = None,
        trailing_pe: Optional[float] = None,
        payout_ratio_pct: Optional[float] = None,
        roe_pct: Optional[float] = None,
        debt_to_equity: Optional[float] = None,
        div_streak: Optional[int] = None,
        div_cagr: Optional[float] = None,
        dividend_tier: str = "Unknown",
        is_dividend_king: bool = False,
    ) -> Dict[str, Any]:
        """Build standardized peer comparison dictionary."""
        return {
            "symbol": symbol,
            "name": name,
            "score": score,
            "dividend_yield_pct": dividend_yield_pct,
            "trailing_pe": trailing_pe,
            "payout_ratio_pct": payout_ratio_pct,
            "roe_pct": roe_pct,
            "debt_to_equity": debt_to_equity,
            "div_streak": div_streak,
            "div_cagr": div_cagr,
            "dividend_tier": dividend_tier,
            "is_dividend_king": is_dividend_king,
        }
    
    @classmethod
    def _peer_from_stock_data(
        cls,
        data: StockData,
        score: int,
    ) -> Dict[str, Any]:
        """Build peer dictionary from StockData object."""
        div_streak = None
        div_cagr = None
        if data.dividend_history:
            div_streak = data.dividend_history.consecutive_years
            div_cagr = data.dividend_history.cagr_5y
        
        return cls._build_peer_dict(
            symbol=data.symbol,
            name=data.name,
            score=score,
            dividend_yield_pct=data.dividend_yield_pct,
            trailing_pe=data.trailing_pe,
            payout_ratio_pct=data.payout_ratio_pct,
            roe_pct=data.roe_pct,
            debt_to_equity=data.debt_to_equity,
            div_streak=div_streak,
            div_cagr=div_cagr,
            dividend_tier=data.dividend_tier,
            is_dividend_king=data.is_dividend_king,
        )
    
    @classmethod
    def get_sector_stocks(
        cls,
        sector: str,
        stock_list: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get all dividend stocks in a sector, sorted by score.
        
        Args:
            sector: Sector name to filter by.
            stock_list: List of symbols to search (defaults to DIVIDEND_KINGS).
            use_cache: Whether to use cached data.
            
        Returns:
            List of peer dictionaries sorted by score (descending).
        """
        stock_list = stock_list or DIVIDEND_KINGS
        cache_key = f"{sector}_{','.join(sorted(stock_list[:5]))}"
        
        if use_cache and cache_key in cls._sector_cache:
            return cls._sector_cache[cache_key]
        
        sector_stocks: List[Dict[str, Any]] = []
        
        for symbol in stock_list:
            data = StockService.fetch(symbol)
            if data and data.sector == sector:
                score = ScoringService.calculate_score(data)
                sector_stocks.append(cls._peer_from_stock_data(data, score))
            time.sleep(API_DELAY_SECONDS)
        
        sector_stocks.sort(key=lambda x: x["score"], reverse=True)
        cls._sector_cache[cache_key] = sector_stocks
        return sector_stocks
    
    @classmethod
    def get_external_competitors(
        cls,
        sector: str,
        exclude_symbols: List[str],
        max_count: int = 3,
    ) -> List[Dict[str, Any]]:
        """Fetch top external dividend-paying reference stocks from sector.
        
        Implements "Dividends Don't Lie" philosophy by prioritizing stocks with:
        - Consistent dividend payment history
        - Reasonable yield (not suspiciously high)
        - Strong dividend coverage
        
        Args:
            sector: Sector name.
            exclude_symbols: Symbols to exclude from results.
            max_count: Maximum number of reference stocks to return.
            
        Returns:
            List of peer dictionaries sorted by dividend quality score.
        """
        if not sector or not sector.strip():
            return []
        
        cache_key = f"ext_{sector}_{len(exclude_symbols)}"
        if cache_key in cls._external_cache:
            return cls._external_cache[cache_key][:max_count]

        try:
            from services.sp500_peers_service import find_sector_peers

            exclude_set = set(exclude_symbols) | set(DIVIDEND_KINGS) | set(DIVIDEND_ARISTOCRATS)
            sp500_peers = find_sector_peers(
                sector=sector,
                exclude_symbols=list(exclude_set),
                max_peers=max_count,
            )
            if sp500_peers:
                for peer in sp500_peers:
                    peer.setdefault("yield_quality", peer.get("interest", 0))
                cls._external_cache[cache_key] = sp500_peers
                return sp500_peers[:max_count]
        except Exception:
            pass
        
        # Fallback: hardcoded reference list + live API
        candidates = []
        sector_parts = sector.split()
        sector_variations = [sector, sector.replace(" ", "")]
        if sector_parts:
            sector_variations.append(sector_parts[0])
        
        for sector_key in sector_variations:
            candidates = SECTOR_REFERENCE_STOCKS.get(sector_key, [])
            if candidates:
                break
        
        if not candidates:
            return []
        
        # Exclude symbols already in our config or exclude list
        all_config_stocks = set(DIVIDEND_KINGS) | set(DIVIDEND_ARISTOCRATS)
        exclude_set = set(exclude_symbols) | all_config_stocks
        candidates = [s for s in candidates if s not in exclude_set]
        
        external_stocks: List[Dict[str, Any]] = []
        for symbol in candidates:
            if len(external_stocks) >= max_count + 2:
                break
            
            try:
                data = StockService.fetch(symbol)
                if not data:
                    continue
                    
                # Apply "Dividends Don't Lie" filters:
                # 1. Must pay a dividend
                if not data.dividend_yield_pct or data.dividend_yield_pct <= 0:
                    continue
                
                # 2. Yield shouldn't be suspiciously high (possible distress)
                if data.dividend_yield_pct > 10:
                    continue
                
                # 3. Should have some dividend history
                has_history = (
                    data.dividend_history and 
                    data.dividend_history.consecutive_years >= 3
                )
                
                score = ScoringService.calculate_score(data)
                
                stock_info = cls._peer_from_stock_data(data, score)
                stock_info["has_history"] = has_history
                stock_info["yield_quality"] = cls._assess_yield_quality(data)
                
                external_stocks.append(stock_info)
                
            except Exception:
                pass
            
            time.sleep(API_DELAY_SECONDS)
        
        # Sort by dividend quality, not just score
        # Prioritize: has history > yield quality > score
        external_stocks.sort(
            key=lambda x: (
                x.get("has_history", False),
                x.get("yield_quality", 0),
                x["score"]
            ),
            reverse=True
        )
        
        cls._external_cache[cache_key] = external_stocks
        return external_stocks[:max_count]
    
    @staticmethod
    def _assess_yield_quality(data: StockData) -> float:
        """
        Assess dividend yield quality based on "Dividends Don't Lie" principles.
        
        Returns score 0-100 where higher = more reliable yield signal.
        """
        score = 50.0  # Base score
        
        # Positive factors
        if data.dividend_history:
            streak = data.dividend_history.consecutive_years
            if streak >= 25:
                score += 25
            elif streak >= 10:
                score += 15
            elif streak >= 5:
                score += 10
            
            # Growing dividends are a strong signal
            if data.dividend_history.cagr_5y and data.dividend_history.cagr_5y > 5:
                score += 10
        
        # Payout ratio - sustainable payouts are key
        if data.payout_ratio_pct:
            if 30 <= data.payout_ratio_pct <= 60:
                score += 15  # Sweet spot
            elif data.payout_ratio_pct < 30:
                score += 10  # Conservative
            elif data.payout_ratio_pct > 80:
                score -= 10  # Risky
        
        # Negative factors (red flags)
        if data.dividend_yield_pct and data.dividend_yield_pct > 7:
            score -= 15  # Unusually high yield may signal trouble
        
        return max(0, min(100, score))
    
    @classmethod
    def get_top_sector_peers(
        cls,
        current_stock: StockData,
        current_score: int,
        include_external: bool = True,
        use_cache: bool = True,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Get sector peers for comparison.
        
        Args:
            current_stock: Stock being analyzed.
            current_score: Score of current stock.
            include_external: Whether to include external competitors.
            use_cache: Whether to use cached sector data.
            
        Returns:
            Tuple of (dividend_stocks_in_sector, external_competitors).
        """
        if current_stock.sector == "N/A":
            return [], []
        
        sector_stocks = cls.get_sector_stocks(current_stock.sector, use_cache=use_cache)
        
        # Add current stock if not in list
        if not any(s["symbol"] == current_stock.symbol for s in sector_stocks):
            sector_stocks = sector_stocks.copy()
            sector_stocks.append(cls._peer_from_stock_data(current_stock, current_score))
            sector_stocks.sort(key=lambda x: x["score"], reverse=True)
        
        external: List[Dict[str, Any]] = []
        if include_external:
            existing_symbols = [s["symbol"] for s in sector_stocks]
            external = cls.get_external_competitors(
                current_stock.sector, existing_symbols, max_count=3
            )
        
        return sector_stocks, external
    
    @classmethod
    def get_quick_sector_peers(
        cls,
        current_stock: StockData,
        current_score: int,
        cached_df: pd.DataFrame,
        include_external: bool = True,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Get sector peers from cached DataFrame (no API calls for main list).
        
        Args:
            current_stock: Stock being analyzed.
            current_score: Score of current stock.
            cached_df: DataFrame with pre-fetched stock data.
            include_external: Whether to include external competitors.
            
        Returns:
            Tuple of (dividend_stocks_in_sector, external_competitors).
        """
        if cached_df is None or current_stock.sector == "N/A":
            return [], []
        
        sector_df = cached_df[cached_df["Sector"] == current_stock.sector]
        
        sector_stocks: List[Dict[str, Any]] = []
        for _, row in sector_df.iterrows():
            stock_data = row.get("_data")
            if stock_data is None:
                continue
            
            div_streak = None
            div_cagr = None
            if hasattr(stock_data, "dividend_history") and stock_data.dividend_history:
                div_streak = stock_data.dividend_history.consecutive_years
                div_cagr = stock_data.dividend_history.cagr_5y
            
            sector_stocks.append(cls._build_peer_dict(
                symbol=row["Symbol"],
                name=row["Company"],
                score=row["Score"],
                dividend_yield_pct=row.get("Yield %"),
                trailing_pe=row.get("P/E"),
                payout_ratio_pct=row.get("Payout %"),
                roe_pct=getattr(stock_data, "roe_pct", None),
                debt_to_equity=getattr(stock_data, "debt_to_equity", None),
                div_streak=div_streak,
                div_cagr=div_cagr,
                dividend_tier=getattr(stock_data, "dividend_tier", "Unknown"),
                is_dividend_king=row["Symbol"] in DIVIDEND_KINGS,
            ))
        
        sector_stocks.sort(key=lambda x: x["score"], reverse=True)
        
        external: List[Dict[str, Any]] = []
        if include_external:
            existing_symbols = [s["symbol"] for s in sector_stocks]
            external = cls.get_external_competitors(
                current_stock.sector, existing_symbols, max_count=3
            )
        
        return sector_stocks, external
