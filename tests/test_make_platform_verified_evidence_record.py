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

ROOT = Path(__file__).resolve().parents[1]


def test_make_platform_verified_evidence_record_policy_matches_registry() -> None:
    maker = _load_maker()
    registry = json.loads((ROOT / "configs" / "platform_verified_evidence.json").read_text(encoding="utf-8"))

    assert maker.DEFAULT_EVIDENCE_POLICY == registry["policy"]


def test_make_platform_verified_evidence_record_generates_linux_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_names(artifact_checker, target, tag)
    promotion_hash = _promotion_config_sha256()
    monkeypatch.chdir(tmp_path)
    assets = Path("staged") / target / tag / "artifacts"
    assets.mkdir(parents=True)
    _write_artifact_set(assets, names)
    builder_evidence = Path("evidence") / target / tag / "builder-identity-linux-i386.json"
    builder_evidence.parent.mkdir(parents=True)
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = Path("evidence") / target / tag / "native-smoke-linux-i386.log"
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
                "--release-source-run-attempt",
                "1",
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
    assert record["promotion_config_sha256"] == promotion_hash
    assert record["artifact_name"] == f"extended-linux-evidence-linux-i386-{tag}"
    assert record["release_asset_source"] == {
        "type": "github-actions-artifact",
        "workflow": ".github/workflows/extended-platform-evidence.yml",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "artifact_name": f"extended-linux-evidence-linux-i386-{tag}",
        "head_sha": "a" * 40,
        "run_attempt": 1,
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
    assert record["builder_identity"]["workflow_run_attempt"] == 1
    assert record["builder_identity"]["workflow_ref"] == (
        "example/remote-ops-workspace/.github/workflows/"
        f"extended-platform-evidence.yml@{'a' * 40}"
    )
    assert record["builder_identity"]["workflow_sha"] == "a" * 40
    assert record["builder_identity"]["source_head_sha"] == "a" * 40
    assert record["builder_identity"]["observed_git_head_sha"] == "a" * 40
    assert record["builder_identity"]["host_identity"]["workflow_run_attempt"] == 1
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
        f"https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--workflow-run-attempt 1 --source-head-sha {'a' * 40} "
        f"--builder-evidence {builder_evidence.as_posix()}"
    )
    assert record["linux_smoke_evidence_sha256"] == {"native_smoke": _sha256(smoke_evidence)}
    assert record["linux_smoke_summary"] == {
        "target": target,
        "release_tag": tag,
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "workflow_run_attempt": 1,
        "source_head_sha": "a" * 40,
        "git_head_sha": "a" * 40,
        "target_arch": "i386",
        "host_label": "linux-i386-builder",
        "evidence_run_id": "linux-i386-1-0-2-run-12345",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "uname_machine": "i686",
        "dpkg_architecture": "i386",
        "userland_bits": "32",
        "os_release": "Debian GNU/Linux 12 (bookworm)",
        "kernel_release": "6.1.0-i386-ci",
        "glibc_version": "glibc 2.36",
        "python_ssl_openssl": "OpenSSL 3.0.13",
        "openssl_cli_version": "OpenSSL 3.0.13",
        "security": {
            "tls_minimum_modern_profiles": "TLS 1.2",
            "tls_preferred_modern_profiles": "TLS 1.3",
            "legacy_compatibility_profile": "isolated-opt-in",
            "legacy_crypto_scope": "profile-only",
            "weak_crypto_global_default": False,
            "modern_defaults_unchanged": True,
            "security_update_channel": "vendor-security-updates-2026-06",
            "cve_review_reference": "vendor-cve-advisory-review-2026-06",
        },
    }
    assert record["local_evidence_preflight_command"] == (
        "python scripts/check_platform_goal_local_evidence.py --root . "
        f"--release-tag {tag} --target {target} --assets-dir {assets.as_posix()} "
        f"--linux-builder-evidence {builder_evidence.as_posix()} "
        f"--linux-smoke-evidence {smoke_evidence.as_posix()} "
        "--linux-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--linux-source-head-sha {'a' * 40} "
        "--linux-source-run-attempt 1"
    )
    assert record["staged_upload_command"] == (
        "python scripts/stage_extended_linux_evidence_upload.py "
        f"--target {target} --release-tag {tag} --source-dir {assets.as_posix()} "
        f"--out-dir platform-evidence-upload/{target}/{tag} --force"
    )
    assert record["artifact_validation_command"] == (
        f"python scripts/check_platform_promotion_artifacts.py --target {target} "
        f"--assets-dir {assets.as_posix()} --tag {tag} --strict"
    )
    assert len(record["release_asset_urls"]) == len(names)
    assert set(record["artifact_sha256"]) == set(names)
    assert all(len(digest) == 64 for digest in record["artifact_sha256"].values())


def test_make_platform_verified_evidence_record_binds_local_evidence_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    root = Path("platform-evidence-staging")
    target_root = root / target / tag
    assets = target_root / "artifacts"
    assets.mkdir(parents=True)
    _write_artifact_set(assets, names)
    builder_evidence = target_root / "builder-identity-linux-i386.json"
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = target_root / "native-smoke-linux-i386.log"
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
                "--release-source-run-attempt",
                "1",
                "--builder-evidence",
                str(builder_evidence),
                "--linux-smoke-evidence",
                str(smoke_evidence),
                "--local-evidence-root",
                str(root),
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
    assert record["local_evidence_preflight_command"].startswith(
        "python scripts/check_platform_goal_local_evidence.py --root platform-evidence-staging "
    )


def test_make_platform_verified_evidence_record_requires_local_preflight_pass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets = Path("staged") / target / tag / "artifacts"
    assets.mkdir(parents=True)
    _write_artifact_set(assets, names)
    builder_evidence = Path("evidence") / target / tag / f"builder-identity-{target}.json"
    builder_evidence.parent.mkdir(parents=True)
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = Path("evidence") / target / tag / f"native-smoke-{target}.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
    )

    monkeypatch.setattr(
        maker,
        "check_local_evidence_preflight",
        lambda args: [f"{target} local preflight sentinel failure"],
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
                "--release-source-run-attempt",
                "1",
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
    assert errors == [f"{target} local preflight sentinel failure"]


def test_make_platform_verified_evidence_record_rejects_file_shaped_linux_directory_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets = Path("native-dist") / "linux" / target / tag / "artifacts.zip"
    assets.mkdir(parents=True)
    _write_artifact_set(assets, names)
    builder_evidence = Path("evidence") / target / tag / f"builder-identity-{target}.json"
    builder_evidence.parent.mkdir(parents=True)
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = Path("evidence") / target / tag / f"native-smoke-{target}.log"
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
                "--release-source-run-attempt",
                "1",
                "--builder-evidence",
                str(builder_evidence),
                "--linux-smoke-evidence",
                str(smoke_evidence),
                "--local-evidence-root",
                "platform-evidence.zip",
                "--runner-label",
                "self-hosted",
                "--runner-label",
                "linux",
                "--runner-label",
                "i386",
            ]
        )
    )

    assert f"artifact directory must be a directory path, got {assets.as_posix()!r}" in errors
    assert "local evidence root must be a directory path, got 'platform-evidence.zip'" in errors
    assert record == {}


