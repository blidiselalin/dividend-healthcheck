from utils.dividend_streak import (
    annual_totals_from_payments,
    annualize_year_payments,
    calculate_consecutive_increase_years,
    resolve_consecutive_years,
)


def test_annualize_year_payments_ignores_one_off_spike():
    payments = [0.09, 0.09, 0.18, 0.09, 0.09]
    assert annualize_year_payments(payments) == 0.36


def test_calculate_consecutive_increase_years_excludes_current_year():
    annual_totals = {
        2023: 1.84,
        2024: 1.94,
        2025: 2.04,
        2026: 0.53,
    }
    assert calculate_consecutive_increase_years(annual_totals) == 2


def test_resolve_consecutive_years_prefers_curated_value():
    annual_totals = {2023: 1.0, 2024: 1.1, 2025: 1.2, 2026: 0.2}
    assert resolve_consecutive_years(curated_years=62, annual_totals=annual_totals) == 62


def test_annual_totals_from_payments_normalizes_by_year():
    year_to_payments = {
        2000: [0.085, 0.085, 0.085, 0.085],
        2001: [0.09, 0.09, 0.18, 0.09, 0.09],
        2002: [0.1, 0.1, 0.1, 0.1],
    }
    totals = annual_totals_from_payments(year_to_payments)
    assert totals[2000] == 0.34
    assert totals[2001] == 0.36
    assert totals[2002] == 0.4
