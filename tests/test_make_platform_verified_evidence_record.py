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
                "--builder-evidence",
                str(builder_evidence),
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
    assert record["artifact_name"] == "extended-linux-i386-native-evidence"
    assert record["workflow_inputs"] == {
        "target": target,
        "release_tag": tag,
        "release_asset_base_url": f"https://github.com/example/remote-ops-workspace/releases/download/{tag}",
    }
    assert record["builder_identity"]["target"] == target
    assert record["builder_identity_sha256"] == _json_sha256(record["builder_identity"])
    assert len(record["release_asset_urls"]) == len(names)
    assert set(record["artifact_sha256"]) == set(names)
    assert all(len(digest) == 64 for digest in record["artifact_sha256"].values())


def test_make_platform_verified_evidence_record_generates_xp_record(tmp_path: Path) -> None:
    maker = _load_maker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x64"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "xp"
    assets.mkdir()
    names = _required_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence = tmp_path / "xp-evidence.json"
    data = _valid_xp_evidence(target, "x64", "x64", tag, names)
    _attach_smoke_evidence_files(tmp_path, data)
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
                "--xp-evidence",
                str(evidence),
            ]
        )
    )

    assert errors == []
    assert record["target"] == target
    assert record["evidence_type"] == "windows-xp-native-host"
    assert record["promotion_config_sha256"] == _promotion_config_sha256()
    assert record["separate_legacy_toolchain"] is True
    assert record["current_python_pyqt6_stack"] is False
    assert set(record["artifact_sha256"]) == set(names)
    assert record["xp_evidence_sha256"] == _sha256(evidence)
    assert record["xp_evidence_contract_sha256"] == _xp_native_evidence_contract_sha256()
    assert record["xp_evidence_summary"] == {
        "target": target,
        "release_tag": tag,
        "os": {
            "name": "Windows XP",
            "architecture": "x64",
            "service_pack": "x64",
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
        "smoke_ids": sorted(result["id"] for result in data["smoke_results"]),
    }
    assert record["xp_smoke_evidence_sha256"] == {
        result["id"]: result["evidence_sha256"] for result in data["smoke_results"]
    }


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
    _write_builder_evidence(builder_evidence, target)
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
                "--builder-evidence",
                str(builder_evidence),
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

    assert append_errors == []
    updated = json.loads(registry.read_text(encoding="utf-8"))
    assert [entry["target"] for entry in updated["accepted_evidence"]] == [target]


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


def _write_builder_evidence(path: Path, target: str) -> None:
    machine = "i686" if target == "linux-i386" else "armv7l"
    data = {
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
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


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
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "os": {
            "name": "Windows XP",
            "architecture": arch,
            "service_pack": service_pack,
        },
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "Separate legacy XP-capable native host toolchain",
        },
        "artifact_validation": {
            "passed": True,
            "command": (
                f"python scripts/check_platform_promotion_artifacts.py --target {target} "
                f"--assets-dir native-dist/windows-xp --tag {release_tag}"
            ),
        },
        "artifacts": artifacts,
        "smoke_results": [
            {
                "id": smoke_id,
                "passed": True,
                "evidence_file": f"xp-smoke-evidence/{smoke_id}.txt",
                "evidence_sha256": hashlib.sha256(smoke_id.encode()).hexdigest(),
            }
            for smoke_id in smoke_ids
        ],
        "security": {
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
        },
    }


def _attach_smoke_evidence_files(root: Path, evidence: dict[str, Any]) -> None:
    for result in evidence["smoke_results"]:
        path = root / result["evidence_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{result['id']} passed on Windows XP evidence host\n", encoding="utf-8")
        result["evidence_sha256"] = _sha256(path)


def _empty_registry() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy": (
            "Only accepted evidence records in this file can promote Linux i386, Linux armhf, "
            "or Windows XP native-host readiness. Accepted records must include release asset URLs "
            "and per-artifact SHA-256 digests, Linux builder identity evidence and builder identity "
            "SHA-256 when applicable, Linux workflow dispatch inputs when applicable, XP evidence "
            "bundle SHA-256 digests, XP evidence contract SHA-256, and XP evidence summary binding "
            "when applicable, and the promotion config SHA-256; "
            "each accepted record must have a unique target, all release evidence for one record must "
            "use the same GitHub repository, and Windows XP x86/x64 pairs must use the same release_tag. "
            "Empty means no promotion."
        ),
        "accepted_evidence": [],
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
