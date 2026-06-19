# MobaXterm Home and Professional Parity Ledger

This ledger tracks the gap between Remote Ops Workspace and public MobaXterm
26.4 Home plus Professional edition behavior. It is intentionally stricter than
the generated feature-family coverage table: the table proves implemented ROW
workflow families, while this ledger tracks whether the project is approaching
full product parity.

Official reference points checked on 2026-06-19:

- https://mobaxterm.mobatek.net/features.html
- https://mobaxterm.mobatek.net/download-home-edition.html

Accepted release evidence for the strict articles below is tracked in
`configs/mobaxterm_parity_evidence.json` and validated by
`python scripts/check_mobaxterm_parity_evidence.py`. The default check keeps
the registry schema and any accepted records honest while leaving missing
articles visible; `--require-complete` is the hard gate for claiming every
article has accepted product-depth evidence.

## Implemented or adapter-backed families

- SSH, SFTP, SCP, FTP, RDP, VNC, Telnet, rlogin, rsh, Mosh, XDMCP and raw
  network launch workflows through validated argv adapters.
- Docked SSH/SFTP browser, follow-terminal-folder route, same-parameters SFTP
  open action, persisted SSH/SFTP browser state evidence and file transfer
  queue/previews, plus MobaXterm 26.4-style side-by-side startup location,
  saved column widths and upload/download overwrite confirmation reviews
  through `row ssh-browser`. The connected PyQt Moba SFTP dock consumes those
  persisted preferences for browser visibility, location metadata, overwrite
  confirmation mode and live table column widths.
- MobaTextEditor/MobaDiff-style `row text preview/write/diff/remote-plan`
  workflow with local text previews, SHA-256 evidence, guarded saves, backup
  creation, unified diffs and SFTP get/put staging plans for remote files.
  `row text open-remote`, `row text save-review`,
  `row text evidence-bundle` and `row text evidence-verify` add a connected
  SFTP-browser editor-tab contract, remote save conflict review, SHA-bound
  connected-session evidence assembly and fail-closed release evidence
  validation for real remote edit sessions. The connected PyQt Moba SFTP dock
  now hosts a `QPlainTextEdit` editor pane with syntax highlighting,
  double-click open routing from file rows, save/diff action capture and SFTP
  get/put command bindings from the same editor-tab plan.
- Smart-card, certificate, PKCS#11 provider and SSH agent handoff options for
  OpenSSH-backed profiles. `row smartcard inventory-plan/select-review/
  mobagent-plan/ssh-browser-plan/evidence-bundle/evidence-verify` adds a
  MobaXterm 26.4-style smart-card management contract for Microsoft
  CryptoAPI/PKCS#11 inventory, OpenSSH public-key retrieval, SSH expert
  certificate selection, MobAgent handoff, same-parameter SSH-browser multiplex
  plans and SHA-bound release evidence bundles. The Moba-style PyQt Tools
  workflow now opens a smart-card management surface for provider selection,
  certificate rows, add/remove controls, OpenSSH public-key export, SSH profile
  selection and MobAgent handoff previews.
  Connected Moba-style sessions now carry the selected smart-card certificate,
  provider, MobAgent handoff flag and public-key metadata into serialized GUI
  state so the PyQt SFTP dock can render the same selection context.
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
  injection back into the live pane with preserved event timing.
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
  plans, and `row servers evidence-verify` fails closed unless every embedded
  service has bundled daemon hashes plus passed real-client evidence. The
  Moba-style PyQt Servers ribbon action now opens a typed GUI configuration
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
  `ROW_HOME/policy.json` is now loaded by profile storage, GUI profile editing,
  quick connect, launcher and Web/PWA policy endpoints so locked profile values
  fail closed at runtime.

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
   bundle writer and a verifier requiring SHA-bound real connected-session
   proof. The PyQt Moba SFTP dock now hosts an actual syntax-aware editor
   widget and wires double-click/open plus save/diff route capture directly
   from the live SFTP browser state. Full parity still needs accepted passing
   evidence bundles from supported release targets proving real remote edits.
5. Macro recorder parity: ROW now has a CLI-backed typed macro store, SSH
   replay workflow, GUI capture control contracts, live connected-pane replay
   plans preserving per-event delay metadata, conflict/cancel review, a
   release-evidence bundle writer and a verifier requiring SHA-bound real
   connected-session replay proof. The PyQt terminal widget now exposes
   Record/Stop/Cancel/Replay controls, captures actual operator-submitted input
   events and injects recorded payloads back into the live pane with
   `QTimer`-scheduled event timing and replay cancel support. Full parity still
   needs accepted passing evidence bundles replaying recorded macros across
   real connected servers on supported release targets.
6. Exact 26.4 SSH-browser behavior: smart-card auth, smart-card management
   contracts, SSH expert certificate selection, MobAgent handoff,
   same-parameter SFTP, smart-card SSH-browser multiplex plans, side-by-side
   startup location, persistent column widths and overwrite confirmation
   reviews are now represented. The connected PyQt GUI state now consumes
   persisted 26.4 browser preferences and smart-card selection state directly,
   including browser visibility, saved table widths, overwrite-confirmation
   mode, selected certificate metadata and MobAgent handoff flags. The PyQt
   Tools workflow now exposes a smart-card management surface for certificate
   inventory, add/remove controls, OpenSSH public-key export, SSH expert
   selection and same-parameter SSH-browser command previews. `row smartcard
   evidence-bundle` now assembles SHA-bound proof for the management UI,
   profile expert setting, MobAgent handoff and smart-card SSH-browser session.
   Full parity still needs accepted release evidence bundles showing those
   behaviors in a real connected SSH/SFTP session with an actual smart card.
7. Professional deployment depth: the ROW customizer now builds a branded
   enterprise bundle and exposes deployment-depth plans, evidence-bundle
   assembly and evidence validation for MSI/EXE rebranding, hard lock
   enforcement in CLI/GUI/Web/profile-editor/quick-connect/launcher surfaces
   and signed organization update channels. Runtime policy consumption now
   exists for profile storage, GUI profile editing, quick connect, launcher and
   Web/PWA surfaces, and signed update manifests can now be verified against
   HTTPS artifact metadata and local SHA-256 evidence. `row customizer
   evidence-bundle` copies supplied proof files plus signed update-manifest
   artifacts into a release evidence root and immediately validates the
   resulting deployment evidence. Full parity still needs actual branded
   Windows installer artifacts, a hosted organization update channel and
   accepted passing release evidence from supported targets.

The active parity target is not complete until every article above has a real
implementation, tests, accepted release evidence in
`configs/mobaxterm_parity_evidence.json` and user-facing documentation.
