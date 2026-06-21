from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any


def test_make_platform_verified_evidence_record_generates_linux_record(tmp_path: Path) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()
    names = _required_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder_evidence = tmp_path / "builder-identity-linux-i386.json"
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
    )

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                target,
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--builder-evidence",
                str(builder_evidence),
                "--linux-smoke-evidence",
                str(smoke_evidence),
                "--runner-label",
                "self-hosted",
                "--runner-label",
                "linux",
                "--runner-label",
                "i386",
            ]
        )
    )

    assert errors == []
    assert record["target"] == target
    assert record["status"] == "accepted"
    assert record["promotion_config_sha256"] == _promotion_config_sha256()
    assert record["artifact_name"] == f"extended-linux-evidence-linux-i386-{tag}"
    assert record["release_asset_source"] == {
        "type": "github-actions-artifact",
        "workflow": ".github/workflows/extended-platform-evidence.yml",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "artifact_name": f"extended-linux-evidence-linux-i386-{tag}",
        "head_sha": "a" * 40,
        "contains_files": names,
    }
    assert record["workflow_inputs"] == {
        "target": target,
        "release_tag": tag,
        "release_asset_base_url": f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
    }
    assert record["builder_identity"]["target"] == target
    assert record["builder_identity"]["release_tag"] == tag
    assert record["builder_identity"]["workflow_run_url"] == (
        "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    )
    assert record["builder_identity"]["source_head_sha"] == "a" * 40
    assert record["builder_identity"]["host_identity"]["host_label"] == "linux-i386-builder"
    assert record["builder_identity"]["host_identity"]["operator_private_data_redacted"] is True
    assert record["builder_identity_sha256"] == _json_sha256(record["builder_identity"])
    assert record["linux_evidence_sources"] == {
        "builder_identity": {
            "file": "builder-identity-linux-i386.json",
            "size_bytes": builder_evidence.stat().st_size,
            "sha256": record["builder_identity_sha256"],
        },
        "native_smoke": {
            "file": "native-smoke-linux-i386.log",
            "size_bytes": smoke_evidence.stat().st_size,
            "sha256": _sha256(smoke_evidence),
        },
    }
    assert record["native_build_command"] == (
        "TARGET_ARCH=i386 PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh"
    )
    assert record["native_smoke_command"] == (
        "bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux "
        "--target linux-i386 --workflow-run-url "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    )
    assert record["linux_smoke_evidence_sha256"] == {"native_smoke": _sha256(smoke_evidence)}
    assert len(record["release_asset_urls"]) == len(names)
    assert set(record["artifact_sha256"]) == set(names)
    assert all(len(digest) == 64 for digest in record["artifact_sha256"].values())


def test_make_platform_verified_evidence_record_generates_xp_record(tmp_path: Path, monkeypatch) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x64"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_names(artifact_checker, target, tag)
    promotion_hash = _promotion_config_sha256()
    xp_contract_hash = _xp_native_evidence_contract_sha256()
    monkeypatch.chdir(tmp_path)
    assets = Path("native-dist") / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    _write_artifact_set(assets, names)
    evidence = Path("evidence") / target / tag / "xp-evidence.json"
    evidence.parent.mkdir(parents=True)
    data = _valid_xp_evidence(target, "x64", "SP2", tag, names)
    _attach_smoke_evidence_files(evidence.parent, data)
    evidence.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                target,
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
                "--release-source-workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/54321",
                "--release-source-artifact-name",
                f"xp-native-evidence-{target}-{tag}",
                "--release-source-head-sha",
                "a" * 40,
                "--xp-evidence",
                str(evidence),
                "--xp-evidence-dir",
                str(evidence.parent),
            ]
        )
    )

    assert errors == []
    assert record["target"] == target
    assert record["evidence_type"] == "windows-xp-native-host"
    assert record["promotion_config_sha256"] == promotion_hash
    assert record["workflow"] == ".github/workflows/xp-native-evidence.yml"
    assert record["workflow_inputs"] == {
        "target": target,
        "release_tag": tag,
        "release_asset_base_url": f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
        "assets_dir": assets.as_posix(),
        "evidence_file": evidence.as_posix(),
        "evidence_dir": evidence.parent.as_posix(),
    }
    assert record["separate_legacy_toolchain"] is True
    assert record["current_python_pyqt6_stack"] is False
    assert set(record["artifact_sha256"]) == set(names)
    assert record["release_asset_source"] == {
        "type": "github-actions-artifact",
        "workflow": ".github/workflows/xp-native-evidence.yml",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/54321",
        "artifact_name": f"xp-native-evidence-{target}-{tag}",
        "head_sha": "a" * 40,
        "contains_files": names,
    }
    assert record["xp_evidence_sha256"] == _sha256(evidence)
    assert record["xp_evidence_contract_sha256"] == xp_contract_hash
    assert record["xp_host_identity_sha256"] == _json_sha256(record["xp_evidence_summary"]["host_identity"])
    assert record["native_evidence_validation_command"] == (
        f"python scripts/check_xp_native_evidence.py --evidence {evidence.as_posix()} "
        f"--assets-dir {assets.as_posix()} --evidence-dir {evidence.parent.as_posix()}"
    )
    assert record["xp_evidence_sources"]["evidence"] == {
        "file": "xp-evidence.json",
        "path": evidence.as_posix(),
        "size_bytes": evidence.stat().st_size,
        "sha256": _sha256(evidence),
    }
    for smoke_result in data["smoke_results"]:
        smoke_id = str(smoke_result["id"])
        smoke_file = str(smoke_result["evidence_file"])
        smoke_path = evidence.parent / smoke_file
        assert record["xp_evidence_sources"]["smoke_evidence"][smoke_id] == {
            "file": smoke_file,
            "size_bytes": smoke_path.stat().st_size,
            "sha256": _sha256(smoke_path),
        }
    assert record["xp_evidence_summary"] == {
        "target": target,
        "release_tag": tag,
        "host_identity": {
            "schema_version": 1,
            "target": target,
            "release_tag": tag,
            "host_label": "xp-x64-lab-01",
            "evidence_run_id": f"xp-x64-{tag.removeprefix('v').replace('.', '-')}-20260620t120000z",
            "observed_at_utc": "2026-06-20T12:00:00Z",
            "operator_private_data_redacted": True,
            "os": {
                "name": "Windows XP",
                "architecture": "x64",
                "service_pack": "SP2",
                "edition": "Professional x64 Edition",
            },
            "toolchain": {
                "separate_legacy_toolchain": True,
                "current_python_pyqt6_stack": False,
                "description": "Separate legacy XP-capable native host toolchain",
            },
        },
        "os": {
            "name": "Windows XP",
            "architecture": "x64",
            "service_pack": "SP2",
            "edition": "Professional x64 Edition",
        },
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
        },
        "security": {
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
            "patch_evidence": _security_patch_evidence(),
        },
        "smoke_ids": sorted(result["id"] for result in data["smoke_results"]),
        "smoke_evidence_files": {
            result["id"]: result["evidence_file"]
            for result in sorted(data["smoke_results"], key=lambda item: item["id"])
        },
        "smoke_commands": {
            result["id"]: result["command"] for result in sorted(data["smoke_results"], key=lambda item: item["id"])
        },
    }
    assert record["xp_smoke_evidence_sha256"] == {
        result["id"]: result["evidence_sha256"] for result in data["smoke_results"]
    }


