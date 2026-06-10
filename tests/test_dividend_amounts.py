"""Tests for dividend amount helpers."""

import unittest
from datetime import date

from data_ingestion.models import DividendRecord
from utils.dividend_amounts import (
    detect_payment_frequency,
    expected_payment_months,
    normalize_payment_amount,
    per_payment_amount,
    resolve_annual_dividend_per_share,
    trailing_annual_dividend,
)


def _monthly_records(count: int = 12, amount: float = 0.27) -> list[DividendRecord]:
    records = []
    for month in range(1, count + 1):
        records.append(
            DividendRecord(
                ex_date=date(2025, month, 15),
                payment_date=None,
                amount=amount,
            )
        )
    return records


class DividendAmountsTests(unittest.TestCase):
    def test_detect_monthly_from_recent_years(self):
        records = _monthly_records(12)
        self.assertEqual(detect_payment_frequency(records), 12)

    def test_trailing_annual_sums_last_twelve_monthly_payments(self):
        records = _monthly_records(12, amount=0.25)
        self.assertEqual(trailing_annual_dividend(records), 3.0)

    def test_resolve_annual_prefers_trailing_over_stale_quarterly_annual(self):
        records = _monthly_records(12, amount=0.27)
        annual = resolve_annual_dividend_per_share(records, document=None, stock=None)
        self.assertAlmostEqual(annual, 3.24, places=2)

    def test_per_payment_uses_latest_not_annual_divided_by_wrong_freq(self):
        records = _monthly_records(12, amount=0.271)
        amount = per_payment_amount(records, document=None, stock=None)
        self.assertAlmostEqual(amount, 0.271, places=3)

    def test_normalize_payment_amount_clamps_annual_lump(self):
        records = _quarterly_records(amount=0.6775)
        normalized = normalize_payment_amount(2.71, records, document=None, stock=None)
        self.assertAlmostEqual(normalized, 0.6775, places=4)

    def test_expected_payment_months_for_quarterly(self):
        records = _quarterly_records()
        months = expected_payment_months(records, stored_frequency=4)
        self.assertEqual(months, {3, 6, 9, 12})


def _quarterly_records(amount: float = 0.48) -> list[DividendRecord]:
    months = (3, 6, 9, 12)
    records: list[DividendRecord] = []
    for year in (2024, 2025, 2026):
        for month in months:
            records.append(
                DividendRecord(
                    ex_date=date(year, month, 10),
                    payment_date=date(year, month, 25),
                    amount=amount,
                )
            )
    return records


if __name__ == "__main__":
    unittest.main()
