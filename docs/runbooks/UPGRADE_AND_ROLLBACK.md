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
Debian package-manager lock before installing. Under that lock, it simulates
the candidate upgrade with APT and checks that the plan contains only the
candidate unpack and configuration. It refuses before writing an installation
journal if an installed dependency cannot satisfy the upgrade. APT uses the
local installer and installed package database for the simulation. Use separate
staging and transaction directories that do not overlap each other or the workspace.

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
If the controller reports `debian-upgrade-plan-refused`, resolve any missing
dependencies with the distribution's package manager and retry with the same
verified stages and transaction directory.
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
The drill also stops the controller after `dpkg` reinstalls the exact
predecessor and before the controller records rollback completion. It checks
that the journal retains `rolling-back`, retrying `rollback` completes
offline, and repeating the completed rollback leaves the journal unchanged.
It also stages a candidate with an unavailable dependency and verifies the
preflight refusal against the unchanged package database and launcher. The
refusal leaves the transaction without an installation journal.
The retained `managed-debian-update.json` records the package digests,
candidate source SHA, run attempt, and observed outcomes. The drill uses an
ephemeral test signer. Production approval uses the release-bound evidence in
the [release promotion runbook](RELEASE_PROMOTION.md).

## Managed RPM package updates

Use `scripts/managed_rpm_update.py` from a root-owned, verified checkout on an
x86-64 RPM host. Use the existing stock RPM installation and a Python environment
with Ed25519 support. Prepare an encrypted workspace backup before upgrading.
The controller changes the package installation. Workspace recovery uses the
separate restore procedure below.

Configure separate v2 trust policies for the installed version and the
candidate. Both policies must select `linux-x86_64` and use the same publisher
key, organization, and channel. The candidate policy's minimum version must
allow the installed predecessor. Use distinct, existing root-owned private
directories for each stage and the transaction, outside `ROW_HOME`.

```bash
python3 -I scripts/managed_rpm_update.py update \
  --version "$CANDIDATE_VERSION" --policy "$CANDIDATE_POLICY" --stage "$CANDIDATE_STAGE" \
  --previous-policy "$PREVIOUS_POLICY" --previous-stage "$PREVIOUS_STAGE" \
  --workspace "$ROW_HOME" --transaction "$TRANSACTION"
```