def test_make_platform_verified_evidence_record_rejects_invalid_release_source_run_attempt_types(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    assets = tmp_path / "artifacts"
    assets.mkdir()
    args = maker.parse_args(
        [
            "--target",
            "linux-i386",
            "--release-tag",
            "v1.0.2",
            "--assets-dir",
            str(assets),
            "--release-asset-base-url",
            "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
            "--workflow-run-url",
            "https://github.com/example/remote-ops-workspace/actions/runs/12345",
            "--release-source-head-sha",
            "a" * 40,
            "--release-source-run-attempt",
            "1",
            "--runner-label",
            "self-hosted",
            "--runner-label",
            "linux",
            "--runner-label",
            "i386",
        ]
    )

    for source_run_attempt in ("first", True):
        args.release_source_run_attempt = source_run_attempt
        errors = maker.validate_common_args(args)

        assert "--release-source-run-attempt must be a positive integer" in errors


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
                "--release-source-run-attempt",
                "1",
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
        "run_attempt": 1,
        "contains_files": names,
    }
    assert record["xp_evidence_sha256"] == _sha256(evidence)
    assert record["xp_evidence_contract_sha256"] == xp_contract_hash
    assert record["xp_host_identity_sha256"] == _json_sha256(record["xp_evidence_summary"]["host_identity"])
    assert record["native_evidence_validation_command"] == (
        f"python scripts/check_xp_native_evidence.py --evidence {evidence.as_posix()} "
        f"--assets-dir {assets.as_posix()} --evidence-dir {evidence.parent.as_posix()}"
    )
    assert record["local_evidence_preflight_command"] == (
        "python scripts/check_platform_goal_local_evidence.py --root . "
        f"--release-tag {tag} --target {target} --assets-dir {assets.as_posix()} "
        f"--xp-evidence {evidence.as_posix()} --xp-evidence-dir {evidence.parent.as_posix()} "
        "--xp-source-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/54321 "
        f"--xp-source-head-sha {'a' * 40} "
        "--xp-source-run-attempt 1"
    )
    assert record["staged_upload_command"] == (
        "python scripts/stage_xp_native_evidence_upload.py "
        f"--target {target} --release-tag {tag} --assets-dir {assets.as_posix()} "
        f"--evidence-output-dir xp-evidence-output/{target}/{tag} "
        f"--out-dir platform-evidence-upload/{target}/{tag} --force"
    )
    assert record["artifact_validation_command"] == (
        f"python scripts/check_platform_promotion_artifacts.py --target {target} "
        f"--assets-dir {assets.as_posix()} --tag {tag} --strict"
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
        "release_source": {
            "workflow": ".github/workflows/xp-native-evidence.yml",
            "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/54321",
            "head_sha": "a" * 40,
            "run_attempt": 1,
        },
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
            "patch_evidence": _xp_security_patch_evidence(),
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


def test_make_platform_verified_evidence_record_rejects_xp_evidence_release_source_head_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets = Path("native-dist") / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    _write_artifact_set(assets, names)
    evidence = Path("evidence") / target / tag / "xp-evidence.json"
    evidence.parent.mkdir(parents=True)
    data = _valid_xp_evidence(target, "x86", "SP3", tag, names)
    _attach_smoke_evidence_files(evidence.parent, data)
    bad_head = "b" * 40
    data["release_source"]["head_sha"] = bad_head
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
                "--release-source-run-attempt",
                "1",
                "--xp-evidence",
                str(evidence),
                "--xp-evidence-dir",
                str(evidence.parent),
            ]
        )
    )

    assert record == {}
    assert (
        f"{target} XP evidence release_source.head_sha must match "
        f"--release-source-head-sha {'a' * 40}, got {bad_head!r}"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_file_shaped_xp_evidence_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x64"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets = Path("native-dist") / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    _write_artifact_set(assets, names)
    evidence_dir = Path("evidence") / target / tag / "xp-evidence.zip"
    evidence_dir.mkdir(parents=True)
    evidence = evidence_dir / "xp-evidence.json"
    data = _valid_xp_evidence(target, "x64", "SP2", tag, names)
    _attach_smoke_evidence_files(evidence_dir, data)
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
                "--release-source-run-attempt",
                "1",
                "--xp-evidence",
                str(evidence),
                "--xp-evidence-dir",
                str(evidence_dir),
            ]
        )
    )

    assert f"XP evidence directory must be a directory path, got {evidence_dir.as_posix()!r}" in errors
    assert record == {}


def test_make_platform_verified_evidence_record_rejects_symlinked_linux_evidence_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()
    builder_evidence = tmp_path / "builder-identity-linux-i386.json"
    builder_evidence.write_text("{}\n", encoding="utf-8")
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    smoke_evidence.write_text("linux smoke placeholder\n", encoding="utf-8")
    symlink_names = {builder_evidence.name, smoke_evidence.name}

    def fake_is_symlink(self: Path) -> bool:
        return self.name in symlink_names

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

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
                "--release-source-run-attempt",
                "1",
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

    assert f"Linux builder evidence file must not be a symlink: {builder_evidence}" in errors
    assert f"Linux smoke evidence file must not be a symlink: {smoke_evidence}" in errors
    assert record == {}


def test_make_platform_verified_evidence_record_rejects_symlinked_linux_evidence_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()
    evidence_parent = tmp_path / "linux-evidence"
    evidence_parent.mkdir()
    builder_evidence = evidence_parent / "builder-identity-linux-i386.json"
    builder_evidence.write_text("{}\n", encoding="utf-8")
    smoke_evidence = evidence_parent / "native-smoke-linux-i386.log"
    smoke_evidence.write_text("linux smoke placeholder\n", encoding="utf-8")

    def fake_is_symlink(self: Path) -> bool:
        return self == evidence_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

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
                "--release-source-run-attempt",
                "1",
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

    assert f"Linux builder evidence file path must not contain symlinked directories: {evidence_parent}" in errors
    assert f"Linux smoke evidence file path must not contain symlinked directories: {evidence_parent}" in errors
    assert record == {}


