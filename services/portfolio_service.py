"""
Portfolio ingestion and analytics service.

Loads the "Portofoliu InteractiveBroker" worksheet and normalizes columns so
the Streamlit UI can expose all available portfolio details and charts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Dict, Iterable, Optional, Tuple

import pandas as pd

from services.vectordb_service import get_vectordb_service


@dataclass(frozen=True)
class PortfolioSummary:
    """Aggregated portfolio metrics for dashboard cards."""

    total_positions: int
    open_positions: int
    closed_positions: int
    total_cost: float
    market_value: float
    unrealized_gain_value: float
    unrealized_gain_pct: float
    day_gain_value: float
    realized_gain_value: float
    annual_dividend_income: float


class PortfolioService:
    """Parses and normalizes the Interactive Brokers portfolio worksheet."""

    DEFAULT_WORKBOOK = Path("data_ingestion") / "Investment_Plan.xlsx"
    DEFAULT_SHEET = "Portofoliu InteractiveBroker"

    _COLUMN_SYNONYMS: Dict[str, Tuple[str, ...]] = {
        "symbol": ("symbol", "ticker", "simbol"),
        "status": ("status", "stare"),
        "shares": ("shares", "nr actiuni", "nractiuni", "qty", "quantity"),
        "last_price": ("last price", "pret actual", "price", "pret"),
        "avg_cost": ("ac/share", "avg cost", "average cost", "pret mediu/actiune"),
        "total_cost": ("total cost", "valoare achizitie", "invested", "total amount"),
        "market_value": ("market value", "val. actuala", "valoare actuala", "value"),
        "total_div_income": (
            "tot div income",
            "venit/an",
            "venit an",
            "div platite",
            "total dividends",
        ),
        "day_gain_pct": ("day gain unrl (%)", "day gain (%)", "day gain %"),
        "day_gain_value": ("day gain unrl ($)", "day gain ($)", "day gain"),
        "total_gain_pct": ("tot gain unrl (%)", "tot gain (%)", "profit %", "total gain %"),
        "total_gain_value": ("tot gain unrl ($)", "total gain ($)", "profit"),
        "realized_gain_value": ("realized gain ($)", "realized gain"),
        "sector": ("sector",),
        "analyst_rating": ("evaluare analisti", "analyst", "analyst rating"),
        "pfcf": ("p/fcf",),
        "dividend_yield_pct": ("dividend yield", "div % aut", "yield %"),
        "ex_dividend_date": ("ex dividend date",),
        "dividend_pay_date": ("dividend pay date",),
        "weight_pct": ("pondere", "weight", "procent/total achizitii"),
    }

    _REQUIRED_CANDIDATES: Tuple[str, ...] = ("symbol", "ticker")
    _STATIC_FIELDS: Tuple[str, ...] = ("symbol", "shares", "avg_cost", "total_div_income")

    @classmethod
    def load_portfolio(
        cls,
        workbook_path: Optional[str] = None,
        sheet_name: str = DEFAULT_SHEET,
    ) -> pd.DataFrame:
        """Load and normalize holdings from workbook sheet."""
        path = Path(workbook_path or cls.DEFAULT_WORKBOOK)
        if not path.exists():
            raise FileNotFoundError(f"Workbook not found: {path}")

        raw = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
        if raw.empty:
            return pd.DataFrame()

        renamed = cls._rename_columns(raw)
        holdings = cls._extract_static_positions(renamed)
        if holdings.empty:
            return holdings

        holdings = cls._coerce_types(holdings)
        holdings = cls._enrich_from_vectordb(holdings)
        holdings = cls._ensure_derived_metrics(holdings)
        holdings = cls._coerce_types(holdings)

        holdings["position_state"] = holdings["shares"].apply(
            lambda x: "open" if pd.notna(x) and x > 0 else "closed"
        )
        holdings["status"] = holdings["position_state"].str.title()

        sort_col = "market_value" if "market_value" in holdings.columns else "total_cost"
        if sort_col in holdings.columns:
            holdings = holdings.sort_values(sort_col, ascending=False, na_position="last")

        return holdings.reset_index(drop=True)

    @classmethod
    def split_positions(cls, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Return (open_positions, closed_positions)."""
        if df.empty:
            return df.copy(), df.copy()

        if "position_state" not in df.columns:
            return df.copy(), df.iloc[0:0].copy()

        open_df = df[df["position_state"] == "open"].copy()
        closed_df = df[df["position_state"] == "closed"].copy()
        return open_df, closed_df

    @classmethod
    def summarize(cls, df: pd.DataFrame) -> PortfolioSummary:
        """Compute top-level portfolio metrics."""
        if df.empty:
            return PortfolioSummary(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        open_df, closed_df = cls.split_positions(df)

        total_cost = cls._safe_sum(open_df, "total_cost")
        market_value = cls._safe_sum(open_df, "market_value")
        unrealized_gain_value = cls._safe_sum(open_df, "total_gain_value")
        day_gain_value = cls._safe_sum(open_df, "day_gain_value")
        realized_gain_value = cls._safe_sum(closed_df, "realized_gain_value")
        annual_dividend_income = cls._safe_sum(open_df, "total_div_income")

        if total_cost > 0:
            unrealized_gain_pct = ((market_value - total_cost) / total_cost) * 100
        else:
            unrealized_gain_pct = 0.0

        return PortfolioSummary(
            total_positions=len(df),
            open_positions=len(open_df),
            closed_positions=len(closed_df),
            total_cost=total_cost,
            market_value=market_value,
            unrealized_gain_value=unrealized_gain_value,
            unrealized_gain_pct=unrealized_gain_pct,
            day_gain_value=day_gain_value,
            realized_gain_value=realized_gain_value,
            annual_dividend_income=annual_dividend_income,
        )

    @classmethod
    def _rename_columns(cls, df: pd.DataFrame) -> pd.DataFrame:
        rename_map: Dict[str, str] = {}
        normalized = {col: cls._norm(col) for col in df.columns}

        for canonical, candidates in cls._COLUMN_SYNONYMS.items():
            matched_col = cls._find_matching_column(normalized, candidates)
            if matched_col:
                rename_map[matched_col] = canonical

        return df.rename(columns=rename_map)

    @classmethod
    def _find_matching_column(
        cls,
        normalized_cols: Dict[str, str],
        candidates: Iterable[str],
    ) -> Optional[str]:
        candidate_set = tuple(cls._norm(c) for c in candidates)

        for col, norm in normalized_cols.items():
            if norm in candidate_set:
                return col

        for col, norm in normalized_cols.items():
            for candidate in candidate_set:
                if candidate and candidate in norm:
                    return col

        return None

    @classmethod
    def _extract_static_positions(cls, df: pd.DataFrame) -> pd.DataFrame:
        symbol_col = None
        for candidate in cls._REQUIRED_CANDIDATES:
            if candidate in df.columns:
                symbol_col = candidate
                break

        if symbol_col is None:
            raise ValueError(
                "Could not identify Symbol/Ticker column in portfolio sheet."
            )

        out = df.copy()
        out["symbol"] = out[symbol_col].astype(str).str.upper().str.strip()
        out = out[out["symbol"].str.match(r"^[A-Z][A-Z0-9.\-]{0,9}$", na=False)]

        excluded_symbols = {
            "N/A",
            "TOTAL",
            "TICKERS",
            "PORTOFOLIU",
            "PORTFOLIO",
            "DEPOSIT",
            "BUY",
            "SELL",
        }
        out = out[~out["symbol"].isin(excluded_symbols)]

        # Keep columns that are in _COLUMN_SYNONYMS or _STATIC_FIELDS
        static_cols = [c for c in cls._COLUMN_SYNONYMS.keys() if c in out.columns]
        if "symbol" not in static_cols:
            static_cols.append("symbol")

        out = out[static_cols]

        # Ensure static columns always exist.
        for col in cls._STATIC_FIELDS:
            if col not in out.columns:
                out[col] = pd.NA

        return out

    @classmethod
    def _enrich_from_vectordb(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Populate dynamic fields automatically from vector DB by symbol."""
        out = df.copy()

        # Initialize missing dynamic columns in out with NA if they do not exist
        dynamic_cols = {
            "name", "sector", "analyst_rating", "dividend_yield_pct", "last_price",
            "market_cap", "pfcf", "day_gain_pct", "day_gain_value", "realized_gain_value",
            "ex_dividend_date", "dividend_pay_date"
        }
        for col in dynamic_cols:
            if col not in out.columns:
                out[col] = pd.NA

        vdb = get_vectordb_service()
        stocks = {}
        if vdb.is_available:
            try:
                symbols = out["symbol"].dropna().astype(str).unique().tolist()
                stocks = vdb.get_stocks(symbols)
            except Exception:
                pass

        enriched_rows = []
        for _, row in out.iterrows():
            symbol = str(row.get("symbol", "")).upper().strip()
            stock = stocks.get(symbol) if stocks else None

            # Get existing values from the spreadsheet as primary, fall back to DB
            def get_val(col, db_val):
                excel_val = row.get(col)
                if pd.notna(excel_val):
                    return excel_val
                return db_val if db_val is not None else pd.NA

            dynamic = {
                "name": get_val("name", stock.name if stock else None),
                "sector": get_val("sector", stock.sector if stock else None),
                "analyst_rating": get_val("analyst_rating", stock.analyst_rating if stock else None),
                "dividend_yield_pct": get_val("dividend_yield_pct", stock.dividend_yield_pct if stock else None),
                "last_price": get_val("last_price", stock.price if stock else None),
                "market_cap": get_val("market_cap", stock.market_cap if stock else None),
                "pfcf": get_val("pfcf", None),
                "day_gain_pct": get_val("day_gain_pct", None),
                "day_gain_value": get_val("day_gain_value", None),
                "realized_gain_value": get_val("realized_gain_value", None),
                "ex_dividend_date": get_val(
                    "ex_dividend_date",
                    stock.dividend_history.ex_dividend_date if stock and stock.dividend_history else None
                ),
                "dividend_pay_date": get_val("dividend_pay_date", None),
            }

            shares = row.get("shares")
            avg_cost = row.get("avg_cost")
            last_price = dynamic["last_price"]

            # Compute total_cost
            excel_total_cost = row.get("total_cost")
            if pd.notna(excel_total_cost):
                total_cost = excel_total_cost
            elif pd.notna(shares) and pd.notna(avg_cost):
                total_cost = float(shares) * float(avg_cost)
            else:
                total_cost = pd.NA

            # Compute market_value
            excel_market_value = row.get("market_value")
            if pd.notna(excel_market_value):
                market_value = excel_market_value
            elif pd.notna(shares) and pd.notna(last_price):
                market_value = float(shares) * float(last_price)
            else:
                market_value = pd.NA

            # Compute gains
            excel_gain_val = row.get("total_gain_value")
            if pd.notna(excel_gain_val):
                total_gain_value = excel_gain_val
            elif pd.notna(total_cost) and pd.notna(market_value):
                total_gain_value = market_value - total_cost
            else:
                total_gain_value = pd.NA

            excel_gain_pct = row.get("total_gain_pct")
            if pd.notna(excel_gain_pct):
                total_gain_pct = excel_gain_pct
            elif pd.notna(total_cost) and pd.notna(market_value):
                total_gain_pct = (total_gain_value / total_cost) * 100 if total_cost else pd.NA
            else:
                total_gain_pct = pd.NA

            dynamic.update({
                "total_cost": total_cost,
                "market_value": market_value,
                "total_gain_value": total_gain_value,
                "total_gain_pct": total_gain_pct,
            })

            enriched_rows.append(dynamic)

        enriched_df = pd.DataFrame(enriched_rows, index=out.index)
        # Drop columns from out that overlap with enriched_df to avoid duplicates
        out = out.drop(columns=[col for col in enriched_df.columns if col in out.columns])
        return pd.concat([out, enriched_df], axis=1)

    @classmethod
    def _coerce_types(cls, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        numeric_cols = {
            "shares",
            "last_price",
            "avg_cost",
            "total_cost",
            "market_value",
            "total_div_income",
            "day_gain_value",
            "total_gain_value",
            "realized_gain_value",
            "pfcf",
        }
        percent_cols = {"day_gain_pct", "total_gain_pct", "dividend_yield_pct", "weight_pct"}

        for col in numeric_cols.intersection(out.columns):
            out[col] = out[col].apply(cls._to_number)

        for col in percent_cols.intersection(out.columns):
            out[col] = out[col].apply(cls._to_percent)

        for col in ("ex_dividend_date", "dividend_pay_date"):
            if col in out.columns:
                out[col] = pd.to_datetime(out[col], errors="coerce")

        return out

    @classmethod
    def _ensure_derived_metrics(cls, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        if "total_cost" not in out.columns and {"shares", "avg_cost"}.issubset(out.columns):
            out["total_cost"] = out["shares"] * out["avg_cost"]

        if "market_value" not in out.columns and {"shares", "last_price"}.issubset(out.columns):
            out["market_value"] = out["shares"] * out["last_price"]

        if "total_gain_value" not in out.columns and {"market_value", "total_cost"}.issubset(out.columns):
            out["total_gain_value"] = out["market_value"] - out["total_cost"]

        if "total_gain_pct" not in out.columns and {"market_value", "total_cost"}.issubset(out.columns):
            base = out["total_cost"].replace(0, pd.NA)
            out["total_gain_pct"] = ((out["market_value"] - out["total_cost"]) / base) * 100

        return out

    @staticmethod
    def _safe_sum(df: pd.DataFrame, col: str) -> float:
        if col not in df.columns:
            return 0.0
        return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())

    @staticmethod
    def _to_number(value: object) -> float:
        if pd.isna(value):
            return float("nan")
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        if not text or text in {"-", "--", "N/A", "n/a"}:
            return float("nan")

        text = text.replace("$", "").replace("€", "").replace("RON", "")
        text = text.replace(",", "")

        match = re.search(r"[-+]?\d*\.?\d+", text)
        if not match:
            return float("nan")
        return float(match.group())

    @classmethod
    def _to_percent(cls, value: object) -> float:
        num = cls._to_number(value)
        if pd.isna(num):
            return num
        return num * 100 if abs(num) <= 1 else num

    @staticmethod
    def _norm(value: object) -> str:
        text = str(value).strip().lower()
        text = text.replace("_", " ")
        text = re.sub(r"\s+", " ", text)
        return text
