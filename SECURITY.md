# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x beta | Yes |
| Earlier versions | No |

## Private vulnerability reporting

**Do not report security vulnerabilities through public GitHub issues, discussions, or pull requests.**

### Preferred reporting method

Email the security contact below. If the repository enables GitHub private vulnerability reporting, that channel is also acceptable.

| Field | Value |
|---|---|
| Security contact | `[OWNER ACTION REQUIRED: SECURITY_CONTACT_EMAIL]` |
| Public application | `[OWNER ACTION REQUIRED: PUBLIC_APPLICATION_URL]` |
| Repository | `[OWNER ACTION REQUIRED: GITHUB_REPOSITORY_URL]` |

### Information to include

Please include as much of the following as you can:

- Affected component (for example authentication, portfolio isolation, import parsing, deployment)
- Detailed reproduction steps
- Potential impact (who or what could be affected)
- Relevant logs or screenshots with secrets, tokens, cookies, and personal financial data removed
- Suggested remediation, when known

### Encryption option

When available, encrypt sensitive report details using the key or method published by the project owner. Until a public key is published, send a high-level description first and ask for a secure channel before transmitting exploit details.

## Response process

These are cautious targets, not guarantees:

| Stage | Target |
|---|---|
| Initial acknowledgement | 5 business days |
| Initial assessment | 10 business days |
| Confirmed issues | Periodic status updates until resolved or declined |
| Disclosure | Coordinated disclosure after a fix is available, or after mutually agreed timing |

## Security scope

Reports in these categories are in scope for the hosted DividendScope application and its repository:

- Authentication bypass
- Cross-user portfolio access
- Credential or token exposure
- SQL injection
- Unsafe file processing
- Remote code execution
- Sensitive-data leakage
- Privilege escalation
- Deployment-secret exposure

## Out of scope

- Automated scanner reports without verified impact
- Denial-of-service testing against production
- Social engineering of maintainers or users
- Third-party provider vulnerabilities with no demonstrated application impact
- Reports based only on outdated dependency versions without a plausible exploit path

## Safe harbor

If you make a good-faith effort to avoid privacy violations, service disruption, and data destruction, and you report findings privately without exploiting them beyond what is needed to demonstrate the issue, the project maintainer intends to treat that research as authorized for the purpose of evaluating a vulnerability report.

This statement is not a bug bounty and does not promise financial rewards, legal immunity in every jurisdiction, or acceptance of every report.

## Non-security issues

Use GitHub issues for non-sensitive bugs and feature requests. See [SUPPORT.md](SUPPORT.md) and [CONTRIBUTING.md](CONTRIBUTING.md).