def test_make_platform_verified_evidence_record_rejects_wrong_linux_release_source_artifact_name(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                target,
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-artifact-name",
                f"extended-linux-evidence-linux-armhf-{tag}",
                "--release-source-head-sha",
                "a" * 40,
                "--runner-label",
                "self-hosted",
                "--runner-label",
                "linux",
                "--runner-label",
                "i386",
            ]
        )
    )

    assert record == {}
    assert (
        f"--release-source-artifact-name must be extended-linux-evidence-linux-i386-{tag} "
        "for linux-i386 Linux evidence"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_unscoped_linux_evidence_file_names(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()
    names = _required_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder_evidence = tmp_path / "builder.json"
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = tmp_path / "native-smoke.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
    )

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                target,
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--builder-evidence",
                str(builder_evidence),
                "--linux-smoke-evidence",
                str(smoke_evidence),
                "--runner-label",
                "self-hosted",
                "--runner-label",
                "linux",
                "--runner-label",
                "i386",
            ]
        )
    )

    assert record == {}
    assert "--builder-evidence file name must be builder-identity-linux-i386.json" in errors
    assert "--linux-smoke-evidence file name must be native-smoke-linux-i386.log" in errors


def test_make_platform_verified_evidence_record_rejects_wrong_xp_release_source_artifact_name(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "xp"
    assets.mkdir()
    evidence = tmp_path / "xp-evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                target,
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
                "--release-source-workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/54321",
                "--release-source-artifact-name",
                f"xp-native-evidence-windows-xp-native-x64-{tag}",
                "--release-source-head-sha",
                "a" * 40,
                "--xp-evidence",
                str(evidence),
                "--xp-evidence-dir",
                str(tmp_path),
            ]
        )
    )

    assert record == {}
    assert (
        f"--release-source-artifact-name must be xp-native-evidence-{target}-{tag} "
        f"for {target} XP evidence"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_xp_evidence_target_mismatch(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    evidence_target = "windows-xp-native-x64"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "xp"
    assets.mkdir()
    target_names = _required_names(artifact_checker, target, tag)
    evidence_names = _required_names(artifact_checker, evidence_target, tag)
    _write_artifact_set(assets, sorted({*target_names, *evidence_names}))
    evidence = tmp_path / "xp-evidence.json"
    data = _valid_xp_evidence(evidence_target, "x64", "SP2", tag, evidence_names)
    _attach_smoke_evidence_files(tmp_path, data)
    evidence.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                target,
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
                "--release-source-workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/54321",
                "--release-source-artifact-name",
                f"xp-native-evidence-{target}-{tag}",
                "--release-source-head-sha",
                "a" * 40,
                "--xp-evidence",
                str(evidence),
                "--xp-evidence-dir",
                str(tmp_path),
            ]
        )
    )

    assert record == {}
    assert (
        f"{target} XP evidence target must match --target {target}, got {evidence_target!r}"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_xp_evidence_release_tag_mismatch(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x64"
    tag = f"v{artifact_checker.read_project_version()}"
    evidence_tag = "v9.9.9"
    assets = tmp_path / "xp"
    assets.mkdir()
    target_names = _required_names(artifact_checker, target, tag)
    evidence_names = _required_names(artifact_checker, target, evidence_tag)
    _write_artifact_set(assets, sorted({*target_names, *evidence_names}))
    evidence = tmp_path / "xp-evidence.json"
    data = _valid_xp_evidence(target, "x64", "SP2", evidence_tag, evidence_names)
    _attach_smoke_evidence_files(tmp_path, data)
    evidence.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                target,
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
                "--release-source-workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/54321",
                "--release-source-artifact-name",
                f"xp-native-evidence-{target}-{tag}",
                "--release-source-head-sha",
                "a" * 40,
                "--xp-evidence",
                str(evidence),
                "--xp-evidence-dir",
                str(tmp_path),
            ]
        )
    )

    assert record == {}
    assert (
        f"{target} XP evidence release_tag must match --release-tag {tag}, got {evidence_tag!r}"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_weak_linux_smoke_log(tmp_path: Path) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()
    names = _required_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder_evidence = tmp_path / "builder-identity-linux-i386.json"
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    smoke_evidence.write_text("linux-i386 native smoke passed\n", encoding="utf-8")

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                target,
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--builder-evidence",
                str(builder_evidence),
                "--linux-smoke-evidence",
                str(smoke_evidence),
                "--runner-label",
                "self-hosted",
                "--runner-label",
                "linux",
                "--runner-label",
                "i386",
            ]
        )
    )

    assert record == {}
    assert any(
        "linux-i386 linux_smoke_evidence missing required line: "
        "native installer smoke command: bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux "
        "--target linux-i386 --workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345"
        in error
        for error in errors
    )


