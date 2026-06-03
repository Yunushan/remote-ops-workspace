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
- Workspace data directories are created with best-effort owner-only permissions where the platform supports it.
- Local profile, vault, layout, snippet, backup and secret-output files are written through atomic replacement helpers with best-effort private file permissions.
- Support bundles include a sanitized profile summary instead of raw `profiles.json`, and intentionally exclude `vault.json` and private keys. Review every bundle before sharing.
- Vault encryption uses the optional `cryptography` package; without it, vault commands fail closed.
- `row connect --dry-run` prints launch arguments so operators can validate commands before connecting.
- SSHv1 profiles are disabled unless the profile protocol is `ssh1`/`sshv1` and `allow_insecure_sshv1=true` is set; protocol v1 remains unsafe even then.

## Boundaries

Remote Ops Workspace builds launch commands and provides workspace abstractions. Security of protocol sessions also depends on the external client used, server configuration, identity provider, local endpoint hygiene, and operator practices.
