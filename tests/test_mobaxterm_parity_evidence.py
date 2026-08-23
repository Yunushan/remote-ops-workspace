from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_mobaxterm_parity_evidence_empty_registry_is_valid_but_not_complete() -> None:
    checker = _load_checker()
    registry = {
        "schema_version": 2,
        "policy": _policy(),
        "accepted_evidence": [],
    }

    assert checker.check_mobaxterm_parity_evidence(registry=registry) == []
    errors = checker.check_mobaxterm_parity_evidence(registry=registry, require_complete=True)

    assert any("missing required MobaXterm parity articles" in error for error in errors)
    assert any("shared-authenticated-transport-terminal-grid" in error for error in errors)


def test_mobaxterm_parity_evidence_catalog_tracks_all_eight_articles() -> None:
    checker = _load_checker()

    assert set(checker.ARTICLE_SPECS) == {
        "embedded-server-suite",
        "embedded-x-server",
        "macro-recorder",
        "moba-text-editor-diff",
        "mobapt-unix-runtime",
        "professional-deployment",
        "shared-authenticated-transport-terminal-grid",
        "ssh-browser-26-4-smartcard",
    }
    transport = checker.ARTICLE_SPECS["shared-authenticated-transport-terminal-grid"]
    assert transport.evidence_type == "moba-shared-transport-terminal-grid-release"
    assert transport.required_checks == {
        "shared_authenticated_transport",
        "structured_connection_state",
        "real_terminal_grid",
        "alternate_screen_semantics",
        "cursor_color_mode_mouse_semantics",
        "real_connected_session",
        "release_asset_attachment",
    }


def test_mobaxterm_record_generator_registers_eighth_article_validator() -> None:
    generator = _load_generator()

    validator = generator.VALIDATORS["shared-authenticated-transport-terminal-grid"]

    assert validator.__name__ == "validate_moba_transport_terminal_evidence"


def test_mobaxterm_parity_evidence_accepts_complete_article_record() -> None:
    checker = _load_checker()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    record = _complete_record(spec)
    registry = {
        "schema_version": 2,
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
        "schema_version": 2,
        "policy": _policy(),
        "accepted_evidence": [record, dict(record)],
    }

    errors = checker.check_mobaxterm_parity_evidence(registry=registry)

    assert "professional-deployment validation_summary.passed must be true" in errors
    assert any("missing required checks" in error for error in errors)
    assert any("artifact_sha256" in error for error in errors)
    assert "accepted_evidence article_id must be unique: professional-deployment" in errors


def test_mobaxterm_parity_evidence_rejects_missing_acceptance_provenance() -> None:
    checker = _load_checker()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    record = _complete_record(spec)
    record.pop("release_source")
    record.pop("acceptance_review")
    record.pop("release_asset_bytes")

    errors = checker.check_record(record)

    assert "professional-deployment release_source must be an object" in errors


def test_mobaxterm_parity_evidence_rejects_provenance_drift() -> None:
    checker = _load_checker()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    record = _complete_record(spec)
    record["release_source"]["repository"] = "other/remote-ops-workspace"
    record["release_source"]["tag_source_head_sha"] = "e" * 40
    record["release_source"]["run_attempt"] = True
    record["acceptance_review"]["review_url"] = (
        "https://github.com/review-drift/remote-ops-workspace/pull/42#pullrequestreview-99"
    )
    record["release_asset_bytes"]["sha256"] = {
        "moba-professional-deployment.zip": "d" * 64
    }

    errors = checker.check_record(record)

    assert any("release asset repository must exactly match" in error for error in errors)
    assert any("tag_source_head_sha must match" in error for error in errors)
    assert any("run_attempt must be a positive integer" in error for error in errors)
    assert any("review_url repository must match" in error for error in errors)
    assert any("release_asset_bytes.sha256 must exactly match" in error for error in errors)


def test_mobaxterm_generator_emits_candidate_and_has_no_registry_append(tmp_path: Path) -> None:
    generator = _load_generator()
    evidence = tmp_path / "evidence.json"
    artifact = tmp_path / "bundle.zip"
    evidence.write_text("{}\n", encoding="utf-8")
    artifact.write_bytes(b"published bytes\n")

    class PassingValidation:
        passed = True
        errors: list[str] = []

        @staticmethod
        def to_dict() -> dict[str, object]:
            return {"passed": True, "errors": [], "summary": {"real": True}}

    generator.VALIDATORS["professional-deployment"] = lambda *_args, **_kwargs: PassingValidation()
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            article_id="professional-deployment",
            release_tag="v1.0.2",
            release_target="windows-x64",
            evidence=evidence,
            assets_dir=tmp_path,
            release_asset_url=[
                "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/bundle.zip"
            ],
            artifact=[f"bundle.zip={artifact}"],
        )
    )

    assert errors == []
    assert record["status"] == "candidate"
    assert "release_source" not in record
    assert "acceptance_review" not in record
    with pytest.raises(SystemExit):
        generator.parse_args(
            [
                "--article-id",
                "professional-deployment",
                "--release-tag",
                "v1.0.2",
                "--release-target",
                "windows-x64",
                "--evidence",
                str(evidence),
                "--append-registry",
            ]
        )


