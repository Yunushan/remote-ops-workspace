# Full Feature Coverage Manifest

Remote Ops Workspace targets **100% public feature-family mapping**, **100% adapter-ready coverage** and **100% release-backed product workflow parity** for the requested product feature families.

The project publishes separate generated scores from `configs/feature_manifest.json`. Feature-family mapping answers whether each public feature family is represented by built-in code, external-client adapters, optional implementations, CLI/GUI workflows, platform scripts, or plugin extension points. Adapter-ready coverage counts implemented adapter, optional, CLI, GUI and combined workflows as ready when they are tied to executable evidence. The `production_parity_coverage` JSON key remains for compatibility, but the public contract is release-backed product workflow parity: implemented workflows count only when tied to executable release evidence, and seam-only or docs-only rows remain partial if they appear. This is not a proprietary native clone claim. Platform verified readiness is separate from feature coverage so verified native release targets, verified mobile Web/PWA contracts and extended compatibility rows do not get blended into one misleading product score.

MobaXterm Home/Professional parity is tracked more strictly in
[`MOBAXTERM_PARITY.md`](MOBAXTERM_PARITY.md). That ledger lists remaining
product-depth articles that are outside the generated feature-family score.
Accepted release evidence for those articles is tracked separately in
`configs/mobaxterm_parity_evidence.json` and validated by
`python scripts/check_mobaxterm_parity_evidence.py`; use
`--require-complete` before making a true full MobaXterm product-depth parity
claim.

## Current coverage score

| Product target | Feature-family mapping | Adapter-ready coverage | Release-backed workflow parity | Workflow gap to 100% | Feature families tracked |
|---|---:|---:|---:|---:|---:|
| MobaXterm | 100.0% | 100.0% | 100.0% | 0.0% | 50 |
| Remmina | 100.0% | 100.0% | 100.0% | 0.0% | 11 |
| mRemoteNG | 100.0% | 100.0% | 100.0% | 0.0% | 15 |
| Terminator | 100.0% | 100.0% | 100.0% | 0.0% | 8 |
| Termius | 100.0% | 100.0% | 100.0% | 0.0% | 22 |
| Devolutions Remote Desktop Manager | 100.0% | 100.0% | 100.0% | 0.0% | 26 |
| Royal TS / Royal TSX | 100.0% | 100.0% | 100.0% | 0.0% | 26 |
| Electerm | 100.0% | 100.0% | 100.0% | 0.0% | 19 |
| Tabby | 100.0% | 100.0% | 100.0% | 0.0% | 21 |
| SecureCRT | 100.0% | 100.0% | 100.0% | 0.0% | 19 |
| Xshell | 100.0% | 100.0% | 100.0% | 0.0% | 19 |
| Bitvise SSH Client | 100.0% | 100.0% | 100.0% | 0.0% | 9 |
| PuTTY | 100.0% | 100.0% | 100.0% | 0.0% | 11 |
| KiTTY | 100.0% | 100.0% | 100.0% | 0.0% | 12 |
| SuperPuTTY | 100.0% | 100.0% | 100.0% | 0.0% | 14 |
| Solar-PuTTY | 100.0% | 100.0% | 100.0% | 0.0% | 12 |
| MTPuTTY | 100.0% | 100.0% | 100.0% | 0.0% | 14 |
| Windows Terminal + OpenSSH | 100.0% | 100.0% | 100.0% | 0.0% | 17 |
| WinSCP | 100.0% | 100.0% | 100.0% | 0.0% | 10 |
| Apache Guacamole | 100.0% | 100.0% | 100.0% | 0.0% | 10 |
| XPipe | 100.0% | 100.0% | 100.0% | 0.0% | 16 |
| Muon SSH | 100.0% | 100.0% | 100.0% | 0.0% | 11 |
| ConEmu (with Cygwin / MSYS2 / SSH) | 100.0% | 100.0% | 100.0% | 0.0% | 12 |
| Cmder | 100.0% | 100.0% | 100.0% | 0.0% | 11 |
| Warp (macOS/Linux, Windows coming) | 100.0% | 100.0% | 100.0% | 0.0% | 12 |
| Hyper | 100.0% | 100.0% | 100.0% | 0.0% | 8 |
| X410 + any terminal (e.g., Windows Terminal, Alacritty) | 100.0% | 100.0% | 100.0% | 0.0% | 7 |
| Xming (or VcXsrv) + PuTTY / mRemoteNG | 100.0% | 100.0% | 100.0% | 0.0% | 10 |
| **Overall** | **100.0%** | **100.0%** | **100.0%** | **0.0%** | **70** |

