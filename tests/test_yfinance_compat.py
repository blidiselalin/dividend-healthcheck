"""yfinance exception compatibility."""

from utils.yfinance_compat import YFinanceError, yahoo_network_errors


def test_yfinance_error_alias_matches_yfinance_1x() -> None:
    from yfinance.exceptions import YFException

    assert YFinanceError is YFException


def test_yahoo_network_errors_includes_curl_cffi() -> None:
    from curl_cffi.requests.exceptions import RequestException as CurlRequestException

    assert CurlRequestException in yahoo_network_errors()
