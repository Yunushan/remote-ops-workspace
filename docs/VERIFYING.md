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
- `python scripts/check_release_truth.py` for repository identity, release workflow matrix and documented artifact truth;
- `python scripts/check_release_toolchain.py` for pinned release constraints, workflow install commands and release toolchain metadata;
- `python scripts/check_optional_dependencies.py` for optional extra declarations, fail-closed missing dependency paths and real PyQt6/vault smoke checks when those extras are installed;
- `python scripts/check_native_release_hardening.py` for native checksum sidecars, native manifest integrity, appimagetool verification hooks and native workflow boundaries;
- `python scripts/check_gui_design_previews.py` for tracked GUI preview PNGs, contact sheet, manifest and static gallery consistency;
- `python scripts/check_first_run_ux.py` for installer first-run guidance, welcome-command coverage and non-confusing public example targets;
- `python scripts/check_feature_reality.py` for executable feature-manifest evidence, including CLI command paths, protocol launch-plan builders, implementation symbols and shipped PWA/Termux files;
- `python -m pytest -q`;
- a CLI smoke test in a temporary `ROW_HOME`, including init, profile listing, example SSH dry-run, doctor JSON, and feature coverage output.

For dependency-constrained environments, run:

```bash
python scripts/verify.py --quick
```

Quick mode skips `pytest` and runs stdlib-backed compile checks, docs consistency, release-truth/toolchain checks, optional dependency smoke checks, native hardening checks, GUI preview checks, first-run UX checks, feature reality checks and the CLI smoke test. It is useful for sandboxed review environments, but it is not a substitute for the full verifier before a release or pull request.

Optional linting is available when the dev extra is installed:

```bash
python scripts/verify.py --lint
```