## Platform verified readiness

| Target | Platform | Channel | Verified readiness | Gap to 100% | Status |
|---|---|---|---:|---:|---|
| windows-x86 | Windows x86 | default-native | 100.0% | 0.0% | verified-default-native |
| windows-x64 | Windows x64 | default-native | 100.0% | 0.0% | verified-default-native |
| windows-arm64 | Windows arm64 | default-native | 100.0% | 0.0% | verified-default-native |
| linux-i386 | Linux i386 | manual-script-native | 70.0% | 30.0% | manual-script-supported |
| linux-x86_64 | Linux x86_64 | default-native | 100.0% | 0.0% | verified-default-native |
| linux-armhf | Linux armhf | manual-script-native | 70.0% | 30.0% | manual-script-supported |
| linux-arm64 | Linux arm64 | default-native | 100.0% | 0.0% | verified-default-native |
| macos-x64 | macOS x64 | default-native | 100.0% | 0.0% | verified-default-native |
| macos-arm64 | macOS arm64 | default-native | 100.0% | 0.0% | verified-default-native |
| android-armv7 | Android/Termux armv7 | default-termux-web | 100.0% | 0.0% | verified-termux-web-mobile |
| android-arm64 | Android/Termux arm64 | default-termux-web | 100.0% | 0.0% | verified-termux-web-mobile |
| ios-web | iOS/iPadOS arm64 | default-web-pwa | 100.0% | 0.0% | verified-ios-web-pwa |
| Windows 8.1 | Windows legacy | legacy-windows | 60.0% | 40.0% | best-effort-source-host |
| Windows 8 | Windows legacy | legacy-windows | 45.0% | 55.0% | legacy-source-only |
| Windows 7 | Windows legacy | legacy-windows | 45.0% | 55.0% | legacy-source-only |
| Windows Vista | Windows legacy | legacy-windows | 25.0% | 75.0% | remote-target-only |
| Windows XP | Windows legacy | legacy-windows | 25.0% | 75.0% | remote-target-only |
| **Overall** | **Verified targets** | **mixed** | **100.0%** | **0.0%** | **mixed readiness** |

Windows XP stays at 25.0% as a native-host readiness row because no modern
Python/PyQt native installer targets XP. Its separate remote-target contract is
100.0% for x86 and x64 endpoints through RDP, VNC, SSH/SSHv1, SFTP/SCP,
Telnet, serial and raw-socket profiles, with weak crypto enabled only by
isolated per-profile legacy opt-ins.

