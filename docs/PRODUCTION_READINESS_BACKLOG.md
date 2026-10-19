# Production Readiness Backlog

Actionable checklist to close the gaps in
[`docs/PRODUCTION_READINESS_SCORECARD.md`](PRODUCTION_READINESS_SCORECARD.md).
Work top to bottom; each item lists what to change, how it is accepted, and how
it is validated. Update the scorecard when an item lands.

Rules:

- Do not relax, skip, or fabricate an evidence gate. Only real, independently
  produced evidence counts.
- Do not add new dependencies without explicit approval (decision D2).
- Do not edit `configs/platform_verified_evidence.json`,
  `configs/mobaxterm_parity_evidence.json`, or
  `configs/release_compliance_policy.json` to manufacture a pass (decision D3).
- Keep 100% line and branch coverage; every source change ships with tests.
- Any edit under `src/remote_ops_workspace/` changes bytes pinned in
  `tests/catalogue-browser/product-source-inventory.json`. Refresh that file's
  `size` and `sha256` (of the LF-normalized bytes) or
  `tests/test_catalogue_source_manifest.py` fails. `source-inputs.json` only
  pins a subset of modules.

## Phase 1 - Docs and hygiene (about +3)

- [x] **H1** Add `.gitignore` entries for local churn: `.test-temp-*/`,
  `artifacts/production-readiness-*`, `artifacts/pytest-*/`,
  `artifacts/*.zip`, `artifacts/workspace-recovery-local.json`,
  `artifacts/pr*-*.md`, `artifacts/Android-*.zip`. Accept: `git status --short`
  shows no untracked artifacts after cleanup. Ask the user before deleting any
  existing local file. Validate: `git status --short`.
- [x] **H2** Add `CHANGELOG.md` (Keep a Changelog format) seeded from
  `docs/RELEASE_NOTES_v1.0.27.md`. Accept: linked from `README.md`. Validate:
  `python scripts/check_docs.py`.
- [x] **H3** Expand `docs/ARCHITECTURE.md` to cover the `moba_*`, `gui_*`
  subsystems and the verification/evidence scripts. Accept: each top-level
  module group is named with its responsibility. Validate:
  `python scripts/check_docs.py`.
- [x] **H4** This scorecard and backlog are registered from
  `docs/PRODUCTION_READINESS.md` and the `README.md` docs list. Validate:
  `python scripts/check_docs.py` and `python -m pytest tests/test_docs_consistency.py -q`.

## Phase 2 - Security fixes with tests (about +3)

- [x] **S1 (Medium)** Verify packaged server/X-server runtime hash at launch.
  `moba_servers.py:993-1023` and `x11.py:481-541` launch runtimes without
  re-checking the manifest `sha256` recorded at `moba_servers.py:582` /
  `x11.py:508`. Accept: launch refuses on hash mismatch. Validate:
  `python -m pytest tests/test_moba_servers.py tests/test_moba_xserver.py tests/test_x11_edges.py -q`.
  Implemented as `verify_packaged_runtime_integrity` (moba_servers) and
  `verify_packaged_x_server_runtime_integrity` (x11), called from
  `start_moba_server` / `start_moba_x_server` after the availability check.
  Packaged (bundled) runtimes are refused when the manifest is missing,
  malformed, unreadable, has no recorded `sha256`, records a different
  executable, or the bytes no longer match. Placeholder bundles carry a hash and
  still verify.
- [x] **S2 (Low-Med)** Harden untrusted XML import. `profile_importers.py:165`
  parses mRemoteNG XML via `xml.etree` with no size cap (`_read_text` at :686).
  Add a byte cap before parse and reject `DOCTYPE`/`ENTITY` declarations without
  a new dependency. Accept: oversized or entity-bearing XML is rejected with a
  clear error. Validate: `python -m pytest tests/test_profile_importers.py tests/test_profile_importers_edges.py -q`.
