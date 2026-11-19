# MobaXterm Home and Professional Parity Ledger

This ledger tracks the gap between Remote Ops Workspace and public MobaXterm
26.4 Home plus Professional edition behavior. It is intentionally stricter than
the generated feature-family coverage table: the table proves implemented ROW
workflow families, while this ledger tracks whether the project is approaching
full product parity.

Official reference points checked on 2026-06-19:

- https://mobaxterm.mobatek.net/features.html
- https://mobaxterm.mobatek.net/download-home-edition.html

A user-supplied MobaXterm 26.3 connected-session capture was also reviewed on
2026-07-18 for layout and interaction measurements. The capture is not copied
into this repository. It is used only to define generic workbench geometry and
behavior: a compact four-band top stack, one left SSH-browser dock, terminal
input on the terminal surface, on-demand editing, a compact monitoring footer,
and a context-configurable bottom telemetry strip. Remote Ops Workspace keeps
its own name, text, icons, colors and product identity and does not claim
affiliation with Mobatek.

The Moba-style preset is a compatibility-oriented workspace, not a claim that
the application contains every MobaXterm feature. In particular, visual
similarity cannot close the strict parity articles below. Real shared-session
SSH/SFTP behavior, a full VT screen implementation, packaged auxiliary
runtimes, and accepted native evidence remain separate requirements.

Accepted release evidence for the eight strict articles below is tracked in
`configs/mobaxterm_parity_evidence.json` and validated by
`python scripts/check_mobaxterm_parity_evidence.py`. The default check keeps
the registry schema and any accepted records honest while leaving missing
articles visible; `--require-complete` is the hard gate for claiming every
article has accepted product-depth evidence.

### Qualify sealed candidates before publication