Linux i386/armhf and Windows XP native-host promotion to 100% is gated by
`configs/platform_parity_promotion.json` and
`python scripts/check_platform_parity_promotion.py`, and real artifact sets are
validated by `python scripts/check_platform_promotion_artifacts.py`. Linux i386
and armhf must gain real default release builders, smoke evidence, native
manifests and checksum sidecars through
`.github/workflows/extended-platform-evidence.yml` before they leave the 70.0%
script-supported row. Windows XP native-host readiness must gain a separate
XP-capable legacy toolchain plus x86/x64 XP host evidence captured with
`scripts/xp_smoke_runner.cmd`, packaged by a modern `xp-evidence` collector,
and validated by `python scripts/check_xp_native_evidence.py` before it leaves the 25.0%
remote-target-only row. Accepted evidence records live in
`configs/platform_verified_evidence.json` and are checked by
`python scripts/check_platform_verified_evidence.py`; an empty registry means no
readiness promotion, and the default registry check rejects unfinalized
candidate records without review-bundle digests. The goal-specific gate is
`python scripts/check_protected_platform_goal.py --release-tag v<project.version> --require-records-complete`
plus `python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag v<project.version>`;
it must fail until linux-i386, linux-armhf, windows-xp-native-x86 and
windows-xp-native-x64 all have finalized accepted records for the same release tag,
same GitHub release repository, target-specific release source workflow file,
same release source head SHA and a positive release source run attempt in each record. Mixed-tag,
mixed-repository, mixed-source-head or same-run-URL conflicting-attempt accepted records
remain aggregate evidence only and cannot complete the protected goal parity block. The release/verifier promotion
gate is `python scripts/verify.py --quick --no-cli-smoke --require-platform-goal-targets --release-tag v<project.version> --platform-review-bundle-dir <bundle-dir> --release-assets-dir <release-assets-dir> --release-repository <owner>/<repo>`,
which also runs `python scripts/check_protected_platform_goal.py --release-tag v<project.version> --require-complete --assets-dir <release-assets-dir> --repository <owner>/<repo>`
and `python scripts/check_release_publish_assets.py --assets-dir <release-assets-dir> --tag v<project.version> --repository <owner>/<repo> --require-platform-goal-targets`
and must fail until the same four records are finalized and accepted from that same release source.
Static readiness JSON keeps `release_asset_provenance_complete=false`; only the
asset-backed protected goal gate can flip that proof state after finalized
records, review bundles and native release bytes match. Use
The readiness JSON also separates `record_complete` from
`release_backed_complete`, so accepted records alone cannot be mistaken for
published release-byte proof.
Protected Linux i386/armhf and Windows XP rows mirror that split with
`accepted_evidence_record_complete`, `release_asset_provenance_complete=false`,
`release_backed_readiness_complete=false` and `static_readiness_evidence_scope`
fields, so row-level readiness never claims published asset-byte proof before
the asset-backed protected goal gate runs with `--assets-dir`.
`python scripts/make_platform_verified_evidence_record.py`
to generate a candidate accepted record from validated artifact and XP evidence
inputs, then bind the packaged review-bundle manifest, archive and SHA-256
sidecar with `python scripts/finalize_platform_verified_evidence_record.py`.
Candidate generation must pass `--staged-upload-out-dir platform-evidence-upload/<target>/v<project.version>`
so the accepted record carries the exact upload staging command; XP candidates
must also pass `--xp-evidence-output-dir <xp-evidence-output-dir>`.
Linux release-source upload staging must use
`python scripts/stage_extended_linux_evidence_upload.py`, and XP release-source
upload staging must use `python scripts/stage_xp_native_evidence_upload.py`;
both stagers re-check finalized accepted-record assets before upload and require
the public final record to use canonical LF-terminated sorted JSON bytes.
Every accepted record must include the current promotion config SHA-256. Linux
records must include builder identity evidence plus its matching SHA-256,
sanitized target-scoped builder `host_identity` binding, workflow dispatch
input binding and `linux_smoke_summary` release/run, runtime architecture,
OpenSSL and legacy-crypto-scope proof values, and XP records must include the validated XP
evidence JSON SHA-256, the current XP evidence contract SHA-256, XP evidence
summary binding and every required smoke evidence SHA-256. Release asset URLs and artifact hash maps must exactly match
the required artifact names for the target; incomplete, duplicate or extra artifact sets do
not promote readiness. The generated platform readiness rows expose required, present and
missing accepted evidence targets so partial XP x86/x64 evidence remains visible
without promoting the Windows XP native-host percentage. Duplicate accepted
evidence targets are rejected, and XP x86/x64 evidence must use the same
`release_tag` before it can promote the Windows XP native-host row.
The checked operator path is documented in
`docs/PLATFORM_PROMOTION_RUNBOOK.md` and verified by
`python scripts/check_platform_promotion_runbook.py`.

Generate the same numbers locally:

```bash
row features --coverage
row features --coverage --json
```

The human `row features --coverage` output prints a `Protected platform goal`
line with the four-target accepted-evidence percentage, a `Release asset
provenance` line that stays `not checked by static report` until the
asset-backed protected goal gate runs, the exact `Asset provenance gate`
command, the exact `Remote evidence audit` command for the live published
release/source-run/source-artifact/final-record/release-asset/tag audit
(`python scripts/check_platform_release_evidence_remote.py ...`), and missing
targets. It also includes missing accepted evidence next to Linux i386,
Linux armhf and Windows XP rows plus a row-level accepted-record/release-asset
provenance note. The JSON output keeps the same row data under
`accepted_evidence_missing_targets` and exposes the four-target goal status
under `platform_verified_readiness.protected_goal_parity`, including
`release_asset_provenance_complete=false`,
`release_asset_provenance_command`, `remote_release_evidence_audit_command` and
`target_evidence_requirements` entries that list the required accepted registry
record, release artifacts, review-bundle files, validation/finalization
commands and XP security/smoke requirements for each protected target.
Protected platform goal parity is **0.0%** for the current accepted-evidence
registry (status=missing-accepted-evidence); the 100.0% overall verified
readiness row does not include Linux i386, Linux armhf or Windows XP
native-host promotion until real accepted evidence completes that separate goal.