def test_make_platform_verified_evidence_record_rejects_builder_source_head_sha_mismatch(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()
    names = _required_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder_evidence = tmp_path / "builder-identity-linux-i386.json"
    _write_builder_evidence(builder_evidence, target, source_head_sha="b" * 40)
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
    )

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                target,
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--builder-evidence",
                str(builder_evidence),
                "--linux-smoke-evidence",
                str(smoke_evidence),
                "--runner-label",
                "self-hosted",
                "--runner-label",
                "linux",
                "--runner-label",
                "i386",
            ]
        )
    )

    assert record == {}
    assert (
        f"{target} builder evidence source_head_sha must match --release-source-head-sha "
        f"{'a' * 40}, got {('b' * 40)!r}"
    ) in errors


def test_append_platform_verified_evidence_record_updates_registry(tmp_path: Path) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-armhf"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()
    names = _required_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder_evidence = tmp_path / "builder-identity-linux-armhf.json"
    _write_builder_evidence(
        builder_evidence,
        target,
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/67890",
    )
    smoke_evidence = tmp_path / "native-smoke-linux-armhf.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/67890",
    )
    registry = tmp_path / "platform_verified_evidence.json"
    registry.write_text(json.dumps(_empty_registry(), indent=2) + "\n", encoding="utf-8")

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                target,
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/67890",
                "--release-source-head-sha",
                "a" * 40,
                "--builder-evidence",
                str(builder_evidence),
                "--linux-smoke-evidence",
                str(smoke_evidence),
                "--runner-label",
                "self-hosted",
                "--runner-label",
                "linux",
                "--runner-label",
                "armhf",
            ]
        )
    )
    assert errors == []
    record["review_bundle"] = _review_bundle(target, tag)
    record["release_asset_source"]["contains_files"] = sorted(
        {
            *record["release_asset_source"]["contains_files"],
            record["review_bundle"]["manifest"]["file"],
            record["review_bundle"]["archive"]["file"],
            record["review_bundle"]["sha256s"]["file"],
            f"platform-verified-evidence-{target}-final.json",
        }
    )

    append_errors = maker.append_record_to_registry(record, registry_path=registry)

    assert append_errors == []
    updated = json.loads(registry.read_text(encoding="utf-8"))
    assert [entry["target"] for entry in updated["accepted_evidence"]] == [target]


