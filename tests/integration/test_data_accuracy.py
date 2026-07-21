"""Optional integration tests for market library data quality (requires ingest)."""
# ruff: noqa: S101

from typing import Any

import pytest

pytestmark = pytest.mark.integration


def _require_dividend_king_enrichment(store: Any) -> None:
    """Skip when the vector DB is S&P-only without full dividend-king enrichment."""
    ko = store.get_by_symbol("KO")
    if ko is None:
        pytest.skip("KO not in database")
    if (ko.dividend_streak_years or 0) < 50:
        pytest.skip(
            "Dividend streak fields not fully enriched; "
            "run full dividend-king ingest before accuracy checks"
        )


def test_database_availability() -> None:
    """Test that the vector database is available and has data."""
    from data_ingestion.vector_store import VectorStore

    store = VectorStore()
    count = store.count()

    if count == 0:
        pytest.skip("Vector database is empty; run ingest for integration tests")
    assert count > 0


def test_dividend_kings_count(store: Any) -> None:
    """Test that we have a reasonable number of Dividend Kings."""
    all_docs = store.get_all_documents()
    kings = [d for d in all_docs if d.dividend_streak_years and d.dividend_streak_years >= 50]

    if len(kings) < 30:
        pytest.skip(
            f"Local vector DB has {len(kings)} stocks with 50+ year streak; "
            "run full ingest for this integration check"
        )
    assert len(kings) >= 30


def test_stock_data_accuracy(store: Any) -> None:  # noqa: C901
    """
    Test data accuracy for 10+ well-known Dividend Kings.

    Validates that key metrics fall within expected real-world ranges.
    """
    _require_dividend_king_enrichment(store)

    # Expected ranges for well-known Dividend Kings (as of early 2026)
    # Format: symbol -> (min_yield, max_yield, min_streak, min_pe, max_pe)
    expected_stocks: dict[str, Any] = {
        "KO": {
            "name_contains": "Coca-Cola",
            "yield_range": (1.5, 4.5),
            "streak_min": 60,
            "pe_range": (15, 35),
            "payout_range": (50, 90),
        },
        "JNJ": {
            "name_contains": "Johnson",
            "yield_range": (1.5, 4.0),
            "streak_min": 60,
            "pe_range": (10, 30),
            "payout_range": (30, 70),
        },
        "PG": {
            "name_contains": "Procter",
            "yield_range": (1.5, 4.0),
            "streak_min": 65,
            "pe_range": (15, 35),
            "payout_range": (50, 80),
        },
        "MMM": {
            "name_contains": "3M",
            "yield_range": (1.0, 6.0),
            "streak_min": 60,
            "pe_range": (5, 50),
            "payout_range": (30, 100),
        },
        "EMR": {
            "name_contains": "Emerson",
            "yield_range": (1.0, 4.0),  # Emerson yield varies with price
            "streak_min": 65,
            "pe_range": (10, 40),
            "payout_range": (30, 80),
        },
        "LOW": {
            "name_contains": "Lowe",
            "yield_range": (1.0, 3.5),
            "streak_min": 50,
            "pe_range": (10, 35),
            "payout_range": (25, 60),
        },
        "CL": {
            "name_contains": "Colgate",
            "yield_range": (1.5, 4.0),
            "streak_min": 60,
            "pe_range": (15, 40),
            "payout_range": (50, 80),
        },
        "ABM": {
            "name_contains": "ABM",
            "yield_range": (1.5, 4.0),
            "streak_min": 55,
            "pe_range": (10, 30),
            "payout_range": (25, 60),
        },
        "FRT": {
            "name_contains": "Federal Realty",
            "yield_range": (3.0, 6.0),
            "streak_min": 55,
            "pe_range": (15, 60),
            "payout_range": (50, 150),  # REIT can be higher
        },
        "GWW": {
            "name_contains": "Grainger",
            "yield_range": (0.5, 2.5),
            "streak_min": 50,
            "pe_range": (15, 35),
            "payout_range": (20, 50),
        },
    }

    passed = 0
    failed = 0
    not_found = 0

    print("\n--- Stock Data Accuracy Tests ---\n")

    for symbol, expected in expected_stocks.items():
        doc = store.get_by_symbol(symbol)

        if doc is None:
            print(f"⚠ {symbol}: Not found in database")
            not_found += 1
            continue

        errors = []

        # Check name
        if expected["name_contains"].lower() not in (doc.name or "").lower():
            errors.append(f"Name '{doc.name}' doesn't contain '{expected['name_contains']}'")

        # Check dividend yield
        if doc.dividend_yield is not None:
            ymin, ymax = expected["yield_range"]
            if not (ymin <= doc.dividend_yield <= ymax):
                errors.append(f"Yield {doc.dividend_yield:.2f}% outside range [{ymin}, {ymax}]")
        else:
            errors.append("Dividend yield is None")

        # Check streak
        if doc.dividend_streak_years is not None:
            if doc.dividend_streak_years < expected["streak_min"]:
                errors.append(
                    f"Streak {doc.dividend_streak_years} < expected min {expected['streak_min']}"
                )
        else:
            errors.append("Dividend streak is None")

        # Check P/E ratio (if available)
        if doc.pe_ratio is not None:
            pmin, pmax = expected["pe_range"]
            if not (pmin <= doc.pe_ratio <= pmax):
                errors.append(f"P/E {doc.pe_ratio:.1f} outside range [{pmin}, {pmax}]")

        # Check payout ratio (if available)
        if doc.payout_ratio is not None:
            prmin, prmax = expected["payout_range"]
            if not (prmin <= doc.payout_ratio <= prmax):
                errors.append(f"Payout {doc.payout_ratio:.1f}% outside range [{prmin}, {prmax}]")

        if errors:
            print(f"✗ {symbol} ({doc.name}): FAILED")
            for err in errors:
                print(f"    - {err}")
            failed += 1
        else:
            streak = doc.dividend_streak_years or "N/A"
            yld = f"{doc.dividend_yield:.2f}%" if doc.dividend_yield else "N/A"
            pe = f"{doc.pe_ratio:.1f}" if doc.pe_ratio else "N/A"
            payout = f"{doc.payout_ratio:.1f}%" if doc.payout_ratio else "N/A"
            print(
                f"✓ {symbol} ({doc.name}): streak={streak}yrs, yield={yld}, "
                f"P/E={pe}, payout={payout}"
            )
            passed += 1

    print(f"\n--- Results: {passed} passed, {failed} failed, {not_found} not found ---")

    assert failed == 0, f"{failed} stock(s) failed accuracy checks"
    assert not_found == 0, f"{not_found} expected symbol(s) missing from database"


