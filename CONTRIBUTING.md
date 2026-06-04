# Contributing

Thanks for helping improve Remote Ops Workspace.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[desktop,security,dev]"
python scripts/verify.py
```

Use `python scripts/verify.py --quick` only when dev dependencies such as
`pytest` are unavailable in a constrained review environment. The quick path is
not a replacement for the full verifier before a pull request or release.

Repository cleanup before tagging:

```bash
python scripts/check_repository_cleanup.py
python scripts/check_repository_cleanup.py --require-clean
```

## Contribution rules

- Do not commit real hostnames, credentials, vault files, private keys, customer data, or screenshots containing secrets.
- Keep protocol launchers shell-safe by using argument arrays, not string concatenation.
- Put proprietary or product-specific behavior behind adapters and plugins.
- Add tests for every new launcher builder, parser, storage change, or security feature.
- Keep examples generic and use RFC 5737 documentation IP ranges such as `192.0.2.0/24`.

## Pull request checklist

- [ ] `python scripts/verify.py` succeeds.
- [ ] `python scripts/check_repository_cleanup.py` succeeds.
- [ ] README/docs updated if behavior changed.
- [ ] No real secrets or private endpoints included.
- [ ] New feature is represented in `configs/feature_manifest.json` when applicable.
