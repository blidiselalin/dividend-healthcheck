"""
Base protocol for stock data providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from data_ingestion.models import DataSource
from data_ingestion.providers.snapshot import FIELD_GROUPS, StockSnapshot


class StockDataProvider(ABC):
    """
    Fetch a normalized ``StockSnapshot`` for one symbol.

    Subclasses declare ``field_groups`` so the composite layer can skip
    providers when all relevant groups are already populated.
    """

    source: DataSource
    field_groups: frozenset[str] = frozenset(FIELD_GROUPS.keys())
    priority: int = 100  # lower = tried first

    @abstractmethod
    def available(self) -> bool:
        """Return True when this provider can run (deps, API keys, etc.)."""

    @abstractmethod
    def fetch(self, symbol: str) -> StockSnapshot | None:
        """Fetch data for ``symbol``; return None on miss or error."""

    def supports_groups(self, missing: set[str]) -> bool:
        return bool(self.field_groups & missing)
