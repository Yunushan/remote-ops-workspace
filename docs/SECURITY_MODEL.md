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
- native Windows rewrites a single-hop SSH/SFTP/SCP `proxy_jump` into an
  explicit child `ssh` command with connection sharing and further proxy
  recursion disabled; the child still uses the selected SSH configuration and
  its host-key policy. Windows rejects multi-hop and non-`[user@]host[:port]`
  jump values rather than embedding unprovable command text;
- SSHv1 requires an explicit `ssh1`/`sshv1` profile protocol,
  `allow_insecure_sshv1=true`, `legacy_target=windows-xp-32` or
  `windows-xp-64`, and `allow_legacy_crypto=true`; when enabled it adds `-1`
  to the generated SSH argv and remains insecure even when an external client
  supports it;
- known weak SSH algorithms, including SHA-1 host-key/KEX overrides and
  CBC/3DES/RC4 cipher overrides, are blocked unless the profile is marked as an
  isolated Windows XP remote target and explicitly sets `allow_legacy_crypto=true`;
- Telnet, rlogin, rsh and FTP are cleartext legacy protocols and are blocked
  by default; each isolated target profile must explicitly set
  `allow_insecure_cleartext=true`, and this exception does not change any
  modern SSH, SFTP, HTTPS, WinRM or RDP default;
- group default options cannot contain `legacy_target` or any insecure protocol,
  legacy-crypto, native-RDP, WinRM HTTP or unsafe proxy-command opt-in; these
  exceptions must be persisted directly on the one reviewed profile they affect;
- FreeRDP `security=rdp` is blocked unless the profile is marked as an isolated
  Windows XP remote target and explicitly sets `allow_legacy_rdp_security=true`;
- generic XP labels such as `xp`, `winxp` and `windows-xp`, plus the
  `legacy_platform` alias key, are rejected for legacy crypto/RDP opt-ins; the
  profile must use the architecture-specific `legacy_target=windows-xp-32` or
  `legacy_target=windows-xp-64` boundary;
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

Release crypto dependency pins live in `requirements-release.txt` and
`configs/release_toolchain.json`. The security baseline keeps modern TLS policy
at TLS 1.3 preferred and TLS 1.2 minimum. TLS 1.3 preferred and TLS 1.2 minimum
are the release defaults, with SSL 2.0, SSL 3.0, TLS 1.0 and
TLS 1.1 treated as deprecated. XP compatibility is implemented as per-profile
remote-target compatibility and must not lower interpreter, OpenSSL, browser or
platform TLS defaults globally.

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

- new vaults require a passphrase of at least 12 characters;
- vault format version 3 records and strictly validates its Scrypt parameters,
  using `N=2^15`, `r=8`, `p=3` (one of OWASP's minimum-equivalent Scrypt
  parameter sets), and stores an encrypted verifier so every `set` operation
  authenticates the passphrase before changing entries;
- authenticated writes to legacy version 1 or 2 vaults generate a fresh salt and
  re-encrypt every entry with the version 3 KDF parameters before committing the
  atomic update; an empty version 1 vault establishes its verifier on first write;
- do not store vault passphrases in shell history;
- prefer `ROW_VAULT_PASSWORD` only for short-lived automation contexts;
- use `row vault set NAME --secret-env ENV` or `row vault set NAME --stdin` for automation so secret values are not placed in argv;
- secret names are validated to reject empty, option-like, whitespace/control-character and parent-directory-style names;
- `row vault get` writes only to an explicit `--out` file; it never prints decrypted secrets to the terminal. POSIX owner-only mode failure aborts the write, while Windows requires an independently secured destination DACL;
- `row vault status` reports path, initialization state and item counts without revealing secret names or values;
- `row vault delete` requires both `--force` and vault-passphrase authentication,
  preventing an unauthenticated local caller from deleting encrypted entries;
- do not commit `vault.json`.

## Local data writes

The default workspace data directory is created with private permissions where the operating system exposes them. Profile storage, vault storage, layouts, snippets, profile backups, native private-key output and explicit vault `--out` secret files use atomic replacement helpers so partially-written files are not left behind after normal write failures.

Files that may contain operator-sensitive values require POSIX private modes:

- `profiles.json`;
- `vault.json`;
- `layouts.json`;
- `snippets.json`;
- `audit.jsonl`;
- profile backup/export bundles created by the local backup helper;
- generated private keys and `row vault get --out` files.

On POSIX, failure to establish `0700` directories or `0600` sensitive files
aborts the write. Windows `chmod` is not evidence of an owner-only DACL. A
Windows operator must provision and verify a current-user-only ACL on the
default data root or `ROW_HOME`; administrators and LocalSystem are part of the
trusted computing base. Multi-user, SMB/WebDAV, cloud-synchronised, FAT/exFAT,
or otherwise ACL-unverifiable `ROW_HOME` locations are outside the private-data
confidentiality guarantee. Use the separate team-sync root only for its narrowed
public metadata schema.

## SSH key generation

`row keygen` avoids placing non-empty key passphrases on `ssh-keygen` command lines. When `--passphrase-env` is used with software keys (`ed25519`, `ecdsa`, `rsa`), Remote Ops Workspace generates the encrypted OpenSSH key pair in-process through the optional `cryptography` backend and its declared `bcrypt` OpenSSH encryption dependency, then redacts the dry-run display. Hardware/FIDO key types (`ed25519-sk`, `ecdsa-sk`) must prompt interactively through `ssh-keygen`; `--passphrase-env` is rejected for those types to avoid leaking passphrases through process arguments.

Operational rules:

- use `--passphrase-env` only with short-lived environment variables;
- unset passphrase environment variables after automation runs;
- inspect `row keygen --dry-run` output before generation when scripting;
- do not commit private keys or generated key directories.

## Audit

Launch events are appended to `audit.jsonl` with centralized redaction for
secret-like keys and common secret-bearing command flags such as `-N`,
`--password`, `--passphrase`, `--secret` and `--token`. Redaction also covers
assignment-style secret arguments such as `--password=value`, URL-embedded
passwords, bearer-token strings and common Windows-style password switches.

Support bundles include `doctor.json` and a sanitized `profiles.summary.json`;
they do not include raw `profiles.json`, `vault.json` or private keys. The
summary preserves counts, protocol names and structural flags, but omits profile
names, hostnames, usernames, paths, command values, credential references, group
names, URL contents and sensitive option key names. Sensitive option keys are
reported only as counts. Treat support bundles as sensitive and review them
before sharing.

Run `python scripts/check_security_polish.py` to verify these production
security polish rules without requiring optional dependencies.