def test_append_platform_verified_evidence_record_rejects_unfinalized_candidate(tmp_path: Path) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-armhf"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()
    names = _required_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder_evidence = tmp_path / "builder-identity-linux-armhf.json"
    _write_builder_evidence(
        builder_evidence,
        target,
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/67890",
    )
    smoke_evidence = tmp_path / "native-smoke-linux-armhf.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/67890",
    )
    registry = tmp_path / "platform_verified_evidence.json"
    registry.write_text(json.dumps(_empty_registry(), indent=2) + "\n", encoding="utf-8")

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                target,
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/67890",
                "--release-source-head-sha",
                "a" * 40,
                "--builder-evidence",
                str(builder_evidence),
                "--linux-smoke-evidence",
                str(smoke_evidence),
                "--runner-label",
                "self-hosted",
                "--runner-label",
                "linux",
                "--runner-label",
                "armhf",
            ]
        )
    )
    assert errors == []

    append_errors = maker.append_record_to_registry(record, registry_path=registry)

    assert "linux-armhf review_bundle must be an object" in append_errors


def test_append_platform_verified_evidence_record_rejects_duplicate_target(tmp_path: Path) -> None:
    maker = _load_maker()
    record = {
        "target": "linux-i386",
        "status": "accepted",
        "readiness_percent": 100.0,
    }
    registry = tmp_path / "platform_verified_evidence.json"
    data = _empty_registry()
    data["accepted_evidence"] = [{"target": "linux-i386"}]
    registry.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors = maker.append_record_to_registry(record, registry_path=registry)

    assert errors == [
        "linux-i386 already has accepted evidence; remove or replace the existing record deliberately before appending"
    ]


def test_make_platform_verified_evidence_record_rejects_missing_linux_runner_label(tmp_path: Path) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                "linux-armhf",
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--runner-label",
                "linux",
            ]
        )
    )

    assert record == {}
    assert any("--runner-label must include" in error for error in errors)


def _required_names(checker: Any, target: str, tag: str) -> list[str]:
    promotion = checker.read_json(Path("configs/platform_parity_promotion.json"))
    entries = checker.promotion_entries(promotion, [])
    version = checker.version_from_tag(tag, [])
    return [checker.expand_version(name, version) for name in checker.required_artifacts(entries[target])]


