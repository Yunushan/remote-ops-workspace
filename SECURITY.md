# Security Policy

## Supported versions

| Version | Status |
|---|---|
| 0.1.x | Supported for security fixes |

## Reporting a vulnerability

Open a private security advisory in GitHub, or contact the maintainers through your repository's configured security contact.

Please include:

- affected version/commit;
- operating system;
- exact protocol/launcher involved;
- reproduction steps;
- whether secrets, hosts, or keys may have been exposed.

## Secret handling rules

- Never commit real secrets, profiles, vaults, private keys, customer hostnames, RDP files, VNC files, or support bundles.
- `configs/*.example.*` files are examples only.
- Use `ROW_HOME=/path/to/private/workspace` for portable/private operator data.
- Vault encryption uses the optional `cryptography` package; without it, vault commands fail closed.
- `row connect --dry-run` prints launch arguments so operators can validate commands before connecting.

## Boundaries

Remote Ops Workspace builds launch commands and provides workspace abstractions. Security of protocol sessions also depends on the external client used, server configuration, identity provider, local endpoint hygiene, and operator practices.
