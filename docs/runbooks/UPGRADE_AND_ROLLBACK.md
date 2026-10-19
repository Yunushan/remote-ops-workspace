# Runbook: Upgrade and rollback

Applies to a source install or a release-candidate build of Remote Ops Workspace.
For the deployment model, see [`../PRODUCTION_DEPLOYMENT.md`](../PRODUCTION_DEPLOYMENT.md).

## Preconditions

- All Remote Ops Workspace windows, terminals and managed helpers are closed.
- You have an encrypted workspace snapshot taken immediately before the change
  (see [`WORKSPACE_BACKUP_AND_RESTORE.md`](WORKSPACE_BACKUP_AND_RESTORE.md)).
- You know the currently installed version and the target version.

## Upgrade

1. Record the current state.

   ```bash
   row --version
   row doctor --json
   row workspace backup --out /secure/row-pre-upgrade.enc --offline
   ```

2. Install the new version. For a source install, check out the target tag and
   reinstall into a fresh virtual environment; do not upgrade in place over a
   running process.

   ```bash
   git fetch --tags
   git checkout <target-tag>
   python -m venv .venv-upgrade && . .venv-upgrade/bin/activate
   python -m pip install --require-hashes -r requirements-locks/linux-x86_64.txt
   python -m pip install .
   ```

   Use the lock file for your platform (for example
   `requirements-locks/macos-arm64.txt` on Apple silicon or
   `requirements-locks/windows-x64.txt` on Windows) and consult
   [`../PYTHON_SUPPORT.md`](../PYTHON_SUPPORT.md) for the supported
   interpreter.

3. Verify before opening the GUI.

   ```bash
   row --version
   row doctor --json
   python scripts/verify.py --quick --lint
   ```

4. Open the GUI, confirm profiles, layouts, vault status and one SSH/SFTP
   connection, then confirm no managed embedded servers were left behind:

   ```bash
   row servers status --json
   ```

## Rollback

1. Close the new version completely.
2. Reinstall the previous version using the same fresh-environment steps above
   at the previous tag.
3. If the upgrade migrated workspace state, restore the pre-upgrade snapshot
   into a new sibling directory and point `ROW_HOME` at it:
   [`WORKSPACE_BACKUP_AND_RESTORE.md`](WORKSPACE_BACKUP_AND_RESTORE.md).
4. Re-run `row doctor --json` and confirm the three checks from the upgrade
   step. Escalate with a support bundle if any check fails.

## Notes

- Never edit `ROW_HOME` by hand during an upgrade; restore from a snapshot
  instead.
- An unsigned preview build is not a supported production upgrade target; see
  [`../PRODUCTION_READINESS.md`](../PRODUCTION_READINESS.md).
