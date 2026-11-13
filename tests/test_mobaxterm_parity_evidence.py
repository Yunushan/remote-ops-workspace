from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_release_mobaxterm_parity as release_parity


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



@pytest.fixture
def reviewed_release(tmp_path, monkeypatch):
    release_sha = "d" * 40
    registry_commit = "e" * 40
    main_tip = "f" * 40
    repository = "example/remote-ops-workspace"
    tag = "v1.0.2"
    name = "remote-ops-workspace-v1.0.2-windows-x64.msi"
    assets_dir = tmp_path / "published"
    evidence_root = tmp_path / "reviewed"
    assets_dir.mkdir()
    evidence_root.mkdir()
    asset = assets_dir / name
    asset.write_bytes(b"published release asset bytes")
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()

    records = []
    for article, spec in release_parity.ARTICLE_SPECS.items():
        record = _complete_record(spec)
        record["article_id"] = article
        record["release_asset_urls"] = [
            f"https://github.com/{repository}/releases/download/{tag}/{name}"
        ]
        record["artifact_sha256"] = {name: digest}
        record["release_asset_bytes"]["sha256"] = {name: digest}
        if article == "shared-authenticated-transport-terminal-grid":
            record["validation_summary"]["summary"] = {
                "repository": repository,
                "release_tag": tag,
                "release_target": record["release_target"],
                "source_head_sha": release_sha,
                "workflow_run_url": record["release_source"]["workflow_run_url"],
                "run_attempt": 2,
            }
        article_root = evidence_root / article
        article_root.mkdir()
        evidence = article_root / "evidence.json"
        evidence.write_bytes(b'{"fixture":true}')
        evidence_digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
        record["evidence_file_sha256"] = evidence_digest
        record["evidence_assets_sha256"] = {"evidence.json": evidence_digest}
        records.append(record)
    registry = {"schema_version": 2, "policy": _policy(), "accepted_evidence": records}

    on_main = f"compare/{registry_commit}...{main_tip}?per_page=1"
    run = "actions/runs/1234/attempts/2"
    review = "pulls/42/reviews/99"
    responses = {
        "branches/main": {"name": "main", "protected": True, "commit": {"sha": main_tip}},
        run: {
            "id": 1234,
            "run_attempt": 2,
            "head_sha": release_sha,
            "status": "completed",
            "conclusion": "success",
            "repository": {"full_name": repository},
            "head_repository": {"full_name": repository},
        },
        review: {
            "id": 99,
            "state": "APPROVED",
            "html_url": records[0]["acceptance_review"]["review_url"],
            "submitted_at": "2026-08-23T12:34:56Z",
            "body": "\n".join(release_parity.review_acceptance_line(record) for record in records),
            "user": {"login": "release-reviewer"},
        },
    }
    for ancestor, descendant in ((release_sha, registry_commit), (registry_commit, main_tip)):
        responses[f"compare/{ancestor}...{descendant}?per_page=1"] = {
            "status": "ahead",
            "behind_by": 0,
            "base_commit": {"sha": ancestor},
            "merge_base_commit": {"sha": ancestor},
        }

    def github_object(expected_repository, resource):
        assert expected_repository == repository
        if resource == f"contents/{release_parity.REGISTRY}?ref={registry_commit}":
            payload = json.dumps(registry).encode("utf-8")
            return {
                "type": "file",
                "path": release_parity.REGISTRY,
                "encoding": "base64",
                "content": base64.b64encode(payload).decode("ascii"),
                "size": len(payload),
            }
        return responses[resource]

    monkeypatch.setattr(release_parity, "github_object", github_object)
    validator_calls = []

    def validate(evidence, *, assets_dir):
        article = assets_dir.name
        assert evidence == assets_dir / "evidence.json"
        validator_calls.append(article)
        summary = next(row["validation_summary"]["summary"] for row in records if row["article_id"] == article)
        return SimpleNamespace(to_dict=lambda: {"passed": True, "summary": summary})

    monkeypatch.setattr(release_parity, "VALIDATORS", dict.fromkeys(release_parity.ARTICLE_SPECS, validate))
    args = {
        "repository": repository,
        "tag": tag,
        "release_sha": release_sha,
        "registry_commit": registry_commit,
        "assets_dir": assets_dir,
        "evidence_root": evidence_root,
    }
    return SimpleNamespace(
        args=args, asset=asset, records=records, responses=responses,
        on_main=on_main, run=run, review=review, validator_calls=validator_calls,
    )


def test_certification_accepts_post_release_registry_and_exact_assets(reviewed_release) -> None:
    assert release_parity.audit_release(**reviewed_release.args) == []
    assert set(reviewed_release.validator_calls) == set(release_parity.ARTICLE_SPECS)


def test_certification_rejects_registry_commit_outside_main(reviewed_release) -> None:
    reviewed_release.responses[reviewed_release.on_main]["status"] = "diverged"

    with pytest.raises(ValueError, match="did not establish .* as an ancestor"):
        release_parity.audit_release(**reviewed_release.args)


