# Verifying The Project

Use the shared verifier for local checks and CI parity:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[desktop,security,dev]"
python scripts/verify.py
```

The full verifier runs:

- `python -m compileall src tests scripts`;
- `python scripts/check_docs.py` for local Markdown links, required release docs and English/Turkish README snippet consistency;
- `python scripts/check_roadmap_truth.py` for roadmap truth checks, keeping shipped release phases, native smoke tests and implemented CLI workflows out of future-planned sections;
- `python scripts/check_ci_workflow.py` for CI workflow policy, including read-only checkout, lint-enabled verification and a dedicated live PyQt6 render smoke job;
- `python scripts/check_release_truth.py` for repository identity, release workflow matrix, release-preflight dependency wiring and documented artifact truth;
- `python scripts/check_release_toolchain.py` for pinned release constraints, workflow install commands and release toolchain metadata;
- `python scripts/check_release_matrix.py` for the machine-readable `configs/release_matrix.json` policy, default GitHub release jobs, script-supported native targets and platform-target release channels;
- `python scripts/check_platform_support_truth.py` for architecture and legacy support truth, including default-native, manual-script, Termux/Web and legacy Windows remote-target readiness claims;
- `python scripts/check_platform_parity_promotion.py` for Linux i386/armhf and Windows XP native-host promotion gates, keeping 100% readiness claims blocked until real builder, release, smoke-test, manifest and checksum evidence exists;
- `python scripts/check_platform_promotion_runbook.py` for the operator runbook in `docs/PLATFORM_PROMOTION_RUNBOOK.md`, keeping target ids, blockers, artifacts and validation commands aligned with `configs/platform_parity_promotion.json`;
- `python scripts/check_platform_promotion_artifacts.py --contract` for the executable artifact validation contract used after real Linux i386, Linux armhf or Windows XP native builder output exists;
- `python scripts/check_extended_platform_evidence.py` for the dispatch-only self-hosted Linux i386/armhf evidence workflow policy, including candidate accepted-evidence record generation in uploaded artifacts;
- `python scripts/check_xp_native_evidence.py --contract` for the Windows XP x86/x64 native evidence JSON contract, including required per-smoke evidence files and SHA-256 checks;
- `python scripts/make_xp_native_evidence_template.py --help` for the failing-by-default XP evidence bundle template generator used before real XP VM or host evidence is collected;
- `python scripts/check_platform_verified_evidence.py` for accepted evidence registry records in `configs/platform_verified_evidence.json`, which are the only records that can promote Linux i386, Linux armhf or Windows XP native-host readiness and must include release asset URLs under the same release tag, per-artifact SHA-256 digests, promotion config SHA-256 binding, Linux builder identity evidence plus its SHA-256 and workflow dispatch input binding when applicable, and XP evidence bundle SHA-256, XP evidence contract SHA-256 and XP evidence summary binding when applicable;
- `python scripts/make_platform_verified_evidence_record.py --help` for the supported generator that turns validated artifact/evidence inputs into candidate accepted registry records with artifact digests and can append them with full-registry validation via `--append-registry`;
- `python scripts/check_mobaxterm_parity_evidence.py` for accepted MobaXterm Home/Professional parity evidence records in `configs/mobaxterm_parity_evidence.json`; the default check validates schema and accepted records while keeping missing parity articles visible, and `--require-complete` is the hard gate for claiming every strict MobaXterm parity article has accepted release evidence;
- `python scripts/make_mobaxterm_parity_evidence_record.py --help` for the supported generator that validates a MobaXterm article evidence bundle, hashes its evidence root and release artifacts, and emits or appends a candidate accepted parity record;
- `python scripts/check_mobile_support.py` for Android 12 through Android 16 (API 31-36), iOS/iPadOS 15 through 26.x and mobile CI contract truth;
- `python scripts/check_release_publish_assets.py` for publish-time release asset completeness, checksum sidecar and release-manifest contract wiring, including a guard that revalidates platform accepted evidence before rejecting Linux i386/armhf and Windows XP native assets unless the required accepted evidence records exist, plus MobaXterm parity accepted-evidence registry validation and the optional `--require-mobaxterm-parity-complete` hard gate for true product-depth parity claims;
- `python scripts/check_optional_dependencies.py` for optional extra declarations, fail-closed missing dependency paths and real PyQt6/vault smoke checks when those extras are installed;
- `python scripts/check_native_release_hardening.py` for native checksum sidecars, native manifest integrity, appimagetool verification hooks and native workflow boundaries;
- `python scripts/check_native_installer_smoke.py` for the native installer smoke contract in `configs/native_installer_smoke.json`, including install, verify, upgrade and uninstall coverage for `.exe`, `.msi`, `.dmg`, `.pkg`, `.deb`, `.rpm` and AppImage release artifacts;
- `row x11 bundle-runtime --out <artifact-dir> --runtime <key> --source <x-server-binary> --system <target-system> --json` to assemble a packaged X server runtime root, then `python scripts/check_moba_xserver_release_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>` for MobaXterm-style packaged X server evidence, including bundled/packaged runtime hash binding, passing X11 smoke JSON and forwarded GUI screenshot hash verification;
- `row mobapt bundle-runtime --out <artifact-dir> --tool <name> --tool-source <name=path> --package <name=version> --package-source <name=version=path> --json` to assemble a ROW-owned MobApt runtime/cache bundle, then `python scripts/check_mobapt_cache_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>` for MobApt-style offline package cache evidence, including ROW-owned runtime manifest hash binding, cached package archive hashes, install-test evidence and terminal-use proof;
- `row servers bundle-runtime <service> --out <artifact-dir> --runtime <runtime-key> --source <daemon-binary> --system <target-system> --json` to assemble packaged embedded-server daemon roots, then `python scripts/check_moba_server_release_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>` for MobaXterm-style embedded server evidence, including packaged daemon hash binding, auth/hardening policy checks and real client proof for every embedded service;
- `row text evidence-bundle <profile> <remote-path> --out-dir <artifact-dir> --local <local-copy> --remote-sha256 <sha256> --open-evidence <open-proof> --save-review-evidence <review-proof> --save-evidence <upload-proof> --connected-evidence <connected-proof> --real-connected-session --sftp-browser-open --editor-tab-visible --json`, then `python scripts/check_moba_text_remote_edit_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>` for MobaTextEditor-style connected remote-edit evidence, including editor-tab open proof, save conflict review proof, upload proof and SHA-bound real connected-session/SFTP-browser evidence;
- `row macro evidence-bundle <macro> --profile <profile> --out-dir <artifact-dir> --capture-evidence <capture-proof> --review-evidence <review-proof> --replay-evidence <profile>=<replay-proof> --connected-profile <profile> --pane-id <profile>=<pane-id> --gui-record-button --gui-stop-button --gui-cancel-button --per-event-timing-captured --confirmation-prompt --cancel-prompt-verified --conflict-checked --real-connected-session --live-terminal-pane --per-keystroke-timing-replay --json`, then `python scripts/check_moba_macro_live_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>` for MobaXterm-style live macro evidence, including GUI record/stop/cancel controls, replay confirmation/cancel review and SHA-bound real connected-terminal per-keystroke timing proof;
- `row smartcard evidence-bundle <profile> --certificate-id <cert-id> --certificate <id|label|provider|fingerprint_sha256|public_key> --out-dir <artifact-dir> --management-evidence <management-proof> --selection-evidence <selection-proof> --mobagent-evidence <mobagent-proof> --browser-evidence <browser-proof> --add-to-mobagent --gui-visible --add-remove-controls --openssh-public-key-visible --expert-setting-visible --certificate-selected --profile-saved --global-add-setting --agent-loaded-certificate --same-parameters-sftp --multiplex-mode --real-connected-session --sftp-browser-open --json`, then `python scripts/check_moba_smartcard_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>` for MobaXterm 26.4 smart-card evidence, including management UI proof, OpenSSH public-key retrieval, SSH expert certificate selection, MobAgent handoff and SHA-bound smart-card SSH-browser multiplex proof;
- `row customizer evidence-bundle --brand-name <brand> --organization <org> --lock-setting <key=value> --update-url <https-url> --update-public-key <key> --out-dir <artifact-dir> --bundle-manifest-evidence <bundle-proof> --installer-evidence <installer-proof> --policy-evidence <policy-proof> --update-evidence <update-proof> --update-manifest <manifest.json> --bundle-manifest-sha256 <sha256> --sha256s-present --windows-exe-rebranded --windows-msi-rebranded --product-name-matches-brand --logo-applied --all-policy-surfaces-passed --https-update-url --signature-verified --organization-channel --json`, then `python scripts/check_moba_professional_deployment_evidence.py --evidence <artifact-dir>/moba-professional-deployment.json --assets-dir <artifact-dir>` for MobaXterm Professional-style deployment evidence, including branded EXE/MSI proof, all policy-lock enforcement surfaces, signed update-manifest verification and local SHA-bound update artifacts;
- `python scripts/check_moba_professional_update_manifest.py --manifest <stable-update.json> --public-key <key> --channel <channel> --organization <org> --assets-dir <artifact-dir>` for MobaXterm Professional-style signed update manifests, including HTTPS artifact URL checks, payload signature verification and local artifact SHA-256 binding;
- `python scripts/check_moba_professional_deployment_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>` for MobaXterm Professional-style deployment evidence, including branded Windows EXE/MSI proof, runtime hard policy-lock enforcement across CLI/GUI/Web/profile-editor/quick-connect/launcher surfaces, signed HTTPS update-channel proof and bundle manifest/SHA-256 proof;
- `python scripts/check_security_polish.py` for production security polish around audit redaction, assignment-style secret arguments, URL-embedded passwords and support-bundle handling of sensitive option key names;
- `python scripts/check_repository_cleanup.py` for Repository cleanup before tagging checks, including ignore coverage, merge-conflict markers, private/support artifacts and unignored transient release outputs;
- `python scripts/check_gui_design_previews.py` for tracked GUI preview PNGs, contact sheet, manifest and static gallery consistency;
- `python scripts/check_gui_visual_metrics.py` for stdlib PNG sampling of static preview layout regions, brightness bands, nonblank visual complexity, product-style color anchors, structural line anchors and named-region topology contracts across all selectable presets and tracked state previews such as `mobaxterm-home.png`;
- `python scripts/check_gui_parity.py` for repository-tracked product-style GUI/UX parity criteria, multi-file and non-package evidence per requirement, user-specific sample-token rejection across GUI evidence files, 100% per-preset requirement coverage and 100% required-dimension coverage across the MobaXterm-style, SecureCRT-style, Termius-style, Remmina-style and mRemoteNG-style presets;
- `python scripts/check_real_gui_render.py` for live PyQt6 main-window rendering when the desktop extra is installed, including all-preset visible control checks, product tab/sidebar/tree/toolbar/status/interaction contracts, live layout geometry and widget topology contracts, representative product tab content, live product workspace-surface evidence, connected MobaXterm SFTP/monitoring dock evidence, nonblank screenshot-pixel metrics and a manifest that records expected versus captured preset ids, per-preset live contract summaries, measured layout/topology evidence for successful captures and top-level measured-evidence completeness/missing/incomplete/failed audit lists; with PyQt6 capture it fails on incomplete measured evidence, and without PyQt6 it verifies the GUI factory fail-closed path;
- `python scripts/check_readme_media.py` for generated README PNG/GIF media, asset hashes, dimensions and README references;
- `python scripts/check_first_run_ux.py` for installer first-run guidance, welcome-command coverage and non-confusing public example targets;
- `python scripts/check_feature_reality.py` for executable feature-manifest evidence, including CLI command paths, protocol launch-plan builders, implementation symbols and shipped PWA/Termux files;
- `python scripts/check_product_readiness.py` for coverage truth checks: 100% adapter-ready coverage, 100% release-backed product workflow parity with JSON evidence, lower platform-readiness gaps and no blanket product or feature overrides;
- `python -m pytest -q`;
- a CLI smoke test in a temporary `ROW_HOME`, including init, profile listing, example SSH dry-run, doctor JSON, and feature coverage output.

For dependency-constrained environments, run:

```bash
python scripts/verify.py --quick
```

Quick mode skips `pytest` and runs stdlib-backed compile checks, docs consistency, roadmap truth checks, CI workflow policy checks, release-truth/toolchain/matrix/platform-support/platform-promotion/platform-promotion-runbook/platform-promotion-artifact/extended-platform-evidence/XP-evidence/platform-verified-evidence/platform-evidence-record/MobaXterm-parity-evidence/mobile-support/publish-asset checks, optional dependency smoke checks, native hardening checks, native installer smoke contract checks, production security checks, repository cleanup checks, GUI preview checks, GUI visual metrics, GUI parity criteria checks, real GUI render smoke checks, README media checks, first-run UX checks, feature reality checks, coverage-truth checks and the CLI smoke test. It is useful for sandboxed review environments, but it is not a substitute for the full verifier before a release or pull request.

Regenerate README media after GUI preview changes:

```bash
python scripts/render_gui_design_previews.py
python scripts/render_readme_media.py
python scripts/check_readme_media.py
```

Before creating a release tag, run the stricter cleanup preflight:

```bash
python scripts/check_repository_cleanup.py --require-clean
```

`--require-clean` adds a `git status --porcelain` check so the tag is created
from a committed tree with no local, generated or untracked changes.

Optional linting is available when the dev extra is installed:

```bash
python -m ruff check src tests scripts
python scripts/verify.py --lint
```

`python scripts/verify.py --lint` adds the same Ruff gate to the normal
verification sequence. Keep the direct command useful for fast local lint-only
checks.
