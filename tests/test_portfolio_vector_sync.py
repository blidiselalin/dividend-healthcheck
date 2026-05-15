"""Tests for portfolio ↔ vector DB linkage."""

from __future__ import annotations

from data_ingestion.models import StockDocument
from data_ingestion.portfolio_store import PortfolioHolding
from services.portfolio_vector_sync import apply_portfolio_fields


def test_apply_portfolio_fields_sets_metadata():
    doc = StockDocument(symbol="KO", name="KO")
    holding = PortfolioHolding(
        symbol="KO",
        shares=20.0,
        avg_cost_per_share=58.58,
        acquisition_value=1171.6,
        commission=1.05,
        dividends_paid=113.2,
        estimated_avg_price=79.52,
        sort_order=23,
    )
    apply_portfolio_fields(
        doc,
        holding=holding,
        purchase_count=3,
        company_name="Coca-Cola Co",
    )
    assert doc.in_portfolio is True
    assert doc.name == "Coca-Cola Co"
    assert doc.portfolio_shares == 20.0
    assert doc.portfolio_purchase_count == 3
    assert "Portfolio holding" in doc.embedding_text
