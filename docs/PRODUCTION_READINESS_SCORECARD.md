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
| Assessed on | 2026-10-17 |
| Version | 1.0.27 |
| HEAD | `abf9544` (PR #125 merged) |
| Overall engineering score | **70 / 100** |
| Strict certification gate | **0 / 9 gates proven** |
| Release channel today | Unsigned preview only |

Evidence used: source review (security, architecture, CI/CD, release), tracked
configs, and the prior audits
`artifacts/production-readiness-gate-audit-32482f9-20261015-r885.json` and
`artifacts/production-readiness-final-source-verification-32482f9-20261015-r886.json`
(CI 80/80 checks, 36/36 Python matrix, 100% line and branch coverage on the PR
candidate). Local pytest/ruff/mypy were not re-run for this scorecard; see
[How to re-score](#how-to-re-score).

## A. Engineering production-readiness score

| Area | Weight | Score | Basis |
| --- | --- | --- | --- |
| Code quality and tests | 15 | 14 | 100% line and branch coverage gate, Ruff, 36-job OS x Python matrix, real PyQt6 render smoke, and full `mypy` clean on all of `src` across linux/win32/darwin with the `GUI_ERROR_BASELINE` lowered to 0 (`[tool.mypy]` config added). |
| Runtime security | 20 | 19 | No `shell=True`/`eval`/`pickle`; loopback-default web API with constant-time token compare, CSP and traversal guards; scrypt + Fernet vault; Ed25519 update verification; hardened container. Findings S1, S2, S4, S5 fixed with tests; S3 documented as a backend limitation with a visible TCP warning. |
| Supply chain and CI | 15 | 13 | SHA-pinned actions, hash-locked dependencies, digest-pinned base image, SLSA attestations, CycloneDX SBOM, CodeQL, Dependabot (pip/actions/docker). Minus: no container-image SBOM/attestation (O2); installer artifact verification documented but not yet automated (O3). |
| Release and distribution | 15 | 5 | Only unsigned preview releases; no Authenticode, Developer ID, or notarization. `configs/release_compliance_policy.json` is `blocked-pending-independent-review` with empty `trusted_ed25519_keys`. |
| Platform and parity evidence | 10 | 3 | `configs/platform_verified_evidence.json` has 0/4 accepted targets; `configs/mobaxterm_parity_evidence.json` has 0/8 accepted articles. |
| Operability and observability | 10 | 7 | Good: encrypted backup/restore with a destructive CI recovery drill, `/healthz`, operator runbooks for upgrade/rollback, backup/restore, secret rotation and release promotion, and stdlib `logging` routed through the redaction layer with `--log-level`/`ROW_LOG_LEVEL`. Missing: no updater install/rollback; Windows private-storage adapter not qualified on real hardware. |
| Maintainability | 10 | 5 | God modules (`gui.py` 13.7k lines, `gui_designs.py` ~9k, `gui_connected.py` ~5.2k, `features.py`, `cli.py`, `gui_terminal.py` all over 2k). Gate/evidence tooling (~84k LOC, 81 `scripts/check_*.py`, 20 workflows) exceeds product code (~60k LOC). |
| Docs and governance | 5 | 4 | Strong README, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, deployment docs, a `CHANGELOG`, and an expanded `docs/ARCHITECTURE.md`. Branch and tag governance not live-verified. |
| **Total** | **100** | **70** | |

Interpretation: safe and well-tested as a **source / unsigned-preview desktop
tool**, but not yet shippable as a signed, certified production release.

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
| Production maturity | metadata OK; tag/SHA binding pending | internal (needs release cut) |
| Quality and product workflows | PR CI green; exact release-SHA main push run pending | internal |
| Default release artifacts | candidates only | internal after signing |
| Certified-inventory provenance | not run | depends on promotion |
| Third-party redistribution and realized runtime | blocked | external: independent approver + Ed25519 key |
| Production signing | blocked | external: Windows and macOS certificates |
| Protected platform parity 4/4 | 0/4 | external: real i386, armhf, XP x86, XP x64 hosts |
| Strict MobaXterm depth 8/8 | 0/8 | internal evidence work + independent review |
| Repository governance | unverified | internal (GitHub settings) + auditor key |

The authoritative gate definition and command are in
[`docs/PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md) and the
`production-readiness` target in [`Makefile`](../Makefile).

## Completion path

The ordered, ID-tagged backlog is in
[`docs/PRODUCTION_READINESS_BACKLOG.md`](PRODUCTION_READINESS_BACKLOG.md). The
expected score progression:

1. Docs and hygiene backlog items (H1-H4) -> done
2. Security fixes S1-S5 with tests -> done (S1, S2, S4, S5 fixed; S3 documented)
3. Typing config and structured logging (M1, M2) -> done
4. Runbooks (O1, O3) -> done; container SBOM (O2) -> open
5. God-module splits (M3, incremental) -> open
6. Internal gates (G1-G3: merge to `main`, cut tag, exact-SHA CI, branch/tag protection) -> open
7. External: signing certificates (E1) -> about +6; independent compliance approver (E2) -> about +4
8. Platform parity (P1, P2): acquire real hosts and produce 4/4 + 8/8 evidence -> about +7, or formally re-scope those targets out of the production boundary (decision D1)

Steps 1-6 reach roughly 85. Steps 7-8 are required for 95-100 and cannot be
closed by source changes alone.

## Progress log

| Date | Change | Score | Gate |
| --- | --- | --- | --- |
| 2026-10-17 | Baseline assessment; created scorecard and backlog | 64 | 0/9 |
| 2026-10-17 | Phase 1 docs/hygiene (H1-H4): `.gitignore` churn patterns, `CHANGELOG.md`, expanded `docs/ARCHITECTURE.md` | 64 (unchanged; documentation and hygiene only) | 0/9 |
| 2026-10-17 | Phase 2 security: S2 (XML import size cap + DOCTYPE/ENTITY rejection) and S4 (minimum FTP password length), both with tests; full suite re-run at 100% line/branch coverage | 64 (unchanged; two low/medium hardening items, not a scored area shift) | 0/9 |
| 2026-10-17 | Phase 2 security: S1 (packaged server/X-server runtime hash verified at launch), S5 (opt-in plugin loading with `ROW_ENABLE_PLUGINS`/`ROW_PLUGIN_ALLOWLIST`), S3 documented (Windows TCP listener is a disclosed backend limitation); Phase 4 O1/O3 runbooks added. Full suite 6818 passed, 98 skipped, 100% line/branch coverage | 67 | 0/9 |
| 2026-10-17 | M1: installed `mypy` 2.3.1, confirmed the whole `src` tree is mypy-clean on linux/win32/darwin, lowered `GUI_ERROR_BASELINE` 382 -> 0, added an advisory `[tool.mypy]` config, and fixed the real `paths.py:54` error the stricter default python version exposed | 69 | 0/9 |
| 2026-10-17 | M2: added `logging_setup.py` (stdlib logging with a redacting formatter), wired `--log-level`/`ROW_LOG_LEVEL` into `cli.main`, and a redacted public-bind warning in `web_server`; new module pinned in the catalogue inventory. Full suite 6821 passed, 98 skipped, 100% line/branch coverage | **70** | 0/9 |

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