- [x] **S3 (Low-Med)** Restrict X server TCP listener. `x11.py:1239` always
  emits `-listen tcp` on Windows. Prefer loopback binding where the backend
  supports it, or require explicit opt-in with a visible warning. Validate:
  `python -m pytest tests/test_x11_edges.py tests/test_x11_client_display.py -q`.
  Resolved as a documented backend limitation. Off Windows the default is
  already `-nolisten tcp`; TCP requires the explicit `allow_tcp` opt-in. Windows
  X clients require TCP (VcXsrv/Xming expose no loopback-only `-listen` mode),
  so the listener stays on and `build_moba_x_server_plan` emits a visible note
  that the runtime may listen on all interfaces and that the host firewall must
  restrict the port. TCP is additionally gated by the managed MIT-MAGIC-COOKIE-1
  `-auth` file. A true loopback-only listener would require a backend that
  supports it.
- [x] **S4 (Low)** Strengthen embedded FTP controls. `embedded_ftp.py:18-20`
  accepts any non-empty credentials; enforce a minimum length/entropy and
  consider dropping `M`/`T` permissions by default under `ROW_FTP_WRITE=1`.
  Validate: `python -m pytest tests/test_embedded_ftp.py tests/test_embedded_server_security.py -q`.
- [x] **S5 (Low)** Make plugin loading opt-in. `plugins.py:92-141` loads any
  entry-point plugin on every launch. Add an allowlist setting and document the
  trust boundary. Validate: `python -m pytest tests/test_plugins.py -q`.
  Implemented: third-party plugins now load only when explicitly enabled by
  `ROW_ENABLE_PLUGINS` (truthy value) or when a caller passes an explicit
  `entry_points_provider`; `ROW_PLUGIN_ALLOWLIST` optionally restricts loading to
  named entry points. When disabled the registry reports a `plugins-disabled`
  failure instead of loading code. Tests that exercise loading opt in explicitly.

## Phase 3 - Typing and observability (about +5)

- [x] **M1** Add a `[tool.mypy]` config to `pyproject.toml` and reduce
  `GUI_ERROR_BASELINE` (`scripts/check_non_gui_types.py`, previously 382) to 0.
  Validate: `python scripts/check_non_gui_types.py` and the mypy jobs in `ci.yml`.
  Verified with `mypy` 2.3.1 installed: the whole `src` tree reports zero errors
  on linux/win32/darwin, so the baseline is now `0` and the gate fails on any
  new error in a non-GUI module or in `gui.py`. Added an advisory `[tool.mypy]`
  section (no `strict`) with `python_version`, `files = ["src"]`, `warn_unused_configs`,
  `show_error_codes`, `pretty = false`, `incremental = false`. Fixed a real error
  the stricter default Python version exposed: `paths.py:54` now chains
  `.joinpath("configs").joinpath(name)` instead of a multi-argument call.
- [x] **M2** Introduce stdlib `logging` for runtime diagnostics (keep CLI user
  output on stdout), routed through `redaction.py`; add `--log-level`. Accept:
  no secrets logged; existing tests pass. Validate:
  `python -m pytest tests/test_logging_setup.py -q`.
  Implemented in `logging_setup.py`: `configure_logging` installs a single
  `StreamHandler` on the `remote_ops_workspace` logger with a
  `RedactingFormatter` that passes every record through `redaction.redact_text`,
  resolves the level from `--log-level` or `ROW_LOG_LEVEL` (default `WARNING`),
  sets `propagate = False`, and replaces prior handlers. `cli.main` configures
  logging at startup and returns exit code 2 for an invalid `ROW_LOG_LEVEL`.
  `web_server.validate_web_bind` emits a redacted warning on an accepted public
  bind. There is no support-bundle command in the repository, so that part of the
  item is not applicable.

## Phase 4 - Operability (about +4)

- [x] **O1** Add runbooks under `docs/runbooks/`: upgrade/rollback,
  vault/backup restore, incident/secret rotation, and release-promotion operator
  steps. Validate: `python scripts/check_docs.py`.
  Added `UPGRADE_AND_ROLLBACK.md`, `WORKSPACE_BACKUP_AND_RESTORE.md`,
  `SECRET_ROTATION_AND_INCIDENT.md` and `RELEASE_PROMOTION.md`.
- [ ] **O2** Generate a container-image SBOM and attestation for
  `docker/Dockerfile.web` in CI. Accept: image is covered by SBOM + attestation
  as source/Python assets already are. Validate: `python -m pytest tests/test_container_base_images.py -q` and CI.