def test_make_platform_verified_evidence_record_rejects_linux_inputs_inside_reserved_workspace_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    monkeypatch.chdir(tmp_path)
    embedded = Path(".git") / target / tag
    assets = embedded / "artifacts"
    assets.mkdir(parents=True)
    builder_evidence = embedded / f"builder-identity-{target}.json"
    builder_evidence.write_text("{}\n", encoding="utf-8")
    smoke_evidence = embedded / f"native-smoke-{target}.log"
    smoke_evidence.write_text("linux smoke placeholder\n", encoding="utf-8")
    staged_upload = embedded / "upload"

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
                "--release-source-run-attempt",
                "1",
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
                "--staged-upload-out-dir",
                str(staged_upload),
            ]
        )
    )

    assert (
        f"artifact directory must not point inside reserved workspace directory '.git': {assets}"
    ) in errors
    assert (
        "Linux builder evidence file must not point inside reserved workspace directory "
        f"'.git': {builder_evidence}"
    ) in errors
    assert (
        "Linux smoke evidence file must not point inside reserved workspace directory "
        f"'.git': {smoke_evidence}"
    ) in errors
    assert (
        "staged upload output directory must not point inside reserved workspace directory "
        f"'.git': {staged_upload}"
    ) in errors
    assert record == {}


def test_make_platform_verified_evidence_record_rejects_symlinked_xp_evidence_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "windows-xp-native-x86" / tag / "artifacts"
    assets.mkdir(parents=True)
    evidence_dir = tmp_path / "windows-xp-native-x86" / tag / "evidence"
    evidence_dir.mkdir(parents=True)
    evidence = evidence_dir / "xp-evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    symlink_names = {evidence.name, evidence_dir.name}

    def fake_is_symlink(self: Path) -> bool:
        return self.name in symlink_names

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

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
                "--release-source-run-attempt",
                "1",
                "--xp-evidence",
                str(evidence),
                "--xp-evidence-dir",
                str(evidence_dir),
            ]
        )
    )

    assert f"XP evidence file must not be a symlink: {evidence}" in errors
    assert f"XP evidence directory must not be a symlink: {evidence_dir}" in errors
    assert record == {}


def test_make_platform_verified_evidence_record_rejects_symlinked_xp_evidence_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "windows-xp-native-x86" / tag / "artifacts"
    assets.mkdir(parents=True)
    evidence_parent = tmp_path / "windows-xp-native-x86" / tag / "evidence-parent"
    evidence_dir = evidence_parent / "evidence"
    evidence_dir.mkdir(parents=True)
    evidence = evidence_dir / "xp-evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")

    def fake_is_symlink(self: Path) -> bool:
        return self == evidence_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

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
                "--release-source-run-attempt",
                "1",
                "--xp-evidence",
                str(evidence),
                "--xp-evidence-dir",
                str(evidence_dir),
            ]
        )
    )

    assert f"XP evidence file path must not contain symlinked directories: {evidence_parent}" in errors
    assert f"XP evidence directory path must not contain symlinked directories: {evidence_parent}" in errors
    assert record == {}


def test_make_platform_verified_evidence_record_rejects_xp_inputs_inside_reserved_workspace_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    monkeypatch.chdir(tmp_path)
    embedded = Path(".github") / target / tag
    assets = embedded / "artifacts"
    assets.mkdir(parents=True)
    evidence_dir = embedded / "evidence"
    evidence_dir.mkdir(parents=True)
    evidence = evidence_dir / "xp-evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    staged_upload = embedded / "upload"
    evidence_output = embedded / "output"

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
                "--release-source-run-attempt",
                "1",
                "--xp-evidence",
                str(evidence),
                "--xp-evidence-dir",
                str(evidence_dir),
                "--staged-upload-out-dir",
                str(staged_upload),
                "--xp-evidence-output-dir",
                str(evidence_output),
            ]
        )
    )

    assert (
        f"artifact directory must not point inside reserved workspace directory '.github': {assets}"
    ) in errors
    assert (
        f"XP evidence file must not point inside reserved workspace directory '.github': {evidence}"
    ) in errors
    assert (
        "XP evidence directory must not point inside reserved workspace directory "
        f"'.github': {evidence_dir}"
    ) in errors
    assert (
        "staged upload output directory must not point inside reserved workspace directory "
        f"'.github': {staged_upload}"
    ) in errors
    assert (
        "XP evidence output directory must not point inside reserved workspace directory "
        f"'.github': {evidence_output}"
    ) in errors
    assert record == {}


def test_make_platform_verified_evidence_record_rejects_symlinked_artifact_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    artifact_parent = tmp_path / "artifact-parent"
    assets = artifact_parent / "linux"
    assets.mkdir(parents=True)

    def fake_is_symlink(self: Path) -> bool:
        return self == artifact_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = maker.validate_common_args(
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
                "--release-source-head-sha",
                "a" * 40,
                "--release-source-run-attempt",
                "1",
            ]
        )
    )

    assert f"artifact directory path must not contain symlinked directories: {artifact_parent}" in errors