def _write_artifact_set(root: Path, names: list[str]) -> None:
    payload_names = [
        name
        for name in names
        if not name.endswith("SHA256SUMS.txt") and not name.endswith("manifest.json")
    ]
    manifest_name = next(name for name in names if name.endswith("manifest.json"))
    sidecar_name = next(name for name in names if name.endswith("SHA256SUMS.txt"))
    for name in payload_names:
        (root / name).write_bytes(_payload_bytes(name))
    records = [
        {
            "file": name,
            "size_bytes": (root / name).stat().st_size,
            "sha256": _sha256(root / name),
        }
        for name in payload_names
    ]
    (root / manifest_name).write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    sidecar_names = [*payload_names, manifest_name]
    (root / sidecar_name).write_text(
        "".join(f"{_sha256(root / name)}  {name}\n" for name in sidecar_names),
        encoding="utf-8",
    )


def _write_builder_evidence(
    path: Path,
    target: str,
    *,
    release_tag: str = "v1.0.2",
    workflow_run_url: str = "https://github.com/example/remote-ops-workspace/actions/runs/12345",
    source_head_sha: str = "a" * 40,
) -> None:
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    data = {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": workflow_run_url,
        "source_head_sha": source_head_sha,
        "host_identity": _linux_host_identity(target, release_tag, workflow_run_url),
        "sudo_non_interactive": True,
        "sys_platform": "linux",
        "platform_machine": machine,
        "uname_machine": machine,
        "dpkg_architecture": dpkg_arch,
        "userland_bits": "32",
        "python_version": "3.12.0",
        "required_tools": {
            "bash": "/usr/bin/bash",
            "curl": "/usr/bin/curl",
            "dpkg": "/usr/bin/dpkg",
            "dpkg-deb": "/usr/bin/dpkg-deb",
            "getconf": "/usr/bin/getconf",
            "openssl": "/usr/bin/openssl",
            "rpm": "/usr/bin/rpm",
            "rpmbuild": "/usr/bin/rpmbuild",
            "sha256sum": "/usr/bin/sha256sum",
            "sudo": "/usr/bin/sudo",
            "tar": "/usr/bin/tar",
        },
        "security_patch_evidence": _security_patch_evidence(),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _linux_host_identity(target: str, release_tag: str, workflow_run_url: str) -> dict[str, object]:
    run_id = workflow_run_url.rstrip("/").split("/")[-1]
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": workflow_run_url,
        "host_label": f"{target}-builder",
        "evidence_run_id": f"{target}-{release_tag.removeprefix('v').replace('.', '-')}-run-{run_id}",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "operator_private_data_redacted": True,
    }


