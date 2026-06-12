"""
SEC EDGAR provider — company facts and identity (free, no API key).

Uses ``data.sec.gov`` XBRL company facts. SEC requires a descriptive User-Agent
(not a secret key). Override with ``SEC_EDGAR_USER_AGENT`` if you deploy publicly.

Docs: https://www.sec.gov/edgar/sec-api-documentation
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

from data_ingestion.base import BaseFetcher
from data_ingestion.models import DataSource
from data_ingestion.providers._numeric import as_float
from data_ingestion.providers.base import StockDataProvider
from data_ingestion.providers.snapshot import StockSnapshot

logger = logging.getLogger(__name__)

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
DEFAULT_USER_AGENT = "DividendScope/1.0 (edgar-data@dividendscope.local)"


class SecEdgarProvider(BaseFetcher, StockDataProvider):
    source = DataSource.SEC_EDGAR
    field_groups = frozenset({"identity", "valuation", "health", "profitability"})
    priority = 20

    def __init__(self, user_agent: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.user_agent = (
            user_agent or os.environ.get("SEC_EDGAR_USER_AGENT") or DEFAULT_USER_AGENT
        ).strip()
        if self.session:
            self.session.headers["User-Agent"] = self.user_agent
            self.session.headers["Accept"] = "application/json"

    def available(self) -> bool:
        return bool(self.session)

    def fetch(self, symbol: str) -> StockSnapshot | None:  # noqa: C901
        if not self.available():
            return None

        symbol = symbol.upper().strip()
        cik = _cik_for_symbol(symbol)
        if not cik:
            return None

        self._rate_limit()
        facts_payload = self._get_facts(cik)
        if not facts_payload:
            return None

        snap = StockSnapshot(symbol=symbol, source=self.source)
        snap.name = facts_payload.get("entityName")
        gaap = (facts_payload.get("facts") or {}).get("us-gaap") or {}

        sic = _entity_sic(facts_payload) or self._submissions_sic(cik)
        if sic:
            snap.industry = sic.get("description") or snap.industry
            snap.sector = _sic_to_sector(sic.get("code")) or snap.sector

        revenue = _latest_gaap_value(
            gaap, "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"
        )
        net_income = _latest_gaap_value(gaap, "NetIncomeLoss")
        equity = _latest_gaap_value(gaap, "StockholdersEquity")
        eps = _latest_gaap_value(gaap, "EarningsPerShareBasic")
        debt = _latest_gaap_value(
            gaap,
            "LongTermDebt",
            "LongTermDebtNoncurrent",
            "DebtInstrumentCarryingAmount",
        )
        operating_income = _latest_gaap_value(gaap, "OperatingIncomeLoss")

        if revenue and net_income and revenue != 0:
            snap.profit_margin = (net_income / revenue) * 100
        if operating_income and revenue and revenue != 0:
            snap.operating_margin = (operating_income / revenue) * 100
        if equity and net_income and equity != 0:
            snap.roe = (net_income / equity) * 100
        if debt and equity and equity != 0:
            snap.debt_to_equity = debt / equity
        if eps:
            snap.pe_ratio = None  # filled when combined with price from Yahoo

        dividends_per_share = _latest_gaap_value(
            gaap,
            "CommonStockDividendsPerShareDeclared",
            "CommonStockDividendsPerShareCashPaid",
        )
        if dividends_per_share:
            snap.annual_dividend = (
                dividends_per_share * 4 if dividends_per_share < 50 else dividends_per_share
            )

        if not snap.populated_scalar_fields():
            return None
        return snap

    def _get_facts(self, cik: int) -> dict[str, Any] | None:
        if not self.session:
            return None
        try:
            response = self.session.get(
                SEC_FACTS_URL.format(cik=cik),
                timeout=20,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            from typing import cast

            return cast(dict[str, Any], response.json())
        except Exception as exc:
            logger.debug("SEC EDGAR facts failed for CIK %s: %s", cik, exc)
            return None

    def _submissions_sic(self, cik: int) -> dict[str, Any] | None:
        if not self.session:
            return None
        self._rate_limit()
        try:
            response = self.session.get(
                SEC_SUBMISSIONS_URL.format(cik=cik),
                timeout=20,
            )
            if response.status_code != 200:
                return None
            data = response.json()
            code = data.get("sic")
            if not code:
                return None
            return {"code": str(code), "description": data.get("sicDescription", "")}
        except Exception:
            return None


@lru_cache(maxsize=1)
def _ticker_index() -> dict[str, int]:
    """Load SEC ticker → CIK map (cached for process lifetime)."""
    import requests

    try:
        response = requests.get(
            SEC_TICKERS_URL,
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning("SEC ticker list unavailable: %s", exc)
        return {}

    index: dict[str, int] = {}
    for entry in payload.values():
        ticker = str(entry.get("ticker", "")).upper()
        cik = entry.get("cik_str") or entry.get("cik")
        if ticker and cik:
            index[ticker] = int(cik)
    return index


def _cik_for_symbol(symbol: str) -> int | None:
    return _ticker_index().get(symbol.upper())


def _entity_sic(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort SIC from company facts metadata."""
    for key in ("sic", "sicCode", "entitySic"):
        if payload.get(key):
            return {
                "code": str(payload[key]),
                "description": payload.get("sicDescription", ""),
            }
    return None


def _sic_to_sector(code: str | None) -> str | None:  # noqa: C901
    if not code:
        return None
    try:
        sic = int(str(code)[:4])
    except ValueError:
        return None
    if 100 <= sic <= 1499:
        return "Energy"
    if 1500 <= sic <= 1799:
        return "Construction"
    if 2000 <= sic <= 3999:
        return "Industrials"
    if 4000 <= sic <= 4999:
        return "Transportation"
    if 5000 <= sic <= 5199:
        return "Wholesale Trade"
    if 5200 <= sic <= 5999:
        return "Retail"
    if 6000 <= sic <= 6799:
        return "Financials"
    if 7000 <= sic <= 8999:
        return "Services"
    if 9100 <= sic <= 9729:
        return "Public Administration"
    return "Other"


def _latest_gaap_value(gaap: dict[str, Any], *names: str) -> float | None:
    for name in names:
        block = gaap.get(name)
        if not block:
            continue
        units = block.get("units") or {}
        series = units.get("USD") or units.get("usd") or units.get("shares") or []
        if not series:
            continue
        ordered = sorted(series, key=lambda row: row.get("end", ""), reverse=True)
        for row in ordered:
            value = as_float(row.get("val"))
            if value is not None:
                return value
    return None


def clear_sec_caches() -> None:
    """Clear cached ticker index (for tests)."""
    _ticker_index.cache_clear()
