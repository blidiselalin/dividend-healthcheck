# Contributing to DividendScope

Thanks for helping improve DividendScope. This guide covers local setup, tests, and pull-request expectations for the public beta.

Please also read:

- [AGENTS.md](AGENTS.md) — architecture index and obsolete patterns
- [.cursor/rules/](.cursor/rules/) — scoped agent/developer rules
- [.github/pull_request_template.md](.github/pull_request_template.md)
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- [SECURITY.md](SECURITY.md) — private vulnerability reporting

## Security reports

Do **not** open a public issue for a security vulnerability. Follow [SECURITY.md](SECURITY.md).

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pre-commit run --all-files
pytest -m "not integration" -q
streamlit run app.py
```

### Docker

Docker Compose is the recommended full-stack path (app + PostgreSQL). See the README “Quick Start — Docker” section and `DEPLOY-GCP.md` for hosted deployment notes.

```bash
docker compose config
docker compose up -d --build
```

### Tests

- Unit tests (no live Postgres required):

  ```bash
  pytest -m "not integration" -q
  ```

- Integration tests require PostgreSQL where applicable:

  ```bash
  pytest -m integration -q
  ```

- Lint / format / type checks:

  ```bash
  pre-commit run --all-files
  ```

## Pull requests

Create focused pull requests:

1. Fix one issue or deliver one slice of work.
2. Prefer small diffs (often 1–5 production files).
3. Search for an existing module before adding a parallel one.
4. Do not mix unrelated refactors with feature work.
5. Do not commit secrets, credentials, or real personal financial data.
6. Use synthetic fixtures only — never real broker statements or real user portfolios.
7. Update docs when behavior or operator process changes.
8. Fill out the pull-request template checklist.

Architecture guardrails (summary — details in `AGENTS.md`):

- Production storage is PostgreSQL when `DATABASE_URL` is set.
- Use `create_portfolio_context()` for portfolio DB access.
- Portfolio UI reload uses `schedule_portfolio_reload()` (not blocking rebuilds in `ui/*`).
- Do not reintroduce runtime Chroma / per-user SQLite writes when Cloud SQL is configured.

## Reporting bugs

Use GitHub issues for **non-sensitive** reproducible bugs.

Before filing:

- Remove portfolio values, account identifiers, OAuth details, broker statements, secrets, and other personal data.
- Include steps to reproduce, expected vs actual behavior, and environment notes (OS, Docker vs local, browser).

For access, privacy, or deletion requests, use [SUPPORT.md](SUPPORT.md) — not a public issue with personal data attached.

## Proposing features

Open a feature-request issue describing the problem, the user outcome, and why an existing path is insufficient. Keep proposals aligned with the beta non-goals in [docs/releases/BETA_SCOPE.md](docs/releases/BETA_SCOPE.md).

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
