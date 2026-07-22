"""yfinance API compatibility across 0.2.x and 1.x releases."""

from __future__ import annotations

try:
    # yfinance 1.x
    from yfinance.exceptions import YFException as YFinanceError
except ImportError:  # pragma: no cover - legacy yfinance
    from yfinance.exceptions import YFinanceError


def yahoo_network_errors() -> tuple[type[BaseException], ...]:
    """Exception types raised by yfinance HTTP clients (requests or curl_cffi)."""
    errors: list[type[BaseException]] = [YFinanceError]
    try:
        import requests

        errors.append(requests.exceptions.RequestException)
    except ImportError:  # pragma: no cover
        pass
    try:
        from curl_cffi.requests.exceptions import RequestException as CurlRequestException

        errors.append(CurlRequestException)
    except ImportError:  # pragma: no cover
        pass
    return tuple(errors)


__all__ = ["YFinanceError", "yahoo_network_errors"]
