# Security Model

## Trust boundaries

Remote Ops Workspace manages profiles and launches clients. It does not make unsafe protocol behavior safe. The trust boundary includes:

- local operator workstation;
- profile store and vault;
- external protocol clients;
- remote hosts;
- network path;
- future sync providers.

## Safe command generation

Launchers build command arrays such as:

```python
["ssh", "-p", "22", "admin@ssh.example.invalid"]
```

They do not use `shell=True` or shell string concatenation for normal protocol launches.

Profile and command launch hardening:

- profile creation, import, GUI editor parsing, storage writes and launch planning share profile validation for supported protocol names, safe text fields, tunnel shape and minimum target requirements;
- hosts and network targets must not start with `-`, contain whitespace, or contain control characters;
- ports must be explicit valid TCP/UDP-style port numbers when a protocol has no safe default, such as raw sockets;
- HTTP/HTTPS profiles only open `http://` or `https://` URLs, reject embedded URL passwords, and use direct browser-launch helpers instead of Windows `cmd /c start`;
- SSH `proxy_jump` is the preferred jump-host path; `proxy_command` is rejected unless the profile explicitly sets `allow_unsafe_proxy_command=true`;
- SSHv1 requires both an explicit `ssh1`/`sshv1` profile protocol and `allow_insecure_sshv1=true`; when enabled it adds `-1` to the generated SSH argv and remains insecure even when an external client supports it;
- SFTP upload, delete, rename and local-overwrite download plans are marked destructive and are refused before execution unless the operator passes `--force`; broad delete/rename targets such as `/`, `.`, `~`, parent traversal and remote globs are rejected even with force;
- GUI process-backed panes track their `QProcess` state, ask before closing tabs or quitting with live sessions, and apply terminate-then-kill cleanup with bounded waits;
- `row serve-web` validates the bind host, refuses non-loopback interfaces unless `--allow-public-bind` is set, disables directory listing and adds static-app browser hardening headers;
- snippets, custom profile commands, broadcast commands, network tools and X11 helpers are parsed as argv lists and rejected when empty or malformed.

## Web/PWA and containers

The bundled Web/PWA is a static demo workspace. It does not expose a live remote
operation API. Demo profiles are kept in `sessionStorage`, not persistent
`localStorage`, to reduce accidental retention of hostnames typed into the
browser.

The included Python static server sends Content Security Policy, frame denial,
referrer, permissions and same-origin resource headers. The service worker caches
only same-origin `GET` requests and deletes stale cache versions during
activation.

The web Docker image runs as UID/GID `10001`, uses `/data` for `ROW_HOME`, and
the compose file binds the published port to `127.0.0.1` with read-only root
filesystem, no-new-privileges, dropped Linux capabilities and a temporary `/tmp`.

## Release supply chain

Release scripts validate that GitHub tag names match `pyproject.toml`, keep
release output inside the repository by default before deleting/recreating it,
reject symlinked release inputs, and stamp source/install archives with
deterministic metadata. Release manifests include `size_bytes` and `sha256` for
each artifact, and the source/Python release job emits a SHA-256 checksum file
for generated artifacts and the release manifest.

GitHub release build jobs run with read-only contents permission and do not
persist checkout credentials. Only the final publish job receives contents write
permission.

## Plugins

Protocol launch plugins are Python packages loaded from the local environment
through the `remote_ops_workspace.plugins` entry-point group. Treat installed
plugins as trusted code: they can run Python during discovery and launch-plan
generation. The core launcher validates the argv list returned by a plugin, but
it cannot sandbox plugin package code. Install plugins only from trusted sources
and inspect `row plugins list --json` before using plugin-backed profiles. Use
`row plugins validate` to catch load failures and invalid sample launch-plan
shape, but do not treat validation as a sandbox or provenance check.

## Vault

The local vault uses `cryptography` with Scrypt-derived Fernet keys. It is optional and fails closed when the dependency is missing.

Operational rules:

- use a strong passphrase;
- do not store vault passphrases in shell history;
- prefer `ROW_VAULT_PASSWORD` only for short-lived automation contexts;
- use `row vault set NAME --secret-env ENV` or `row vault set NAME --stdin` for automation so secret values are not placed in argv;
- secret names are validated to reject empty, option-like, whitespace/control-character and parent-directory-style names;
- `row vault get` refuses to print secrets unless `--show` is provided, or writes to an explicit `--out` file with best-effort owner-only permissions where supported;
- `row vault status` reports path, initialization state and item counts without revealing secret names or values;
- `row vault delete` requires `--force` to reduce accidental deletion;
- do not commit `vault.json`.

## Local data writes

The default workspace data directory is created with best-effort owner-only permissions where the operating system supports them. Profile storage, vault storage, layouts, snippets, profile backups, native private-key output and explicit vault `--out` secret files use atomic replacement helpers so partially-written files are not left behind after normal write failures.

Files that may contain operator-sensitive values are written with best-effort private file permissions:

- `profiles.json`;
- `vault.json`;
- `layouts.json`;
- `snippets.json`;
- `audit.jsonl`;
- profile backup/export bundles created by the local backup helper;
- generated private keys and `row vault get --out` files.

Permissions are best-effort on platforms that do not expose POSIX mode bits consistently, so operators should still keep `ROW_HOME` on a trusted local filesystem.

## SSH key generation

`row keygen` avoids placing non-empty key passphrases on `ssh-keygen` command lines. When `--passphrase-env` is used with software keys (`ed25519`, `ecdsa`, `rsa`), Remote Ops Workspace generates the encrypted OpenSSH key pair in-process through the optional `cryptography` backend and redacts the dry-run display. Hardware/FIDO key types (`ed25519-sk`, `ecdsa-sk`) must prompt interactively through `ssh-keygen`; `--passphrase-env` is rejected for those types to avoid leaking passphrases through process arguments.

Operational rules:

- use `--passphrase-env` only with short-lived environment variables;
- unset passphrase environment variables after automation runs;
- inspect `row keygen --dry-run` output before generation when scripting;
- do not commit private keys or generated key directories.

## Audit

Launch events are appended to `audit.jsonl` with redaction for secret-like keys and common secret-bearing command flags such as `-N`, `--password`, `--passphrase`, `--secret` and `--token`.

Support bundles include `doctor.json` and a sanitized `profiles.summary.json`; they do not include raw `profiles.json`, `vault.json` or private keys. The summary preserves counts, protocol names and structural flags, but omits profile names, hostnames, usernames, paths, command values, credential references, group names and URL contents. Treat support bundles as sensitive and review them before sharing.