- [x] **O3** Document installer trust. `installers/install.sh` and
  `installers/install.ps1` are source installers with no integrity checks. For
  binary downloads, document and automate SHA-256 plus
  `gh attestation verify`. Validate: `python scripts/check_docs.py`.
  Documented in `docs/runbooks/RELEASE_PROMOTION.md` (installer trust boundary +
  checksum/attestation verification steps). Automating verification inside the
  installers remains a follow-up.

## Phase 5 - Maintainability (about +3)

- [ ] **M3** Split god modules incrementally, starting with `gui.py` (dialogs,
  actions, menus) and moving `gui_designs.py` style data to packaged QSS/JSON
  assets. Behaviour-preserving; coverage stays 100%. Validate:
  `python -m pytest --cov --cov-branch --cov-fail-under=100` and
  `python scripts/check_gui_interactions.py --require-pyqt6`.

## Phase 6 - Internal certification gates (about +3)

- [ ] **G1** Merge the release commit to `main`, cut the exact version tag, and
  confirm the exact-SHA `ci` push run is successful.
  Validate: `python scripts/check_python315_ci_evidence.py --repository <owner/repo> --branch main --sha <release-sha>`.
- [ ] **G2** Enable branch protection (required checks, conversation
  resolution, linear history, no force-push/deletion) and an active tag ruleset
  with no bypass actors; enroll the governance auditor key.
  Validate: `python scripts/check_repository_governance.py --repository <owner/repo> --branch main --sha <release-sha> --release-tag <tag>`.
- [ ] **G3** Run the strict aggregate gate; it must print
  `production readiness: 100/100 gates passed` before certification.
  Validate: `make production-readiness ...` (see
  [`docs/PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md)).

## External prerequisites (cannot be closed by source changes)

- [ ] **E1 (Production signing, about +6)** Obtain Windows Authenticode and
  macOS Developer ID/notarization credentials and produce release-bound native
  proofs. Configure protected `release` environment secrets (never commit them).
- [ ] **E2 (Independent compliance approval, about +4)** Enroll a real Ed25519
  public key from an independent compliance authority in
  `configs/release_compliance_policy.json` and sign the exact approval JSON over
  the closed-world runtime/license/consumed-lock evidence bundle.

## Platform parity (about +7, or re-scope via D1)

- [ ] **P1** Bring real hosts online: i386 Linux (`self-hosted,linux,i386`),
  armhf Linux (`self-hosted,linux,armhf`), and Windows XP SP3 x86 plus XP x64
  collectors (`self-hosted,xp-evidence`). Validate:
  `python scripts/check_platform_evidence_runner_readiness.py --repository <owner/repo> --require-goal-targets --require-idle`.
- [ ] **P2** Produce accepted release-bound records for the four protected
  targets (4/4) and the eight strict MobaXterm articles (8/8) per
  `configs/platform_parity_promotion.json` and
  [`docs/PLATFORM_PROMOTION_RUNBOOK.md`](PLATFORM_PROMOTION_RUNBOOK.md).
  Validate: `python scripts/check_platform_verified_evidence.py ... --require-goal-targets --require-review-bundles --release-tag <tag>` and `python scripts/check_mobaxterm_parity_evidence.py --require-complete`.

## Decisions

- [ ] **D1 (owner: user, open)** Decide whether legacy targets (Linux
  i386/armhf, Windows XP x86/x64) and strict MobaXterm 8/8 stay inside the
  production gate or are re-scoped to "community/legacy, unsupported in
  production". Recommendation: re-scope the legacy targets and keep MobaXterm
  depth as a roadmap item. Re-scoping must update
  `configs/platform_parity_promotion.json`, `docs/PLATFORM_SUPPORT.md`, the
  `production-readiness` target in `Makefile`, and their check scripts and tests
  together, so the gate stays honest.
- [x] **D2** No new dependency without explicit approval.
- [x] **D3** Never edit accepted evidence registries or the compliance policy to
  manufacture a pass.

## Validation summary

- Docs: `python scripts/check_docs.py`,
  `python -m pytest tests/test_docs_consistency.py tests/test_roadmap_truth.py tests/test_release_truth.py -q`.
- Code: `python scripts/verify.py --quick --lint`,
  `python -m pytest --cov --cov-branch --cov-fail-under=100`,
  `python scripts/check_non_gui_types.py`.
- Re-score after each landed item and update
  [`docs/PRODUCTION_READINESS_SCORECARD.md`](PRODUCTION_READINESS_SCORECARD.md).