## Scoring method

Coverage can be one of:

- **implemented**: working code exists in this repo;
- **implemented-adapter**: working command builder exists and delegates to an external client;
- **implemented-optional**: working code exists when an optional dependency is installed;
- **implemented-cli / implemented-gui / implemented-cli-gui**: working user-facing CLI, GUI, or combined workflow exists;
- **implemented-shell**: working shell exists for the named interface;
- **plugin-seam / adapter-seam / docs-adapter**: feature is mapped to an extension point and documented integration path.

Feature-family mapping weights:

| Status | Weight |
|---|---:|
| implemented | 1.00 |
| implemented-cli-gui | 1.00 |
| implemented-cli | 1.00 |
| implemented-gui | 1.00 |
| implemented-adapter | 1.00 |
| implemented-optional | 1.00 |
| implemented-shell | 1.00 |
| gui-shell | 0.40 |
| adapter-seam | 0.25 |
| docs-adapter | 0.20 |
| plugin-seam | 0.20 |
| manifest-seam | 0.15 |
| script-seam | 0.15 |

Adapter-ready coverage weights:

| Status | Weight |
|---|---:|
| implemented | 1.00 |
| implemented-cli-gui | 1.00 |
| implemented-cli | 1.00 |
| implemented-gui | 1.00 |
| implemented-adapter | 1.00 |
| implemented-optional | 1.00 |
| implemented-shell | 1.00 |
| gui-shell | 0.40 |
| adapter-seam | 0.25 |
| docs-adapter | 0.20 |
| plugin-seam | 0.20 |
| manifest-seam | 0.15 |
| script-seam | 0.15 |

Release-backed workflow parity weights:

| Status | Weight |
|---|---:|
| implemented | 1.00 |
| implemented-cli-gui | 1.00 |
| implemented-cli | 1.00 |
| implemented-gui | 1.00 |
| implemented-adapter | 1.00 |
| implemented-optional | 1.00 |
| implemented-shell | 1.00 |
| gui-shell | 0.40 |
| adapter-seam | 0.25 |
| docs-adapter | 0.20 |
| plugin-seam | 0.20 |
| manifest-seam | 0.15 |
| script-seam | 0.15 |

Every feature record also exposes generated evidence in `row features --coverage --json`, including feature id, status, implementation kind, product mapping and manifest extension point. `scripts/check_feature_reality.py` separately verifies implemented feature families against executable evidence such as CLI parser command paths, launch-plan builders, implementation symbols and shipped PWA/Termux files.

## Release-backed workflow evidence

`row features --coverage --json` includes `workflow_parity_contract` and
`workflow_parity_evidence`. The evidence ledger has one row for `Overall` and
one row for each product target. Each row lists:

- `product`, `coverage_percent`, `gap_percent` and `feature_count`;
- `feature_ids`, the exact feature-family IDs used by that product score;
- `feature_evidence`, with `id`, `status`, `implementation_kind`,
  `extension_point`, `status_weight`, `release_backed` and `evidence_refs`;
- `native_clone_claimed: false`, because the score is not a proprietary native
  clone claim or embedded protocol-engine parity claim.

`scripts/check_product_readiness.py` fails if a 100% workflow-parity row lacks
that evidence, has partial mapped features, uses blanket overrides, or blends
platform readiness into product feature coverage.

Adapter-ready coverage and release-backed product workflow parity use the
manifest status weights directly and do not use blanket per-product overrides.
Seam-only and docs-only rows remain partial, while implemented adapter,
optional, CLI, GUI, shell and combined workflows count as workflow parity when
they are tied to executable release evidence.

## Product feature family mapping

### MobaXterm-style families

