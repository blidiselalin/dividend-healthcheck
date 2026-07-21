"""yfinance API compatibility across 0.2.x and 1.x releases."""

from __future__ import annotations

try:
    # yfinance 1.x
    from yfinance.exceptions import YFException as YFinanceError
except ImportError:  # pragma: no cover - legacy yfinance
    from yfinance.exceptions import YFinanceError

__all__ = ["YFinanceError"]
