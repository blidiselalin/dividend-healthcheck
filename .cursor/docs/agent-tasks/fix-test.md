# Task: fix a failing test

1. Run the single failing test:
   ```bash
   pytest tests/<file>.py::test_name -x --tb=short
   ```
2. Fix the **root cause** in the smallest file set (usually 1–3 files).
3. Re-run the test file, then the full unit suite:
   ```bash
   pytest tests/<file>.py -q
   pytest -m "not integration" -q
   ```
4. Run pre-commit:
   ```bash
   pre-commit run --all-files
   ```
5. Do **not** refactor unrelated modules or reformat the whole repo.

## Keep tests lean

- Add tests only for the regression you fixed — not a mirror test for every branch.
- Do not add tests that only assert mocks were called unless call order is the contract.
- Prefer one focused test over several overlapping cases for the same bug.
- Reuse fixtures from `tests/conftest.py` and existing `_row()` / `_doc_with_*` helpers in the same test file.

## Common pitfalls in this repo

- Unit tests must run **without** `DATABASE_URL` (`PYTEST_USE_SQLITE=1` in `tests/conftest.py`).
- Pass explicit `db_path=tmp_path / "portfolio.db"` to `create_portfolio_context()`.
- Postgres mocks: `@pytest.mark.postgres_mock` — mock URL, not live `:5432`.
- Fingerprint tests: `_row_tuple()` must use `row.keys()`, not `for key in row` on `sqlite3.Row`.