def _write_linux_smoke_evidence(
    path: Path,
    target: str,
    artifact_hashes: dict[str, str],
    *,
    workflow_run_url: str = "https://github.com/example/remote-ops-workspace/actions/runs/12345",
) -> None:
    arch = "i386" if target == "linux-i386" else "armhf"
    artifact_lines = [
        f"native installer smoke artifact sha256: {name} {artifact_hashes[name]}"
        for name in sorted(artifact_hashes)
    ]
    path.write_text(
        "\n".join(
            [
                f"native installer smoke command: bash scripts/smoke_linux_native.sh --arch {arch} "
                f"--dist native-dist/linux --target {target} --workflow-run-url {workflow_run_url}",
                "native installer smoke release: v1.0.2",
                f"native installer smoke target arch: {arch}",
                f"native installer smoke target: {target}",
                f"native installer smoke workflow run: {workflow_run_url}",
                *artifact_lines,
                "native installer smoke: DEB install",
                "native installer smoke: DEB verify",
                "native installer smoke: DEB upgrade",
                "native installer smoke: DEB uninstall",
                "native installer smoke: RPM install",
                "native installer smoke: RPM verify",
                "native installer smoke: RPM upgrade",
                "native installer smoke: RPM uninstall",
                "native installer smoke: AppImage install",
                "native installer smoke: AppImage verify",
                "native installer smoke: AppImage upgrade",
                "native installer smoke: AppImage uninstall",
                f"native installer smoke passed for Linux {arch}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _smoke_artifact_hashes(root: Path, names: list[str]) -> dict[str, str]:
    return {
        name: _sha256(root / name)
        for name in names
        if name.endswith((".deb", ".rpm", ".AppImage"))
    }


def _payload_bytes(name: str) -> bytes:
    payload = f"{name}\n".encode()
    if name.endswith(".deb"):
        return b"!<arch>\n" + payload
    if name.endswith(".rpm"):
        return bytes.fromhex("edabeedb") + payload
    if name.endswith(".AppImage"):
        return b"\x7fELF" + payload
    if name.endswith(".tar.gz"):
        return _tar_gz_bytes(name, payload)
    if name.endswith(".zip"):
        return _zip_bytes(name, payload)
    return payload


def _tar_gz_bytes(name: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo(name=f"{name}.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _zip_bytes(name: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{name}.txt", payload)
    return buffer.getvalue()


def _valid_xp_evidence(
    target: str,
    arch: str,
    service_pack: str,
    release_tag: str,
    artifacts: list[str],
) -> dict[str, Any]:
    smoke_ids = [
        "cli_launch",
        "gui_or_legacy_host_ui_launch",
        "loopback_profile_dry_run",
        "artifact_manifest_validation",
        "legacy_crypto_profile_scoped",
        "modern_defaults_unchanged",
    ]
    os_record = {
        "name": "Windows XP",
        "architecture": arch,
        "service_pack": service_pack,
    }
    if arch == "x64":
        os_record["edition"] = "Professional x64 Edition"
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "os": os_record,
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "Separate legacy XP-capable native host toolchain",
        },
        "host_identity": {
            "schema_version": 1,
            "target": target,
            "release_tag": release_tag,
            "host_label": f"xp-{arch}-lab-01",
            "evidence_run_id": f"xp-{arch}-{release_tag.removeprefix('v').replace('.', '-')}-20260620t120000z",
            "observed_at_utc": "2026-06-20T12:00:00Z",
            "operator_private_data_redacted": True,
            "os": dict(os_record),
            "toolchain": {
                "separate_legacy_toolchain": True,
                "current_python_pyqt6_stack": False,
                "description": "Separate legacy XP-capable native host toolchain",
            },
        },
        "artifact_validation": {
            "passed": True,
            "command": (
                f"python scripts/check_platform_promotion_artifacts.py --target {target} "
                f"--assets-dir native-dist/windows-xp/{target}/{release_tag} --tag {release_tag}"
            ),
        },
        "artifacts": artifacts,
        "smoke_results": [
            {
                "id": smoke_id,
                "passed": True,
                "command": (
                    f"scripts/xp_smoke_runner.cmd --target {target} --release-tag {release_tag} "
                    f"--smoke-id {smoke_id} --evidence-file xp-smoke-evidence/{smoke_id}.txt "
                    f"--proof-file xp-smoke-proof/{smoke_id}.txt"
                ),
                "evidence_file": f"xp-smoke-evidence/{smoke_id}.txt",
                "evidence_sha256": hashlib.sha256(smoke_id.encode()).hexdigest(),
            }
            for smoke_id in smoke_ids
        ],
        "security": {
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
            "patch_evidence": _security_patch_evidence(),
        },
    }


def _attach_smoke_evidence_files(root: Path, evidence: dict[str, Any]) -> None:
    for result in evidence["smoke_results"]:
        path = root / result["evidence_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        security_lines = _xp_security_smoke_lines(str(result["id"]))
        path.write_text(
            f"xp smoke target: {evidence['target']}\n"
            f"xp smoke release: {evidence['release_tag']}\n"
            f"xp smoke id: {result['id']}\n"
            f"{security_lines}"
            f"{result['id']} passed on Windows XP evidence host\n",
            encoding="utf-8",
        )
        result["evidence_sha256"] = _sha256(path)


def _xp_security_smoke_lines(smoke_id: str) -> str:
    if smoke_id == "legacy_crypto_profile_scoped":
        return (
            "legacy compatibility profile: isolated-opt-in\n"
            "legacy crypto scope: profile-only\n"
            "weak crypto global default: false\n"
        )
    if smoke_id == "modern_defaults_unchanged":
        return (
            "modern TLS minimum: TLS 1.2\n"
            "modern TLS preferred: TLS 1.3\n"
            "modern defaults unchanged: true\n"
            "weak crypto global default: false\n"
        )
    return ""


def _empty_registry() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy": (
            "Only accepted evidence records in this file can promote Linux i386, Linux armhf, "
            "or Windows XP native-host readiness. Accepted records must include release asset URLs, "
            "review-bundle manifest release asset URL binding, review bundle release asset URLs, "
            "release-importable artifact source binding, "
            "release source head SHA binding, "
            "release source workflow file binding, "
            "finalized accepted-record source file binding, "
            "Linux release source artifact names must be target/release-scoped, "
            "XP release source artifact names must be target/release-scoped, "
            "and per-artifact SHA-256 digests, Linux builder identity evidence, builder identity "
            "SHA-256, builder identity release/run binding, "
            "Linux builder/smoke source file binding, "
            "Linux builder source head SHA binding, "
            "Linux builder host identity binding when applicable, "
            "Linux builder rpm and non-interactive sudo evidence, Linux security patch evidence, "
            "Linux native build and smoke command provenance, "
            "Linux smoke evidence SHA-256 and Linux smoke release/run binding, "
            "Linux workflow dispatch inputs when applicable, XP workflow dispatch inputs when applicable, "
            "XP evidence source file binding, XP evidence bundle SHA-256 digests, "
            "XP evidence validation command binding, XP evidence contract SHA-256, "
            "XP evidence summary binding, XP host identity SHA-256 binding, XP security patch evidence, "
            "tracked scripts/xp_smoke_runner.cmd XP smoke command provenance, "
            "canonical XP smoke proof-file command binding, "
            "canonical XP smoke evidence-file summary binding and "
            "XP security smoke proof-line binding when applicable, and review "
            "bundle manifest, review bundle archive, and review bundle SHA-256 sidecar digests "
            "before strict promotion, and release uploads must include those review bundle files with matching "
            "size, SHA-256 and checksum-sidecar coverage; each accepted record must include "
            "the promotion config SHA-256, have a unique target, all release evidence for one record must "
            "use the same GitHub repository, and Windows XP x86/x64 pairs must use the same release_tag "
            "and GitHub repository. "
            "Empty means no promotion."
        ),
        "accepted_evidence": [],
    }


def _review_bundle(target: str, release_tag: str) -> dict[str, object]:
    if target.startswith("linux-"):
        stem = f"extended-linux-evidence-bundle-{target}-{release_tag}"
        bundle_type = "extended-linux-native-evidence"
    else:
        stem = f"xp-native-evidence-bundle-{target}-{release_tag}"
        bundle_type = "windows-xp-native-host-evidence"
    base_url = f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}"
    return {
        "bundle_type": bundle_type,
        "manifest": {"file": f"{stem}.json", "sha256": "3" * 64, "size_bytes": 123},
        "archive": {"file": f"{stem}.zip", "sha256": "4" * 64, "size_bytes": 456},
        "sha256s": {"file": f"{stem}-SHA256SUMS.txt", "sha256": "5" * 64, "size_bytes": 78},
        "release_asset_urls": [
            f"{base_url}/{stem}.json",
            f"{base_url}/{stem}.zip",
            f"{base_url}/{stem}-SHA256SUMS.txt",
        ],
    }


def _security_patch_evidence() -> dict[str, object]:
    return {
        "python_ssl_openssl": "OpenSSL 3.0.13",
        "openssl_cli_version": "OpenSSL 3.0.13",
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _promotion_config_sha256() -> str:
    data = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _xp_native_evidence_contract_sha256() -> str:
    data = json.loads(Path("configs/xp_native_evidence_contract.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _json_sha256(data: dict[str, object]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _load_maker():
    path = Path("scripts/make_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("make_platform_verified_evidence_record", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_promotion_artifacts_checker():
    path = Path("scripts/check_platform_promotion_artifacts.py")
    spec = importlib.util.spec_from_file_location("check_platform_promotion_artifacts_for_record", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
