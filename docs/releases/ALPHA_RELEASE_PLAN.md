# Alpha release validation and follow-up

This file distinguishes the published alpha tag from the follow-up changes on the current branch. It does not change or retag the published release.

## Published baseline

- Release: [`v0.1.0-alpha.1`](https://github.com/blidiselalin/dividend-healthcheck/releases/tag/v0.1.0-alpha.1)
- Tag commit: `79a3bf879f1a2850259d73edf5bae116d21d5eb5`
- Release type: local prerelease; no attached build assets

## Alpha.1 deployment limitation

The published tag excludes `.streamlit/secrets.toml` from the Docker build and does not mount it at runtime. With the documented Compose deployment, OAuth may therefore remain unconfigured and the app can skip the login gate. Do not use alpha.1 Compose for real-portfolio access on a public host. The fail-closed changes below are unreleased until a new commit and tag.

## Follow-up changes prepared after alpha.1

- Docker Compose mounts the host `.streamlit` directory read-only and forces authentication. Missing OIDC settings now show a locked error instead of opening the shared local portfolio context.
- OAuth availability is determined from Streamlit secrets, the source consumed by `st.login()`.
- The yield-history fixture uses a fixed start date and keeps dividend dates within the generated price history.

These changes require a new commit and a later release tag before they are present in a published artifact.

## Verification on this checkout

- The tagged fixture reproduced the `6 == 5` failure locally on Python 3.11 and 3.12. GitHub’s [alpha.1 test run](https://github.com/blidiselalin/dividend-healthcheck/actions/runs/45148602140) still reflects that fixture.
- The follow-up passed all 14 focused auth and yield-history tests on Python 3.11.18 and 3.12.16.
- Each local unit suite recorded **903 passed and 9 skipped** across two runs. The offline run passed 901 tests, with 9 skips and 15 deselections. The two public demo tests that call Yahoo passed separately with network access. The 13 PostgreSQL integration tests were outside these runs.
- Docker Compose configuration parsed successfully. Ruff, Ruff format, strict mypy, and vulture passed.
- A GitHub Actions run on a commit containing the fix is still pending.

## Explicit alpha scope exclusions

- **Run-dated S&P 500 constituent snapshots with market history for every member:** not included in alpha.1. The existing current-universe/peer ingestion does not preserve a constituent snapshot for each run. Keep this as a planned integration item; do not describe it as working.
- **Yahoo month-by-month dividend reconciliation for the user's holdings:** not completed or verified for alpha.1. Automated tests cover actual/estimated dividend calculation paths, but a holdings table alone does not supply the dated receipt ledger needed to reconcile October and November totals. This remains a planned validation item requiring a dated export or transaction records.

## Release gate for the next alpha

- [x] Run the unit tests locally on Python 3.11 and 3.12.
- [ ] Verify the Python 3.11 and 3.12 jobs on GitHub for a commit containing the follow-up patch.
- [x] Pre-commit passed on the current checkout: Ruff, Ruff format, strict mypy, and vulture.
- [ ] Run PostgreSQL integration tests and exercise configured OAuth, missing-secret fail-closed behavior, and two-user portfolio isolation in staging.
- [ ] Put exact test results and the scope exclusions above in the next alpha release notes.
- [ ] Publish a new alpha tag only after these gates pass. Do not move `v0.1.0-alpha.1`.