- Tabbed SSH terminal workflow.
- SFTP/SCP/FTP file transfer profiles, `row files` SFTP browser actions, transfer queues and local/remote previews.
- MobaXterm-style connected-session SSH/SFTP browser panel with remote path toolbar and file table.
- Connected-session action to open SFTP with the same SSH parameters, including port, user, certificate, PKCS#11 provider and agent handoff options.
- MobaXterm 26.4 SSH-browser behavior through `row ssh-browser`, including persisted side-by-side startup location, saved table column widths, upload/download overwrite confirmation reviews and connected PyQt dock consumption of the persisted visibility/location/column-width state.
- MobaXterm 26.4 smart-card management through `row smartcard` and the PyQt Smart cards dialog, including Microsoft CryptoAPI/PKCS#11 inventory plans, certificate add/remove controls, OpenSSH public-key retrieval, SSH expert certificate selection review, MobAgent add/remove/list plans, same-parameter SSH-browser multiplex plans, connected PyQt session state for selected certificate/provider/MobAgent metadata, smart-card release evidence bundle assembly and SHA-bound evidence verification.
- MobaTextEditor/MobaDiff-style `row text` workflow for local text preview, guarded writes, hash evidence, backups, unified diffs, SFTP remote edit staging plans, connected editor-tab open plans, PyQt SFTP-dock `QPlainTextEdit` editor hosting with syntax highlighting, double-click file-row open routing, save/diff action capture, save conflict reviews, remote-edit evidence bundle assembly and SHA-bound connected-session release evidence verification.
- Multi-execution broadcast preview that generates safe per-profile SSH broadcast plans from the Moba-style ribbon.
- Typed terminal macro recording and replay through `row macro record/list/show/remove/replay/capture-plan/live-plan/evidence-bundle/evidence-verify`, with persisted typed-event metadata, SSH stdin replay plans, PyQt terminal Record/Stop/Cancel/Replay controls, operator input capture, connected-pane per-event timing injection, confirmation/cancel review, live replay evidence bundle assembly and SHA-bound release evidence verification.
- Terminal syntax highlighting for prompts, notes, warnings, errors, success markers, IP addresses, paths and custom keyword rules.
- Professional Customizer-style enterprise bundle generator for branding, welcome text, seed profiles, policy locks, install scripts, manifest and SHA-256 evidence, plus `row customizer deployment-plan/evidence-bundle/update-verify/evidence-verify` contracts for branded Windows EXE/MSI artifacts, signed organization update manifests, SHA-bound deployment evidence assembly and runtime hard-lock enforcement from `ROW_HOME/policy.json` across CLI profile storage, GUI profile editor, quick connect, launcher and Web/PWA surfaces.
- MobApt-style Unix tool inventory plus explicit host package-manager plans for `search`, `install` and `update`, with external execution gated by `--execute`, plus ROW-owned runtime/cache root scanning through `ROW_MOBAPT_RUNTIME_DIR`, `row mobapt bundle-runtime` release-owned runtime/cache bundle assembly and `row mobapt cache-verify` offline package/terminal-use evidence validation.
- Embedded server suite workflow with `row servers status/start/stop`, loopback-safe Python HTTP serving, service lifecycle state and host daemon adapters for SSH/SFTP, FTP, TFTP, Telnet, VNC and NFS, plus `row servers bundle-runtime` packaged daemon assembly, packaged daemon runtime discovery through `ROW_SERVER_RUNTIME_DIR`, auth/hardening configuration plans, a PyQt Servers dialog backed by the same GUI configuration-surface contract and `row servers evidence-verify` client-proof release evidence validation.
- Follow terminal folder workflow that rebuilds the SFTP list plan from the active terminal path.
- Remote monitoring plan and panel backed by agentless SSH `/proc`, `df`, `who` and process-count telemetry.
- Bottom connected-session telemetry strip for CPU, RAM, disk, network, connection and process status.
- SSH connection banner/status block for direct SSH, compression, smart-card auth, SSH-browser and X11 state.
- RDP, VNC, Telnet, rlogin, rsh, Mosh, XDMCP and raw network tool launchers.
- Per-protocol launch options for OpenSSH, Mosh, RDP, VNC and serial console adapters.
- X11 forwarding workflow through OpenSSH `-X`/`-Y`.
- External X server helper path plus MobaXterm-style managed runtime discovery for VcXsrv, XLaunch, Xming, XQuartz, Xorg, Xvfb, Xephyr and Xnest, with `row x11 bundle-runtime` packaged runtime assembly, packaged runtime preference through `ROW_XSERVER_RUNTIME_DIR`, extension inventory, `DISPLAY` binding, display collision checks, PID state recording, stop/status lifecycle supervision, `row x11 smoke` evidence capture and `row x11 evidence-verify` forwarded-GUI release evidence validation.
- Macros/snippets CLI.
- Portable mode through `ROW_HOME`.
- Network toolbox CLI.

