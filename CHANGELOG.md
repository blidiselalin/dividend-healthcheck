# Changelog

All notable changes to DividendScope are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/) with
explicit prerelease labels for public alpha builds.

## [Unreleased]

### Fixed

- Docker Compose now mounts Streamlit secrets and requires authentication before portfolio access.
- The yield-history test fixture keeps dividend dates inside the generated price-history window.

### Scope

- Full run-dated S&P 500 constituent snapshots and complete market-history coverage are deferred to a later alpha.
- Yahoo portfolio-level month-by-month dividend reconciliation is deferred until a dated transaction/receipt ledger is available.

See [the alpha release plan](docs/releases/ALPHA_RELEASE_PLAN.md) for current validation gates and boundaries.

## [0.1.0-alpha.1] — 2026-11-23

Published prerelease: [GitHub release](https://github.com/blidiselalin/dividend-healthcheck/releases/tag/v0.1.0-alpha.1).

The tag is the initial local alpha. Its release validation and follow-up scope are recorded in [ALPHA_RELEASE_PLAN.md](docs/releases/ALPHA_RELEASE_PLAN.md).

### Added

- Public sample / demo portfolio experience for educational product exploration
- Google OAuth authentication for hosted users
- Invite-only access path for real portfolios
- Manual holdings and authenticated broker-file import flows already present in the application
- Dividend income, portfolio health, and research analytics views
- Security, privacy, terms, support, and contributing documentation for the alpha

### Changed

- README public-facing guidance clarified for educational use and research-score labels
- Repository license set to MIT (`LICENSE`)

### Security

- Private vulnerability reporting process documented in `SECURITY.md`
- Privacy notice and prerelease terms may need legal review before general availability

### Known limitations

- Pre-release quality; availability and market-data accuracy are not guaranteed
- Real portfolio access remains invite-only
- No automatic IBKR synchronization, trading, payments, or public sharing of real portfolios
- Owner/legal details remain a pre-general-availability follow-up
- Project license is MIT; copyright-owner details need confirmation before general availability

[Unreleased]: https://github.com/blidiselalin/dividend-healthcheck/compare/v0.1.0-alpha.1...HEAD
[0.1.0-alpha.1]: https://github.com/blidiselalin/dividend-healthcheck/releases/tag/v0.1.0-alpha.1
