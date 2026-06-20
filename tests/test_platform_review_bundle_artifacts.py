from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def test_platform_review_bundle_artifacts_validates_finalized_xp_bundle(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
    )

    assert errors == []


def test_platform_review_bundle_artifacts_validates_finalized_linux_bundle(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_linux_record(tmp_path)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
    )

    assert errors == []


def test_platform_review_bundle_artifacts_accepts_required_release_tag(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
        required_targets=("windows-xp-native-x86",),
        required_release_tag="v1.0.2",
    )

    assert errors == []


def test_platform_review_bundle_artifacts_goal_targets_require_release_tag(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
        required_targets=validator.PROTECTED_GOAL_TARGETS,
    )

    assert errors == ["protected platform goal required targets require --release-tag vX.Y.Z"]


def test_platform_review_bundle_artifacts_rejects_required_release_tag_mismatch(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
        required_targets=("windows-xp-native-x86",),
        required_release_tag="v1.0.3",
    )

    assert errors == [
        "missing required accepted evidence targets for release_tag v1.0.3: "
        "['windows-xp-native-x86']"
    ]


def test_platform_review_bundle_artifacts_rejects_review_bundle_hash_mismatch(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    record["review_bundle"]["archive"]["sha256"] = "0" * 64
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
    )

    assert (
        "windows-xp-native-x86 review_bundle archive.sha256 does not match file "
        "xp-native-evidence-bundle-windows-xp-native-x86-v1.0.2.zip"
    ) in errors


def test_platform_review_bundle_artifacts_rejects_registry_candidate_drift(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    record["checks"] = [*record["checks"], "tampered-after-finalization"]
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
    )

    assert (
        "windows-xp-native-x86 archived candidate_record must match accepted evidence record without review_bundle"
        in errors
    )


def _finalized_xp_record(tmp_path: Path) -> dict[str, Any]:
    finalizer = _load_script("finalize_platform_verified_evidence_record")
    helpers = _load_platform_verified_evidence_tests()
    bundle_helpers = _load_finalize_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    candidate.pop("review_bundle")
    candidate_path, manifest, archive, sidecar = bundle_helpers._write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert errors == []
    return record


def _finalized_linux_record(tmp_path: Path) -> dict[str, Any]:
    finalizer = _load_script("finalize_platform_verified_evidence_record")
    helpers = _load_platform_verified_evidence_tests()
    bundle_helpers = _load_finalize_tests()
    target = "linux-i386"
    release_tag = "v1.0.2"
    candidate = helpers._linux_record(target)
    candidate.pop("review_bundle")
    artifact_archive_files = bundle_helpers._attach_artifact_files(candidate)

    candidate_path = tmp_path / "platform-verified-evidence-linux-i386.json"
    builder_path = tmp_path / "builder-identity-linux-i386.json"
    smoke_path = tmp_path / "native-smoke-linux-i386.log"
    builder_path.write_text(json.dumps(candidate["builder_identity"], indent=2) + "\n", encoding="utf-8")
    bundle_helpers._write_linux_smoke_evidence(smoke_path, target, candidate["artifact_sha256"])
    candidate["linux_smoke_evidence_sha256"] = {"native_smoke": bundle_helpers._sha256(smoke_path)}
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")

    manifest, archive, sidecar = bundle_helpers._write_bundle_files(
        tmp_path,
        stem=f"extended-linux-evidence-bundle-{target}-{release_tag}",
        bundle_type="extended-linux-native-evidence",
        target=target,
        release_tag=release_tag,
        manifest_records={
            "promotion_config_sha256": candidate["promotion_config_sha256"],
            "release_asset_urls": candidate["release_asset_urls"],
            "validated_commands": bundle_helpers._linux_validated_commands(candidate),
            "workflow": candidate["workflow"],
            "workflow_inputs": candidate["workflow_inputs"],
            "workflow_run_url": candidate["workflow_run_url"],
            "runner_labels": candidate["runner_labels"],
            "security_patch_evidence": candidate["builder_identity"]["security_patch_evidence"],
            "builder_evidence": bundle_helpers._file_record(builder_path),
            "smoke_evidence": [
                bundle_helpers._smoke_file_record(smoke_path, smoke_id="native_smoke", name=smoke_path.name)
            ],
            "candidate_record": bundle_helpers._file_record(candidate_path),
            "artifacts": bundle_helpers._artifact_records(candidate),
        },
        archive_files={
            **artifact_archive_files,
            builder_path.name: builder_path.read_bytes(),
            smoke_path.name: smoke_path.read_bytes(),
            candidate_path.name: candidate_path.read_bytes(),
        },
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert errors == []
    return record


def _registry_with(record: dict[str, Any]) -> dict[str, Any]:
    registry = json.loads(Path("configs/platform_verified_evidence.json").read_text(encoding="utf-8"))
    return {**registry, "accepted_evidence": [record]}


def _load_script(name: str) -> Any:
    path = Path("scripts") / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_verified_evidence_tests() -> Any:
    path = Path("tests/test_platform_verified_evidence.py")
    spec = importlib.util.spec_from_file_location("platform_verified_evidence_test_helpers_for_bundles", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_finalize_tests() -> Any:
    path = Path("tests/test_finalize_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("finalize_platform_verified_evidence_test_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
