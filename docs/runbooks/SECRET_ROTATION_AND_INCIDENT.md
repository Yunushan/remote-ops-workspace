# Runbook: Secret rotation and incident response

The local vault stores secrets encrypted at rest; secrets never appear in
process arguments. See [`../SECURITY_MODEL.md`](../SECURITY_MODEL.md) for the
threat model.

## Routine secret rotation

1. Confirm vault health without revealing values.

   ```bash
   row vault status --json
   row vault list
   ```

2. Prefer supplying new values through the environment so they never reach shell
   history or a process list.

   ```bash
   ROW_ROUTER_PASSWORD='<new-value>' row vault set prod/router-password --secret-env ROW_ROUTER_PASSWORD
   ```

3. Retire the old value once profiles referencing it connect successfully.

   ```bash
   row vault delete old/router-password --force
   ```

4. Re-run the affected connection and confirm the new value works.

## Suspected credential exposure

1. Treat the exposed value as compromised. Disable it at the remote system first;
   rotation in ROW alone does not revoke a leaked remote credential.
2. Rotate the secret in the vault (above) and update any host that consumed it.
3. If the vault passphrase itself may be exposed, initialize a fresh vault and
   re-enter secrets rather than reusing the old passphrase.
4. Capture a sanitized support bundle for review. Never paste secret values or an
   unredacted `ROW_HOME` into a ticket; runtime logs pass through the redaction
   layer, but treat every export as potentially sensitive.

## Managed-process and host incidents

1. Inspect managed state and stop anything unexpected.

   ```bash
   row servers status --json
   row servers stop <service>
   row x11 status --json
   ```

2. If an embedded server may have been exposed, confirm it was bound to loopback
   and, where applicable, TLS-protected. Public binds require an explicit
   `--allow-public-bind` and, for FTP, TLS on control and data connections.
3. Rotate the FTP credential and re-create the server with a fresh
   `ROW_FTP_PASSWORD` of at least 12 characters.

## Post-incident

- Record what was rotated, when, and where the value was used.
- Re-run `row doctor --json` and, if the workspace may be inconsistent, restore
  from a known-good snapshot:
  [`WORKSPACE_BACKUP_AND_RESTORE.md`](WORKSPACE_BACKUP_AND_RESTORE.md).
