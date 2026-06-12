"""
S&P 500 index constituents — load, cache, and normalize tickers for Yahoo Finance.
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

    DEFAULT_CACHE_PATH = DATA_DIR / "sp500_symbols.json"
except ImportError:
    DATA_DIR = Path("data")  # type: ignore[misc]
    DELISTED_SYMBOLS = frozenset()  # type: ignore[misc]
    DEFAULT_CACHE_PATH = DATA_DIR / "sp500_symbols.json"

_CACHE_MAX_AGE_DAYS = 30
_MIN_SYMBOLS = 400
_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_USER_AGENT = "DividendScope/1.0 (local portfolio analytics; +https://github.com/)"
# Committed repo copy (503 symbols) — used when DATA_DIR cache is empty (CI, fresh installs).
_BUNDLED_REPO_PATH = Path(__file__).resolve().parent.parent / "data" / "sp500_symbols.json"

# Last-resort only — normal path uses data/sp500_symbols.json (503 names, committed).
_FALLBACK_SYMBOLS: list[str] = [
    "AAPL",
    "MSFT",
    "AMZN",
    "NVDA",
    "GOOGL",
    "GOOG",
    "META",
    "BRK-B",
    "UNH",
    "JNJ",
    "XOM",
    "JPM",
    "V",
    "PG",
    "MA",
    "HD",
    "CVX",
    "MRK",
    "ABBV",
    "KO",
    "PEP",
    "COST",
    "AVGO",
    "WMT",
    "MCD",
    "CSCO",
    "ACN",
    "TMO",
    "ABT",
    "DHR",
    "LIN",
    "NEE",
    "PM",
    "TXN",
    "CMCSA",
    "RTX",
    "HON",
    "UPS",
    "LOW",
    "INTC",
    "AMD",
    "QCOM",
    "INTU",
    "SPGI",
]


def yahoo_ticker(symbol: str) -> str:
    """Normalize tickers for yfinance (BRK.B → BRK-B)."""
    return str(symbol.strip().upper().replace(".", "-"))


def _normalize_sector_key(sector: str) -> str:
    key = sector.strip().lower()
    key = re.sub(r"[^a-z0-9]+", " ", key).strip()
    aliases: dict[str, str] = {
        "health care": "healthcare",
        "consumer defensive": "consumer staples",
        "consumer cyclical": "consumer discretionary",
        "financial services": "financials",
        "basic materials": "materials",
        "telecommunication services": "communication services",
        "telecommunications": "communication services",
    }
    return str(aliases.get(key, key))


def sectors_match(sector_a: str, sector_b: str) -> bool:
    """Loose sector match for cross-source labels (Yahoo vs GICS)."""
    if not sector_a or not sector_b:
        return False
    a = _normalize_sector_key(sector_a)
    b = _normalize_sector_key(sector_b)
    if a == b:
        return True
    return a in b or b in a


def _fetch_wikipedia_html() -> str:
    request = urllib.request.Request(_WIKI_URL, headers={"User-Agent": _USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310
        return str(response.read().decode("utf-8", errors="replace"))


def _parse_symbols_from_html(html: str) -> list[str]:
    """Parse tickers from the constituents table (BeautifulSoup, no pandas)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="constituents")
    if table is None:
        for candidate in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in candidate.find_all("th")]
            if "symbol" in headers:
                table = candidate
                break
    if table is None:
        raise ValueError("Could not find S&P 500 constituents table on Wikipedia")

    symbols: list[str] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        raw = cells[0].get_text(strip=True)
        if not raw or raw.lower() == "symbol":
            continue
        symbols.append(yahoo_ticker(raw))

    symbols = [symbol for symbol in symbols if symbol and symbol not in DELISTED_SYMBOLS]
    return sorted(set(symbols))


