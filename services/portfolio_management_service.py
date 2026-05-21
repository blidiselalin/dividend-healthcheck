"""
Create and update portfolio data (holdings, purchases, deposits) and sync the vector DB.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

from config import DELISTED_SYMBOLS
from data_ingestion.deposits_store import DepositsStore, MonthlyDeposit
from data_ingestion.portfolio_store import PortfolioHolding, PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore, PurchaseRecord
from services.portfolio_vector_sync import sync_portfolio_to_vector_db

logger = logging.getLogger(__name__)

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

SECTION_KEYS = (
    "dashboard",
    "dividends",
    "dividend_growth",
    "journal",
    "holdings",
    "deposits",
    "all",
)


@dataclass(frozen=True)
class SymbolValidation:
    symbol: str
    valid: bool
    message: str
    company_name: Optional[str] = None


class PortfolioManagementService:
    """Portfolio CRUD and vector DB sync for new tickers."""

    def __init__(
        self,
        portfolio: Optional[PortfolioStore] = None,
        journal: Optional[PurchaseJournalStore] = None,
        deposits: Optional[DepositsStore] = None,
    ) -> None:
        self.portfolio = portfolio or PortfolioStore()
        self.journal = journal or PurchaseJournalStore()
        self.deposits = deposits or DepositsStore()

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper().replace(" ", "")

    def validate_symbol(self, symbol: str) -> SymbolValidation:
        normalized = self.normalize_symbol(symbol)
        if not normalized:
            return SymbolValidation("", False, "Enter a ticker symbol.")
        if normalized in DELISTED_SYMBOLS:
            return SymbolValidation(
                normalized, False, f"{normalized} is marked delisted in config."
            )
        if not _SYMBOL_RE.match(normalized):
            return SymbolValidation(
                normalized,
                False,
                "Use 1–10 characters: letters, digits, dot, or hyphen (e.g. KO, BRK.B).",
            )

        try:
            from services.shared_market_db import get_document

            cached = get_document(normalized)
            if cached is not None and cached.name and cached.name != normalized:
                return SymbolValidation(
                    normalized,
                    True,
                    "OK (shared S&P library)",
                    company_name=cached.name,
                )

            from data_ingestion.yfinance_enricher import YFinanceEnricher

            enricher = YFinanceEnricher(request_delay=0.2)
            document = enricher.fetch_document(normalized)
            if document is None or not document.name or document.name == normalized:
                return SymbolValidation(
                    normalized,
                    False,
                    f"Could not find {normalized} in the shared library or Yahoo Finance.",
                )
            return SymbolValidation(
                normalized,
                True,
                "OK",
                company_name=document.name,
            )
        except Exception as exc:
            logger.warning("Symbol validation failed for %s: %s", normalized, exc)
            return SymbolValidation(
                normalized,
                False,
                f"Could not verify {normalized}: {exc}",
            )

    def add_ticker(
        self,
        symbol: str,
        *,
        shares: float,
        avg_cost_per_share: float,
        commission: float = 0.0,
        dividends_paid: float = 0.0,
        company_name: Optional[str] = None,
        enrich_vector: bool = True,
        skip_validation: bool = False,
    ) -> Dict[str, Any]:
        """Add a new holding and register it in the vector database."""
        normalized = self.normalize_symbol(symbol)
        if self.portfolio.holding_exists(normalized):
            raise ValueError(f"{normalized} is already in the portfolio.")

        resolved_name = company_name
        if not skip_validation:
            check = self.validate_symbol(normalized)
            if not check.valid:
                raise ValueError(check.message)
            resolved_name = resolved_name or check.company_name

        holding = self.portfolio.upsert_holding(
            normalized,
            shares=shares,
            avg_cost_per_share=avg_cost_per_share,
            commission=commission,
            dividends_paid=dividends_paid,
            company_name=resolved_name,
        )
        vector_stats: Dict[str, Any] = {}
        if enrich_vector:
            vector_stats = sync_portfolio_to_vector_db(
                enrich_missing=True,
                symbols=[normalized],
            )
        return {
            "holding": holding,
            "vector_sync": vector_stats,
            "symbol": normalized,
        }

    def update_holding_fields(
        self,
        symbol: str,
        **fields: Any,
    ) -> Optional[PortfolioHolding]:
        holding = self.portfolio.update_holding(symbol, **fields)
        if holding is not None:
            sync_portfolio_to_vector_db(enrich_missing=False, symbols=[holding.symbol])
        return holding

    def remove_ticker(self, symbol: str) -> bool:
        normalized = self.normalize_symbol(symbol)
        return self.portfolio.delete_holding(normalized)

    def add_purchase(
        self,
        symbol: str,
        purchase_date: date,
        price_usd: float,
    ) -> PurchaseRecord:
        normalized = self.normalize_symbol(symbol)
        if not self.portfolio.holding_exists(normalized):
            raise ValueError(f"Add {normalized} to holdings before logging purchases.")
        record = self.journal.add_purchase(normalized, purchase_date, price_usd)
        sync_portfolio_to_vector_db(enrich_missing=False, symbols=[normalized])
        return record

    def add_deposit(
        self,
        *,
        year: int,
        month: int,
        label: str,
        deposit_eur: float,
        deposit_usd: float,
        portfolio_eur: float,
    ) -> MonthlyDeposit:
        return self.deposits.upsert_deposit(
            year=year,
            month=month,
            label=label,
            deposit_eur=deposit_eur,
            deposit_usd=deposit_usd,
            portfolio_eur=portfolio_eur,
        )

    def list_holdings(self) -> List[PortfolioHolding]:
        return self.portfolio.list_holdings()
