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
| Assessed on | 2026-11-22 |
| Version | 1.0.27 |
| Assessed `main` commit | `4b1f02a67bd8877acd8c784283af7c46f3cc3535` |
| Overall engineering score | **78 / 100** |
| Strict certification gate | **Pending a signed, release-bound audit** |
| Current release for this version | [v1.0.27 unsigned preview](https://github.com/Yunushan/remote-ops-workspace/releases/tag/v1.0.27) |

Since the Nov. 17 assessment at `a1d14f1`, two dependency updates have landed
on `main`, bringing PyQt6 to 6.12.1 and PyQt6-sip to 13.13.1. All 74 hosted
checks passed on the merged commit. This preserves the prior 78/100 score.
The assessed commit predates the v1.0.28 candidate changes in PR #194.
[Changes since the previous assessment](https://github.com/Yunushan/remote-ops-workspace/compare/a1d14f1f2e5367497c750627307bc7e3bba24aa5...4b1f02a67bd8877acd8c784283af7c46f3cc3535)

## A. Engineering production-readiness score

| Area | Weight | Score | Basis |
| --- | --- | --- | --- |
| Code quality and tests | 15 | 14 | All 65 CI jobs passed on the assessed commit, including the 100% line and branch coverage gate and native Windows readiness. CodeQL and the real Ubuntu browser qualification also passed. [Main CI](https://github.com/Yunushan/remote-ops-workspace/actions/runs/44942627492) · [Coverage](https://github.com/Yunushan/remote-ops-workspace/actions/runs/44942627492/job/136962949960) · [CodeQL](https://github.com/Yunushan/remote-ops-workspace/actions/runs/44942627579) · [Browser](https://github.com/Yunushan/remote-ops-workspace/actions/runs/44942627543) |
| Runtime security | 20 | 20 | The earlier runtime integrity, input validation, FTP, and plugin fixes remain in place. X11 servers now require explicit TCP opt-in, including the Windows TCP-only backends that require it to serve X clients. [PR #183](https://github.com/Yunushan/remote-ops-workspace/pull/183) |
| Supply chain and CI | 15 | 15 | The smoke-tested Web/PWA image manifest, build provenance and CycloneDX SBOM all identify `sha256:3dd01ffc0f9454d9bec7f8caf5b32a205a8f3247ac50f6a416151975575df106`. The downloaded-installer verifier binds the bytes to the immutable release digest and provenance. Its live end-to-end check requires a certified release. [Provenance](https://github.com/Yunushan/remote-ops-workspace/attestations/70601031) · [SBOM](https://github.com/Yunushan/remote-ops-workspace/attestations/70601035) · [Verification](https://github.com/Yunushan/remote-ops-workspace/actions/runs/44942627492/job/136963125109) · [Release promotion runbook](runbooks/RELEASE_PROMOTION.md) |
| Release and distribution | 15 | 5 | Seven modern native candidate builds passed. The latest preview for this version has 48 assets. Production signing and independent, exact-artifact redistribution approval are open. [Native matrix](https://github.com/Yunushan/remote-ops-workspace/actions/runs/43055313245) · [Preview release](https://github.com/Yunushan/remote-ops-workspace/releases/tag/v1.0.27) · [Compliance policy](../configs/release_compliance_policy.json) |
| Platform and parity evidence | 10 | 3 | The protected platform registry has 0/4 accepted targets. The strict MobaXterm registry has 0/8 accepted articles. [Platform registry](../configs/platform_verified_evidence.json) · [Parity registry](../configs/mobaxterm_parity_evidence.json) |
| Operability and observability | 10 | 9 | Windows x64 and Linux x64 native recovery drills passed in the earlier native matrix. On the assessed commit, the Windows NTFS job exercised authenticated staging, interrupted recovery, and tamper rejection under a separate unprivileged identity. Automatic updater installation and rollback remain open on the assessed version. [Windows recovery](https://github.com/Yunushan/remote-ops-workspace/actions/runs/43055313245/job/130646688694) · [Linux recovery](https://github.com/Yunushan/remote-ops-workspace/actions/runs/43055313245/job/130646688872) · [NTFS job](https://github.com/Yunushan/remote-ops-workspace/actions/runs/44942627490/job/136962949762) |
| Maintainability | 10 | 7 | Workflow and transfer dialogs and the packaged QSS were extracted previously. Quick Connect parsing and shared Qt menus now have dedicated modules. Several large GUI and CLI modules remain. [PR #159](https://github.com/Yunushan/remote-ops-workspace/pull/159) · [PR #183](https://github.com/Yunushan/remote-ops-workspace/pull/183) · [PR #187](https://github.com/Yunushan/remote-ops-workspace/pull/187) |
| Docs and governance | 5 | 5 | Retains the previously verified engineering controls. Public GitHub metadata confirms that `main` is protected and the `v*` ruleset is active with update and deletion restrictions. Release certification still requires the authenticated exact-tag audit and an independent auditor signature. [Tag ruleset](https://github.com/Yunushan/remote-ops-workspace/rules/24350907) |
| **Total** | **100** | **78** | |

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
| Production maturity | Production/Stable metadata passes for v1.0.27. A certified release must bind the next exact tag and SHA. | internal |
| Quality and product workflows | Exact-main CI passed for the assessed commit. Repeat the release audit at the tagged SHA. | internal |
| Default release artifacts | Native candidates and an unsigned preview are available. | depends on signing and promotion |
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
5. Continue GUI decomposition (M3) and qualify installation and rollback for the managed updater.
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
