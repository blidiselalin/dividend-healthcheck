## Summary

<!-- What changed and why (1–3 sentences) -->

## Checklist

- [ ] `pre-commit run --all-files` passes
- [ ] `pytest -m "not integration"` passes
- [ ] No unrelated file churn (scope matches the task)
- [ ] Migration added if Postgres schema changed (`migrations/00N_*.sql`)
- [ ] Store `_ensure_schema()` updated for SQLite dev fallback (if schema changed)
- [ ] Portfolio UI changes use background reload, not blocking sync rebuilds in `ui/*`

## Test plan

<!-- How you verified the change -->
