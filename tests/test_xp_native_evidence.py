from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any


def test_xp_native_evidence_contract_passes_current_tree() -> None:
    checker = _load_xp_native_evidence_checker()

    assert checker.main(["--contract"]) == 0


def test_xp_native_evidence_accepts_x86_bundle(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "assets"
    assets.mkdir()
    names = _required_artifact_names(artifact_checker, "windows-xp-native-x86", tag)
    _write_artifact_set(assets, names)
    evidence = tmp_path / "xp-evidence.json"
    data = _valid_evidence("windows-xp-native-x86", "x86", "SP3", tag, names)
    _attach_smoke_evidence_files(tmp_path, data)
    evidence.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )

    errors = checker.check_xp_native_evidence(evidence, assets_dir=assets)

    assert errors == []


def test_xp_native_evidence_rejects_current_stack_claim(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "x64", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["toolchain"]["current_python_pyqt6_stack"] = True
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x64 evidence toolchain.current_python_pyqt6_stack must be False" in errors


def test_xp_native_evidence_rejects_missing_smoke(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["smoke_results"] = evidence["smoke_results"][:1]
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert any("windows-xp-native-x86 evidence missing smoke results" in error for error in errors)


def test_xp_native_evidence_rejects_sensitive_pattern(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["notes"] = "operator used token=example"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "XP native evidence contains forbidden sensitive pattern: token=" in errors


def test_xp_native_evidence_rejects_missing_smoke_evidence_file(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["smoke_results"][0]["evidence_file"] = "missing-cli-launch.txt"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert any("smoke result cli_launch evidence_file missing" in error for error in errors)


def test_xp_native_evidence_rejects_smoke_evidence_hash_mismatch(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["smoke_results"][0]["evidence_sha256"] = "0" * 64
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert any("smoke result cli_launch evidence_file SHA-256 mismatch" in error for error in errors)


def test_xp_native_evidence_rejects_artifact_validation_tag_mismatch(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, "windows-xp-native-x64", tag)
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "x64", tag, names)
    evidence["artifact_validation"]["command"] = evidence["artifact_validation"]["command"].replace(
        f"--tag {tag}",
        "--tag v9.9.9",
    )
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        f"windows-xp-native-x64 evidence artifact_validation.command must include exactly one --tag {tag}, "
        "got ['v9.9.9']"
    ) in errors


def test_xp_native_evidence_rejects_duplicate_artifact_validation_tag(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, "windows-xp-native-x86", tag)
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", tag, names)
    evidence["artifact_validation"]["command"] = (
        f"{evidence['artifact_validation']['command']} --tag v9.9.9"
    )
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        f"windows-xp-native-x86 evidence artifact_validation.command must include exactly one --tag {tag}, "
        f"got ['{tag}', 'v9.9.9']"
    ) in errors


def test_xp_native_evidence_rejects_inexact_artifact_list(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, "windows-xp-native-x86", tag)
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", tag, [*names[:-1], names[0]])
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert any("windows-xp-native-x86 evidence artifacts contain duplicate names" in error for error in errors)
    assert any("windows-xp-native-x86 evidence artifacts missing expected names" in error for error in errors)


def _valid_evidence(
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
            "command": f"python scripts/check_platform_promotion_artifacts.py --target {target} --assets-dir native-dist/windows-xp --tag {release_tag}",
        },
        "artifacts": artifacts or [f"remote-ops-workspace-{target}-placeholder"],
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


def _required_artifact_names(checker: Any, target: str, tag: str) -> list[str]:
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


def _payload_bytes(name: str) -> bytes:
    payload = f"{name}\n".encode()
    if name.endswith(".zip"):
        return _zip_bytes(name, payload)
    return payload


def _zip_bytes(name: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{name}.txt", payload)
    return buffer.getvalue()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_xp_native_evidence_checker():
    path = Path("scripts/check_xp_native_evidence.py")
    spec = importlib.util.spec_from_file_location("check_xp_native_evidence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_promotion_artifacts_checker():
    path = Path("scripts/check_platform_promotion_artifacts.py")
    spec = importlib.util.spec_from_file_location("check_platform_promotion_artifacts_for_xp", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
