from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_checker():
    path = Path("scripts/check_release_maturity.py")
    spec = importlib.util.spec_from_file_location("check_release_maturity", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load release maturity checker")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preproduction_metadata_cannot_receive_production_certification() -> None:
    checker = _load_checker()
    pyproject = '''
[project]
version = "1.0.24"
classifiers = [
  "Development Status :: 3 - Alpha",
]
'''

    errors = checker.check_maturity(pyproject, "v1.0.24")

    assert any("Production/Stable" in error for error in errors)
    assert any("pre-production classifiers" in error for error in errors)


def test_production_classifier_and_exact_tag_pass() -> None:
    checker = _load_checker()
    pyproject = '''
[project]
version = "2.3.4"
classifiers = [
  "Development Status :: 5 - Production/Stable",
]
'''

    assert checker.check_maturity(pyproject, "v2.3.4") == []


def test_production_metadata_rejects_wrong_release_tag() -> None:
    checker = _load_checker()
    pyproject = '''
[project]
version = "2.3.4"
classifiers = [
  "Development Status :: 5 - Production/Stable",
]
'''

    errors = checker.check_maturity(pyproject, "v2.3.5")

    assert any("must match project version" in error for error in errors)


def test_project_table_parser_ignores_decoy_versions_and_classifier_strings() -> None:
    checker = _load_checker()
    pyproject = '''
# version = "9.9.9"
[tool.decoy]
version = "8.8.8"
message = "Development Status :: 3 - Alpha"

[project]
version = "2.3.4"
classifiers = ["Development Status :: 5 - Production/Stable"]
'''

    assert checker.check_maturity(pyproject, "v2.3.4") == []


def test_malformed_pyproject_is_rejected_without_regex_fallback() -> None:
    checker = _load_checker()

    errors = checker.check_maturity(
        '[project]\nversion = "2.3.4"\nclassifiers = [',
        "v2.3.4",
    )

    assert len(errors) == 1
    assert "not valid TOML" in errors[0]
