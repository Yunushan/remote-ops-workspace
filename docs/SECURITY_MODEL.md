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
["ssh", "-p", "22", "admin@192.0.2.10"]
```

They do not use `shell=True` or shell string concatenation for normal protocol launches.

Command launch hardening:

- hosts and network targets must not start with `-`, contain whitespace, or contain control characters;
- ports must be explicit valid TCP/UDP-style port numbers when a protocol has no safe default, such as raw sockets;
- HTTP/HTTPS profiles only open `http://` or `https://` URLs, reject embedded URL passwords, and use direct browser-launch helpers instead of Windows `cmd /c start`;
- SSH `proxy_jump` is the preferred jump-host path; `proxy_command` is rejected unless the profile explicitly sets `allow_unsafe_proxy_command=true`;
- snippets, custom profile commands, broadcast commands, network tools and X11 helpers are parsed as argv lists and rejected when empty or malformed.

## Vault

The local vault uses `cryptography` with Scrypt-derived Fernet keys. It is optional and fails closed when the dependency is missing.

Operational rules:

- use a strong passphrase;
- do not store vault passphrases in shell history;
- prefer `ROW_VAULT_PASSWORD` only for short-lived automation contexts;
- `row vault get` refuses to print secrets unless `--show` is provided, or writes to an explicit `--out` file with best-effort owner-only permissions where supported;
- do not commit `vault.json`.

## SSH key generation

`row keygen` avoids placing non-empty key passphrases on `ssh-keygen` command lines. When `--passphrase-env` is used with software keys (`ed25519`, `ecdsa`, `rsa`), Remote Ops Workspace generates the encrypted OpenSSH key pair in-process through the optional `cryptography` backend and redacts the dry-run display. Hardware/FIDO key types (`ed25519-sk`, `ecdsa-sk`) must prompt interactively through `ssh-keygen`; `--passphrase-env` is rejected for those types to avoid leaking passphrases through process arguments.

Operational rules:

- use `--passphrase-env` only with short-lived environment variables;
- unset passphrase environment variables after automation runs;
- inspect `row keygen --dry-run` output before generation when scripting;
- do not commit private keys or generated key directories.

## Audit

Launch events are appended to `audit.jsonl` with redaction for secret-like keys and common secret-bearing command flags such as `-N`, `--password`, `--passphrase`, `--secret` and `--token`. Treat support bundles as sensitive.
