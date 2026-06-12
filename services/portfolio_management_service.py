"""
Create and update portfolio data (holdings, purchases, deposits) and sync the vector DB.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from config import DELISTED_SYMBOLS
from data_ingestion.deposits_store import DepositsStore, MonthlyDeposit
from data_ingestion.portfolio_store import PortfolioHolding, PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore, PurchaseRecord
from services.portfolio_context import create_portfolio_context
from services.portfolio_dividend_sync_service import sync_received_dividends
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
    company_name: str | None = None


class PortfolioManagementService:
    """Portfolio CRUD and vector DB sync for new tickers."""

    def __init__(
        self,
        portfolio: PortfolioStore | None = None,
        journal: PurchaseJournalStore | None = None,
        deposits: DepositsStore | None = None,
    ) -> None:
        if portfolio is None and journal is None and deposits is None:
            ctx = create_portfolio_context()
            self.portfolio = ctx.portfolio
            self.journal = ctx.journal
            self.deposits = ctx.deposits
        else:
            anchor = portfolio or journal or deposits
            path = anchor.db_path if anchor is not None else None
            self.portfolio = portfolio or PortfolioStore(db_path=path, seed=False)
            self.journal = journal or PurchaseJournalStore(db_path=path, seed=False)
            self.deposits = deposits or DepositsStore(db_path=path, seed=False)

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
                "Use 1-10 characters: letters, digits, dot, or hyphen (e.g. KO, BRK.B).",
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

            from data_ingestion.stock_enricher import create_stock_enricher

            enricher = create_stock_enricher(request_delay=0.2)
            document = enricher.fetch_document(normalized)
            if document is None or not document.name or document.name == normalized:
                return SymbolValidation(
                    normalized,
                    False,
                    f"Could not find {normalized} in the shared library or market data APIs.",
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
        company_name: str | None = None,
        enrich_vector: bool = True,
        skip_validation: bool = False,
    ) -> dict[str, Any]:
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
        vector_stats: dict[str, Any] = {}
        if enrich_vector:
            vector_stats = sync_portfolio_to_vector_db(
                enrich_missing=True,
                symbols=[normalized],
            )
        sync_received_dividends(db_path=self.portfolio.db_path, symbols=[normalized])
        return {
            "holding": holding,
            "vector_sync": vector_stats,
            "symbol": normalized,
        }

    def update_holding_fields(
        self,
        symbol: str,
        **fields: Any,
    ) -> PortfolioHolding | None:
        old_symbol = self.normalize_symbol(symbol)
        new_symbol = fields.get("symbol")
        if new_symbol:
            new_symbol = self.normalize_symbol(new_symbol)
            fields["symbol"] = new_symbol
        else:
            new_symbol = old_symbol

        ticker_changed = new_symbol != old_symbol

        if ticker_changed:
            if self.portfolio.holding_exists(new_symbol):
                raise ValueError(f"{new_symbol} is already in the portfolio.")

            check = self.validate_symbol(new_symbol)
            if not check.valid:
                raise ValueError(check.message)

            if "company_name" not in fields or not fields["company_name"]:
                fields["company_name"] = check.company_name

            with self.portfolio._connect() as connection:
                if connection.is_postgres:
                    connection.execute(
                        "UPDATE holdings SET symbol = ? WHERE user_id = ? AND symbol = ?",
                        (new_symbol, connection.user_id, old_symbol),
                    )
                    connection.execute(
                        "UPDATE purchase_journal SET symbol = ? WHERE user_id = ? AND symbol = ?",
                        (new_symbol, connection.user_id, old_symbol),
                    )
                    connection.execute(
                        "UPDATE dividend_receipts SET symbol = ? WHERE user_id = ? AND symbol = ?",
                        (new_symbol, connection.user_id, old_symbol),
                    )
                else:
                    connection.execute(
                        "UPDATE holdings SET symbol = ? WHERE symbol = ?",
                        (new_symbol, old_symbol),
                    )
                    connection.execute(
                        "UPDATE purchase_journal SET symbol = ? WHERE symbol = ?",
                        (new_symbol, old_symbol),
                    )
                    connection.execute(
                        "UPDATE dividend_receipts SET symbol = ? WHERE symbol = ?",
                        (new_symbol, old_symbol),
                    )

            holding = self.portfolio.update_holding(new_symbol, **fields)
            if holding is not None:
                sync_portfolio_to_vector_db(enrich_missing=False, symbols=[old_symbol])
                sync_portfolio_to_vector_db(enrich_missing=True, symbols=[new_symbol])
                sync_received_dividends(db_path=self.portfolio.db_path, symbols=[new_symbol])
        else:
            holding = self.portfolio.update_holding(old_symbol, **fields)
            if holding is not None:
                sync_portfolio_to_vector_db(enrich_missing=False, symbols=[holding.symbol])
                sync_received_dividends(db_path=self.portfolio.db_path, symbols=[holding.symbol])

        return holding

    def remove_ticker(self, symbol: str) -> bool:
        normalized = self.normalize_symbol(symbol)
        removed = self.portfolio.delete_holding(normalized)
        if removed:
            sync_received_dividends(db_path=self.portfolio.db_path)
        return removed

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
        sync_received_dividends(db_path=self.portfolio.db_path, symbols=[normalized])
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

    def list_deposits(self) -> list[MonthlyDeposit]:
        return self.deposits.list_deposits()

    def get_deposit(self, year: int, month: int) -> MonthlyDeposit | None:
        period_key = f"{year:04d}-{month:02d}"
        for item in self.list_deposits():
            if item.period_key == period_key:
                return item
        return None

    def deposits_missing_portfolio_value(self) -> list[MonthlyDeposit]:
        return [item for item in self.list_deposits() if item.portfolio_eur <= 0]

    @staticmethod
    def estimate_portfolio_eur_from_usd(
        value_usd: float,
        deposit: MonthlyDeposit | None = None,
        *,
        default_fx: float = 0.92,
    ) -> float:
        """Convert a USD portfolio total to EUR using the month's deposit FX when available."""
        if value_usd <= 0:
            return 0.0
        if deposit is not None and deposit.deposit_eur > 0 and deposit.deposit_usd > 0:
            fx = deposit.deposit_eur / deposit.deposit_usd
        else:
            fx = default_fx
        return round(value_usd * fx, 2)

    def list_holdings(self) -> list[PortfolioHolding]:
        return self.portfolio.list_holdings()
