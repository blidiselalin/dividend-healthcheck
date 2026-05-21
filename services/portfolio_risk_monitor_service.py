"""
Portfolio risk snapshot: load holdings, evaluate attention rules, cache metadata.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from config import PORTFOLIO_RISK_REFRESH_SECONDS
from services.portfolio_attention_service import AttentionItem, AttentionSummary, PortfolioAttentionService
from services.portfolio_details_service import PortfolioDetailsService

if TYPE_CHECKING:
    from services.portfolio_analysis_preload import PortfolioAnalysisPreload
    from services.portfolio_details_service import PortfolioDetailRow


class PortfolioRiskMonitorService:
    """Build and serialize portfolio risk / attention snapshots."""

    def __init__(
        self,
        attention: Optional[PortfolioAttentionService] = None,
        details: Optional[PortfolioDetailsService] = None,
    ) -> None:
        self._attention = attention or PortfolioAttentionService()
        self._details = details or PortfolioDetailsService()

    @staticmethod
    def is_stale(
        checked_at: Optional[datetime],
        *,
        interval_seconds: int = PORTFOLIO_RISK_REFRESH_SECONDS,
        now: Optional[datetime] = None,
    ) -> bool:
        if checked_at is None:
            return True
        reference = now or datetime.now()
        return (reference - checked_at).total_seconds() >= interval_seconds

    def load_portfolio_payload(
        self,
    ) -> tuple[List["PortfolioDetailRow"], "PortfolioAnalysisPreload"]:
        return self._details.build_rows_with_cache()

    def build_summary(
        self,
        rows: List["PortfolioDetailRow"],
        preload: "PortfolioAnalysisPreload",
        *,
        reference_date: Optional[date] = None,
        include_news: bool = False,
    ) -> AttentionSummary:
        news_by_symbol = None
        if include_news:
            preview = self._attention.build_summary(rows, preload, reference_date=reference_date)
            symbols = [item.symbol for item in preview.risk_items]
            if symbols:
                news_by_symbol = self._attention.fetch_news_for_symbols(symbols)
        return self._attention.build_summary(
            rows,
            preload,
            reference_date=reference_date,
            news_by_symbol=news_by_symbol,
        )

    @staticmethod
    def summary_to_store(summary: AttentionSummary) -> Dict[str, Any]:
        return {
            "reference_date": summary.reference_date.isoformat(),
            "risk_items": [
                PortfolioRiskMonitorService._item_to_store(item)
                for item in summary.risk_items
            ],
            "dividend_items": [
                PortfolioRiskMonitorService._item_to_store(item)
                for item in summary.dividend_items
            ],
            "opportunity_items": [
                PortfolioRiskMonitorService._item_to_store(item)
                for item in summary.opportunity_items
            ],
        }

    @staticmethod
    def summary_from_store(data: Optional[Dict[str, Any]]) -> Optional[AttentionSummary]:
        if not data:
            return None
        ref_raw = data.get("reference_date")
        ref = date.fromisoformat(ref_raw) if ref_raw else date.today()

        if "risk_items" in data or "dividend_items" in data or "motion_dividend_items" in data:
            risk_items = [
                PortfolioRiskMonitorService._item_from_store(item)
                for item in data.get("risk_items", [])
            ]
            dividend_items = [
                PortfolioRiskMonitorService._item_from_store(item)
                for item in data.get(
                    "dividend_items",
                    data.get("motion_dividend_items", []),
                )
            ]
            opportunity_items = [
                PortfolioRiskMonitorService._item_from_store(item)
                for item in data.get("opportunity_items", [])
            ]
            return AttentionSummary(
                risk_items=risk_items,
                opportunity_items=opportunity_items,
                dividend_items=dividend_items,
                reference_date=ref,
            )

        from services.portfolio_attention_service import split_legacy_attention_items

        legacy_items = [
            PortfolioRiskMonitorService._item_from_store(item)
            for item in data.get("items", [])
        ]
        return split_legacy_attention_items(legacy_items, ref)

    @staticmethod
    def _item_to_store(item: AttentionItem) -> Dict[str, Any]:
        payload = asdict(item)
        payload["categories"] = list(item.categories)
        payload["reasons"] = list(item.reasons)
        if payload.get("ex_date") is not None:
            payload["ex_date"] = payload["ex_date"].isoformat()
        if payload.get("pay_date") is not None:
            payload["pay_date"] = payload["pay_date"].isoformat()
        return payload

    @staticmethod
    def _item_from_store(data: Dict[str, Any]) -> AttentionItem:
        ex_raw = data.get("ex_date")
        pay_raw = data.get("pay_date")
        return AttentionItem(
            symbol=data["symbol"],
            company=data["company"],
            severity=data["severity"],
            score=int(data["score"]),
            categories=tuple(data.get("categories", ())),
            reasons=tuple(data.get("reasons", ())),
            portfolio_weight_pct=data.get("portfolio_weight_pct"),
            profit_pct=data.get("profit_pct"),
            timing=data.get("timing"),
            ex_date=date.fromisoformat(ex_raw) if ex_raw else None,
            pay_date=date.fromisoformat(pay_raw) if pay_raw else None,
        )