def test_mobaxterm_finalizer_binds_reviewed_published_bytes(tmp_path: Path) -> None:
    checker = _load_checker()
    finalizer = _load_finalizer()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    published = tmp_path / "moba-professional-deployment.zip"
    published.write_bytes(b"published release bytes\n")
    digest = hashlib.sha256(published.read_bytes()).hexdigest()
    candidate = _complete_record(spec)
    candidate["status"] = "candidate"
    candidate["artifact_sha256"] = {published.name: digest}
    candidate.pop("release_source")
    candidate.pop("acceptance_review")
    candidate.pop("release_asset_bytes")

    errors, accepted = finalizer.finalize_candidate(
        candidate,
        repository="example/remote-ops-workspace",
        source_head_sha="d" * 40,
        tag_source_head_sha="d" * 40,
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/1234",
        run_attempt=2,
        reviewer="release-reviewer",
        review_url=(
            "https://github.com/example/remote-ops-workspace/pull/42#pullrequestreview-99"
        ),
        reviewed_at="2026-08-23T12:34:56Z",
        published_assets={published.name: published},
    )

    assert errors == []
    assert accepted["status"] == "accepted"
    assert accepted["release_asset_bytes"]["sha256"] == {published.name: digest}
    assert checker.check_record(accepted) == []


def test_mobaxterm_finalizer_rejects_tampered_published_bytes(tmp_path: Path) -> None:
    checker = _load_checker()
    finalizer = _load_finalizer()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    published = tmp_path / "moba-professional-deployment.zip"
    published.write_bytes(b"tampered\n")
    candidate = _complete_record(spec)
    candidate["status"] = "candidate"
    candidate.pop("release_source")
    candidate.pop("acceptance_review")
    candidate.pop("release_asset_bytes")

    errors, accepted = finalizer.finalize_candidate(
        candidate,
        repository="example/remote-ops-workspace",
        source_head_sha="d" * 40,
        tag_source_head_sha="d" * 40,
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/1234",
        run_attempt=2,
        reviewer="release-reviewer",
        review_url=(
            "https://github.com/example/remote-ops-workspace/pull/42#pullrequestreview-99"
        ),
        reviewed_at="2026-08-23T12:34:56Z",
        published_assets={published.name: published},
    )

    assert accepted == {}
    assert any("published release asset bytes" in error for error in errors)


def _load_checker():
    path = Path("scripts/check_mobaxterm_parity_evidence.py")
    spec = importlib.util.spec_from_file_location("check_mobaxterm_parity_evidence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_generator():
    path = Path("scripts/make_mobaxterm_parity_evidence_record.py")
    spec = importlib.util.spec_from_file_location("make_mobaxterm_parity_evidence_record", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_finalizer():
    path = Path("scripts/finalize_mobaxterm_parity_evidence_record.py")
    spec = importlib.util.spec_from_file_location("finalize_mobaxterm_parity_evidence_record", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _complete_record(spec):
    return {
        "article_id": "professional-deployment",
        "status": "accepted",
        "evidence_type": spec.evidence_type,
        "release_tag": "v1.0.2",
        "release_target": "windows-x64",
        "validation_command": spec.validation_command,
        "evidence_file_sha256": "a" * 64,
        "evidence_assets_sha256": {"moba-professional-deployment.json": "b" * 64},
        "release_asset_urls": [
            "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
            "moba-professional-deployment.zip"
        ],
        "artifact_sha256": {"moba-professional-deployment.zip": "c" * 64},
        "checks": sorted(spec.required_checks),
        "validation_summary": {
            "passed": True,
            "errors": [],
            "summary": {"release_target": "windows-x64", "brand_name": "Corp Ops"},
        },
        "release_source": {
            "repository": "example/remote-ops-workspace",
            "release_tag": "v1.0.2",
            "head_sha": "d" * 40,
            "tag_source_head_sha": "d" * 40,
            "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/1234",
            "run_attempt": 2,
        },
        "acceptance_review": {
            "reviewer": "release-reviewer",
            "review_url": (
                "https://github.com/example/remote-ops-workspace/pull/42#pullrequestreview-99"
            ),
            "reviewed_at": "2026-08-23T12:34:56Z",
        },
        "release_asset_bytes": {
            "verified": True,
            "verified_by": "release-reviewer",
            "verified_at": "2026-08-23T12:34:56Z",
            "sha256": {"moba-professional-deployment.zip": "c" * 64},
        },
    }


def _policy() -> str:
    return (
        "Only accepted evidence records in this file can close strict MobaXterm 26.4 Home/Professional parity "
        "articles. Accepted records must include one unique article_id, status accepted, a vX.Y.Z release_tag, "
        "a release_target, the exact validation command for that article, SHA-256 digests for the validated "
        "evidence JSON and evidence assets, release asset URLs under the same GitHub release tag, per-artifact "
        "SHA-256 digests, required article checks, and a validation summary proving the article evidence passed. "
        "Acceptance additionally requires the exact GitHub repository, source head SHA and tag source head SHA, "
        "the exact source workflow run URL and positive run attempt, reviewer provenance, and hashes of the "
        "published release bytes matching the accepted per-artifact SHA-256 values. Candidate generation cannot "
        "append or accept its own output; a separate reviewed finalization step is mandatory. "
        "Empty means the generated feature-family score remains separate from true product-depth parity."
    )
