"""
Top dividend stock universe — S&P Dividend Aristocrats plus quality S&P 500 payers.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from config import DATA_DIR, DELISTED_SYMBOLS

    DEFAULT_CACHE_PATH = DATA_DIR / "top_dividend_symbols.json"
except ImportError:
    DATA_DIR = Path("data")  # type: ignore[misc]
    DELISTED_SYMBOLS = frozenset()  # type: ignore[misc]
    DEFAULT_CACHE_PATH = DATA_DIR / "top_dividend_symbols.json"

_BUNDLED_REPO_PATH = Path(__file__).resolve().parent.parent / "data" / "top_dividend_symbols.json"
_ARISTOCRATS_URL = "https://en.wikipedia.org/wiki/S%26P_500_Dividend_Aristocrats"
_USER_AGENT = "DividendScope/1.0 (local portfolio analytics; +https://github.com/)"
_CACHE_MAX_AGE_DAYS = 30
_TARGET_COUNT = 100

# High-quality S&P 500 dividend payers beyond the Aristocrats
# (sector leaders, REITs, utilities, etc.)
_SUPPLEMENTAL_SP500_DIVIDEND: tuple[str, ...] = (
    "AAPL",
    "AEP",
    "ALL",
    "AMGN",
    "AMT",
    "AVB",
    "AVGO",
    "BAC",
    "BK",
    "BMY",
    "CAG",
    "CCI",
    "CME",
    "COP",
    "COST",
    "CSCO",
    "D",
    "DE",
    "DLR",
    "DUK",
    "EOG",
    "EQIX",
    "EQR",
    "ESS",
    "EXC",
    "GILD",
    "GIS",
    "GS",
    "HD",
    "HON",
    "HST",
    "HUM",
    "ICE",
    "INTC",
    "JPM",
    "K",
    "KHC",
    "KMI",
    "L",
    "LMT",
    "LLY",
    "LOW",
    "MET",
    "MMC",
    "MO",
    "MPC",
    "MRK",
    "MS",
    "MSFT",
    "NDAQ",
    "OKE",
    "PFE",
    "PM",
    "PNC",
    "PSX",
    "QCOM",
    "REG",
    "RTX",
    "SBAC",
    "SCHW",
    "SLB",
    "SO",
    "STT",
    "STZ",
    "T",
    "TFC",
    "TRGP",
    "TRV",
    "TXN",
    "UNH",
    "UNP",
    "USB",
    "VICI",
    "VLO",
    "VZ",
    "WEC",
    "WMB",
    "WM",
    "WY",
    "XEL",
    "ZTS",
)


def _yahoo_ticker(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


def fetch_aristocrats_from_wikipedia() -> list[str]:
    """Download current S&P 500 Dividend Aristocrats from Wikipedia."""
    request = urllib.request.Request(_ARISTOCRATS_URL, headers={"User-Agent": _USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310
        html = response.read().decode("utf-8", errors="replace")

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    symbols: list[str] = []
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not any("symbol" in header or "ticker" in header for header in headers):
            continue
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            for text in (cell.get_text(strip=True) for cell in cells):
                if re.fullmatch(r"[A-Z]{1,5}(?:[.-][A-Z0-9])?", text):
                    symbols.append(_yahoo_ticker(text))
                    break
        if symbols:
            break

    if not symbols:
        raise ValueError("Could not parse S&P Dividend Aristocrats table on Wikipedia")

    return sorted({symbol for symbol in symbols if symbol and symbol not in DELISTED_SYMBOLS})


def build_top_dividend_symbols(
    *,
    sp500: set[str] | None = None,
    limit: int = _TARGET_COUNT,
) -> list[str]:
    """Merge Aristocrats with supplemental S&P payers, capped at ``limit``."""
    if sp500 is None:
        from data_ingestion.sp500_universe import sp500_symbol_set

        sp500 = sp500_symbol_set()

    try:
        aristocrats = fetch_aristocrats_from_wikipedia()
    except Exception as exc:
        logger.warning("Aristocrats Wikipedia fetch failed: %s", exc)
        aristocrats = []

    ordered: list[str] = []
    seen: set[str] = set()
    for symbol in list(aristocrats) + list(_SUPPLEMENTAL_SP500_DIVIDEND):
        normalized = _yahoo_ticker(symbol)
        if (
            not normalized
            or normalized in seen
            or normalized in DELISTED_SYMBOLS
            or normalized not in sp500
        ):
            continue
        seen.add(normalized)
        ordered.append(normalized)
        if len(ordered) >= limit:
            break
    return ordered


def load_cached_symbols(
    cache_path: Path = DEFAULT_CACHE_PATH,
    *,
    enforce_ttl: bool = True,
) -> list[str] | None:
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        updated = payload.get("updated")
        symbols = payload.get("symbols") or []
        if not symbols:
            return None
        if enforce_ttl and updated:
            updated_at = datetime.fromisoformat(updated)
            if datetime.now() - updated_at > timedelta(days=_CACHE_MAX_AGE_DAYS):
                return None
        normalized = [_yahoo_ticker(symbol) for symbol in symbols]
        return normalized if normalized else None
    except Exception as exc:
        logger.warning("Could not read top dividend list at %s: %s", cache_path, exc)
        return None


def save_cached_symbols(symbols: list[str], cache_path: Path = DEFAULT_CACHE_PATH) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated": datetime.now().isoformat(timespec="seconds"),
        "count": len(symbols),
        "source": "wikipedia_aristocrats+sp500_supplemental",
        "symbols": sorted(set(symbols)),
    }
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_bundled(*, require_count: int = 50) -> list[str] | None:
    for path in (DEFAULT_CACHE_PATH, _BUNDLED_REPO_PATH):
        bundled = load_cached_symbols(path, enforce_ttl=False)
        if bundled and len(bundled) >= require_count:
            return bundled
    return None


def get_top_dividend_symbols(*, refresh: bool = False) -> list[str]:
    """
    Return up to 100 curated dividend tickers (Aristocrats + supplemental S&P payers).

    Order: user cache → bundled ``data/top_dividend_symbols.json`` → live rebuild.
    """
    if not refresh:
        cached = load_cached_symbols(DEFAULT_CACHE_PATH, enforce_ttl=True)
        if cached:
            return cached
        bundled = _load_bundled()
        if bundled:
            return bundled

    try:
        symbols = build_top_dividend_symbols()
        if symbols:
            save_cached_symbols(symbols, DEFAULT_CACHE_PATH)
            logger.info("Refreshed top dividend list (%s symbols)", len(symbols))
            return symbols
    except Exception as exc:
        logger.warning("Top dividend rebuild failed: %s", exc)

    bundled = _load_bundled(require_count=1)
    if bundled:
        return bundled

    from config import DIVIDEND_ARISTOCRATS, DIVIDEND_KINGS

    return sorted(
        {
            symbol
            for symbol in DIVIDEND_KINGS + DIVIDEND_ARISTOCRATS
            if symbol not in DELISTED_SYMBOLS
        }
    )


def top_dividend_symbol_set(*, refresh: bool = False) -> set[str]:
    return set(get_top_dividend_symbols(refresh=refresh))
