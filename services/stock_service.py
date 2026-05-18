"""
Stock data fetching service with multi-provider aggregation.

This module handles data fetching from multiple sources, combining them
into a unified StockData model. Sources are abstracted as "public data".
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import yfinance as yf

from models.stock import StockData, DividendHistory
from config import MAX_DIVIDEND_YIELD_PCT, MAX_PAYOUT_RATIO_PCT, DATA_SOURCES
from utils.dividend_streak import annual_totals_from_payments, calculate_consecutive_increase_years


class StockService:
    """Service for fetching and aggregating stock data from multiple sources."""
    
    @staticmethod
    def _to_percent(value: Optional[float], max_valid: float = 100.0) -> Optional[float]:
        """Convert value to percentage, handling decimal and percentage formats."""
        if value is None:
            return None
        pct = value if value > 1 else value * 100
        if pct > max_valid or pct < -100:
            return None
        return pct
    
    @staticmethod
    def _safe_get(info: Dict, *keys: str, default: Any = None) -> Any:
        """Safely get value from dict, trying multiple keys."""
        for key in keys:
            if key in info and info[key] is not None:
                return info[key]
        return default
    
    @classmethod
    def _calc_dividend_history(
        cls, stock: Any, info: Dict, symbol: str
    ) -> Optional[DividendHistory]:
        """
        Calculate comprehensive dividend history metrics.
        
        Note: yfinance typically provides ~20 years of dividend data.
        For stocks with 50+ year streaks (Dividend Kings), we can only
        verify the streak within available data. The actual streak may
        be longer based on external data sources.
        """
        try:
            dividends = None
            
            # Try to get full dividend history
            try:
                dividends = stock.dividends
            except Exception:
                pass
            
            # Fallback to history if dividends property fails
            if dividends is None or dividends.empty:
                from utils.yfinance_history import fetch_price_history

                for period in ("max", "10y", "5y"):
                    hist = fetch_price_history(symbol, period=period)
                    if hist is not None and not hist.empty and "Dividends" in hist.columns:
                        dividends = hist["Dividends"][hist["Dividends"] > 0]
                        if not dividends.empty:
                            break
                if dividends is None or dividends.empty:
                    return None
            
            if dividends is None or dividends.empty:
                return None
            
            # Group by year and sum dividends
            div_df = dividends.to_frame("dividend")
            div_df["year"] = div_df.index.year
            annual = div_df.groupby("year")["dividend"].sum()
            
            if len(annual) < 2:
                return None
            
            current_year = datetime.now().year
            years_list = list(annual.index)
            values_list = list(annual.values)

            year_to_payments = {
                int(year): group["dividend"].tolist()
                for year, group in div_df.groupby("year")
            }
            annual_totals = annual_totals_from_payments(year_to_payments)
            consecutive = calculate_consecutive_increase_years(annual_totals)

            # Calculate total years of dividend payments
            total_years = len(annual)
            
            # For current annual dividend, prefer the last complete year
            if years_list and years_list[-1] == current_year and len(values_list) >= 2:
                current_annual = float(values_list[-2])  # Last complete year
            else:
                current_annual = float(annual.iloc[-1])
            
            # Calculate 5-year CAGR
            cagr_5y = 0.0
            if total_years >= 6:  # Need 6 years for 5-year growth
                start_5y = float(annual.iloc[-6])
                if start_5y > 0 and current_annual > 0:
                    cagr_5y = ((current_annual / start_5y) ** (1 / 5) - 1) * 100
            
            # Calculate 10-year CAGR
            cagr_10y = 0.0
            if total_years >= 11:  # Need 11 years for 10-year growth
                start_10y = float(annual.iloc[-11])
                if start_10y > 0 and current_annual > 0:
                    cagr_10y = ((current_annual / start_10y) ** (1 / 10) - 1) * 100
            elif total_years >= 3:
                # Fall back to available history
                start = float(annual.iloc[0])
                years_span = total_years - 1
                if start > 0 and current_annual > 0 and years_span > 0:
                    cagr_10y = ((current_annual / start) ** (1 / years_span) - 1) * 100
            
            # Get ex-dividend date
            ex_date = None
            raw_ex = info.get("exDividendDate")
            if raw_ex:
                try:
                    ex_date = datetime.fromtimestamp(raw_ex).date()
                except (ValueError, TypeError, OSError):
                    pass
            
            # Detect payment frequency from recent year
            payment_frequency = 4  # Default quarterly
            current_year = years_list[-1]
            payments_this_year = len(div_df[div_df["year"] == current_year])
            if payments_this_year >= 10:
                payment_frequency = 12  # Monthly
            elif payments_this_year >= 3:
                payment_frequency = 4   # Quarterly
            elif payments_this_year >= 2:
                payment_frequency = 2   # Semi-annual
            elif payments_this_year >= 1:
                payment_frequency = 1   # Annual
            
            return DividendHistory(
                consecutive_years=consecutive,
                total_years=total_years,
                cagr_5y=round(cagr_5y, 2),
                cagr_10y=round(cagr_10y, 2),
                current_annual=round(current_annual, 4),
                ex_dividend_date=ex_date,
                payment_frequency=payment_frequency,
            )
        except Exception:
            return None
    
    @classmethod
    def _calc_returns(cls, stock: Any, symbol: str) -> Dict[str, Optional[float]]:
        """Calculate price returns for various periods."""
        from utils.yfinance_history import fetch_price_history

        returns = {"1y": None, "5y": None, "1y_total": None}

        try:
            hist_1y = fetch_price_history(symbol, period="1y")
            if len(hist_1y) >= 200:
                returns["1y"] = ((hist_1y["Close"].iloc[-1] / hist_1y["Close"].iloc[0]) - 1) * 100
                if "Dividends" in hist_1y.columns:
                    total_div = hist_1y["Dividends"].sum()
                    start_price = hist_1y["Close"].iloc[0]
                    end_price = hist_1y["Close"].iloc[-1]
                    returns["1y_total"] = ((end_price + total_div) / start_price - 1) * 100
        except Exception:
            pass

        try:
            hist_5y = fetch_price_history(symbol, period="5y")
            if len(hist_5y) >= 1000:
                returns["5y"] = ((hist_5y["Close"].iloc[-1] / hist_5y["Close"].iloc[0]) - 1) * 100
        except Exception:
            pass

        return returns
    
    @classmethod
    def _calc_dividend_yield(cls, info: Dict, price: float) -> Optional[float]:
        """Calculate dividend yield with validation and fallback."""
        raw_yield = info.get("dividendYield")
        
        if raw_yield is not None:
            yield_pct = cls._to_percent(raw_yield, MAX_DIVIDEND_YIELD_PCT)
            if yield_pct is not None:
                return yield_pct
        
        # Fallback calculation
        dividend_rate = info.get("dividendRate")
        if dividend_rate and price and price > 0:
            calculated = (dividend_rate / price) * 100
            if calculated <= MAX_DIVIDEND_YIELD_PCT:
                return calculated
        
        return None
    
    @classmethod
    def _calc_derived_metrics(cls, info: Dict, price: float) -> Dict[str, Optional[float]]:
        """Calculate derived metrics not directly available."""
        metrics = {}
        
        # Price distance from 52-week high
        high_52w = info.get("fiftyTwoWeekHigh")
        if high_52w and price:
            metrics["price_to_52w_high_pct"] = ((price / high_52w) - 1) * 100
        
        # Target upside
        target = info.get("targetMeanPrice")
        if target and price and price > 0:
            metrics["target_upside_pct"] = ((target / price) - 1) * 100
        
        # Interest coverage (operating income / interest expense)
        op_income = info.get("operatingIncome")
        interest = info.get("interestExpense")
        if op_income and interest and interest > 0:
            metrics["interest_coverage"] = op_income / interest
        
        # Dividend coverage (EPS / Dividend per share)
        eps = info.get("trailingEps")
        div_rate = info.get("dividendRate")
        if eps and div_rate and div_rate > 0:
            metrics["dividend_coverage"] = eps / div_rate
        
        return metrics
    
    @classmethod
    def _assess_data_quality(cls, data: StockData) -> float:
        """Assess data completeness (0-100)."""
        critical_fields = [
            data.dividend_yield_pct, data.payout_ratio_pct, data.dividend_history,
            data.trailing_pe, data.price, data.market_cap, data.debt_to_equity,
        ]
        important_fields = [
            data.roe_pct, data.forward_pe, data.profit_margin_pct,
            data.current_ratio, data.target_price, data.beta,
        ]
        
        critical_count = sum(1 for f in critical_fields if f is not None)
        important_count = sum(1 for f in important_fields if f is not None)
        
        return (critical_count / len(critical_fields)) * 70 + (important_count / len(important_fields)) * 30
    
    @classmethod
    def fetch(cls, symbol: str) -> Optional[StockData]:
        """Fetch comprehensive stock data from aggregated public sources.
        
        Args:
            symbol: Stock ticker symbol.
            
        Returns:
            StockData object or None if fetch failed.
        """
        import logging
        
        # Suppress yfinance HTTP error logging temporarily
        yf_logger = logging.getLogger("yfinance")
        old_level = yf_logger.level
        yf_logger.setLevel(logging.CRITICAL)
        
        try:
            stock = yf.Ticker(symbol)
            
            # Some tickers have yfinance API issues with certain periods
            # Use fast_info as fallback if info fails
            try:
                info = stock.info
            except Exception:
                try:
                    fast = stock.fast_info
                    info = {
                        "regularMarketPrice": getattr(fast, "last_price", None),
                        "currentPrice": getattr(fast, "last_price", None),
                        "marketCap": getattr(fast, "market_cap", None),
                        "fiftyTwoWeekHigh": getattr(fast, "year_high", None),
                        "fiftyTwoWeekLow": getattr(fast, "year_low", None),
                    }
                except Exception:
                    return None
            
            if not info or info.get("regularMarketPrice") is None:
                return None
            
            price = cls._safe_get(info, "currentPrice", "regularMarketPrice", default=0)
            returns = cls._calc_returns(stock, symbol)
            derived = cls._calc_derived_metrics(info, price)
            
            # Build data object with all available metrics
            data = StockData(
                symbol=symbol,
                name=cls._safe_get(info, "longName", "shortName", default=symbol),
                sector=info.get("sector", "N/A"),
                industry=info.get("industry", "N/A"),
                
                # Dividend metrics
                dividend_yield_pct=cls._calc_dividend_yield(info, price),
                dividend_rate=info.get("dividendRate"),
                payout_ratio_pct=cls._to_percent(info.get("payoutRatio"), MAX_PAYOUT_RATIO_PCT),
                dividend_history=cls._calc_dividend_history(stock, info, symbol),
                dividend_coverage=derived.get("dividend_coverage"),
                
                # Price & valuation
                price=price,
                market_cap=info.get("marketCap"),
                trailing_pe=info.get("trailingPE"),
                forward_pe=info.get("forwardPE"),
                peg_ratio=info.get("pegRatio"),
                price_to_book=info.get("priceToBook"),
                price_to_sales=info.get("priceToSalesTrailing12Months"),
                ev_ebitda=info.get("enterpriseToEbitda"),
                fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
                fifty_two_week_low=info.get("fiftyTwoWeekLow"),
                price_to_52w_high_pct=derived.get("price_to_52w_high_pct"),
                
                # Financial health
                # Note: yfinance debtToEquity is returned as percentage (e.g., 279 = 2.79x)
                debt_to_equity=info.get("debtToEquity") / 100 if info.get("debtToEquity") else None,
                interest_coverage=derived.get("interest_coverage"),
                current_ratio=info.get("currentRatio"),
                quick_ratio=info.get("quickRatio"),
                
                # Profitability
                roe_pct=cls._to_percent(info.get("returnOnEquity")),
                roa_pct=cls._to_percent(info.get("returnOnAssets")),
                profit_margin_pct=cls._to_percent(info.get("profitMargins")),
                operating_margin_pct=cls._to_percent(info.get("operatingMargins")),
                gross_margin_pct=cls._to_percent(info.get("grossMargins")),
                
                # Growth
                revenue_growth_pct=cls._to_percent(info.get("revenueGrowth")),
                earnings_growth_pct=cls._to_percent(info.get("earningsGrowth")),
                
                # Analyst & market
                beta=info.get("beta"),
                target_price=info.get("targetMeanPrice"),
                target_upside_pct=derived.get("target_upside_pct"),
                analyst_rating=info.get("recommendationKey"),
                num_analysts=info.get("numberOfAnalystOpinions"),
                
                # Performance
                price_return_1y=returns.get("1y"),
                total_return_1y=returns.get("1y_total"),
                price_return_5y=returns.get("5y"),
                
                # Data tracking
                data_sources=[DATA_SOURCES["primary"], DATA_SOURCES["fundamentals"]],
            )
            
            # Assess data quality
            data.data_quality_score = cls._assess_data_quality(data)
            
            return data
            
        except Exception:
            return None
        finally:
            # Restore yfinance logger level
            yf_logger.setLevel(old_level)