def test_make_platform_verified_evidence_record_rejects_path_qualified_release_base_url(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()

    errors = maker.validate_common_args(
        maker.parse_args(
            [
                "--target",
                "linux-i386",
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/nested/releases/download/{tag}",
                "--release-source-head-sha",
                "a" * 40,
                "--release-source-run-attempt",
                "1",
            ]
        )
    )

    assert (
        "--release-asset-base-url must be exactly "
        f"https://github.com/<owner>/<repo>/releases/download/{tag}"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_malformed_release_base_repository_slug(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()

    errors = maker.validate_common_args(
        maker.parse_args(
            [
                "--target",
                "linux-i386",
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace?download=1/releases/download/{tag}",
                "--release-source-head-sha",
                "a" * 40,
                "--release-source-run-attempt",
                "1",
            ]
        )
    )

    assert (
        "--release-asset-base-url must be exactly "
        f"https://github.com/<owner>/<repo>/releases/download/{tag}"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_release_base_url_tag_mismatch(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()

    errors = maker.validate_common_args(
        maker.parse_args(
            [
                "--target",
                "linux-i386",
                "--release-tag",
                tag,
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                "https://github.com/example/remote-ops-workspace/releases/download/v9.9.9",
                "--release-source-head-sha",
                "a" * 40,
                "--release-source-run-attempt",
                "1",
            ]
        )
    )

    assert f"--release-asset-base-url release tag must match --release-tag {tag}" in errors


def test_make_platform_verified_evidence_record_rejects_malformed_linux_workflow_run_urls(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    args = maker.parse_args(
        [
            "--target",
            "linux-i386",
            "--release-tag",
            tag,
            "--assets-dir",
            str(tmp_path / "linux-i386" / tag / "artifacts"),
            "--release-asset-base-url",
            f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
            "--workflow-run-url",
            "https://github.com/example/remote-ops-workspace/actions/runs/not-a-run-id",
            "--release-source-workflow-run-url",
            "https://github.com/example/remote-ops-workspace/actions/runs/not-a-run-id",
            "--release-source-head-sha",
            "a" * 40,
            "--release-source-run-attempt",
            "1",
        ]
    )

    errors = maker.validate_linux_args(args)

    assert "--workflow-run-url must be a GitHub Actions run URL" in errors
    assert "--release-source-workflow-run-url must be a GitHub Actions run URL" in errors


def test_make_platform_verified_evidence_record_rejects_malformed_xp_release_source_workflow_run_url(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    args = maker.parse_args(
        [
            "--target",
            target,
            "--release-tag",
            tag,
            "--assets-dir",
            str(tmp_path / target / tag / "artifacts"),
            "--release-asset-base-url",
            f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
            "--release-source-workflow-run-url",
            "https://github.com/example/remote-ops-workspace/actions/workflows/xp-native-evidence.yml",
            "--release-source-artifact-name",
            f"xp-native-evidence-{target}-{tag}",
            "--release-source-head-sha",
            "a" * 40,
            "--release-source-run-attempt",
            "1",
        ]
    )

    errors = maker.validate_xp_args(args)

    assert "--release-source-workflow-run-url must be a GitHub Actions run URL" in errors


def test_make_platform_verified_evidence_record_rejects_linux_workflow_run_repository_mismatch(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    args = maker.parse_args(
        [
            "--target",
            "linux-i386",
            "--release-tag",
            tag,
            "--assets-dir",
            str(tmp_path / "linux-i386" / tag / "artifacts"),
            "--release-asset-base-url",
            f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
            "--workflow-run-url",
            "https://github.com/other/remote-ops-workspace/actions/runs/12345",
            "--release-source-workflow-run-url",
            "https://github.com/other/remote-ops-workspace/actions/runs/12345",
            "--release-source-head-sha",
            "a" * 40,
            "--release-source-run-attempt",
            "1",
        ]
    )

    errors = maker.validate_linux_args(args)

    assert (
        "--workflow-run-url repository must match --release-asset-base-url repository "
        "example/remote-ops-workspace, got other/remote-ops-workspace"
    ) in errors
    assert (
        "--release-source-workflow-run-url repository must match --release-asset-base-url repository "
        "example/remote-ops-workspace, got other/remote-ops-workspace"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_xp_release_source_repository_mismatch(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x64"
    tag = f"v{artifact_checker.read_project_version()}"
    args = maker.parse_args(
        [
            "--target",
            target,
            "--release-tag",
            tag,
            "--assets-dir",
            str(tmp_path / target / tag / "artifacts"),
            "--release-asset-base-url",
            f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
            "--release-source-workflow-run-url",
            "https://github.com/other/remote-ops-workspace/actions/runs/12345",
            "--release-source-artifact-name",
            f"xp-native-evidence-{target}-{tag}",
            "--release-source-head-sha",
            "a" * 40,
            "--release-source-run-attempt",
            "1",
        ]
    )

    errors = maker.validate_xp_args(args)

    assert (
        "--release-source-workflow-run-url repository must match --release-asset-base-url repository "
        "example/remote-ops-workspace, got other/remote-ops-workspace"
    ) in errors


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
                "--release-source-run-attempt",
                "1",
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


def test_make_platform_verified_evidence_record_rejects_extra_xp_artifact_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets = Path("native-dist") / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    _write_artifact_set(assets, names)
    (assets / "unexpected.txt").write_text("extra\n", encoding="utf-8")
    evidence = Path("evidence") / target / tag / "xp-evidence.json"
    evidence.parent.mkdir(parents=True)
    data = _valid_xp_evidence(target, "x86", "SP3", tag, names)
    _attach_smoke_evidence_files(evidence.parent, data)
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
                "--release-source-run-attempt",
                "1",
                "--xp-evidence",
                str(evidence),
                "--xp-evidence-dir",
                str(evidence.parent),
            ]
        )
    )

    assert record == {}
    assert f"{target} artifacts include unexpected files: ['unexpected.txt']" in errors


def test_make_platform_verified_evidence_record_rejects_xp_artifact_validation_assets_dir_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets = Path("native-dist") / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    _write_artifact_set(assets, names)
    evidence = Path("evidence") / target / tag / "xp-evidence.json"
    evidence.parent.mkdir(parents=True)
    data = _valid_xp_evidence(target, "x86", "SP3", tag, names)
    data["artifact_validation"]["command"] = data["artifact_validation"]["command"].replace(
        f"native-dist/windows-xp/{target}/{tag}",
        f"staged/{target}/{tag}/artifacts",
    )
    _attach_smoke_evidence_files(evidence.parent, data)
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
                "--release-source-run-attempt",
                "1",
                "--xp-evidence",
                str(evidence),
                "--xp-evidence-dir",
                str(evidence.parent),
            ]
        )
    )

    assert record == {}
    assert (
        f"{target} XP evidence artifact_validation.command --assets-dir must match "
        f"--assets-dir {assets.as_posix()}, got ['staged/{target}/{tag}/artifacts']"
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
                "--release-source-run-attempt",
                "1",
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


def test_make_platform_verified_evidence_record_rejects_unscoped_linux_generator_inputs(
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
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
    )
    staged_upload = tmp_path / "upload"

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
                "--release-source-run-attempt",
                "1",
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
                "--staged-upload-out-dir",
                str(staged_upload),
            ]
        )
    )

    assert record == {}
    assert any("artifact directory must include target path segment 'linux-i386'" in error for error in errors)
    assert any("artifact directory must include release_tag path segment" in error for error in errors)
    assert any("Linux builder evidence file must include target path segment 'linux-i386'" in error for error in errors)
    assert any("Linux smoke evidence file must include release_tag path segment" in error for error in errors)
    assert any(
        "staged upload output directory must include target path segment 'linux-i386'" in error
        for error in errors
    )
    assert any("staged upload output directory must include release_tag path segment" in error for error in errors)


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
                "--release-source-run-attempt",
                "1",
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


def test_make_platform_verified_evidence_record_rejects_unscoped_xp_generator_inputs(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_names(artifact_checker, target, tag)
    assets = tmp_path / "xp"
    assets.mkdir()
    _write_artifact_set(assets, names)
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    evidence = evidence_dir / "xp-evidence.json"
    data = _valid_xp_evidence(target, "x86", "SP3", tag, names)
    data["artifact_validation"]["command"] = data["artifact_validation"]["command"].replace(
        f"native-dist/windows-xp/{target}/{tag}",
        assets.as_posix(),
    )
    _attach_smoke_evidence_files(evidence_dir, data)
    evidence.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    staged_upload = tmp_path / "upload"
    evidence_output = tmp_path / "output"

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
                "--release-source-run-attempt",
                "1",
                "--xp-evidence",
                str(evidence),
                "--xp-evidence-dir",
                str(evidence_dir),
                "--staged-upload-out-dir",
                str(staged_upload),
                "--xp-evidence-output-dir",
                str(evidence_output),
            ]
        )
    )

    assert record == {}
    assert any(
        "artifact directory must include target path segment 'windows-xp-native-x86'" in error
        for error in errors
    )
    assert any("XP evidence file must include release_tag path segment" in error for error in errors)
    assert any("XP evidence directory must include target path segment 'windows-xp-native-x86'" in error for error in errors)
    assert any(
        "staged upload output directory must include target path segment 'windows-xp-native-x86'" in error
        for error in errors
    )
    assert any("XP evidence output directory must include release_tag path segment" in error for error in errors)


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
                "--release-source-run-attempt",
                "1",
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
                "--release-source-run-attempt",
                "1",
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
                "--release-source-run-attempt",
                "1",
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
        "--target linux-i386 --workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--workflow-run-attempt 1 --source-head-sha {'a' * 40} "
        f"--builder-evidence {builder_evidence.as_posix()}"
        in error
        for error in errors
    )