### Remmina-style families

- RDP, VNC, SSH, SPICE and X2Go launchers.
- RDP, VNC, SPICE and X2Go viewer option mapping through native client argv.
- Profile grouping and tags.
- GUI profile editor backed by the shared profile store.
- Remmina profile import from `.remmina` files and directories.
- SSH tunneling model.
- Plugin architecture for protocols and features.
- Cross-distro Linux/Unix packaging scripts.

### mRemoteNG-style families

- Connection tree via groups and tags.
- GUI profile editing for quick connection updates.
- RDP, VNC, ICA, SSH, Telnet, HTTP/HTTPS, rlogin and raw socket launchers.
- Per-connection RDP display/security/device options and SSH adapter options.
- Quick connect through CLI/GUI.
- Import/export profile bundles.
- mRemoteNG `confCons.xml` import for nested connection trees.
- Group inheritance through group-level profile defaults.
- Credential store through the local vault.

### Terminator-style families

- Tabs.
- Horizontal and vertical process-backed split-pane UI shell.
- Saved layout/profile CLI and GUI opener.
- GUI layout editor for profile and command panes.
- Keyboard shortcuts.
- Broadcast/fanout command CLI with per-target result reporting.
- Plugin architecture.

### Termius-style families

- SSH, Mosh, Telnet, SFTP browser and port-forwarding models.
- SSH keepalive/proxy/host-key options and Mosh port/prediction options.
- Hosts, groups and tags.
- Local encrypted vault.
- Snippets/macros CLI.
- SSH keygen and FIDO/security-key adapters through OpenSSH.
- Local export/import and mounted/shared-directory sync provider.
- Termius-style JSON host import for local migration.
- SFTP queued transfer and preview workflow for SSH hosts.
- Desktop, Web/PWA, Android/Termux and iOS/iPadOS Web/PWA workflows.

## Current implementation status

The current v1.0.9 repo is an adapter-first foundation, not a proprietary clone. It has working profile storage, command generation, dry-run inspection, external process launch, doctor checks, optional encrypted vault, audit log, snippets/macros, typed macro recording/replay plans plus live GUI capture/replay evidence-bundle contracts and PyQt terminal macro controls, saved layouts that can be launched from CLI or opened and edited in the GUI, broadcast/fanout commands with per-target results, protocol-specific launch option builders, profile importers for common external exports, SSH keygen/FIDO adapters, smart-card certificate management and MobAgent evidence-bundle contracts, SFTP batch file operations, transfer queues and previews, MobaXterm 26.4 SSH-browser state/overwrite evidence with connected PyQt dock consumption of saved visibility, location, column-width and smart-card selection metadata, MobaTextEditor/MobaDiff-style text preview/write/diff/staging plus connected editor-tab/save-review/evidence-bundle/release-evidence contracts and a PyQt SFTP-dock syntax-aware editor widget with double-click open plus save/diff route capture, GUI SFTP panes, MobApt-style Unix tool/package-manager adapters, release-owned runtime/cache bundle assembly and offline runtime/cache evidence verification, MobaXterm-style local server suite status/lifecycle adapters, a PyQt Servers configuration dialog plus packaged daemon assembly and client-proof release evidence verification, Professional Customizer deployment-depth contracts and evidence-bundle assembly for branded Windows EXE/MSI artifacts, runtime hard policy locks and signed update-manifest verification, packaged X server runtime assembly/discovery and forwarded-GUI release evidence verification, network toolbox commands, mounted-directory sync, Web/PWA shell and PyQt6 GUI shell with process-backed terminal panes.

For each requested product target, the repository maps every tracked public
feature family and the implemented rows now score as adapter-ready under the
adapter-first readiness contract. Release-backed product workflow parity is also
100% for the tracked workflows because every mapped row is tied to implemented
code, tested launch-plan builders, shipped platform scripts, GUI/CLI workflows
or explicit plugin boundaries. Platform verified readiness remains separate
because manual native builders and legacy Windows remote-target tiers are
extended compatibility rows, not verified release targets.
