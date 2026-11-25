# Production Readiness Scorecard

This scorecard is the maintained, numeric assessment of how close the project is
to a production release. It complements the pass/fail gate in
[`docs/PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md) with a weighted score so
progress can be tracked over time. The itemized work to close each gap lives in
[`docs/PRODUCTION_READINESS_BACKLOG.md`](PRODUCTION_READINESS_BACKLOG.md).

Two independent numbers are reported:

- **A. Engineering production-readiness score (0-100)** — a weighted quality
  measure of the source, security, CI, and release engineering as they exist
  today.
- **B. Strict certification gate (`make production-readiness`)** — the project's
  own evidence gate, which is pass/fail per gate and is only ever `100/100` when
  every external prerequisite is proven. It is **not** a percentage.

The two must not be conflated: a high engineering score never closes a
certification gate, and no gate may be relaxed, fabricated, or inferred from a
green build.

## Assessment record

| Field | Value |
| --- | --- |
| Assessed on | 2026-11-25 |
| Version | 1.0.28 candidate |
| Assessed `main` commit | [`b4f730793ff58b6f4eccff147e35cd833ff1aa39`](https://github.com/Yunushan/remote-ops-workspace/commit/b4f730793ff58b6f4eccff147e35cd833ff1aa39) |
| Overall engineering score | **82 / 100** |
| Strict certification gate | **Pending a signed, release-bound audit** |
| Release status | v1.0.28 is untagged. The previous version has an [unsigned preview](https://github.com/Yunushan/remote-ops-workspace/releases/tag/v1.0.27). |

PR #194 completed the GUI and CLI refactor tracked as M3. The three-point
increase on November 23 reflected the merged code, complete branch coverage
and native GUI interaction tests. The release CI verifier accepted attempt 2
of the push workflow on the assessed commit.
[Merged changes](https://github.com/Yunushan/remote-ops-workspace/pull/194) · [Accepted main CI attempt](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45170610904/attempts/2)

The November 25 retry closed the remaining code-quality point on the same
commit. Windows x64 and Linux x64 passed with Riverbank's PyQt6 preview
`6.12.2.dev2611241405`. Intel macOS had passed with preview
`6.12.2.dev2611151023`. All three jobs used Qt `6.12.0` and passed rendering
and interaction checks for all GUI presets.
[Forward compatibility attempt 2](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45178873700/attempts/2)

## A. Engineering production-readiness score

| Area | Weight | Score | Basis |
| --- | --- | --- | --- |
| Code quality and tests | 15 | 15 | Main CI, CodeQL and the Ubuntu browser qualification passed. The coverage job passed 8,946 tests with 100% statement and branch coverage. The scheduled forward-compatibility workflow passed with PyQt6 bindings newer than the release pin on Windows x64, Linux x64 and Intel macOS. [Coverage](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45170610904/job/137702174949) · [CodeQL](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45170611005) · [Browser](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45170610989) · [Forward compatibility](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45178873700/attempts/2) |
| Runtime security | 20 | 20 | The earlier runtime integrity, input validation, FTP, and plugin fixes remain in place. X11 servers now require explicit TCP opt-in, including the Windows TCP-only backends that require it to serve X clients. [PR #183](https://github.com/Yunushan/remote-ops-workspace/pull/183) |
| Supply chain and CI | 15 | 15 | Main CI verified build provenance and a CycloneDX SBOM for the smoke-tested Web/PWA image `sha256:2c192195e126257d618ea3c92220c61f4e335822343b41a3336cb772d17002df`. Live end-to-end verification of a published installer requires the first certified release. [Provenance](https://github.com/Yunushan/remote-ops-workspace/attestations/71079485) · [SBOM](https://github.com/Yunushan/remote-ops-workspace/attestations/71079494) · [Verification](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45170610904/job/137681726182) |
| Release and distribution | 15 | 5 | Seven native v1.0.28 candidates passed on the assessed commit across Windows x64, x86 and ARM64, Linux x64 and ARM64, and macOS Intel and Apple silicon. Production signing and independent redistribution approval for the exact artifacts remain open. [Merged-commit native matrix](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45180801759) · [Compliance policy](../configs/release_compliance_policy.json) |
| Platform and parity evidence | 10 | 3 | The protected platform registry has 0/4 accepted targets. The strict MobaXterm registry has 0/8 accepted articles. [Platform registry](../configs/platform_verified_evidence.json) · [Parity registry](../configs/mobaxterm_parity_evidence.json) |
| Operability and observability | 10 | 9 | The Windows NTFS job verified authenticated staging and interrupted recovery. Debian upgrade and recovery passed on x64 and ARM64, as did RPM upgrade and rollback on x64. Cross-version Windows installer recovery still requires two genuinely signed MSI packages. [NTFS qualification](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45170611006/job/137678852885) · [Linux x64](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45180801759/job/137713870303) · [Linux ARM64](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45180801759/job/137713870235) · [Signed MSI qualification](../.github/workflows/windows-msi-upgrade-qualification.yml) |
| Maintainability | 10 | 10 | Qt actions, session lifecycle, preset layouts and CLI commands now live in dedicated modules. Six desktop presets use a packaged stylesheet and settings. From the previous assessment, `gui.py` fell from 13,033 to 1,143 lines and `cli.py` from 3,472 to 1,725. Full coverage and native Windows rendering and interaction tests passed through the desktop entry point. [Merged refactor](https://github.com/Yunushan/remote-ops-workspace/pull/194) · [Native GUI interactions](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45170610904/job/137702106015) · [Coverage](https://github.com/Yunushan/remote-ops-workspace/actions/runs/45170610904/job/137702174949) |
| Docs and governance | 5 | 5 | Retains the previously verified engineering controls. Public GitHub metadata confirms that `main` is protected and the `v*` ruleset is active with update and deletion restrictions. Release certification still requires the authenticated exact-tag audit and an independent auditor signature. [Tag ruleset](https://github.com/Yunushan/remote-ops-workspace/rules/24350907) |
| **Total** | **100** | **82** | |

The assessed commit supports source use and unsigned-preview distribution.
A certified release requires the evidence below.

### Score bands

| Band | Meaning |
| --- | --- |
| 0-49 | Prototype. Do not distribute. |
| 50-69 | Preview-quality source. Usable by developers with caveats. |
| 70-84 | Production-capable source and release engineering, pending external certification. |
| 85-94 | Production-ready engineering with minor residual items. |
| 95-100 | Fully certified: signed, independently approved, evidence-complete release. |

## B. Strict certification gate (`make production-readiness`)

| Gate | State | Blocker type |
| --- | --- | --- |
| Production maturity | Production/Stable metadata passes for v1.0.28. Certification still requires an exact tag and SHA. | internal |
| Quality and product workflows | Exact-main CI passed for the assessed commit. Repeat the release audit at the tagged SHA. | internal |
| Default release artifacts | v1.0.28 has native candidate builds. | depends on signing and promotion |
| Certified-inventory provenance | Requires the immutable release and its successful production-promotion attempt. | depends on promotion |
| Third-party redistribution and realized runtime | blocked | external: independent approver + Ed25519 key |
| Production signing | blocked | external: Windows and macOS certificates |
| Protected platform parity 4/4 | 0/4 | external: real i386, armhf, XP x86, XP x64 hosts |
| Strict MobaXterm depth 8/8 | 0/8 | internal evidence work + independent review |
| Repository governance | Protected branch and active tag ruleset confirmed. The authenticated release-bound audit and trusted auditor key remain open. | repository access and independent auditor |

The authoritative gate definition and command are in
[`docs/PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md) and the
`production-readiness` target in [`Makefile`](../Makefile).

