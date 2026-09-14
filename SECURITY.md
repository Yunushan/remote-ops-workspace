# Security Policy

## Supported versions

| Version | Status |
|---|---|
| 1.x | Supported for security fixes |

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
  It must be a trusted, single-user local filesystem, not a team share.
- On POSIX, private workspace directories and sensitive files require owner-only
  modes (`0700`/`0600`) or the write fails. Windows `chmod` does not prove an
  owner-only DACL: operators must pre-provision and verify a current-user-only
  ACL on `ROW_HOME` (administrators and LocalSystem remain trusted).
- Local profile, vault, layout, snippet, backup and secret-output files use
  atomic replacement. Windows portable/shared roots are outside the
  confidentiality guarantee unless their DACL is secured independently.
- Support bundles include a sanitized profile summary instead of raw `profiles.json`, and intentionally exclude `vault.json` and private keys. Review every bundle before sharing.
- Support bundle summaries omit sensitive option key names and report only a sensitive option key count for password/token/credential-like option names.
- Vault encryption uses the optional `cryptography` package and an explicitly
  versioned Scrypt KDF parameter set; authenticated writes migrate older vaults
  to the current stronger parameters. Without the backend, vault commands fail
  closed.
- `row connect --dry-run` prints launch arguments so operators can validate commands before connecting.
- Audit redaction covers secret-like payload keys, assignment-style secret arguments such as `--password=value`, split secret flags such as `--token VALUE`, URL-embedded passwords, bearer tokens and common Windows-style password switches.
- SSHv1 profiles are disabled unless the profile protocol is `ssh1`/`sshv1`,
  `allow_insecure_sshv1=true`, `legacy_target=windows-xp-32` or
  `windows-xp-64`, and `allow_legacy_crypto=true` are set; protocol v1 remains
  unsafe even then.
- Known weak SSH algorithms and RDP native security mode are blocked for modern
  profiles. They require isolated Windows XP x86/x64 profile flags and do not
  change global defaults for Windows 10/11, Linux or macOS releases.

## Boundaries

Remote Ops Workspace builds launch commands and provides workspace abstractions. Security of protocol sessions also depends on the external client used, server configuration, identity provider, local endpoint hygiene, and operator practices.
