"""End-to-end portfolio workflow test across core services."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date

from data_ingestion.deposits_store import DepositsStore
from data_ingestion.dividend_income_store import MonthlyNetDividend
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore
from services.portfolio_deposits_service import PortfolioDepositsService
from services.portfolio_dividend_income_service import PortfolioDividendIncomeService
from services.portfolio_management_service import PortfolioManagementService
from services.portfolio_purchase_journal_service import PortfolioPurchaseJournalService


def test_portfolio_workflow_services_share_state(temp_db) -> None:
    portfolio = PortfolioStore(db_path=temp_db, seed=False)
    journal = PurchaseJournalStore(db_path=temp_db, seed=False)
    deposits = DepositsStore(db_path=temp_db, seed=False)

    management = PortfolioManagementService(
        portfolio=portfolio,
        journal=journal,
        deposits=deposits,
    )

    management.add_ticker(
        "KO",
        shares=20,
        avg_cost_per_share=50.0,
        skip_validation=True,
        enrich_vector=False,
    )
    management.add_purchase("KO", date(2024, 1, 10), 48.0)
    management.add_purchase("KO", date(2024, 3, 20), 52.0)
    management.add_deposit(
        year=2024,
        month=3,
        label="March 2024",
        deposit_eur=1000.0,
        deposit_usd=1090.0,
        portfolio_eur=9800.0,
    )

    journal_service = PortfolioPurchaseJournalService(
        journal_store=journal, portfolio_store=portfolio
    )
    deposits_service = PortfolioDepositsService(store=deposits)

    purchases = journal_service.list_purchases()
    purchase_summary = journal_service.summarize(purchases)
    deposit_summary = deposits_service.summarize()

    assert purchase_summary.total_lots == 2
    assert purchase_summary.symbols_with_buys == 1
    assert purchase_summary.symbols_in_portfolio == 1

    assert deposit_summary.month_count == 1
    assert deposit_summary.total_deposits_eur == 1000.0
    assert deposit_summary.latest_portfolio_eur == 9800.0

    income_service = PortfolioDividendIncomeService()
    income_records = [
        MonthlyNetDividend(
            period=date(2024, 3, 1),
            year=2024,
            month=3,
            month_label="Mar",
            net_usd=90.0,
            tax_rate_pct=10.0,
            gross_usd=100.0,
            tax_withheld_usd=10.0,
        )
    ]
    income_summary = income_service.summarize(records=income_records, ytd_year=2024)
    assert income_summary.total_net_usd == 90.0
    assert income_summary.ytd_net_usd == 90.0
