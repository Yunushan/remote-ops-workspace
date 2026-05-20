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

## Vault

The local vault uses `cryptography` with Scrypt-derived Fernet keys. It is optional and fails closed when the dependency is missing.

Operational rules:

- use a strong passphrase;
- do not store vault passphrases in shell history;
- prefer `ROW_VAULT_PASSWORD` only for short-lived automation contexts;
- do not commit `vault.json`.

## Audit

Launch events are appended to `audit.jsonl` with simple redaction for secret-like keys. Treat support bundles as sensitive.