def test_certification_rejects_other_release_and_changed_download(reviewed_release) -> None:
    stale = next(row for row in reviewed_release.records if row["article_id"] == "professional-deployment")
    stale["release_tag"] = "v1.0.1"
    stale["release_source"]["release_tag"] = "v1.0.1"
    stale["release_asset_urls"][0] = stale["release_asset_urls"][0].replace("/download/v1.0.2/", "/download/v1.0.1/")
    assert _load_checker().check_record(stale) == []
    reviewed_release.asset.write_bytes(b"changed download")

    errors = release_parity.audit_release(**reviewed_release.args)

    assert any("professional-deployment accepted record must bind the exact release" in error for error in errors)
    assert any("SHA-256 differs from the downloaded release asset" in error for error in errors)


@pytest.mark.parametrize(
    ("key", "field", "value", "expected_error"),
    [
        ("run", "run_attempt", 3, "does not match successful release evidence"),
        ("review", "state", "DISMISSED", "review is not approved"),
    ],
)
def test_certification_checks_live_attempt_and_review(
    reviewed_release, key, field, value, expected_error,
) -> None:
    reviewed_release.responses[getattr(reviewed_release, key)][field] = value

    errors = release_parity.audit_release(**reviewed_release.args)

    assert any(expected_error in error for error in errors)


def test_finalizer_prints_the_same_review_line_before_acceptance(reviewed_release, tmp_path, capsys) -> None:
    record = reviewed_release.records[0]
    candidate = {key: value for key, value in record.items()
                 if key not in {"release_source", "acceptance_review", "release_asset_bytes"}}
    candidate["status"] = "candidate"
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    source = record["release_source"]

    assert _load_finalizer().main([
        "--candidate-record", str(candidate_path), "--repository", source["repository"],
        "--source-head-sha", source["head_sha"], "--tag-source-head-sha", source["tag_source_head_sha"],
        "--workflow-run-url", source["workflow_run_url"], "--run-attempt", str(source["run_attempt"]),
        "--print-review-line",
    ]) == 0
    assert capsys.readouterr().out.strip() == release_parity.review_acceptance_line(record)


def test_certification_rejects_review_body_that_only_accepts_another_article(reviewed_release) -> None:
    review = reviewed_release.responses[reviewed_release.review]
    other = reviewed_release.records[-1]
    review["body"] = release_parity.review_acceptance_line(other)

    errors = release_parity.audit_release(**reviewed_release.args)

    assert len(errors) == len(reviewed_release.records) - 1
    assert all("does not explicitly accept this exact article evidence" in error for error in errors)


def test_certification_rejects_changed_evidence_after_approval(reviewed_release) -> None:
    reviewed_release.records[0]["evidence_file_sha256"] = "2" * 64

    errors = release_parity.audit_release(**reviewed_release.args)

    assert len(errors) == 1
    assert "does not explicitly accept this exact article evidence" in errors[0]


def test_certification_rejects_unrelated_comment_with_matching_author(reviewed_release) -> None:
    review = reviewed_release.responses[reviewed_release.review]
    comment_url = "https://github.com/example/remote-ops-workspace/issues/42#issuecomment-99"
    reviewed_release.responses["issues/comments/99"] = {
        "id": 99, "html_url": comment_url, "created_at": review["submitted_at"],
        "user": review["user"], "body": "Thanks for putting this together.",
    }
    for record in reviewed_release.records:
        record["acceptance_review"]["review_url"] = comment_url

    errors = release_parity.audit_release(**reviewed_release.args)

    assert len(errors) == len(reviewed_release.records)
    assert all("does not explicitly accept this exact article evidence" in error for error in errors)


@pytest.mark.parametrize(("edit", "expected"), [
    ("changed", "SHA-256 differs"),
    ("missing", "files are missing"),
    ("extra", "unexpected file"),
])
def test_certification_checks_exact_reviewed_evidence_files(reviewed_release, edit, expected) -> None:
    article = reviewed_release.records[0]["article_id"]
    root = reviewed_release.args["evidence_root"] / article
    evidence = root / "evidence.json"
    if edit == "changed":
        evidence.write_bytes(b"changed evidence")
    elif edit == "missing":
        evidence.unlink()
    else:
        (root / "unexpected.txt").write_text("unreviewed", encoding="utf-8")

    errors = release_parity.audit_release(**reviewed_release.args)

    assert len(errors) == 1
    assert expected in errors[0]
    assert article not in reviewed_release.validator_calls


def test_certification_refuses_evidence_when_the_article_validator_fails(reviewed_release, monkeypatch) -> None:
    article = reviewed_release.records[0]["article_id"]
    monkeypatch.setitem(release_parity.VALIDATORS, article,
                        lambda *_args, **_kwargs: SimpleNamespace(to_dict=lambda: {"passed": False}))
    errors = release_parity.audit_release(**reviewed_release.args)
    assert len(errors) == 1
    assert "article validator did not pass" in errors[0]


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
