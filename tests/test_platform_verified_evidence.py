from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

POLICY = (
    "Only accepted evidence records in this file can promote Linux i386, Linux armhf, "
    "or Windows XP native-host readiness. Accepted records must include release asset URLs "
    "and per-artifact SHA-256 digests, Linux builder identity evidence and builder identity "
    "SHA-256 when applicable, Linux workflow dispatch inputs when applicable, XP evidence "
    "bundle SHA-256 digests, XP evidence contract SHA-256, and XP evidence summary binding "
    "when applicable, and the promotion config SHA-256; "
    "each accepted record must have a unique target, all release evidence for one record must "
    "use the same GitHub repository, and Windows XP x86/x64 pairs must use the same release_tag. "
    "Empty means no promotion."
)


def test_platform_verified_evidence_checker_passes_empty_registry() -> None:
    checker = _load_platform_verified_evidence_checker()

    assert checker.main() == 0


def test_platform_verified_evidence_accepts_linux_i386_record() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [_linux_record("linux-i386")],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert errors == []


def test_platform_verified_evidence_rejects_missing_promotion_config_hash() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["promotion_config_sha256"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 promotion_config_sha256 must be a SHA-256 hex digest" in errors


def test_platform_verified_evidence_rejects_stale_promotion_config_hash() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["promotion_config_sha256"] = "0" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 promotion_config_sha256 must match current promotion config SHA-256" in errors


def test_platform_verified_evidence_rejects_missing_release_asset_urls() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["release_asset_urls"] = []
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf evidence must include release_asset_urls" in errors


def test_platform_verified_evidence_rejects_missing_artifact_sha256() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    del record["artifact_sha256"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf evidence must include artifact_sha256 map" in errors


def test_platform_verified_evidence_rejects_release_asset_url_tag_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_urls"][0] = record["release_asset_urls"][0].replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v9.9.9/",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("linux-i386 release asset URL tag must match release_tag v1.0.2" in error for error in errors)


def test_platform_verified_evidence_rejects_mixed_release_repositories() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["release_asset_urls"][0] = record["release_asset_urls"][0].replace(
        "github.com/example/remote-ops-workspace",
        "github.com/other/remote-ops-workspace",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("windows-xp-native-x86 release asset URLs must use one GitHub repository" in error for error in errors)


def test_platform_verified_evidence_rejects_unexpected_release_asset_url() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["release_asset_urls"].append(
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
        "remote-ops-workspace-v1.0.2-windows-xp-x86-extra.zip"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "windows-xp-native-x86 release asset URLs reference unexpected files" in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_duplicate_release_asset_url() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_urls"].append(record["release_asset_urls"][0])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("linux-i386 release asset URLs contain duplicate files" in error for error in errors)


def test_platform_verified_evidence_rejects_linux_workflow_repository_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["workflow_run_url"] = "https://github.com/other/remote-ops-workspace/actions/runs/12345"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("linux-i386 workflow_run_url repository must match release asset repository" in error for error in errors)


def test_platform_verified_evidence_rejects_missing_linux_workflow_inputs() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["workflow_inputs"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 evidence must include workflow_inputs object" in errors


def test_platform_verified_evidence_rejects_linux_workflow_input_base_url_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["workflow_inputs"]["release_asset_base_url"] = (
        "https://github.com/example/remote-ops-workspace/releases/download/v9.9.9"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "linux-armhf workflow_inputs release_asset_base_url must be a GitHub release download URL" in error
        for error in errors
    )
    assert "linux-armhf workflow_inputs release_asset_base_url must prefix every release_asset_url" in errors


def test_platform_verified_evidence_rejects_artifact_validation_command_tag_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["artifact_validation_command"] = record["artifact_validation_command"].replace(
        "--tag v1.0.2",
        "--tag v9.9.9",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf artifact_validation_command must include exactly one --tag v1.0.2, got ['v9.9.9']" in errors


def test_platform_verified_evidence_rejects_duplicate_artifact_validation_command_tag() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["artifact_validation_command"] = (
        f"{record['artifact_validation_command']} --tag v9.9.9"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 artifact_validation_command must include exactly one --tag v1.0.2, "
        "got ['v1.0.2', 'v9.9.9']"
    ) in errors


def test_platform_verified_evidence_rejects_missing_builder_identity() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["builder_identity"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 evidence must include builder_identity object" in errors


def test_platform_verified_evidence_rejects_missing_builder_identity_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["builder_identity_sha256"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity_sha256 must be a SHA-256 hex digest" in errors


def test_platform_verified_evidence_rejects_stale_builder_identity_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["builder_identity"]["python_version"] = "3.13.0"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf builder_identity_sha256 must match builder_identity JSON SHA-256" in errors


def test_platform_verified_evidence_rejects_wrong_builder_machine() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["builder_identity"]["uname_machine"] = "x86_64"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("linux-armhf builder_identity uname_machine must be one of" in error for error in errors)


def test_platform_verified_evidence_rejects_duplicate_target_records() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [_linux_record("linux-i386"), _linux_record("linux-i386")],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "accepted_evidence target must be unique: linux-i386" in errors


def test_platform_verified_evidence_rejects_mismatched_xp_pair_release_tags() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            _xp_record("windows-xp-native-x86", release_tag="v1.0.2"),
            _xp_record("windows-xp-native-x64", release_tag="v1.0.3"),
        ],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "Windows XP native evidence pair must use one release_tag, got ['v1.0.2', 'v1.0.3']" in errors


def test_platform_verified_evidence_rejects_partial_xp_pair() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["checks"] = ["artifact_validation"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("windows-xp-native-x86 evidence missing required checks" in error for error in errors)


def test_platform_verified_evidence_rejects_missing_xp_evidence_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    del record["xp_evidence_sha256"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_sha256 must be a SHA-256 hex digest" in errors


def test_platform_verified_evidence_rejects_missing_xp_contract_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    del record["xp_evidence_contract_sha256"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_contract_sha256 must be a SHA-256 hex digest" in errors


def test_platform_verified_evidence_rejects_stale_xp_contract_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["xp_evidence_contract_sha256"] = "0" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 xp_evidence_contract_sha256 must match current XP evidence contract SHA-256"
        in errors
    )


def test_platform_verified_evidence_rejects_missing_xp_smoke_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    del record["xp_smoke_evidence_sha256"]["cli_launch"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("windows-xp-native-x64 xp_smoke_evidence_sha256 missing smoke ids" in error for error in errors)


def test_platform_verified_evidence_rejects_missing_xp_evidence_summary() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    del record["xp_evidence_summary"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_summary must be an object" in errors


def test_platform_verified_evidence_rejects_xp_evidence_summary_target_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["xp_evidence_summary"]["target"] = "windows-xp-native-x86"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x64 xp_evidence_summary target must be windows-xp-native-x64" in errors


def _linux_record(target: str) -> dict[str, object]:
    arch = "i386" if target == "linux-i386" else "armhf"
    rpm_arch = "i686" if target == "linux-i386" else "armv7hl"
    artifact = "extended-linux-i386-native-evidence" if target == "linux-i386" else "extended-linux-armhf-native-evidence"
    release_asset_urls = [
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-{arch}.deb",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-{rpm_arch}.rpm",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-{arch if target == 'linux-armhf' else 'i686'}.AppImage",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-{arch if target == 'linux-armhf' else 'i686'}-native.tar.gz",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-{arch if target == 'linux-armhf' else 'i686'}-native-manifest.json",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-{arch if target == 'linux-armhf' else 'i686'}-native-SHA256SUMS.txt",
    ]
    builder_identity = _builder_identity(target)
    return {
        "target": target,
        "evidence_type": "extended-linux-native",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": "v1.0.2",
        "promotion_config_sha256": _promotion_config_sha256(),
        "workflow": ".github/workflows/extended-platform-evidence.yml",
        "workflow_inputs": {
            "target": target,
            "release_tag": "v1.0.2",
            "release_asset_base_url": "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        },
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "artifact_name": artifact,
        "runner_labels": ["self-hosted", "linux", arch],
        "builder_identity": builder_identity,
        "builder_identity_sha256": _json_sha256(builder_identity),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            "--assets-dir native-dist/linux --tag v1.0.2"
        ),
        "checks": [
            "builder_preflight",
            "native_build",
            "native_smoke",
            "artifact_validation",
            "release_asset_attachment",
        ],
        "release_asset_urls": release_asset_urls,
        "artifact_sha256": _artifact_hashes_from_urls(release_asset_urls),
    }


def _xp_record(target: str, *, release_tag: str = "v1.0.2") -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    release_asset_urls = [
        f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}/remote-ops-workspace-{release_tag}-windows-xp-{arch}-native.zip",
        f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}/remote-ops-workspace-{release_tag}-windows-xp-{arch}-native-manifest.json",
        f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}/remote-ops-workspace-{release_tag}-windows-xp-{arch}-native-SHA256SUMS.txt",
    ]
    return {
        "target": target,
        "evidence_type": "windows-xp-native-host",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": release_tag,
        "promotion_config_sha256": _promotion_config_sha256(),
        "architecture": arch,
        "separate_legacy_toolchain": True,
        "current_python_pyqt6_stack": False,
        "xp_evidence_sha256": "b" * 64,
        "xp_evidence_contract_sha256": _xp_native_evidence_contract_sha256(),
        "xp_evidence_summary": _xp_evidence_summary(target, release_tag),
        "xp_smoke_evidence_sha256": _xp_smoke_hashes(),
        "native_evidence_validation_command": (
            "python scripts/check_xp_native_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>"
        ),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            f"--assets-dir native-dist/windows-xp --tag {release_tag}"
        ),
        "checks": [
            "xp_native_evidence_validation",
            "artifact_validation",
            "vm_or_host_smoke",
            "legacy_crypto_profile_scoped",
            "modern_defaults_unchanged",
            "release_asset_attachment",
        ],
        "release_asset_urls": release_asset_urls,
        "artifact_sha256": _artifact_hashes_from_urls(release_asset_urls),
    }


def _artifact_hashes_from_urls(urls: list[str]) -> dict[str, str]:
    return {Path(url).name: "a" * 64 for url in urls}


def _xp_evidence_summary(target: str, release_tag: str = "v1.0.2") -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    return {
        "target": target,
        "release_tag": release_tag,
        "os": {
            "name": "Windows XP",
            "architecture": arch,
            "service_pack": "SP3" if arch == "x86" else "x64",
        },
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
        },
        "security": {
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
        },
        "smoke_ids": sorted(_xp_smoke_hashes()),
    }


def _xp_smoke_hashes() -> dict[str, str]:
    return {
        "cli_launch": "c" * 64,
        "gui_or_legacy_host_ui_launch": "d" * 64,
        "loopback_profile_dry_run": "e" * 64,
        "artifact_manifest_validation": "f" * 64,
        "legacy_crypto_profile_scoped": "1" * 64,
        "modern_defaults_unchanged": "2" * 64,
    }


def _builder_identity(target: str) -> dict[str, object]:
    machine = "i686" if target == "linux-i386" else "armv7l"
    return {
        "schema_version": 1,
        "target": target,
        "sys_platform": "linux",
        "platform_machine": machine,
        "uname_machine": machine,
        "python_version": "3.12.0",
        "required_tools": {
            "bash": "/usr/bin/bash",
            "curl": "/usr/bin/curl",
            "dpkg-deb": "/usr/bin/dpkg-deb",
            "rpmbuild": "/usr/bin/rpmbuild",
            "sha256sum": "/usr/bin/sha256sum",
            "sudo": "/usr/bin/sudo",
            "tar": "/usr/bin/tar",
        },
    }


def _promotion_config_sha256() -> str:
    data = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _xp_native_evidence_contract_sha256() -> str:
    data = json.loads(Path("configs/xp_native_evidence_contract.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _json_sha256(data: dict[str, object]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _load_platform_verified_evidence_checker():
    path = Path("scripts/check_platform_verified_evidence.py")
    spec = importlib.util.spec_from_file_location("check_platform_verified_evidence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