The controller authenticates the previous RPM first, retains both exact
installer files, and matches the previous package's signed bytes to the
installed RPM header, launcher owner, and file digests. It then invokes
`rpm --freshen` and verifies the installed candidate. Manage ROW through one
deployment tool during the transaction. The managed controllers share a
transaction lock, and RPM acquires its native database lock for package changes.
[RPM transaction options](https://rpm.org/docs/6.0.x/man/rpm.8)

Use a fresh transaction directory for each version pair. Keep the transaction
directory and its private, digest-bound RPM snapshots until rollout validation
is complete. Reissuing `update` verifies a completed installation or recovers
an interrupted transaction. If the controller recovers the predecessor during
an update, it reports `rolled-back` and exits with status 1.

```bash
python3 -I scripts/managed_rpm_update.py rollback \
  --workspace "$ROW_HOME" --transaction "$TRANSACTION"
```

This command works offline. On a completed update it first verifies that the
exact candidate is still installed. During recovery it recognizes only the two
recorded RPM identities. If the installed package or a retained file fails
verification, keep the journal and inspect the installation before making
further package changes.

## RPM rollback qualification

The x86-64 `all-modern` native candidate job runs this drill against the
pinned v1.0.27 release RPM and the exact RPM from the native smoke report.
It retains `build/candidate-proof/linux-x86_64/rpm-recovery.json` with the
candidate artifacts. The receipt binds the source commit, workflow attempt,
native smoke proof digest, both package digests, and the Fedora image digest.
The job also runs the managed controller from the same checkout against the
same RPM pair in a separate offline container. Its receipt records the HTTPS
downloads, tamper refusals, interruption recovery, and concurrent update
result. The tagged release binds both drills in the same evidence archive.

Use a disposable x86-64 Fedora Docker container with Python 3.10 or later,
`rpm`, and `rpm2archive`. Start with a fresh RPM database for ROW and no
`/usr/bin/row`. Mount the checkout and both inputs read-only. Use the expected
SHA-256 from each package's verified release evidence. For a local candidate,
record its checkout SHA and the digest of the RPM built from that checkout.

```bash
docker run --rm --platform linux/amd64 --network none \
  --security-opt no-new-privileges \
  --mount "type=bind,source=$PWD,target=/source,readonly" \
  --mount "type=bind,source=$RPM_INPUTS,target=/packages,readonly" \
  "$FEDORA_DRILL_IMAGE" python3 -I /source/scripts/qualify_rpm_recovery.py \
  --previous-rpm "/packages/$PREVIOUS_RPM" --previous-sha256 "$PREVIOUS_SHA256" \
  --candidate-rpm "/packages/$CANDIDATE_RPM" --candidate-sha256 "$CANDIDATE_SHA256" \
  > rpm-recovery.json
```

The drill seeds an SSH profile and vault entry through the installed
predecessor. A digest-verified launcher from the candidate RPM takes an
encrypted backup before the package changes. This supports predecessors that
predate `row workspace backup`. The drill upgrades with normal RPM dependency
checks, adds candidate-only data, and checks RPM's default downgrade refusal.
It restores the backup into a separate workspace, performs the explicit
`rpm --upgrade --oldpackage` downgrade, and checks that the predecessor can
read the restored profile and decrypt the vault entry. The receipt records
both package and launcher digests. Keep it with the source and container
identities. [RPM installation options](https://rpm.org/docs/latest/man/rpm.8)

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
   For an RPM downgrade, use `rpm --upgrade --oldpackage` with the verified
   predecessor RPM. If another package manager refuses a downgrade, follow
   its supported removal and reinstall sequence while retaining both
   workspace directories. Finish
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

## macOS PKG release evidence

The native smoke checks the expanded PKG before installation. The
distribution must name the exact version of the stock component and require
macOS 14.4 or later. The component must target the root volume with
relocation disabled, and its bill of materials must list the launcher and
contain only app paths and their shared parent directories. After installation
and same-version reinstall, the smoke compares the registered package
identity, version, location, and app paths with that package. It checks the
installed app's code signature and executable before running the app probes.
The DMG and PKG checks also compare the installed bundle against the original
signed build after install and reinstall. The comparison covers relative paths,
entry types, regular-file contents, and literal symbolic-link targets. The
candidate proof rehashes the original bundle before accepting all four results.
[Apple Distribution XML reference](https://developer.apple.com/library/archive/documentation/DeveloperTools/Reference/DistributionDefinitionRef/Chapters/Distribution_XML_Ref.html) ·
[Apple package receipt example](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools)

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
baseline. After cancellation the workflow confirms both private NTFS stage
leaves are absent. One `update` command downloads both provenance-verified
MSIs from a disposable signed loopback HTTPS feed and installs the candidate.
The workflow checks the order and completeness of the HTTPS requests, closes
the feed, and verifies that an offline `update` retry recognizes the exact
installed candidate. The workflow
checkout takes the encrypted pre-upgrade backup, which also covers older
predecessors that can read and write the fixture but lack the backup command.
The drill verifies that cancellation preserves the original workspace and
adds a candidate-only profile and vault entry after a successful retry. The
candidate CLI restores the backup into a fresh sibling. The drill uninstalls
the candidate, reinstalls the same predecessor, and runs offline preflight
on the retained stages. It checks that the predecessor can read the old profile
and decrypt the restored vault. It compares the full restored file inventory
with the baseline and checks that the upgraded workspace and encrypted archive
survive the restore. Keep the
`signed-windows-msi-upgrade-<run>-<attempt>` receipt with the qualification
evidence. The receipt binds all managed CLI results to the exact x64 MSI
inputs and records how the encrypted workspace was recovered. The loopback
feed uses ephemeral HTTPS and Ed25519 credentials for the qualification.
Sealed-candidate results can inform promotion review. Independent approval
and final published artifact verification still apply.

For operability review, download the receipt from the exact successful run
attempt. The workflow attests the completed receipt in a separate hosted job
after checking its SHA-256 against the Windows job's output. For a rerun,
rerun all jobs so the Windows program and attestation use the same attempt.
Use an authenticated GitHub CLI with read access to Actions and attestations.
Get the workflow's reviewed `main` commit and the expected MSI digests from
the independently verified immutable releases or sealed candidate inventories.

```bash
python -I scripts/check_signed_windows_msi_upgrade.py \
  --receipt "$receipt_path" --workflow-sha "$workflow_sha" --require-automatic-update \
  --previous "$previous_tag" "$previous_sha" "$previous_msi_sha256" \
  --candidate "$candidate_tag" "$candidate_sha" "$candidate_msi_sha256"
```

The verifier checks the package and launcher identities, NTFS stage receipts,
the initial download and offline retry, rollback, and encrypted-workspace recovery. It
binds the receipt bytes to the GitHub-hosted attestation and checks the outcome
of the specific workflow attempt.
[GitHub CLI attestation verification](https://cli.github.com/manual/gh_attestation_verify) ·
[Workflow attempt API](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run-attempt)

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
certificate checks may contact configured trust services.

#### Stage and apply in one command

Close the application and complete the encrypted workspace backup first. Use
elevated Windows x64 Python and the same trust policies, versions, and workspace
selection as preflight. Choose distinct private NTFS stage leaves under qualified
parent directories. The command downloads an authenticated asset set for each
missing stage leaf. It revalidates existing stages from disk and refuses a stage
that cannot be recovered under the selected trust policy.

```powershell
python -I scripts/managed_windows_msi.py update --policy $candidatePolicy --stage $candidateStage --version $candidateVersion --previous-policy $previousPolicy --previous-stage $previousStage --previous-version $previousVersion
```

The command applies the same signature, installer, and installed-predecessor
checks as `apply`. It can retry with both stages retained and the update feed
offline. Windows certificate checks still use the configured trust services.

#### Apply from the retained stages

Close the application and complete the encrypted workspace backup before
starting the upgrade. Use an elevated Windows x64 Python environment and
the same workspace selection, policies, versions, and stages as preflight.

```powershell
python -I scripts/managed_windows_msi.py apply --policy $candidatePolicy --stage $candidateStage --version $candidateVersion --previous-policy $previousPolicy --previous-stage $previousStage --previous-version $previousVersion
```

The command reauthenticates both stages and retains their read-only handles
until Windows Installer returns and the installed state is checked. The
candidate's launch condition requires Windows Installer to detect the exact
expected predecessor before removal. The command suppresses installer UI and
automatic reboot. Windows Installer owns rollback of a failed transaction.
The staging deadline covers authentication and verification. The command waits
for Windows Installer while the verified files remain held.

`msi-applied` means the exact candidate registration and launcher were verified.
Reissuing either command reports `msi-already-applied` if that state is
already present. `msi-previous-preserved` reports a failed install with the
exact predecessor verified. An installer-busy or reboot-required result calls
for waiting or restarting Windows before retrying. `msi-state-unverified`
requires inspecting the machine before another operation. Keep both stages
and the encrypted workspace backup until the release is accepted. For an
operator-requested downgrade after a successful install, use the restore and
reinstall procedure above.

## Notes

- Never edit `ROW_HOME` by hand during an upgrade; restore from a snapshot
  instead.
- An unsigned preview build is not a supported production upgrade target; see
  [`../PRODUCTION_READINESS.md`](../PRODUCTION_READINESS.md).
