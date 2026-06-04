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
- `python scripts/check_release_matrix.py` for the machine-readable `configs/release_matrix.json` policy, default GitHub release jobs, script-supported native targets and platform-target release channels;
- `python scripts/check_optional_dependencies.py` for optional extra declarations, fail-closed missing dependency paths and real PyQt6/vault smoke checks when those extras are installed;
- `python scripts/check_native_release_hardening.py` for native checksum sidecars, native manifest integrity, appimagetool verification hooks and native workflow boundaries;
- `python scripts/check_security_polish.py` for production security polish around audit redaction, assignment-style secret arguments, URL-embedded passwords and support-bundle handling of sensitive option key names;
- `python scripts/check_repository_cleanup.py` for Repository cleanup before tagging checks, including ignore coverage, merge-conflict markers, private/support artifacts and unignored transient release outputs;
- `python scripts/check_gui_design_previews.py` for tracked GUI preview PNGs, contact sheet, manifest and static gallery consistency;
- `python scripts/check_readme_media.py` for generated README PNG/GIF media, asset hashes, dimensions and README references;
- `python scripts/check_first_run_ux.py` for installer first-run guidance, welcome-command coverage and non-confusing public example targets;
- `python scripts/check_feature_reality.py` for executable feature-manifest evidence, including CLI command paths, protocol launch-plan builders, implementation symbols and shipped PWA/Termux files;
- `python scripts/check_product_readiness.py` for coverage truth checks: 100% adapter-ready coverage, 100% production-parity coverage, lower platform-readiness gaps and no blanket product or feature overrides;
- `python -m pytest -q`;
- a CLI smoke test in a temporary `ROW_HOME`, including init, profile listing, example SSH dry-run, doctor JSON, and feature coverage output.

For dependency-constrained environments, run:

```bash
python scripts/verify.py --quick
```

Quick mode skips `pytest` and runs stdlib-backed compile checks, docs consistency, release-truth/toolchain/matrix checks, optional dependency smoke checks, native hardening checks, production security checks, repository cleanup checks, GUI preview checks, README media checks, first-run UX checks, feature reality checks, coverage-truth checks and the CLI smoke test. It is useful for sandboxed review environments, but it is not a substitute for the full verifier before a release or pull request.

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
python scripts/verify.py --lint
```
