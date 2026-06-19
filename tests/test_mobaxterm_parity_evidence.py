from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_mobaxterm_parity_evidence_empty_registry_is_valid_but_not_complete() -> None:
    checker = _load_checker()
    registry = {
        "schema_version": 1,
        "policy": _policy(),
        "accepted_evidence": [],
    }

    assert checker.check_mobaxterm_parity_evidence(registry=registry) == []
    errors = checker.check_mobaxterm_parity_evidence(registry=registry, require_complete=True)

    assert any("missing required MobaXterm parity articles" in error for error in errors)


def test_mobaxterm_parity_evidence_accepts_complete_article_record() -> None:
    checker = _load_checker()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    record = {
        "article_id": "professional-deployment",
        "status": "accepted",
        "evidence_type": spec.evidence_type,
        "release_tag": "v1.0.2",
        "release_target": "windows-x64",
        "validation_command": spec.validation_command,
        "evidence_file_sha256": "a" * 64,
        "evidence_assets_sha256": {"moba-professional-deployment.json": "b" * 64},
        "release_asset_urls": [
            "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/moba-professional-deployment.zip"
        ],
        "artifact_sha256": {"moba-professional-deployment.zip": "c" * 64},
        "checks": sorted(spec.required_checks),
        "validation_summary": {
            "passed": True,
            "errors": [],
            "summary": {"release_target": "windows-x64", "brand_name": "Corp Ops"},
        },
    }
    registry = {
        "schema_version": 1,
        "policy": _policy(),
        "accepted_evidence": [record],
    }

    assert checker.check_mobaxterm_parity_evidence(registry=registry) == []


def test_mobaxterm_parity_evidence_rejects_incomplete_article_record() -> None:
    checker = _load_checker()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    record = {
        "article_id": "professional-deployment",
        "status": "accepted",
        "evidence_type": spec.evidence_type,
        "release_tag": "v1.0.2",
        "release_target": "windows-x64",
        "validation_command": spec.validation_command,
        "evidence_file_sha256": "a" * 64,
        "evidence_assets_sha256": {"moba-professional-deployment.json": "b" * 64},
        "release_asset_urls": [
            "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/moba-professional-deployment.zip"
        ],
        "artifact_sha256": {"moba-professional-deployment.zip": "not-a-sha"},
        "checks": ["branded_windows_exe"],
        "validation_summary": {"passed": False, "errors": ["failed"], "summary": {}},
    }
    registry = {
        "schema_version": 1,
        "policy": _policy(),
        "accepted_evidence": [record, dict(record)],
    }

    errors = checker.check_mobaxterm_parity_evidence(registry=registry)

    assert "professional-deployment validation_summary.passed must be true" in errors
    assert any("missing required checks" in error for error in errors)
    assert any("artifact_sha256" in error for error in errors)
    assert "accepted_evidence article_id must be unique: professional-deployment" in errors


def _load_checker():
    path = Path("scripts/check_mobaxterm_parity_evidence.py")
    spec = importlib.util.spec_from_file_location("check_mobaxterm_parity_evidence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _policy() -> str:
    return (
        "Only accepted evidence records in this file can close strict MobaXterm 26.4 Home/Professional parity "
        "articles. Accepted records must include one unique article_id, status accepted, a vX.Y.Z release_tag, "
        "a release_target, the exact validation command for that article, SHA-256 digests for the validated "
        "evidence JSON and evidence assets, release asset URLs under the same GitHub release tag, per-artifact "
        "SHA-256 digests, required article checks, and a validation summary proving the article evidence passed. "
        "Empty means the generated feature-family score remains separate from true product-depth parity."
    )
