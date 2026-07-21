# Task: add a Postgres schema change

1. Add `migrations/00N_short_description.sql` (next incrementing number).
2. Mirror the table/column in the relevant store's `_ensure_schema()` for SQLite dev/tests only.
3. Use `db.parsing.parse_date` / `parse_optional_date` for any new date columns read from rows.
4. Apply locally:
   ```bash
   python -m db --migrate
   ```
5. Run tests:
   ```bash
   pytest -m "not integration" -q
   pre-commit run --all-files
   ```

## Do not

- Skip the migration SQL file ( `ensure_schema()` tracks `schema_migrations` ).
- Use `date.fromisoformat(row[...])` on Postgres query results.
- Set global `DATABASE_URL` in unit tests.

See `.cursor/docs/agents/storage.md` for data ownership and store patterns.