def test_data_sanity(store: Any) -> None:
    """Test that all data values are within sane ranges."""
    _require_dividend_king_enrichment(store)
    all_docs = store.get_all_documents()

    issues = []

    for doc in all_docs:
        # Dividend yield should be 0-30%
        if doc.dividend_yield is not None and (doc.dividend_yield < 0 or doc.dividend_yield > 30):
            issues.append(f"{doc.symbol}: Invalid yield {doc.dividend_yield}%")

        # Payout ratio should be 0-150% (higher values are capped in fix_invalid_values)
        if doc.payout_ratio is not None and (doc.payout_ratio < 0 or doc.payout_ratio > 150):
            issues.append(f"{doc.symbol}: Invalid payout ratio {doc.payout_ratio}%")

        # Streak should be 0-100 years
        if doc.dividend_streak_years is not None and (
            doc.dividend_streak_years < 0 or doc.dividend_streak_years > 100
        ):
            issues.append(f"{doc.symbol}: Invalid streak {doc.dividend_streak_years} years")

        # P/E should be positive and < 500
        if doc.pe_ratio is not None and (doc.pe_ratio < 0 or doc.pe_ratio > 500):
            issues.append(f"{doc.symbol}: Invalid P/E {doc.pe_ratio}")

        # Price should be positive
        if doc.current_price is not None and doc.current_price <= 0:
            issues.append(f"{doc.symbol}: Invalid price {doc.current_price}")

    if issues:
        print("\n⚠ Data sanity issues found:")
        for issue in issues[:10]:  # Show first 10
            print(f"  - {issue}")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more")
    else:
        print("✓ All data values within sane ranges")

    assert not issues, f"Data sanity issues: {issues[:5]}"


def test_service_layer() -> None:
    """Test that the VectorDBService works correctly."""
    try:
        from services.vectordb_service import get_vectordb_service
    except ImportError as exc:
        pytest.skip(f"VectorDBService not importable: {exc}")

    service = get_vectordb_service()

    if not service.is_available:
        pytest.skip("VectorDBService not available (no data)")

    data = service.get_stock("KO")
    assert data is not None, "Should be able to get KO"
    assert data.symbol == "KO"
    assert data.dividend_yield_pct is not None

    stats = service.get_stats()
    assert stats["total_documents"] > 0