## Completion path

The ordered, ID-tagged backlog is in
[`docs/PRODUCTION_READINESS_BACKLOG.md`](PRODUCTION_READINESS_BACKLOG.md). The
current path:

1. Docs and hygiene backlog items (H1-H4) -> done
2. Security fixes S1-S5 with tests -> done
3. Typing config and structured logging (M1, M2) -> done
4. Runbooks, installer verification and container SBOM (O1-O3) -> done
5. GUI and CLI decomposition (M3) is complete. Qualify cross-version Windows installation and rollback when signed MSI artifacts are available.
6. Prepare Windows and macOS signing (E1), independent compliance approval (E2), and independent tag-governance attestation (G2).
7. Qualify the four protected hosts and obtain independent review for the eight MobaXterm articles (P1-P2).
8. Certify and audit the exact tagged release (G1, G3).

Certification requires the signing, review, host, and release evidence in
steps 6-8. See the backlog for the owner's production scope decision (D1).

## Progress log

| Date | Change | Score | Gate |
| --- | --- | --- | --- |
| 2026-10-17 | Baseline assessment; created scorecard and backlog | 64 | 0/9 |
| 2026-10-17 | Phase 1 docs/hygiene (H1-H4): `.gitignore` churn patterns, `CHANGELOG.md`, expanded `docs/ARCHITECTURE.md` | 64 (unchanged; documentation and hygiene only) | 0/9 |
| 2026-10-17 | Phase 2 security: S2 (XML import size cap + DOCTYPE/ENTITY rejection) and S4 (minimum FTP password length), both with tests; full suite re-run at 100% line/branch coverage | 64 (unchanged; two low/medium hardening items, not a scored area shift) | 0/9 |
| 2026-10-17 | Phase 2 security: S1 (packaged server/X-server runtime hash verified at launch), S5 (opt-in plugin loading with `ROW_ENABLE_PLUGINS`/`ROW_PLUGIN_ALLOWLIST`), S3 documented (Windows TCP listener is a disclosed backend limitation); Phase 4 O1/O3 runbooks added. Full suite 6818 passed, 98 skipped, 100% line/branch coverage | 67 | 0/9 |
| 2026-10-17 | M1: installed `mypy` 2.3.1, confirmed the whole `src` tree is mypy-clean on linux/win32/darwin, lowered `GUI_ERROR_BASELINE` 382 -> 0, added an advisory `[tool.mypy]` config, and fixed the real `paths.py:54` error the stricter default python version exposed | 69 | 0/9 |
| 2026-10-17 | M2: added `logging_setup.py` (stdlib logging with a redacting formatter), wired `--log-level`/`ROW_LOG_LEVEL` into `cli.main`, and a redacted public-bind warning in `web_server`; new module pinned in the catalogue inventory. Full suite 6821 passed, 98 skipped, 100% line/branch coverage | **70** | 0/9 |
| 2026-11-14 | Published image provenance and SBOM, installer verification, native recovery, GUI extraction, and live governance advanced the assessment on `cedf1e0`. | **75** | Pending release-bound audit |
| 2026-11-17 | Windows X11 TCP opt-in, NTFS private-staging qualification, and shared Qt menu and Quick Connect extraction verified on `a1d14f1`. | **78** | Pending release-bound audit |
| 2026-11-22 | The merged Qt dependency updates passed all 74 hosted checks on `4b1f02a`, including GUI interaction, coverage and image attestation. | **78** | Pending release-bound audit |
| 2026-11-23 | Merged the GUI and CLI decomposition on `b4f7307`. Native GUI interaction and full statement and branch coverage passed on main. | **81** | Pending release-bound audit |
| 2026-11-25 | Hosted forward-compatibility checks passed with newer PyQt6 bindings on Windows x64, Linux x64 and Intel macOS on `b4f7307`. | **82** | Pending release-bound audit |

## How to re-score

After each backlog step, or when asked for a fresh assessment:

```bash
python scripts/verify.py --quick --lint
python scripts/check_non_gui_types.py
python scripts/check_docs.py
python scripts/check_release_maturity.py --release-tag <tag>
python scripts/check_platform_verified_evidence.py --registry configs/platform_verified_evidence.json --require-goal-targets --require-review-bundles --release-tag <tag>
python scripts/check_mobaxterm_parity_evidence.py --require-complete
```

Then:

1. Recompute each area score against the rubric above using the new evidence.
2. Update the assessment record (date, HEAD, scores) and the gate table.
3. Move completed items in the backlog to `[x]` with the PR or commit reference.
4. Never edit `configs/platform_verified_evidence.json`,
   `configs/mobaxterm_parity_evidence.json`, or
   `configs/release_compliance_policy.json` to move a score. Only real,
   independently produced evidence counts.