def test_make_platform_verified_evidence_record_rejects_missing_linux_smoke_security_proof(
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
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
    )
    missing_line = "native installer smoke TLS preferred modern profiles: TLS 1.3"
    smoke_evidence.write_text(
        smoke_evidence.read_text(encoding="utf-8").replace(f"{missing_line}\n", ""),
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
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--release-source-run-attempt",
                "1",
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
    assert f"linux-i386 linux_smoke_evidence missing required line: {missing_line}" in errors


def test_linux_smoke_log_rejects_required_line_suffix_spoof(tmp_path: Path) -> None:
    maker = _load_maker()
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(smoke_evidence, "linux-i386", {})
    text = smoke_evidence.read_text(encoding="utf-8")
    required_line = "native installer smoke passed for Linux i386"
    spoofed_text = text.replace(required_line, f"{required_line} with suffix")
    native_smoke_command = text.splitlines()[0].removeprefix("native installer smoke command: ")

    errors = maker.check_linux_smoke_log_text(
        "linux-i386",
        "v1.0.2",
        native_smoke_command,
        "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        spoofed_text,
        workflow_run_attempt=1,
        source_head_sha="a" * 40,
    )

    assert f"linux-i386 linux_smoke_evidence missing required line: {required_line}" in errors


def test_linux_smoke_log_rejects_duplicate_required_line(tmp_path: Path) -> None:
    maker = _load_maker()
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(smoke_evidence, "linux-i386", {})
    text = smoke_evidence.read_text(encoding="utf-8")
    required_line = "native installer smoke passed for Linux i386"
    duplicated_text = f"{text}{required_line}\n"
    native_smoke_command = text.splitlines()[0].removeprefix("native installer smoke command: ")

    errors = maker.check_linux_smoke_log_text(
        "linux-i386",
        "v1.0.2",
        native_smoke_command,
        "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        duplicated_text,
        workflow_run_attempt=1,
        source_head_sha="a" * 40,
    )

    assert (
        "linux-i386 linux_smoke_evidence must include exactly one required line: "
        "native installer smoke passed for Linux i386 (got 2)"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_missing_linux_smoke_git_head_proof(
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
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
    )
    missing_line = f"native installer smoke git head sha: {'a' * 40}"
    smoke_evidence.write_text(
        smoke_evidence.read_text(encoding="utf-8").replace(f"{missing_line}\n", ""),
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
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--release-source-run-attempt",
                "1",
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
    assert f"linux-i386 linux_smoke_evidence missing required line: {missing_line}" in errors


def test_make_platform_verified_evidence_record_rejects_missing_linux_smoke_security_provenance(
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
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
    )
    missing_line = "native installer smoke CVE review reference: vendor-cve-advisory-review-2026-06"
    smoke_evidence.write_text(
        smoke_evidence.read_text(encoding="utf-8").replace(f"{missing_line}\n", ""),
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
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--release-source-run-attempt",
                "1",
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
        "linux-i386 linux_smoke_evidence missing required line: "
        "native installer smoke CVE review reference: <expected security value>"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_forbidden_linux_smoke_security_proof(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-armhf"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()
    names = _required_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder_evidence = tmp_path / "builder-identity-linux-armhf.json"
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = tmp_path / "native-smoke-linux-armhf.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
    )
    smoke_evidence.write_text(
        smoke_evidence.read_text(encoding="utf-8")
        + "native installer smoke TLS minimum modern profiles: TLS 1.0\n"
        + "native installer smoke weak crypto global default: true\n",
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
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--release-source-run-attempt",
                "1",
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

    assert record == {}
    assert (
        "linux-armhf linux_smoke_evidence contains forbidden security proof line: "
        "native installer smoke TLS minimum modern profiles: TLS 1.0"
    ) in errors
    assert (
        "linux-armhf linux_smoke_evidence contains forbidden security proof line: "
        "native installer smoke weak crypto global default: true"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_case_variant_forbidden_linux_smoke_security_proof(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-armhf"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()
    names = _required_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder_evidence = tmp_path / "builder-identity-linux-armhf.json"
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = tmp_path / "native-smoke-linux-armhf.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
    )
    smoke_evidence.write_text(
        smoke_evidence.read_text(encoding="utf-8")
        + "Native Installer Smoke Weak Crypto Global Default: TRUE\n",
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
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--release-source-run-attempt",
                "1",
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

    assert record == {}
    assert (
        "linux-armhf linux_smoke_evidence contains forbidden security proof line: "
        "native installer smoke weak crypto global default: true"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_wrong_linux_smoke_runtime(
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
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
    )
    smoke_evidence.write_text(
        smoke_evidence.read_text(encoding="utf-8").replace(
            "native installer smoke uname machine: i686",
            "native installer smoke uname machine: x86_64",
        ),
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
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--release-source-run-attempt",
                "1",
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
        "linux-i386 linux_smoke_evidence native installer smoke uname machine "
        "must be one of ['i386', 'i486', 'i586', 'i686', 'x86'], got 'x86_64'"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_wrong_linux_smoke_identity(
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
    _write_builder_evidence(builder_evidence, target)
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
    )
    smoke_evidence.write_text(
        smoke_evidence.read_text(encoding="utf-8")
        .replace(
            "native installer smoke evidence run id: linux-i386-1-0-2-run-12345",
            "native installer smoke evidence run id: linux-i386-1-0-2-run-99999",
        )
        .replace(
            "native installer smoke observed at utc: 2026-06-20T12:00:00Z",
            "native installer smoke observed at utc: not-a-time",
        ),
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
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--release-source-run-attempt",
                "1",
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
        "linux-i386 linux_smoke_evidence native installer smoke evidence run id "
        "must be 'linux-i386-1-0-2-run-12345', got 'linux-i386-1-0-2-run-99999'"
    ) in errors
    assert (
        "linux-i386 linux_smoke_evidence native installer smoke observed at utc "
        "must be UTC ISO-8601 seconds ending in Z, got 'not-a-time'"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_linux_builder_smoke_identity_drift(
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
    _write_builder_evidence(builder_evidence, target)
    builder_data = json.loads(builder_evidence.read_text(encoding="utf-8"))
    builder_data["host_identity"]["evidence_run_id"] = "linux-i386-1-0-2-run-99999"
    builder_data["host_identity"]["observed_at_utc"] = "2026-06-20T12:30:00Z"
    builder_evidence.write_text(json.dumps(builder_data, indent=2) + "\n", encoding="utf-8")
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
                "--release-source-run-attempt",
                "1",
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
        "linux-i386 linux_smoke_evidence native installer smoke evidence run id must match "
        "builder_identity.host_identity.evidence_run_id 'linux-i386-1-0-2-run-99999', "
        "got 'linux-i386-1-0-2-run-12345'"
    ) in errors
    assert (
        "linux-i386 linux_smoke_evidence native installer smoke observed at utc must not be earlier than "
        "builder_identity.host_identity.observed_at_utc '2026-06-20T12:30:00Z', "
        "got '2026-06-20T12:00:00Z'"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_linux_builder_smoke_security_drift(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-armhf"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "linux"
    assets.mkdir()
    names = _required_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder_evidence = tmp_path / "builder-identity-linux-armhf.json"
    _write_builder_evidence(builder_evidence, target)
    builder_data = json.loads(builder_evidence.read_text(encoding="utf-8"))
    builder_data["security_patch_evidence"]["security_update_channel"] = "vendor-security-updates-2026-07"
    builder_data["security_patch_evidence"]["cve_review_reference"] = "vendor-cve-advisory-review-2026-07"
    builder_evidence.write_text(json.dumps(builder_data, indent=2) + "\n", encoding="utf-8")
    smoke_evidence = tmp_path / "native-smoke-linux-armhf.log"
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
                "--release-source-run-attempt",
                "1",
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

    assert record == {}
    assert (
        "linux-armhf linux_smoke_evidence native installer smoke security update channel must match "
        "builder_identity.security_patch_evidence.security_update_channel 'vendor-security-updates-2026-07', "
        "got 'vendor-security-updates-2026-06'"
    ) in errors
    assert (
        "linux-armhf linux_smoke_evidence native installer smoke CVE review reference must match "
        "builder_identity.security_patch_evidence.cve_review_reference 'vendor-cve-advisory-review-2026-07', "
        "got 'vendor-cve-advisory-review-2026-06'"
    ) in errors


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
                "--release-source-run-attempt",
                "1",
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


def test_make_platform_verified_evidence_record_rejects_builder_observed_git_head_sha_mismatch(
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
    _write_builder_evidence(builder_evidence, target, observed_git_head_sha="b" * 40)
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
                "--release-source-run-attempt",
                "1",
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
        f"{target} builder evidence observed_git_head_sha must match --release-source-head-sha "
        f"{'a' * 40}, got {('b' * 40)!r}"
    ) in errors


def test_make_platform_verified_evidence_record_rejects_dirty_builder_git_worktree(
    tmp_path: Path,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = "v1.0.2"
    assets = tmp_path / "linux"
    assets.mkdir()
    names = _required_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder_evidence = tmp_path / "builder-identity-linux-i386.json"
    _write_builder_evidence(builder_evidence, target, git_worktree_clean=False)
    smoke_evidence = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
        workflow_run_attempt=1,
        source_head_sha="a" * 40,
    )

    errors, record = maker.build_evidence_record(
        maker.parse_args(
            [
                "--target",
                target,
                "--release-tag",
                tag,
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--release-source-head-sha",
                "a" * 40,
                "--release-source-run-attempt",
                "1",
                "--assets-dir",
                str(assets),
                "--release-asset-base-url",
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
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
    assert f"{target} builder evidence git_worktree_clean must be true" in errors


def test_append_platform_verified_evidence_record_updates_registry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-armhf"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets = Path("staged") / target / tag / "artifacts"
    assets.mkdir(parents=True)
    _write_artifact_set(assets, names)
    builder_evidence = Path("evidence") / target / tag / "builder-identity-linux-armhf.json"
    builder_evidence.parent.mkdir(parents=True)
    _write_builder_evidence(
        builder_evidence,
        target,
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/67890",
    )
    smoke_evidence = Path("evidence") / target / tag / "native-smoke-linux-armhf.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/67890",
    )
    registry = Path("platform_verified_evidence.json")
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
                "--release-source-run-attempt",
                "1",
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
    record["finalized_record_release_asset_url"] = (
        f"https://github.com/example/remote-ops-workspace/releases/download/{tag}/"
        f"platform-verified-evidence-{target}-final.json"
    )

    append_errors = maker.append_record_to_registry(record, registry_path=registry)

    assert append_errors == []
    updated = json.loads(registry.read_text(encoding="utf-8"))
    assert [entry["target"] for entry in updated["accepted_evidence"]] == [target]


def test_append_platform_verified_evidence_record_rejects_unfinalized_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "linux-armhf"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets = Path("staged") / target / tag / "artifacts"
    assets.mkdir(parents=True)
    _write_artifact_set(assets, names)
    builder_evidence = Path("evidence") / target / tag / "builder-identity-linux-armhf.json"
    builder_evidence.parent.mkdir(parents=True)
    _write_builder_evidence(
        builder_evidence,
        target,
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/67890",
    )
    smoke_evidence = Path("evidence") / target / tag / "native-smoke-linux-armhf.log"
    _write_linux_smoke_evidence(
        smoke_evidence,
        target,
        _smoke_artifact_hashes(assets, names),
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/67890",
    )
    registry = Path("platform_verified_evidence.json")
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
                "--release-source-run-attempt",
                "1",
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


def test_make_platform_verified_evidence_record_cli_refuses_to_append_generated_candidate(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    maker = _load_maker()
    registry = tmp_path / "platform_verified_evidence.json"
    registry.write_text(json.dumps(_empty_registry(), indent=2) + "\n", encoding="utf-8")
    output = tmp_path / "platform-verified-evidence-linux-i386.json"

    def fake_build_evidence_record(_args):
        return [], {
            "target": "linux-i386",
            "status": "accepted",
            "readiness_percent": 100.0,
            "review_bundle": {},
            "finalized_record_release_asset_url": (
                "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
                "platform-verified-evidence-linux-i386-final.json"
            ),
        }

    monkeypatch.setattr(maker, "build_evidence_record", fake_build_evidence_record)

    exit_code = maker.main(
        [
            "--target",
            "linux-i386",
            "--release-tag",
            "v1.0.2",
            "--assets-dir",
            str(tmp_path / "artifacts"),
            "--release-asset-base-url",
            "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
            "--append-registry",
            "--registry",
            str(registry),
            "--out",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "linux-i386 generated evidence cannot be appended by this generator" in captured.err
    assert "scripts/finalize_platform_verified_evidence_record.py --append-registry" in captured.err
    assert not output.exists()
    assert json.loads(registry.read_text(encoding="utf-8"))["accepted_evidence"] == []


def test_make_platform_verified_evidence_record_cli_rejects_wrong_output_file_name(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    maker = _load_maker()
    output = tmp_path / "generated-candidate.json"

    def fake_build_evidence_record(_args):
        return [], {"target": "linux-i386", "status": "accepted", "readiness_percent": 100.0}

    monkeypatch.setattr(maker, "build_evidence_record", fake_build_evidence_record)

    exit_code = maker.main(
        [
            "--target",
            "linux-i386",
            "--release-tag",
            "v1.0.2",
            "--assets-dir",
            str(tmp_path / "artifacts"),
            "--release-asset-base-url",
            "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
            "--out",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert not output.exists()
    assert (
        "platform verified evidence record: platform verified evidence record output file name must be "
        "platform-verified-evidence-linux-i386.json, got 'generated-candidate.json'"
    ) in captured.err


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


def test_make_platform_verified_evidence_record_rejects_unsafe_output_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    output = tmp_path / "platform-verified-evidence-linux-i386.json"
    output.write_text("{}\n", encoding="utf-8")

    def fake_is_symlink(self: Path) -> bool:
        return self == output

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = maker.check_text_output_path(output, "platform verified evidence record output file")

    assert errors == [
        f"platform verified evidence record output file must not be a symlink: {output}"
    ]


def test_make_platform_verified_evidence_record_rejects_symlinked_output_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    output_parent = tmp_path / "linked-output" / "records"
    output = output_parent / "platform-verified-evidence-linux-i386.json"

    def fake_is_symlink(self: Path) -> bool:
        return self == tmp_path / "linked-output"

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = maker.check_text_output_path(output, "platform verified evidence record output file")

    assert errors == [
        "platform verified evidence record output file directory path must not contain symlinked directories: "
        f"{tmp_path / 'linked-output'}"
    ]


def test_append_platform_verified_evidence_record_rejects_symlinked_registry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    registry = tmp_path / "platform_verified_evidence.json"
    registry.write_text(json.dumps(_empty_registry(), indent=2) + "\n", encoding="utf-8")

    def fake_is_symlink(self: Path) -> bool:
        return self == registry

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = maker.append_record_to_registry({"target": "linux-i386"}, registry_path=registry)

    assert errors == [f"platform verified evidence registry must not be a symlink: {registry}"]


def test_append_platform_verified_evidence_record_rejects_symlinked_registry_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_maker()
    linked_parent = tmp_path / "linked-config"
    registry_parent = linked_parent / "configs"
    registry = registry_parent / "platform_verified_evidence.json"

    def fake_is_symlink(self: Path) -> bool:
        return self == linked_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = maker.append_record_to_registry({"target": "linux-i386"}, registry_path=registry)

    assert errors == [
        f"platform verified evidence registry directory path must not contain symlinked directories: {linked_parent}"
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
                "--release-source-run-attempt",
                "1",
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
            **_manifest_record_metadata(name),
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


def _manifest_record_metadata(name: str) -> dict[str, str]:
    if name.endswith(".tar.gz"):
        return {"architecture": _artifact_architecture(name), "format": "tar.gz"}
    if name.endswith(".AppImage"):
        return {"architecture": _artifact_architecture(name), "format": "AppImage"}
    if name.endswith(".deb"):
        return {"architecture": _artifact_architecture(name), "format": "deb"}
    if name.endswith(".rpm"):
        return {"architecture": _artifact_architecture(name), "format": "rpm"}
    if name.endswith(".zip"):
        return {"architecture": _artifact_architecture(name), "format": "zip"}
    return {}


def _artifact_architecture(name: str) -> str:
    if "-linux-i386." in name:
        return "i386"
    if "-linux-i686." in name or "-linux-i686-native." in name:
        return "i686"
    if "-linux-armhf." in name or "-linux-armhf-native." in name:
        return "armhf"
    if "-linux-armv7hl." in name:
        return "armv7hl"
    if "-windows-xp-x86-native." in name:
        return "x86"
    if "-windows-xp-x64-native." in name:
        return "x64"
    return ""


def _write_builder_evidence(
    path: Path,
    target: str,
    *,
    release_tag: str = "v1.0.2",
    workflow_run_url: str = "https://github.com/example/remote-ops-workspace/actions/runs/12345",
    workflow_run_attempt: int = 1,
    source_head_sha: str = "a" * 40,
    observed_git_head_sha: str | None = None,
    git_worktree_clean: bool = True,
) -> None:
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    data = {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": workflow_run_url,
        "workflow_run_attempt": workflow_run_attempt,
        "workflow_ref": (
            "example/remote-ops-workspace/.github/workflows/"
            f"extended-platform-evidence.yml@{source_head_sha}"
        ),
        "workflow_sha": source_head_sha,
        "source_head_sha": source_head_sha,
        "observed_git_head_sha": observed_git_head_sha or source_head_sha,
        "git_worktree_clean": git_worktree_clean,
        "host_identity": _linux_host_identity(target, release_tag, workflow_run_url, workflow_run_attempt),
        "sudo_non_interactive": True,
        "sys_platform": "linux",
        "platform_machine": machine,
        "uname_machine": machine,
        "dpkg_architecture": dpkg_arch,
        "userland_bits": "32",
        "os_release": "Debian GNU/Linux 12 (bookworm)",
        "kernel_release": "6.1.0-i386-ci",
        "glibc_version": "glibc 2.36",
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


def _linux_host_identity(
    target: str,
    release_tag: str,
    workflow_run_url: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    run_id = workflow_run_url.rstrip("/").split("/")[-1]
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": workflow_run_url,
        "workflow_run_attempt": workflow_run_attempt,
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
    workflow_run_attempt: int = 1,
    source_head_sha: str = "a" * 40,
    builder_evidence: Path | str | None = None,
) -> None:
    arch = "i386" if target == "linux-i386" else "armhf"
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    run_id = workflow_run_url.rstrip("/").rsplit("/", 1)[-1]
    evidence_run_id = f"{target}-1-0-2-run-{run_id}"
    builder_evidence_path = (
        Path(builder_evidence).as_posix()
        if builder_evidence is not None
        else (path.parent / f"builder-identity-{target}.json").as_posix()
    )
    artifact_lines = [
        f"native installer smoke artifact sha256: {name} {artifact_hashes[name]}"
        for name in sorted(artifact_hashes)
    ]
    path.write_text(
        "\n".join(
            [
                f"native installer smoke command: bash scripts/smoke_linux_native.sh --arch {arch} "
                f"--dist native-dist/linux --target {target} --workflow-run-url {workflow_run_url} "
                f"--workflow-run-attempt {workflow_run_attempt} "
                f"--source-head-sha {source_head_sha} --builder-evidence {builder_evidence_path}",
                "native installer smoke release: v1.0.2",
                f"native installer smoke target arch: {arch}",
                f"native installer smoke target: {target}",
                f"native installer smoke workflow run: {workflow_run_url}",
                f"native installer smoke workflow run attempt: {workflow_run_attempt}",
                f"native installer smoke source head sha: {source_head_sha}",
                f"native installer smoke git head sha: {source_head_sha}",
                f"native installer smoke host label: {target}-builder",
                f"native installer smoke evidence run id: {evidence_run_id}",
                "native installer smoke observed at utc: 2026-06-20T12:00:00Z",
                f"native installer smoke uname machine: {machine}",
                f"native installer smoke dpkg architecture: {dpkg_arch}",
                "native installer smoke userland bits: 32",
                "native installer smoke os release: Debian GNU/Linux 12 (bookworm)",
                "native installer smoke kernel release: 6.1.0-i386-ci",
                "native installer smoke glibc version: glibc 2.36",
                "native installer smoke python ssl openssl: OpenSSL 3.0.13",
                "native installer smoke openssl cli version: OpenSSL 3.0.13",
                "native installer smoke security update channel: vendor-security-updates-2026-06",
                "native installer smoke CVE review reference: vendor-cve-advisory-review-2026-06",
                "native installer smoke TLS minimum modern profiles: TLS 1.2",
                "native installer smoke TLS preferred modern profiles: TLS 1.3",
                "native installer smoke legacy compatibility profile: isolated-opt-in",
                "native installer smoke legacy crypto scope: profile-only",
                "native installer smoke weak crypto global default: false",
                "native installer smoke modern defaults unchanged: true",
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
    host_identity = {
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
    }
    release_source = _xp_release_source()
    security = _xp_security_patch_evidence()
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "release_source": release_source,
        "os": os_record,
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "Separate legacy XP-capable native host toolchain",
        },
        "host_identity": host_identity,
        "artifact_validation": {
            "passed": True,
            "command": (
                f"python scripts/check_platform_promotion_artifacts.py --target {target} "
                f"--assets-dir native-dist/windows-xp/{target}/{release_tag} --tag {release_tag} --strict"
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
                    f"--proof-file xp-smoke-proof/{smoke_id}.txt "
                    f"--host-label {host_identity['host_label']} "
                    f"--evidence-run-id {host_identity['evidence_run_id']} "
                    f"--observed-at-utc {host_identity['observed_at_utc']} "
                    f"--source-workflow-run-url {release_source['workflow_run_url']} "
                    f"--source-head-sha {release_source['head_sha']} "
                    f"--source-run-attempt {release_source['run_attempt']} "
                    f"--security-update-channel {security['security_update_channel']} "
                    f"--cve-review-reference {security['cve_review_reference']} "
                    f'--os-name "{os_record["name"]}" '
                    f"--os-architecture {os_record['architecture']} "
                    f"--os-service-pack {os_record['service_pack']}"
                    + (
                        f' --os-edition "{os_record["edition"]}"'
                        if "edition" in os_record
                        else ""
                    )
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
            "patch_evidence": security,
        },
    }


def _xp_release_source() -> dict[str, object]:
    return {
        "workflow": ".github/workflows/xp-native-evidence.yml",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/54321",
        "head_sha": "a" * 40,
        "run_attempt": 1,
    }


def _attach_smoke_evidence_files(root: Path, evidence: dict[str, Any]) -> None:
    host_identity = evidence["host_identity"]
    release_source = evidence["release_source"]
    host_probe_lines = _xp_host_probe_lines(evidence["target"], evidence["os"])
    for result in evidence["smoke_results"]:
        path = root / result["evidence_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        security_lines = _xp_security_smoke_lines(str(result["id"]))
        path.write_text(
            f"xp smoke target: {evidence['target']}\n"
            f"xp smoke release: {evidence['release_tag']}\n"
            f"xp smoke id: {result['id']}\n"
            f"xp smoke os name: {evidence['os']['name']}\n"
            f"xp smoke os architecture: {evidence['os']['architecture']}\n"
            f"xp smoke os service pack: {evidence['os']['service_pack']}\n"
            + (
                f"xp smoke os edition: {evidence['os']['edition']}\n"
                if "edition" in evidence["os"]
                else ""
            )
            + host_probe_lines
            + f"xp smoke host label: {host_identity['host_label']}\n"
            f"xp smoke evidence run id: {host_identity['evidence_run_id']}\n"
            f"xp smoke observed at utc: {host_identity['observed_at_utc']}\n"
            f"xp smoke source workflow run: {release_source['workflow_run_url']}\n"
            f"xp smoke source head sha: {release_source['head_sha']}\n"
            f"xp smoke source run attempt: {release_source['run_attempt']}\n"
            f"{_artifact_manifest_smoke_lines(evidence, str(result['id']))}"
            f"{security_lines}"
            f"{result['id']} passed on Windows XP evidence host\n",
            encoding="utf-8",
        )
        result["evidence_sha256"] = _sha256(path)


def _xp_host_probe_lines(target: str, os_identity: dict[str, Any]) -> str:
    if target.endswith("x64"):
        ver_output = "Microsoft Windows [Version 5.2.3790]"
        processor_architecture = "AMD64"
        caption = "Microsoft Windows XP Professional x64 Edition"
    else:
        ver_output = "Microsoft Windows XP [Version 5.1.2600]"
        processor_architecture = "x86"
        caption = "Microsoft Windows XP Professional"
    service_pack = str(os_identity["service_pack"]).removeprefix("SP")
    return (
        "xp smoke host probe command: ver\n"
        f"xp smoke host probe output: {ver_output}\n"
        f"xp smoke processor architecture env: {processor_architecture}\n"
        "xp smoke processor architecture w6432 env: \n"
        f"xp smoke wmic os caption: {caption}\n"
        f"xp smoke wmic os csdversion: Service Pack {service_pack}\n"
    )


def _xp_security_smoke_lines(smoke_id: str) -> str:
    if smoke_id == "legacy_crypto_profile_scoped":
        return (
            "legacy compatibility profile: isolated-opt-in\n"
            "legacy crypto scope: profile-only\n"
            "weak crypto global default: false\n"
            "security update channel: vendor-security-updates-2026-06\n"
            "CVE review reference: vendor-cve-advisory-review-2026-06\n"
        )
    if smoke_id == "modern_defaults_unchanged":
        return (
            "modern TLS minimum: TLS 1.2\n"
            "modern TLS preferred: TLS 1.3\n"
            "modern defaults unchanged: true\n"
            "weak crypto global default: false\n"
            "security update channel: vendor-security-updates-2026-06\n"
            "CVE review reference: vendor-cve-advisory-review-2026-06\n"
        )
    return ""


def _artifact_manifest_smoke_lines(evidence: dict[str, Any], smoke_id: str) -> str:
    if smoke_id != "artifact_manifest_validation":
        return ""
    return (
        "".join(f"xp smoke artifact file: {name}\n" for name in evidence["artifacts"])
        + "xp smoke artifact manifest validated: true\n"
        + "xp smoke artifact sha256s validated: true\n"
    )


def _empty_registry() -> dict[str, Any]:
    registry = json.loads((ROOT / "configs" / "platform_verified_evidence.json").read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "policy": registry["policy"],
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
        "security_update_channel": "vendor-security-updates-2026-06",
        "cve_review_reference": "vendor-cve-advisory-review-2026-06",
    }


def _xp_security_patch_evidence() -> dict[str, object]:
    return {
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
        "security_update_channel": "vendor-security-updates-2026-06",
        "cve_review_reference": "vendor-cve-advisory-review-2026-06",
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
