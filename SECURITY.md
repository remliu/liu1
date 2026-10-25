# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 1.x | ✅ |

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Send a private report to the maintainer with:

- affected version / commit
- reproduction steps
- impact assessment
- suggested fix, if available

You should receive an acknowledgement within 3 business days. Please allow time for a fix before public disclosure.

## Security model

WebScan SOP is a local-first workflow manager, not a scanner.

- It does **not** send requests to target systems.
- It stores project metadata in a local SQLite database.
- It has no built-in authentication and must not be exposed directly to the public internet.
- The default bind address is `127.0.0.1`.
- Demo data is fictional.
- The release EXE is unsigned; verify the published SHA-256 before running it.

For production use, place it behind a reverse proxy with HTTPS, authentication, RBAC, audit logging and backups.

## Legal

Use this project only for authorized security testing and defensive security work. Unauthorized scanning or intrusion is illegal in many jurisdictions.
