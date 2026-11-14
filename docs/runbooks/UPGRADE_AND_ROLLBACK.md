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

2. Install the new version in a fresh virtual environment after closing the
   running application. The example below uses the source release locks for
   Linux x86_64. Use the Python patch version recorded at the top of those
   locks and a new environment directory for each version. Set
   `target_tag` to the release tag you intend to install.

   ```bash
   git fetch --tags
   git checkout --detach "$target_tag"
   python3.14 -m venv .venv-upgrade
   . .venv-upgrade/bin/activate
   export PIP_CONFIG_FILE=/dev/null PIP_REQUIRE_VIRTUALENV=1
   python -m pip install --require-hashes --only-binary=:all: \
     --requirement requirements-locks/source-linux-x86_64-bootstrap.txt
   python -m pip install --require-hashes --no-build-isolation \
     --only-binary=:all: --no-binary=pyftpdlib \
     --requirement requirements-locks/source-linux-x86_64.txt
   python -m pip install --no-deps --no-build-isolation '.[desktop,security,package,servers]'
   python -m pip check
   ```

   For a native package, verify the downloaded installer before running it.
   Follow the [release promotion runbook](RELEASE_PROMOTION.md#verify-a-published-artifact)
   for the verification command. For source builds on other platforms, use
   the matching bootstrap lock, runtime lock, and install options from the
   tagged release workflow.

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