Dispatch the article's evidence workflow at the exact release tag. Each of
the eight workflows accepts the optional `candidate_inventory` input as
`RUN_ID ARTIFACT_ID sha256:DIGEST`. Use the run ID, numeric inventory artifact
ID and original ZIP digest from the successful build's **Report promotion
coordinates** summary. The workflow verifies the inventory's GitHub
attestation and the exact wheel or Debian package it names. Leave the input
empty to verify and use bytes from the immutable published release.
See the [candidate staging procedure](runbooks/RELEASE_PROMOTION.md#stage-the-candidate-for-review).

Put each article's reviewed files in its own `<article-id>/` directory, with
the article document named `evidence.json`. Use the verified asset from the
qualification when running
`python scripts/make_mobaxterm_parity_evidence_record.py` with that article
directory as `--assets-dir`. Save the candidate JSON outside the article
directory so the reviewed file set stays intact.

Pass the candidate, repository, exact source and resolved tag SHA, and the
successful Actions run URL and attempt to
`python scripts/finalize_mobaxterm_parity_evidence_record.py --print-review-line`.
Have the reviewer include the resulting `ROW parity acceptance` line verbatim
on its own line in the GitHub review for those exact bytes. Certification
compares the review's live URL, author, timestamp and acceptance line with the
record and checks that the review follows completion of the evidence attempt's
jobs. A pull-request review must have GitHub's `APPROVED` state.

### Preflight reviewed evidence against the sealed inventory

Keep the original workflow `candidate.json` for each article as
`candidates/<article-id>.json` under the evidence root. Put a
`candidate-reviews.json` object in the same root, keyed by all eight article
IDs. Each value contains the GitHub `reviewer` login, the exact
`review_url`, and the UTC `reviewed_at` timestamp.

Run the preflight from the tagged checkout after
[staging the sealed assets](runbooks/RELEASE_PROMOTION.md#stage-the-candidate-for-review).
Use the hash-locked release verifier environment and the same GitHub
credentials as for staging. Supply the independently approved Professional
update origins through `RELEASE_PROFESSIONAL_UPDATE_ORIGINS`.

```bash
python scripts/check_candidate_mobaxterm_parity.py \
  --repository "$release_repository" --tag "$release_tag" --sha "$release_sha" \
  --candidate-inventory "$build_run_id $candidate_inventory_artifact_id $candidate_inventory_archive_digest" \
  --assets-dir "$release_assets_dir" --evidence-root "$parity_evidence_root"
```

The preflight verifies the inventory attestation, staged asset bytes, original
Actions archives, captured evidence, GitHub reviews, and hosted Professional
update bytes. It reports whether the eight candidate reviews match the staged
release. The accepted registry is written during finalization after publication.

After review and immutable release publication, download the referenced
release assets and rerun the finalizer with the same inputs, the review URL,
login and UTC timestamp, and one `--published-release-asset name=path` for each
download. Save the accepted JSON outside the article directory. Finalization
re-hashes the published assets and binds the matching bytes to the accepted
schema-v2 record. Use `--append-registry` together with `--out` when adding a
reviewed record to the registry.

For production certification, merge the reviewed registry into protected
`main` after the published release is available and retain the full commit
SHA. The aggregate gate reads the registry from that commit and verifies all
eight records against the exact release SHA, the live workflow attempts and
reviews, and the downloaded release assets. See the
[production-readiness gate](PRODUCTION_READINESS.md).

## Implemented or adapter-backed families

- SSH, SFTP, SCP, FTP, RDP, VNC, Telnet, rlogin, rsh, Mosh, XDMCP and raw
  network launch workflows through validated argv adapters.
- Docked SSH/SFTP browser, operator-controlled folder-follow route, same-parameters SFTP
  open action, persisted SSH/SFTP browser state evidence and file transfer
  queue/previews, plus MobaXterm 26.4-style side-by-side startup location,
  saved column widths and upload/download overwrite confirmation reviews
  through `row ssh-browser`. The connected PyQt Moba SFTP dock consumes those
  persisted preferences for browser visibility, location metadata, overwrite
  confirmation mode and live table column widths.
  The folder-follow control currently keeps the browser on its selected remote
  path; it does not observe the interactive shell's working directory.
  Background SFTP and monitoring also start separate OpenSSH processes. Key or
  agent authentication works automatically; password-only profiles can use the
  explicit **Authenticate background tools** action with either a local encrypted
  vault `credential_ref` or a direct session password. The credential is held
  only for the current GUI session, submitted through a hidden native Windows
  ConPTY, and wiped when the connected dock closes. The visible terminal password
  is never copied or inferred.
- MobaTextEditor/MobaDiff-style `row text preview/write/diff/remote-plan`
  workflow with local text previews, SHA-256 evidence, guarded saves, backup
  creation, unified diffs and SFTP get/put staging plans for remote files.
  `row text open-remote`, `row text save-review`,
  `row text evidence-bundle` and `row text evidence-verify` add a connected
  SFTP-browser editor-tab contract, remote save conflict review, SHA-bound
  connected-session evidence assembly and fail-closed release evidence
  validation for real remote edit sessions. The connected PyQt Moba workspace
  keeps the editor surface hidden until a file-open action, rather than
  permanently reducing the live SFTP file list. Syntax highlighting,
  double-click routing, save/diff review and SFTP get/put command bindings
  remain part of the editor-tab plan.
- Smart-card, certificate, PKCS#11 provider and SSH agent handoff options for
  OpenSSH-backed profiles. `row smartcard inventory-plan/select-review/
  mobagent-plan/ssh-browser-plan/evidence-bundle/evidence-verify` adds a
  MobaXterm 26.4-style smart-card management contract for Microsoft
  CryptoAPI/PKCS#11 inventory, OpenSSH public-key retrieval, SSH expert
  certificate selection, MobAgent handoff, same-parameter SSH-browser multiplex
  plans and SHA-bound release evidence bundles. The Moba-style PyQt Tools
  dialog displays certificate data saved in the profile. Its PKCS#11 inventory
  opens an installed library, lists its OpenSSH public keys by fingerprint,
  and copies the selected public key. Operators can load or remove the
  provider's keys using the configured SSH agent. **Use key for profile** saves
  the chosen public key for SSH and SFTP, and **Clear saved selection** restores
  normal profile identity selection. The private key stays on the card.
  Connected Moba-style sessions now carry the selected smart-card certificate,
  provider, MobAgent handoff flag and public-key metadata into serialized GUI
  state so the PyQt SFTP dock can render the same selection context.
  OpenSSH SFTP and SCP receive the selected provider through `PKCS11Provider`,
  with quoting for paths that contain spaces. Local qualification with a SoftHSM
  software token verified direct SSH, interactive SFTP, agent-backed batch SFTP
  and SCP. The Linux Qt file browser listed a remote file over the same
  token-authenticated connection as the terminal through the managed Unix
  control socket. Hardware smart-card release acceptance remains pending.
- MultiExec-style SSH broadcast preview backed by the same broadcast planner as
  the CLI.
- Terminal tabs, split panes, local shell profiles, search, shortcuts, snippets,
  typed macro recording/replay and syntax highlighting rules. `row macro
  capture-plan`, `row macro live-plan`, `row macro evidence-bundle` and
  `row macro evidence-verify` add GUI capture control contracts,
  connected-pane replay review, confirmation/cancel prompts, SHA-bound proof
  bundle assembly and release evidence validation for live macro replay. The
  PyQt terminal pane now exposes Record/Stop/Cancel/Replay macro controls,
  captures operator-submitted terminal input and schedules recorded payload
  injection back into the live pane with preserved event timing. Connected SSH
  panes request a remote TTY, accept printable, navigation and control keys
  directly on the transcript surface, expose Copy/Paste/Select/Clear/Restart/
  Stop through a terminal context menu and close through a non-blocking
  terminate-then-kill lifecycle. Moba rail icon and rotated-label hit areas now
  dispatch the same action; Sessions/Favorites switch the visible profile tree
  without destroying a connected SFTP dock, and SFTP returns to that dock. The
  connected SFTP toolbar now routes path/parent navigation, download/upload
  transfer queues, reconnect, Tools and terminal focus to live GUI workflows.
  The transcript keeps linear multi-line mouse/keyboard selections stable while
  output arrives, copies exact visible lines, renders bounded ANSI SGR
  foreground/background styles, and exposes cyan underlined HTTP(S) links that
  require an explicit Ctrl+click.
  New-file, new-folder, delete, ASCII-mode and split-view controls remain
  disabled in that dock until safe operational backends replace their earlier
  metadata-only previews.
  The terminal renderer keeps a bounded transcript and a cursor-addressed
  alternate-screen buffer. Applications can request xterm SGR mouse reporting
  for clicks, wheel input and cell motion. Hold Shift to use local selection or
  scrolling while the application is tracking the mouse.
- MobApt-style `row mobapt status/search/install/update` workflow that
  inventories Unix tools, discovers host package managers such as `apt`,
  `brew`, `winget`, `scoop` and `choco`, builds explicit argv plans and
  requires `--execute` before an external package manager is run.
  `row mobapt runtime-status` scans ROW-owned runtime/cache roots from
  `ROW_MOBAPT_RUNTIME_DIR`, `row mobapt bundle-runtime` assembles a
  release-owned runtime/cache tree with tool binaries or explicit rehearsal
  shims, package archives, package index, manifest and evidence files, and
  `row mobapt cache-verify` fails closed unless a runtime manifest, offline
  package archives, package index, install-test evidence and terminal probe
  evidence are SHA-256 bound.
- Embedded server suite workflow through `row servers status/start/stop`,
  including loopback-safe Python HTTP serving, service lifecycle state and host
  daemon adapter discovery for SSH/SFTP, FTP, TFTP, Telnet, VNC and NFS.
  `row servers runtime-status` scans release-packaged daemon roots from
  `ROW_SERVER_RUNTIME_DIR`, `row servers bundle-runtime` assembles
  release-owned packaged daemon roots from supplied service binaries,
  `row servers config-plan` emits first-class auth/hardening configuration
  plans. On Linux, administrators manage the Telnet and NFS daemons through
  the host service manager. The Telnet plan leaves xinetd disabled by default
  and requires system PAM login and explicit approval for cleartext use. The
  NFS plan specifies NFSv4 over TCP and requires administrator-scoped exports
  with Kerberos privacy (`sec=krb5p`). `row servers evidence-verify` checks the
  bundled daemon hashes and hashed client-test attachments for every service.
  The Moba-style PyQt Servers ribbon action opens a typed GUI configuration
  surface backed by the same status, packaged-runtime, hardening, start/stop
  and evidence command contracts.
- X11 forwarding, external X server helper launch plans and MobaXterm-style
  managed X server runtime status for VcXsrv, XLaunch, Xming, XQuartz, Xorg,
  Xvfb, Xephyr and Xnest, including extension inventory, `DISPLAY` binding and
  display collision checks, plus managed PID state recording and `row x11 stop`
  lifecycle control. `row x11 package-status` prefers release-packaged runtime
  roots from `ROW_XSERVER_RUNTIME_DIR`, `row x11 bundle-runtime` assembles a
  release-owned packaged runtime root from supplied X server binaries,
  `row x11 smoke` captures X11 probe evidence with pass/fail status, probe
  output, notes and SHA-256-backed evidence JSON, and `row x11 evidence-verify`
  fails closed unless a packaged runtime, smoke evidence and real
  X11-forwarded GUI screenshot hashes match.
- Profiles, groups, tags, MobaXterm bookmark imports, portable `ROW_HOME`,
  encrypted vault, keygen, proxy/jump host support, tunnels and network tools.
- Professional Customizer-style `row customizer build` enterprise bundle with
  branding, welcome text, seed profiles, policy locks, installer helper scripts,
  manifest and SHA-256 evidence. `row customizer deployment-plan`,
  `row customizer evidence-bundle` and `row customizer evidence-verify` add
  Professional deployment-depth contracts and SHA-bound evidence assembly for
  branded Windows EXE/MSI artifacts, hard policy-lock enforcement surfaces and
  signed organization update channels. `row customizer update-verify` validates
  signed HTTPS update manifests and release artifact SHA-256 bindings.
  The administrator-owned OS machine-policy path is loaded ahead of the
  portable `ROW_HOME/policy.json` fallback by profile storage, GUI profile
  editing, quick connect, launcher and Web/PWA policy endpoints so a user-level
  environment override cannot shadow installed locked values. An open profile
  editor or Web profile API applies a newly installed machine policy on the
  next write. The schema and types are validated strictly and malformed
  installed policies fail closed.

## Remaining parity articles

1. Embedded X server parity: ROW now has a managed X server runtime contract,
   packaged runtime discovery through `ROW_XSERVER_RUNTIME_DIR`, extension
   inventory, display collision checks, lifecycle supervision, smoke evidence
   capture, a packaged-runtime bundle writer and a release-evidence verifier
   for real X11-forwarded GUI applications. Full parity still needs
   production-grade X server binaries attached to release targets and accepted
   passing evidence bundles from those targets.
2. MobApt and embedded Unix environment parity: ROW now has a MobApt-style
   status/planning/execution workflow for host package managers, Unix tool
   inventory, ROW-owned runtime/cache manifest discovery, a bundle writer that
   can assemble release-owned runtime/cache artifacts, and an offline package
   evidence verifier that requires terminal-use proof. Full parity still needs
   production-grade Unix command binaries, real package archives attached to
   releases and accepted passing release evidence proving newly installed Unix
   tools are usable inside the terminal.
3. Embedded server suite parity: ROW now has a MobaXterm-style server-suite
   inventory, HTTP runtime, loopback bind policy, start/stop lifecycle records,
   adapter plans for common local daemons, packaged daemon discovery, a daemon
   bundle writer, auth/hardening configuration plans, a PyQt Servers dialog for
   service rows, runtime roots, hardening state and lifecycle command previews,
   and a release-evidence verifier requiring real client proofs for every
   service. Full parity still needs production-grade daemon binaries for every
   embedded service attached to releases and accepted passing evidence proving
   each daemon serves real clients on supported targets.
4. MobaTextEditor/MobaDiff parity: ROW now has a CLI-backed text editor/diff
   workflow for local files, SFTP remote edit staging plans, connected
   editor-tab open plans, direct save conflict reviews, a release-evidence
   bundle writer and a release verifier for recorded connected-session
   evidence. The PyQt Moba SFTP dock keeps its editor surface hidden until an
   explicit file-open action. In the live connected workspace, opening a file
   runs an asynchronous SFTP download, loads the returned text into an
   editable editor, tracks the downloaded SHA-256 baseline, checks the remote
   file again before saving and prompts on conflicts. The browser resolves
   OpenSSH listing paths against the directory it requested. An overwrite approval
   applies to the reviewed bytes. The editor downloads the remote file again
   after approval and requests fresh approval if the bytes change. The final
   check and the upload are separate SFTP requests. The release audit
   verifies the displayed diff, a declined overwrite, a remote change during
   approval that triggers a fresh review, and a successful upload that matches
   an independent server readback. It ties these observations to the
   authenticated SFTP connection and the exact release package and workflow
   attempt. Full parity requires accepted evidence from supported release
   targets.
5. ROW provides a CLI-backed typed macro store and SSH replay workflow. The
   PyQt terminal records submitted lines, printable keys typed into the
   terminal, and Enter. A key or paste outside the supported typed input
   cancels the recording so replay preserves the captured sequence. The replay
   dialog identifies the destination and defaults to Cancel. Replay sends the
   events in order with their recorded delays and stops if the session changes
   or the terminal requests a password. Recording skips masked password input.
   The release-evidence checker compares recorded events and review decisions
   with the bytes, timestamps, and session identity observed over SSH. Full
   parity still requires accepted live replay evidence from supported release
   targets.
6. Exact 26.4 SSH-browser behavior: smart-card auth, smart-card management
   contracts, SSH expert certificate selection, MobAgent handoff,
   same-parameter SFTP, smart-card SSH-browser multiplex plans, side-by-side
   startup location, persistent column widths and overwrite confirmation
   reviews are now represented. The connected PyQt GUI state now consumes
   persisted 26.4 browser preferences and smart-card selection state directly,
   including browser visibility, saved table widths, overwrite-confirmation
   mode, selected certificate metadata and MobAgent handoff flags. The PyQt
   Tools dialog displays saved certificate metadata and opens the live PKCS#11
   inventory. Refresh reads public keys from the selected provider and the
   copy action exports the selected OpenSSH record. Loading into the SSH
   agent uses a masked PIN prompt. Removing the provider asks for confirmation
   and leaves unrelated agent keys in place. `row smartcard
   evidence-bundle` now assembles SHA-bound proof for the management UI,
   profile expert setting, MobAgent handoff and smart-card SSH-browser session.
   The release validator matches the card certificate to the agent key and the
   remote server's authentication log, then checks that the file browser uses
   the terminal's SSH connection. Full parity still needs an accepted capture
   from a physical card. See [smart-card release capture](#smart-card-release-capture).
7. Professional deployment depth: the ROW customizer builds a branded
   enterprise bundle. The Windows native build can use its product name,
   publisher, icon and welcome text to compile enterprise EXE and MSI
   installers with a deployment-specific upgrade identity. ROW also exposes
   evidence-bundle assembly and evidence validation for MSI/EXE rebranding, hard lock
   enforcement in CLI/GUI/Web/profile-editor/quick-connect/launcher surfaces
   and signed organization update channels. Runtime policy consumption now
   exists for profile storage, GUI profile editing, quick connect, launcher and
   Web/PWA surfaces, and signed update manifests can now be verified against
   HTTPS artifact metadata and local SHA-256 evidence. `row customizer
   evidence-bundle` copies supplied proof files plus signed update-manifest
   artifacts into a release evidence root and immediately validates the
   resulting deployment evidence. The release audit ties both inspected
   installer files to the signed organization manifest and validates the
   recorded native metadata against the original customization. Full parity
   requires accepted Windows deployment evidence and qualification of the
   policy surfaces and hosted organization update channel.
8. Shared authenticated transport and terminal-screen behavior. On POSIX
   hosts, the SFTP browser and monitoring can reuse a matching terminal's
   OpenSSH control connection after a local master check succeeds. A managed
   session exposes connection, authentication, closure and reconnect state
   through the terminal, SFTP and monitoring controls. Automatic tools wait
   for a verified connection and pause when it closes. Linux interactive SSH and SFTP
   panes use a controlling pseudoterminal. OpenSSH receives the initial viewport
   dimensions and forwards later resizes to its remote PTY. The Windows
   terminal uses ConPTY when available, and background tools authenticate
   separately. The ConPTY worker skips resize requests for dimensions Windows
   already applied, preventing repeated repaints at the same pane size.
   Linux SSH and SFTP panes lay out primary-screen output in
   cell-width rows backed by bounded scrollback. Resizing reflows soft
   wraps while preserving hard line breaks, wide characters, ANSI styles,
   and logical copy and search results. Clearing the primary display keeps
   scrollback. Clearing saved lines keeps the visible cells and cursor.
   The alternate screen keeps its own
   cursor-addressed grid.
   Both account for wide characters and combining marks in cursor positions,
   erasure and colored output. The alternate screen also keeps wide characters
   intact when wrapping or clipping at the right edge. When the viewport
   resizes, the visible alternate screen updates even if the remote
   application is quiet. Saved cursor positions and scrolling regions stay
   within the resized grid. Index and reverse index scroll only at the
   configured region boundaries. Cursor-position reports respect origin mode
   and keep delayed wrap within the visible columns.
   Applications can set and query block, underline and bar cursor styles.
   The cursor uses the desktop's blink timing and restores the primary-screen
   style when an application leaves the alternate screen.
   With a stable row count and palette, Qt updates only the alternate screen
   rows with changed text or ANSI styling. Cursor-only updates leave the
   document intact.
   Full parity requires evidence of shared authenticated transport, structured
   connection state and a terminal grid with alternate-screen, cursor, color,
   mode and mouse semantics.
   The strict evidence catalog tracks this article as
   `shared-authenticated-transport-terminal-grid`. Its dedicated validator is
   `python scripts/check_moba_transport_terminal_evidence.py --evidence
   <evidence.json> --assets-dir <artifact-dir>`. The validator fails closed
   unless six separate SHA-bound proof records share the exact release target,
   session/transport identity, source head SHA, GitHub Actions run URL and run
   attempt. Those records must prove one authenticated transport for terminal,
   SFTP and monitoring, structured connection transitions, a real cell grid,
   alternate-screen restoration, cursor/color/mode/mouse semantics and a real
   non-loopback connected session. Synthetic, fixture, simulated or transcript
   fallback captures are rejected. This article still remains unaccepted: a
   validator is only a contract, and no real reviewed connected-release record
   has been added to `configs/mobaxterm_parity_evidence.json`.

### Professional Windows installer release evidence

Run **Professional deployment release evidence** at the exact release tag.
The Windows build job verifies the wheel before creating the
customizer bundle, then signs the branded EXE and MSI using the existing
protected `release` signing environment. Configure `ROW_PROFESSIONAL_BRAND`,
`ROW_PROFESSIONAL_ORGANIZATION`, `ROW_PROFESSIONAL_LOGO_BASE64` (the organization's
ICO file), and `ROW_PROFESSIONAL_DEPLOYMENT_ID` (the approved stable deployment
GUID) as variables in that environment.

Download `professional-build-<run-id>-<attempt>` and use `native/` to publish
the exact signed installers to the approved organization HTTPS channel. The
organization signs and hosts the update manifest using those installer hashes.
Keep the signing key with the organization. The workflow's separate Linux job
uses the wheel and original customizer bundle from this same attempt to record
the live `protocol=ssh` policy checks.

Configure the `professional-update-review` environment with required reviewers
and the `RELEASE_PROFESSIONAL_UPDATE_URL`, `RELEASE_PROFESSIONAL_UPDATE_ORIGINS`
(space-separated), and `RELEASE_PROFESSIONAL_UPDATE_PUBLIC_KEY` variables.
Approve the waiting Windows qualification job after the signed update manifest
and both installers are available at their approved HTTPS locations. That job
inspects the native branding, verifies the signature and actual downloads, and
uploads `professional-deployment-evidence-<run-id>-<attempt>` for independent
review. Retain its original ZIP under `workflow-artifacts/` for certification.
If the run must be repeated, start a new attempt with all jobs and publish the
installer bytes from that new attempt before approving the review job.

The published audit requires all three successful jobs from this exact tagged
attempt, their Windows and Linux runner labels, the uploaded review ZIP, and
the published wheel. It also repeats the live update downloads using the
production audit's independently approved `RELEASE_PROFESSIONAL_UPDATE_ORIGINS`.

Build both branded installers from the published source asset for the release
under review. Record its `name` and SHA-256 in `release_asset` and record the
GitHub repository, release tag, source SHA, workflow run URL and run attempt
in `source`. Include both objects in the deployment evidence manifest and
the `installer_branding` capture. Include the published source asset when
generating the candidate record. Use the original customizer `manifest.json`
for the `bundle_manifest` attachment and its manifest digest.

Keep the EXE and MSI in the evidence bundle. The signed organization update
manifest must record the release version, HTTPS update URL, and exactly one
entry per branded installer with its name, target, HTTPS URL, relative
`file` path, `sha256`, and `size_bytes`. Use the same organization as the
customizer bundle.

Preflight delivery with `check_moba_professional_deployment_evidence.py`
and one `--update-origin <https-origin>` per independently approved origin.
The check uses certificate-verified HTTPS and compares the bytes served for
the manifest and each reviewed installer. The published release audit
repeats the downloads with the release operator's approved origin list.

On Windows, capture the native branding with
`scripts/capture_moba_professional_installers.py`. Supply the original
customizer directory, the native build output with
`enterprise-installers.json`, the signed organization manifest and its
trusted public key. The command reads the EXE version information and icon
resource and decompiles the MSI with WiX. It checks both installer hashes
against the signed manifest before writing the review directory.

```powershell
python scripts/capture_moba_professional_installers.py `
  --bundle $CustomizerDirectory --installers $NativeBuildDirectory `
  --update-manifest $SignedManifest --update-key $OrganizationPublicKey `
  --source $SourceIdentityJson --release-asset $PublishedSourceAsset `
  --out $ReviewDirectory
```

Use `--wix` if the WiX CLI is outside PATH. Use `--local` in place of
`--source` and omit `--release-asset` for a local inspection. Keep the
generated files together with `installer-capture.json` for the later
deployment audit and policy capture.

The `installer_branding` attachment uses schema
`row.moba-professional.windows-installers.v1`. Its `installer_sha256` map
records both installer filenames and digests computed before native
inspection. Set `exe_icon_offset` to the extracted icon image's byte offset
in the EXE resource section. Reference each capture file with `evidence_file` and
`evidence_sha256` relative to the evidence root.

| Field | Attachment |
| --- | --- |
| `build_manifest` | `enterprise-installers.json` from the native build |
| `logo` and `welcome` | Original ICO and welcome text from the customizer bundle |
| `exe_version` | EXE version resource values captured as JSON with `ProductName`, `CompanyName`, and `ProductVersion` |
| `exe_icon` | Image bytes extracted from an EXE icon resource |
| `msi_database` | WiX decompile XML from the branded MSI |
| `msi_icon` and `msi_welcome` | Icon and welcome bytes exported from the MSI by WiX |

The `policy_locks` attachment uses schema
`row.moba-professional.policy-surfaces.v1` and carries the same `source` and
`release_asset` objects as the installer capture. Reference the original
`config/policy.json` as `policy_document` and declare its exact
`locked_settings` in the evidence manifest. Use a policy with a protocol lock
and exercise distinct `allowed_protocol` and `denied_protocol` values under
`attempts`.

Use `scripts/capture_moba_professional_policy.py` to record live enforcement in
an isolated Linux lab. Build the dependency-locked Qt fixture image with
`scripts/build_qt_release_fixture.sh`. Start the container with `--network none`,
drop `NET_ADMIN`, `NET_RAW`, and `SYS_ADMIN`, and mount the repository, original
customizer bundle, and release wheel read-only. Install the wheel in the
image's `/opt/editor` environment using `pip install --no-index --no-deps`.
Mount a writable output directory and run the following command in the
container with the bundle and wheel mounted at the paths shown.

```bash
version=1.0.28
/opt/editor/bin/python -I /src/scripts/capture_moba_professional_policy.py \
  --wheel "/input/remote_ops_workspace-${version}-py3-none-any.whl" \
  --bundle /bundle --out /output/policy-review --local
```

Use the release's version in the wheel filename. The recorder requires a
customizer bundle with a single `protocol=ssh` lock. It tests Telnet refusal
and SSH allowance using loopback targets. It writes `policy-review.json`,
`policy-capture.json`, and the original policy and bundle manifest. For a
tagged release capture, omit `--local` and pass the GitHub Actions `GITHUB_*`
identity into the container. Use the same release wheel and workflow attempt
identity for the Windows installer capture. A local rehearsal still requires
a tagged capture for acceptance. The Linux fixture tests application policy
enforcement and Linux file permissions. Windows installer qualification
remains a separate step.

Assemble both capture directories with the exact wheel, the independently
trusted organization public key, and the approved HTTPS origin. The assembler
verifies the common release identity and original customizer manifest, checks
the installer metadata and all six policy surfaces, and downloads the signed
manifest and both installers to verify their delivered bytes. It writes the
review directory only after all checks pass.

```powershell
python scripts/assemble_moba_professional_evidence.py `
  --installer-review $InstallerReview --policy-review $PolicyReview `
  --wheel $PublishedWheel --update-key $OrganizationPublicKey `
  --update-origin $ApprovedHttpsOrigin --out $DeploymentReview
python scripts/make_mobaxterm_parity_evidence_record.py `
  --article-id professional-deployment --release-tag $ReleaseTag `
  --release-target windows-x64 --evidence "$DeploymentReview/evidence.json" `
  --assets-dir $DeploymentReview --release-asset-url $PublishedWheelUrl `
  --artifact "$(Split-Path -Leaf $PublishedWheel)=$PublishedWheel" --out $CandidateJson
```

Keep the candidate JSON outside the review directory. For a local rehearsal,
use both local captures, add `--local` to the assembly command, and omit the
candidate generation command. A local rehearsal without an approved origin
validates the signed manifest and installer files on disk. Supply a local
HTTPS origin to check delivery as well.

Start the GUI and authenticated Web API before installing the machine policy.
Record the stable process IDs in `gui_process` and `web_process`, with
`before` and `after` values. Capture the policy endpoint's HTTP status and
JSON body under `public_policy_before` and `public_policy`. As an unprivileged
operator, confirm the machine policy denies write access and retains its
digest while the portable fallback is writable. Record these observations as
`machine_policy_write_refused`, `machine_policy_unchanged`,
`portable_policy_writable`, and `gui_and_web_started_before_machine_install`.
Both `installed_policy_sha256` and `machine_policy_sha256` bind the deployed
document.

| Surface | Runtime observations |
| --- | --- |
| Web, CLI and profile editor | `store_before`, `store_after_denial` and `store_after_allowance` SHA-256 values and `saved_protocol` read back from storage |
| Web | `denied` and `allowed` HTTP status and body |
| CLI | `denied` and `allowed` exit status as `exit`, with refusal text in `stderr` |
| Profile editor | `denied` list containing the displayed refusal |
| Saved layouts and Quick Connect | `gui` and `quick-connect` each contain the `denied` dialog text and the counts `tabs_before`, `tabs_after_denial` and `tabs_after_allowance` |
| Launcher | `denied` refusal text, `allowed_protocol` and `allowed_argv` from the plan for the allowed profile |

### Article 8 evidence contract

The `row.moba-transport-terminal.release-evidence.v2` envelope records the
release target and the tested package in `release_asset` with its published
`name` and `sha256`. It also records the exact GitHub repository, release tag,
source SHA, Actions run and attempt, UTC capture time, and the non-loopback
SSH session, transport, and host-key digest. Set `synthetic`, `fixture`, and
`simulation` to `false` only for a native connected capture.

Its `proofs` object must contain exactly these six `file` plus `sha256`
references: `shared_transport`, `connection_state`, `terminal_grid`,
`alternate_screen`, `terminal_modes` and `connected_session`. Every referenced
JSON file must remain under the evidence root without symlink traversal, match
its dedicated `row.moba-transport-terminal.*-proof.v2` schema, and repeat the
release asset, host-key digest, and release, session, transport, and source
identity. Each proof has a `captures` object with a separate `file` and
`sha256` reference for each of its raw observations.

| Proof | Capture keys |
| --- | --- |
| Shared transport | `sshd_log` and `ssh_client_log` |
| Connection state | `state_log` |
| Terminal grid | `initial_screen` and `updated_screen` |
| Alternate screen | `primary_before`, `alternate_screen`, and `primary_restored` |
| Terminal modes | `mode_capture` |
| Connected session | `transcript`, `sftp_capture`, and `monitoring_capture` |

Retain the OpenSSH client debug log and server verbose log as UTF-8 files.
Record `ssh_user`, `client_endpoint`, and `server_endpoint` in the shared
transport proof, with an IP `address` and TCP `port` for each endpoint. The
validator reads the negotiated host-key fingerprint from the client and
checks for one authentication and a PTY shell, SFTP subsystem, and command
channel on the same server-observed socket. The state log records the desktop
SSH state snapshots in order under `events` and the snapshots shown by
`terminal`, `sftp`, and `monitoring` under `connected_views`. The validator
checks the close reason, terminal exit status, reconnect, and the shared
authenticated state. Keep the terminal, SFTP, and monitoring observations so
a reviewer can check the operation on each channel. The terminal transcript
must include a `ROW_SHARED_` line followed by the remote shell's
`SSH_CONNECTION` value and a `ROW_SFTP_SHA256_` line followed by the remote
file digest. The validator compares those values with the authenticated
socket and bytes read over SFTP. It also checks the monitoring process and
CPU sample, re-hashes all twelve captures, and compares the primary and
alternate screen snapshots.

The screen captures are JSON. The grid captures retain the primary line
before and after reflow, both viewport sizes, the remote PTY resize and
cursor reply, the scroll-region rows, and the one-row Qt document change.
The alternate-screen captures retain the original and restored primary
screens, the full-screen application at both sizes, its cursor transitions,
and the peer's observation of input after exit. The modes capture retains
the peer's cursor, key, paste, and mouse bytes alongside the three rendered
color styles and cursor visibility. The grid, alternate-screen, and modes
receipts each repeat the SSH socket observed by their remote challenge.

Generate the candidate with the tested package as `--artifact`. The candidate
and published-release audit check that the exact package bytes match the
capture. Independent review still requires the retained capture files.

Dispatch `transport-terminal-evidence.yml` at the exact release tag.
The workflow verifies the wheel, installs its
locked dependencies, and captures all six proofs through that installed
wheel. It retains `transport-terminal-evidence-<run-id>-<attempt>` for
review. The release audit requires the successful qualification job, its
native runner labels, and the exact retained candidate and capture bytes.

The `transport-evidence` environment must restrict deployment to approved
release tags and require operator approval. Its dedicated self-hosted Linux
x64 runner needs an unprivileged service account, GitHub CLI, OpenSSH,
`systemd-detect-virt`, and the system libraries required by the locked Qt
runtime. The administrator provisions `/etc/row-transport-evidence/peer.json`
with the private IP `address`, TCP `port`, and dedicated peer `user`. Keep
`peer.json`, `known_hosts`, and the peer's append-only `sshd.log` beside it
in a root-controlled directory with runner read access. The runner owns
the separate `identity` file and keeps it private. The log must contain the
dedicated peer's OpenSSH verbose output, with no rotation during capture.

On that peer, install `scripts/transport_terminal_peer.py` from the exact tag
as `/usr/local/lib/row-transport-peer.py`. The unprivileged peer account
needs Python 3, a full Vim build, `systemd-detect-virt`, SFTP, and a UTF-8
`document.txt` in its home directory containing `opening fixture: café`
followed by a newline. Pin the peer's key in `known_hosts`. The workflow uses
the dedicated peer, checks the installed challenge program against the
release checkout, and leaves approval to the release reviewer.

For a local Linux smoke test, use `scripts/run_qt_release_fixture.py --capture
transport --image <fixture-image> --server-image <vim-peer-image> --wheel
<package.whl> --out <new-dir>`. The peer image must have OpenSSH, Python,
and a full Vim build. The smoke test retains all twelve captures from the
installed wheel and checks the remote observations against the same
authenticated socket before the reconnect. Its qualification record marks
the run as local.

The active parity target is not complete until every article above has a real
implementation, tests, accepted release evidence in
`configs/mobaxterm_parity_evidence.json` and user-facing documentation.
### Embedded server release evidence

Place `evidence.json` and the attachments in the same article evidence directory. Use the
`row.moba-servers.release-evidence.v1` envelope with the exact release target, all eight
service policies and client tests, and these release bindings.

- `source` contains `repository`, `release_tag`, `head_sha`, `workflow_run_url`, and
  integer `run_attempt` from the workflow that captured the sessions.
- `release_asset` contains the published package `name` and tested `sha256`.
- `runtime_manifest` contains `file` and `sha256` for the `servers-runtime.json` from
  `row servers bundle-runtime`. Include the native executable bytes for all eight
  manifest entries and record their relative paths and hashes in the service records.

For Debian, supply the approved six external daemons to the normal native
packager through `ROW_RELEASE_SERVER_BUNDLE`. Its input manifest covers
TFTP, SSH, SFTP, Telnet, VNC, and NFS for the selected architecture. The
packager adds HTTP and FTP from the exact built ROW launcher and ships the
eight entries under `/usr/lib/remote-ops-workspace/servers`. The installed
launcher discovers this directory automatically. Capture client sessions with
`ROW_SERVER_RUNTIME_DIR` unset and verify the paths with
`row servers runtime-status --json`. The release audit compares the reviewed
manifest and all eight daemon digests with the downloaded Debian package,
including the shared HTTP and FTP launcher bytes. Redistribution approval and
the live client captures remain required.

The Debian packager derives `Depends` from the staged ELF files and the
PyInstaller launcher, including its embedded GLIBC symbol requirements.
It records the same dependency list as `debian_depends` in the installed
manifest. The release audit compares that list with the package control
field. Use apt to install the Debian package so it can resolve those
libraries from the distro repositories. Configure the host-managed server
policies and accounts before running the client captures.

Add a `debian_notices` object to the input manifest, keyed by distro package
name. Record the exact `version`, the covered `services`, and the notice's
`sha256` and `size_bytes`. Cover each external service once. A single OpenSSH
record can cover SSH and SFTP. Supply the unmodified notice as
`notices/<package>.copyright` beside the manifest. Keep the same relative
paths in the review attachments. The installer places these notices beneath
`/usr/share/doc/remote-ops-workspace/server-notices`. The archive audit
checks their bytes against the manifest.

For OpenSSH built with the package-owned libexec path, use the same daemon
bytes for the SSH and SFTP roles. Put `sshd-session` and `sshd-auth` under
`linux/openssh/libexec` in the bundle and add their SHA-256 digests to the
manifest's `openssh_helpers` object, keyed by filename. The installed libexec
path is `/usr/lib/remote-ops-workspace/servers/linux/openssh/libexec`. Keep
both helpers with the reviewed manifest. The packager checks their native
architecture, and the audit compares both files with the downloaded package.
Exercise SSH and SFTP on a host where the distro's OpenSSH helpers are absent.

Point each `client_test.evidence_file` and `evidence_sha256` at a
`row.moba-servers.live-client.v1` receipt. Include `service`, `runtime_sha256`,
`release_asset_sha256`, `source_head_sha`, `workflow_run_url`, `run_attempt`, the
`endpoint` with `host` and integer `port`, the executed `argv`, and the integer
`exit_code`. Render the command with `shlex.join(argv)` for `client_test.command`.
Keep credential values out of the recorded arguments and captures.

- Bind each `capture` with `file` and `sha256`. File transfers and SSH command
  output should reproduce the exact bytes from a separately attached `challenge`.
- For Telnet, attach the client transcript with the login prompts and the
  challenge output on a line of its own. Remove credential values.
- For VNC, attach an RGB or RGBA PNG of the observed framebuffer with visible
  content. A server challenge file is optional for this receipt.
- For NFS, attach the bytes read from the export, the `mount_options` output
  showing TCP NFSv4 with `sec=krb5p`, and the `rejected_sys_mount` output.
  Remove inherited RDMA settings and startup flags when applying the
  TCP-only configuration, then verify the effective kernel listeners.

On Debian, assemble the review directory with
`scripts/assemble_debian_server_evidence.py`. Use the exact Debian release asset
exercised by the clients. The installed root may be the filesystem of the
qualification host or a clean extraction of the same asset with `dpkg-deb -x`.
In the capture directory, place a `captures.json` index with the exact `source`
and `release_asset` objects observed during collection. Its `services` array
contains one entry per service with `service`, the observed `policy` object in
the server config-plan schema, and a `receipt` reference containing `file` and
`sha256`. Place the receipts and their referenced data files relative to this
directory, using visible files and directory names that can be retained in the
Actions archive. The assembler checks the embedded daemon bytes and notices
against the supplied package and validates all eight client receipts before
writing the review directory.

```bash
mkdir -p "$review_dir"
python scripts/assemble_debian_server_evidence.py \
  --deb "$tested_deb" --target linux-x86_64 \
  --installed-root "$installed_root" --captures "$capture_dir" \
  --out "$review_dir/embedded-server-suite"
```

Use the generated `evidence.json` and the same release asset with `--artifact`
when generating the candidate. The published-release audit re-runs the capture
checks on the reviewed attachments and checks the release bytes and GitHub
workflow and reviewer provenance.

For Debian amd64, dispatch `embedded-server-evidence.yml` at the exact
release tag. The Ubuntu runner verifies the DEB, then builds the lab from a
digest-pinned Debian image and signed
Debian package metadata. It installs the tested DEB inside disposable
containers. It starts a Debian guest with no network adapter for NFSv4.2
over loopback, verifies a Kerberos-privacy read and rejection of `sec=sys`,
and then exercises the other seven services on another container's loopback
interfaces. The captures carry the workflow's tag, source SHA, run and attempt.

The job assembles a candidate and uploads one artifact named
`embedded-server-evidence-<run-id>-<attempt>`. Keep the original ZIP at
`workflow-artifacts/embedded-server-evidence-<run-id>-<attempt>.zip` in the
review evidence root. The release audit ties the reviewed files to that ZIP
and the successful dedicated job.

For a local rehearsal, use the same Dockerfile and runner. Provide a
`release_dir` containing the tested DEB, an empty `build_context` directory,
and the verified SHA-256.

```bash
docker build --platform linux/amd64 \
  --build-context "release=$release_dir" \
  --build-arg "ROW_DEB=$asset" --build-arg "ROW_DEB_SHA256=$deb_sha256" \
  --file docker/Dockerfile.debian-server-evidence --tag row-debian-server-lab "$build_context"
python scripts/run_debian_server_lab.py --image row-debian-server-lab \
  --deb "$release_dir/$asset" --sha256 "$deb_sha256" --out "$captures" --local
```

The local receipts carry rehearsal provenance and cannot be submitted to
the release workflow.

### Connected editor release evidence

Dispatch `connected-editor-evidence.yml` at the exact release tag. The
workflow verifies the wheel's release provenance, installs those exact bytes
and opens the editor against a disposable SSH peer on a private Docker
network. It publishes a candidate and the bound captures for independent
review.

Run the connected Qt editor against an authenticated OpenSSH server using the
release package under review. Use a UTF-8 test file. Open it from the SFTP
browser, edit it locally and capture the displayed diff. Change the remote
file and decline the overwrite. Attempt to save again while changing the
remote file a second time inside the approval prompt. Approve the first
prompt, decline the fresh prompt and verify that both declines leave the
corresponding server version intact. Then approve the save and read the file
back separately from the server.

Use the downloaded file, dialog capture and saved remote file as the
`open_action`, `save_review` and `save_action` attachments. Record the dialog
sequence in a JSON array with `title`, `decision`, `text`, `detail`,
`default_is_no` and `remote_sha256_at_answer` on each entry. The diff entry
contains the full displayed diff. The four overwrite entries record
`No`, `Yes`, `No` and `Yes` in that order.

The `connected_session` attachment uses schema
`row.moba-text.connected-edit-capture.v1` and records `status` as `passed`.
Include the same `profile`, `remote_path`, `release_target`, `source` and
`release_asset` as the evidence manifest. The `source` object identifies the
`repository`, `release_tag`, `head_sha`, `workflow_run_url` and `run_attempt`.
The `release_asset` object contains the package `name` and `sha256`.
Record the `ssh_login`, `declined_remote_sha256` and
`changed_during_approval_remote_sha256` observed after the two declines.

Store these attachments in the evidence root and reference each one from the
connected capture with `evidence_file` and `evidence_sha256`. Use nonempty
captures of at most 1 MiB per file.

| Attachment | Contents |
| --- | --- |
| `first_conflict` and `second_conflict` | The distinct server snapshots preserved by the two declines |
| `staged` | Editor bytes staged for upload |
| `server_readback` | An independent server read after the approved save |
| `diagnostics` | Qt capture JSON with `status`, `errors` and `sftp_output` |
| `sshd_log` | OpenSSH server log showing the connection, authentication and SFTP subsystem for the same login and socket |

### Macro replay release evidence

Dispatch `macro-replay-evidence.yml` at the exact release tag. It runs the
installed wheel's terminal against a disposable SSH peer and submits the recording,
timing and reconnect evidence for independent review.

Use the `row.moba-macro.live-replay-evidence.v1` envelope with the same `source`
and `release_asset` fields as the embedded-server contract. The capture
attachment is the JSON recording from a PyQt terminal pane. Record multiple
printable keystrokes with a deliberate pause of at least 240 ms between two
events so the observer can distinguish timed replay from a burst of input.

The review attachment uses `row.moba-macro.live-review.v1` and includes
`input_sha256` and `profiles`. Under each profile, record the `decline`,
`complete`, `cancel`, and `reconnect` attempts. Each entry contains the dialog
`text`, `default_is_cancel`, `decision`, and `before` and `after` byte counts.
For decline, cancel, and reconnect, include the measured `quiet_ms` after the
action. Observe for at least the full recorded delay. End the original session
after the cancellation check, then observe the replacement session without
sending any input.

Each `row.moba-macro.ssh-replay.v1` attachment identifies its `profile`,
`destination`, `ssh_user`, `input_sha256`, `source`, `release_asset`,
`receiver_pid`, `replacement_receiver_pid`, and `enter_byte` (`0a` or `0d`).
Bind `terminal_transcript`, `replacement_transcript`, `server_bytes`, and
`ssh_log` with relative `file` paths and `sha256` values. Record one JSONL row
for each byte observed by the remote receiver with `pid`, one-based `index`,
two-digit `hex`, and `monotonic_ns`. The receiver prints the same observations
as `ROW_INPUT_<index>_<hex>_<monotonic_ns>` lines. Each terminal transcript
starts the session with `ROW_MACRO_READY_<pid>` followed on the same line by
the client IP and port and the server IP and port from `SSH_CONNECTION`.
Capture the SSH server log for those two public-key-authenticated remote PTYs.
Use disposable accounts and test input to keep credentials out of the capture.

### Smart-card release capture

Dispatch `smartcard-browser-evidence.yml` at the exact release tag.
Use a dedicated, unprivileged Linux x86_64 desktop runner labeled
`smartcard-evidence` with access to a physical test reader and a local desktop
session. Protect the `smartcard-evidence` environment with release-tag
deployment rules and a required reviewer. For the public repository, check the
queue and bring an isolated [one-job runner](https://docs.github.com/en/actions/reference/runners/self-hosted-runners#ephemeral-runners-for-autoscaling)
online for the approved release job. Use a disposable test account, test card,
and private OpenSSH test peer. The desktop needs the vendor PKCS#11 library,
`p11tool` and OpenSSH with Unix control sockets. Run the manual capture locally
as the runner's test account.

Read `capture-request.json` under the private runner work directory reported by
the workflow. It supplies the exact source, wheel digest and remote filename
for this attempt. Set `work` to that directory and launch the installed desktop.
Use the dedicated test agent's `SSH_AUTH_SOCK` in that shell.

```bash
export ROW_HOME="$work/workspace"
"$work/venv/bin/python" -I -m remote_ops_workspace gui
```

Connect to the test peer with the disposable login and physical test card.
Use the server's IP address and explicit port in the SSH profile. Authorize
the card's key for that login and capture the server log at `LogLevel VERBOSE`
with `sshd -E <file>`. The log must show the card key authenticating the
interactive terminal and the SFTP subsystem starting on that same connection.
Create the remote file named by `fixture_name` in the request and refresh the
desktop file browser to show it.

Capture the outputs below during the session. Use a dedicated agent and a test
card whose public certificate and token metadata can be shared with the reviewer.
Open **Tools → Smart cards → PKCS#11 inventory**, choose the installed vendor
library, and refresh. Use **Copy public key** to capture the OpenSSH record and
**Use key for profile** to save the chosen key. ROW writes an OpenSSH public
identity file from the saved record and requests `IdentitiesOnly=yes`. An
explicit `IdentityAgent` or the profile's agent handoff setting selects the
agent as the private key source. With direct card authentication, ROW disables
agent authentication for that launch. OpenSSH can also offer identities
explicitly listed in SSH configuration.

Use **Load into SSH agent** to load the provider's keys. If the profile sets
`IdentityAgent`, the dialog uses that socket. Otherwise it uses the active
OpenSSH agent. Confirm removal during cleanup to unload the provider's keys.
On systems with a managed control socket, the file browser waits for the
authenticated terminal connection.

| Bundle action | Required attachment |
| --- | --- |
| `management_interface` | JSON with `token_url`, `exported_openssh_public_key`, `certificate_der`, `present_tokens` and `removed_tokens`. The last three are file references. Export the public certificate in DER from the selected token. Save stdout from successful `LC_ALL=C p11tool --provider "$provider" --list-tokens` runs with the card inserted and removed. The removed inventory can be empty. |
| `ssh_session_selection` | The saved SSH profile JSON with the selected `smartcard_certificate_id`, absolute `pkcs11:` provider in `smartcard_provider`, and `add_smartcard_to_mobagent` set to the string `true` in `options`. |
| `mobagent` | Raw `ssh-add -L` output from the dedicated agent after handing off the selected card. |
| `ssh_browser` | JSON with schema `row.moba-smartcard.connected-capture.v1`, the same `source`, `release_asset` and `release_target` as the envelope, and `profile` set to the saved profile name. Include the executed `terminal_argv` and `sftp_argv` arrays, their `control_path`, the `fixture_name`, and `file_rows` as the displayed filenames. Include `sshd_log` and `sftp_listing` file references for the server log and the raw listing from that browser refresh. |

Use `row smartcard evidence-bundle` to assemble the four action attachments.
Keep the nested captures inside the same evidence root and reference them by
relative `evidence_file` and `evidence_sha256`. Use the request's `source` and
`release_asset` values in both the browser JSON and the bundle's
`evidence.json`. Store only reviewable test data in the referenced files.
Prepare the bundle in `$work/inbox/capture` and rename that directory to
`$work/inbox/ready` after closing the session and writing all attachments.
The workflow waits up to 40 minutes, then validates the completed capture and
archives the referenced files with `candidate.json` for independent review.

Run `python scripts/check_moba_smartcard_evidence.py --evidence <evidence.json>
--assets-dir <artifact-dir>` with the project's `security` extra installed.
The parity record generator and certification audit use the same validator.
The audit also verifies the original `smartcard-browser-evidence-<run>-<attempt>`
Actions ZIP. An independent reviewer checks the physical-card run and the
published wheel before accepting the resulting record.
