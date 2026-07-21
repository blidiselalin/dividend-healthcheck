"""yfinance exception compatibility."""

from utils.yfinance_compat import YFinanceError


def test_yfinance_error_alias_matches_yfinance_1x() -> None:
    from yfinance.exceptions import YFException

    assert YFinanceError is YFException
