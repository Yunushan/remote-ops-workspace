# Runbook: Upgrade and rollback

Applies to source installs and promoted native releases of Remote Ops Workspace.
For the deployment model, see [`../PRODUCTION_DEPLOYMENT.md`](../PRODUCTION_DEPLOYMENT.md).

## Preconditions

- All Remote Ops Workspace windows, terminals and managed helpers are closed.
- You know the currently installed release tag and commit, the target release,
  the installation format and architecture, and the active `ROW_HOME`.
- For a native install, keep the verified previous installer and its release
  coordinates available before upgrading. Confirm that it can be reinstalled on
  the receiving host.

## Upgrade

1. Record the current state and take an encrypted offline snapshot. Keep the
   backup and passphrase separately. Use a verified CLI that supports
   `row workspace backup` and `row workspace restore`. If the installed version
   lacks these commands, keep a verified copy of a compatible CLI outside the
   installation directory and run the backup against the existing `ROW_HOME`.

   ```bash
   row --version
   row doctor --json
   row workspace backup --out /secure/row-pre-upgrade.enc --offline
   ```

2. For a native package, verify the new installer against its promoted release
   tag and commit using the
   [release promotion runbook](RELEASE_PROMOTION.md#verify-a-published-artifact).
   For Windows and macOS, include `--verify-platform-signature` before running
   the installer.
   Keep the same installation format, architecture, and scope.

   For a source install, use a fresh virtual environment. The example below
   uses the source release locks for Linux x86_64. Use the Python patch version
   recorded at the top of those locks and a new environment directory for each
   version. Set `target_tag` to the release tag you intend to install.

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

   For source builds on other platforms, use
   the matching bootstrap lock, runtime lock, and install options from the
   tagged release workflow.

3. Verify before opening the GUI. Run the CLI from the new installation and
   check that its reported version matches the target release.

   ```bash
   row --version
   row doctor --json
   ```

4. Open the GUI, confirm profiles, layouts, vault status and one SSH/SFTP
   connection, then confirm no managed embedded servers were left behind:

   ```bash
   row servers status --json
   ```

## Managed Debian package updates

Use `scripts/managed_linux_update.py` from a root-owned, verified release
checkout for an existing `remote-ops-workspace` DEB installation. Run it as a
Linux administrator. Put both v2 trust policies, the staging directories and
the transaction directory under root-owned paths with no writable or symlinked
ancestors. Create the two staging directories and the transaction directory with
mode `0700` outside `ROW_HOME`.

The previous policy points to the signed manifest for the currently installed
version. Both policies use the same signer, organization, channel and selected
target. The candidate policy's minimum version must allow the retained previous
version. Set the policy's freshness window to cover staging and installation.
Close the application and take the [encrypted workspace backup](WORKSPACE_BACKUP_AND_RESTORE.md)
before installing. Use the distribution's package manager to install any new
dependencies declared by the candidate DEB before running the offline apply.

Use `update` to authenticate and install the exact target version in one
invocation. It stages the prior installer first and reuses complete staged
downloads after authenticating them again. It keeps the package manager
available during downloads, then rechecks the installed package under the
Debian package-manager lock before installing. Use separate staging and
transaction directories that do not overlap each other or the workspace.

```bash
python3 -I scripts/managed_linux_update.py update --version 1.0.28 \
  --workspace /home/operator/.config/remote-ops-workspace \
  --policy /root/row-updates/candidate.json --stage /root/row-updates/candidate \
  --previous-policy /root/row-updates/previous.json --previous-stage /root/row-updates/previous \
  --transaction /root/row-updates/transition-1.0.28
```

If a download is interrupted and leaves an incomplete stage, retain it and use
a fresh private directory for that stage. Once installation is journaled,
retry the same `update` command with the same transaction directory. It uses
the retained installers without accessing the network. A recovered rollback
reports `rolled-back` with a nonzero exit status.

To download and install in separate maintenance steps, use the staging and
offline `apply` commands below.

```bash
python3 -I scripts/managed_linux_update.py stage-previous \
  --workspace /home/operator/.config/remote-ops-workspace \
  --policy /root/row-updates/previous.json --stage /root/row-updates/previous
python3 -I scripts/managed_linux_update.py stage-candidate --version 1.0.28 \
  --workspace /home/operator/.config/remote-ops-workspace \
  --policy /root/row-updates/candidate.json --stage /root/row-updates/candidate
python3 -I scripts/managed_linux_update.py apply --version 1.0.28 \
  --workspace /home/operator/.config/remote-ops-workspace \
  --policy /root/row-updates/candidate.json --stage /root/row-updates/candidate \
  --previous-policy /root/row-updates/previous.json --previous-stage /root/row-updates/previous \
  --transaction /root/row-updates/transition-1.0.28
```

Keep the transaction directory. Before creating its journal, the controller
reuses retained installer files only if their bytes match the signed manifests.
If a file conflicts, use a separate private transaction directory.
The controller records the installation attempt
before invoking `dpkg` and uses the retained installer if installation or its
verification fails. If `apply` is interrupted, repeat it with the same
transaction directory to recover the previous package. An automatic rollback
reports `rolled-back` with a nonzero exit status for the failed apply.

To roll the package back explicitly, close the application and run the following
command from the same verified checkout. It verifies both retained DEBs
offline and compares the installed launcher and any bundled server files with
the candidate DEB. A change to those bytes causes a refusal before the journal
or installation changes, even when the installed version matches.

```bash
python3 -I scripts/managed_linux_update.py rollback \
  --workspace /home/operator/.config/remote-ops-workspace \
  --transaction /root/row-updates/transition-1.0.28
```

Before opening the previous application, restore the encrypted backup into a
private sibling workspace if the newer version used `ROW_HOME`. Follow the data
restore and validation steps below.

The x86-64 all-modern native candidate job also runs an automated update drill
using the byte-verified previous release and exact candidate DEBs. It stages the
packages through certificate-validated HTTPS inside an isolated Debian
container and exercises `update` from fresh staging directories, including a
controlled `dpkg` failure that restores the previous installer. It then shuts
down the feed and exercises reuse of complete stages and operator-requested
rollback. It checks that changing the launcher under the same installed
version prevents explicit rollback. For candidates with an embedded server
bundle, it also checks changes to the installed manifest. It interrupts
the controller during package configuration and checks that retrying with
`update` restores the previous launcher while the HTTPS feed is offline.
The retained `managed-debian-update.json` records the package digests,
candidate source SHA, run attempt, and observed outcomes. The drill uses an
ephemeral test signer. Production approval uses the release-bound evidence in
the [release promotion runbook](RELEASE_PROMOTION.md).

## Rollback

1. Close the upgraded application, terminals, and managed helpers. Preserve
   the upgraded `ROW_HOME` for investigation and record the failure with the
   installed version and affected platform.
2. Restore the pre-upgrade backup into a new, private direct sibling of the
   upgraded workspace using the verified recovery CLI. Keep `ROW_HOME` pointed
   at the upgraded directory during restore. If recovery depends on the
   installed CLI, restore before removing that installation. On Windows,
   use a parent directory with a private ACL for the restore destination.
   The example assumes `ROW_HOME` is `/private/row-workspace`. See the
   [backup and restore runbook](WORKSPACE_BACKUP_AND_RESTORE.md).

   ```bash
   row workspace restore --backup /secure/row-pre-upgrade.enc \
     --destination /private/row-restored --offline
   ```

3. For a native rollback, recheck the previous installer's published provenance
   using its own release coordinates. Include `--verify-platform-signature`
   for Windows and macOS. Reinstall using the same platform and package format.
   If the package manager refuses a downgrade, follow its supported removal and
   reinstall sequence while retaining both workspace directories. Finish
   installation before starting the previous application. For a source
   rollback, select the retained environment for the previous tag or recreate
   it with that tag's locks.
4. Set `ROW_HOME` to the restored directory for the CLI and GUI before the first
   launch of the previous version. Confirm the expected `row --version`, run
   `row doctor --json`, and check profiles, layouts, and vault access by using a
   known saved credential in a test connection. Check `row servers status --json`
   after closing the test session. If any check fails, retain the encrypted backup
   and both workspace directories and follow the
   [incident runbook](SECRET_ROTATION_AND_INCIDENT.md).

## Windows MSI release evidence

The stock and branded MSIs remove the previous product after Windows Installer
initializes the installation transaction. With rollback enabled, Windows
Installer can restore the removed product if an upgrade fails. The build reads
the compiled MSI and checks that removal runs inside the transaction. It also
checks that the upgrade rules remove all features of older products in the
same package family and refuse a downgrade. See the
[WiX upgrade schedule](https://docs.firegiant.com/wix3/xsd/wix/majorupgrade/)
and [Windows Installer Upgrade table](https://learn.microsoft.com/en-us/windows/win32/msi/upgrade-table).

The native Windows smoke reads the stock MSI's package identity, architecture,
and launcher component before installation. During installation and reinstall
it checks that Windows Installer registered the exact ProductCode, PackageCode,
version, and Program Files launcher. It compares the installed launcher with
the payload read from the MSI's embedded cabinet after install and reinstall.
After uninstall it checks that the per-machine registration and launcher are gone. The candidate proof
binds these observations to the MSI's SHA-256 and the built executable bytes.
See the [Windows Installer product query](https://learn.microsoft.com/en-us/windows/win32/api/msi/nf-msi-msigetproductinfoexw)
and [component query](https://learn.microsoft.com/en-us/windows/win32/api/msi/nf-msi-msigetcomponentpathexw).

The native candidate smoke reinstalls the same version. To exercise x64
cross-version rollback, dispatch **Signed Windows MSI upgrade qualification**
on `main` with two ordered release tags and their full commit SHAs. Leave an
inventory input empty to use a certified immutable publish for that version.
To qualify a sealed candidate before publication, supply the corresponding
`previous_inventory` or `candidate_inventory` input as
`RUN_ID INVENTORY_ARTIFACT_ID sha256:ZIP_DIGEST`. Copy the coordinates from
the successful release build's summary. Both versions can use sealed
candidates. The workflow resolves each live tag, verifies the inventory
attestation for its exact build attempt, and compares the Windows x64 MSI
with that inventory under the retained file handle. All packages must pass
Authenticode and timestamp checks. At each installed checkpoint, the drill
holds the launcher against write and delete access and matches it to the
corresponding MSI's cabinet before running the CLI. Use an MSI predecessor
for this drill.

The workflow holds both MSIs against write and delete access throughout
verification, installation, cancellation, and retry. It installs the
predecessor and first requests an upgrade with rollback disabled for that
invocation. The compiled launch condition must refuse the upgrade before
predecessor removal and preserve the registration, launcher, and workspace.
The drill uses the installer log to identify the refusal and leaves machine
policy unchanged. It then cancels an upgrade through Windows Installer after the
predecessor's launcher disappears, and compares the
restored product registration, launcher SHA-256, and CLI version with the
baseline. It then retries with the same signed MSI bytes and checks that the
candidate replaces the prior product and uninstalls cleanly. The workflow
checkout takes the encrypted pre-upgrade backup, which also covers older
predecessors that can read and write the fixture but lack the backup command.
The drill verifies that cancellation preserves the original workspace and
adds a candidate-only profile and vault entry after a successful retry. The
candidate CLI restores the backup into a fresh sibling. The drill reinstalls the
same predecessor, and checks that the predecessor can read the old profile
and decrypt the restored vault. It compares the full restored file inventory
with the baseline and checks that the upgraded workspace and encrypted archive
survive the restore. Keep the
`signed-windows-msi-upgrade-<run>-<attempt>` receipt with the qualification
evidence. This exercise covers the stock x64 installer and encrypted workspace
recovery. The managed updater's automated policy and installation paths
require their own qualification.
Sealed-candidate results can inform promotion review. Independent approval
and final published artifact verification still apply.

### Managed Windows MSI preflight

Use native Windows x64 Python with the security extra and SignTool from a
machine-registered Windows SDK. Use private NTFS stages and separate v2
trust policies for the installed version and the candidate. Each policy
must select `windows-x64` and match the same publisher key, organization,
and channel. The configured minimum version must allow the predecessor.

```powershell
python -I scripts/managed_windows_msi.py stage --policy $previousPolicy --stage $previousStage --version $previousVersion
python -I scripts/managed_windows_msi.py stage --policy $candidatePolicy --stage $candidateStage --version $candidateVersion
python -I scripts/managed_windows_msi.py preflight --policy $candidatePolicy --stage $candidateStage --version $candidateVersion --previous-policy $previousPolicy --previous-stage $previousStage --previous-version $previousVersion
```

Preflight reauthenticates both complete staged sets under retained handles that
deny write and delete access. It checks both stock MSI signatures and
timestamps, the candidate's rollback sequence, the exact installed predecessor
registration, and the absence of the candidate registration. Windows
Installer's related-products query must return exactly the predecessor.
Preflight reads the launcher payload directly from each MSI's embedded
cabinet. It requires the installed predecessor's launcher
to match its MSI byte for byte and returns `install_permitted: false`. Windows
certificate checks may contact configured trust services. Use the existing
endpoint-management installation procedure after completing workspace recovery
preparation.

## Notes

- Never edit `ROW_HOME` by hand during an upgrade; restore from a snapshot
  instead.
- An unsigned preview build is not a supported production upgrade target; see
  [`../PRODUCTION_READINESS.md`](../PRODUCTION_READINESS.md).