def _parse_symbols_with_pandas(html: str) -> list[str]:
    import pandas as pd

    tables = pd.read_html(html)
    df = tables[0]
    column = "Symbol" if "Symbol" in df.columns else df.columns[0]
    symbols = [yahoo_ticker(str(value)) for value in df[column].tolist()]
    symbols = [symbol for symbol in symbols if symbol and symbol not in DELISTED_SYMBOLS]
    return sorted(set(symbols))


def fetch_sp500_from_wikipedia() -> list[str]:
    """Download current S&P 500 tickers from Wikipedia."""
    html = _fetch_wikipedia_html()
    try:
        symbols = _parse_symbols_from_html(html)
        if len(symbols) >= _MIN_SYMBOLS:
            return symbols
    except Exception as exc:
        logger.debug("BeautifulSoup S&P 500 parse failed: %s", exc)

    return _parse_symbols_with_pandas(html)


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
        normalized = [yahoo_ticker(symbol) for symbol in symbols]
        return normalized if len(normalized) >= _MIN_SYMBOLS or not enforce_ttl else None
    except Exception as exc:
        logger.warning("Could not read S&P 500 list at %s: %s", cache_path, exc)
        return None


def _bundled_symbol_paths() -> list[Path]:
    """User cache under DATA_DIR, then committed repo ``data/sp500_symbols.json``."""
    seen: set[str] = set()
    paths: list[Path] = []
    for path in (DEFAULT_CACHE_PATH, _BUNDLED_REPO_PATH):
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def _load_bundled_sp500(*, require_full: bool = True) -> list[str] | None:
    """Load bundled list from cache file or repo without Wikipedia."""
    for path in _bundled_symbol_paths():
        bundled = load_cached_symbols(path, enforce_ttl=False)
        if not bundled:
            continue
        if require_full and len(bundled) < _MIN_SYMBOLS:
            continue
        return bundled
    return None


def save_cached_symbols(symbols: list[str], cache_path: Path = DEFAULT_CACHE_PATH) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated": datetime.now().isoformat(timespec="seconds"),
        "count": len(symbols),
        "source": "wikipedia",
        "symbols": sorted(set(symbols)),
    }
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_sp500_symbols(*, refresh: bool = False) -> list[str]:
    """
    Return S&P 500 tickers.

    Order: fresh cache → Wikipedia refresh → bundled ``data/sp500_symbols.json``
    (committed, 503 symbols) → tiny emergency fallback.
    """
    cache_path = DEFAULT_CACHE_PATH

    if not refresh:
        cached = load_cached_symbols(cache_path, enforce_ttl=True)
        if cached:
            return cached
        bundled = _load_bundled_sp500()
        if bundled:
            logger.info("Using bundled S&P 500 list (%s symbols)", len(bundled))
            return bundled

    try:
        symbols = fetch_sp500_from_wikipedia()
        if len(symbols) >= _MIN_SYMBOLS:
            save_cached_symbols(symbols, cache_path)
            logger.info("Refreshed S&P 500 list from Wikipedia (%s symbols)", len(symbols))
            return symbols
        logger.warning("Wikipedia returned only %s symbols", len(symbols))
    except urllib.error.URLError as exc:
        logger.warning("S&P 500 Wikipedia network error: %s", exc)
    except Exception as exc:
        logger.warning("S&P 500 Wikipedia fetch failed: %s", exc)

    bundled = _load_bundled_sp500(require_full=False)
    if bundled and len(bundled) >= _MIN_SYMBOLS:
        logger.info("Using bundled S&P 500 list (%s symbols)", len(bundled))
        return bundled

    if bundled:
        logger.warning("Bundled S&P 500 list has only %s symbols; expected ~503", len(bundled))
        return bundled

    logger.warning(
        "Using minimal S&P 500 emergency fallback (%s symbols). "
        "Add data/sp500_symbols.json or run: python ingest_data.py --ensure-sp500",
        len(_FALLBACK_SYMBOLS),
    )
    return list(_FALLBACK_SYMBOLS)


def sp500_symbol_set(*, refresh: bool = False) -> set[str]:
    return set(get_sp500_symbols(refresh=refresh))
