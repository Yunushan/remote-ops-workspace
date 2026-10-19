# Runbook: Workspace backup and restore

`row workspace` produces a single encrypted snapshot of the whole `ROW_HOME`
tree and restores it into a new sibling directory. It is the supported way to
capture or move full workspace state.

## Backup

1. Close every Remote Ops Workspace window, terminal and managed helper.
2. Write the snapshot to a path outside `ROW_HOME`. Supply the passphrase through
   an environment variable to avoid an interactive prompt.

   ```bash
   row workspace backup --out /secure/row-2026-10-17.enc --offline --passphrase-env ROW_BACKUP_PASSPHRASE
   ```

   `--offline` is mandatory: it is your assertion that no other ROW process is
   running. A backup taken while processes run can capture inconsistent state.
3. Store the snapshot and its passphrase separately. Losing the passphrase
   makes the snapshot unrecoverable by design.

## Restore

1. Close every Remote Ops Workspace window, terminal and managed helper.
2. Restore into a new sibling directory next to the current `ROW_HOME`. The
   original directory is retained until you remove it yourself.

   ```bash
   row workspace restore --backup /secure/row-2026-10-17.enc --destination /path/to/ROW_HOME.restored --offline --passphrase-env ROW_BACKUP_PASSPHRASE
   ```

3. Inspect the restored directory before switching to it.

   ```bash
   row --version
   row doctor --json
   row vault status --json
   ```

4. Launch against the restored directory (`ROW_HOME=/path/to/ROW_HOME.restored`),
   confirm profiles, layouts and one SSH/SFTP connection, then remove the
   original directory only once you are satisfied.

## Notes

- The restore target must be a new directory; the command refuses to overwrite
  an existing workspace.
- The snapshot is authenticated-encrypted with scrypt key derivation (n=2^15,
  r=8, p=3) and Fernet. Treat the passphrase and snapshot as secret material.
  See [`../SECURITY_MODEL.md`](../SECURITY_MODEL.md).
- The CI recovery drill (`scripts/smoke_workspace_recovery.py`) exercises this
  path; see [`../PRODUCTION_READINESS.md`](../PRODUCTION_READINESS.md).
