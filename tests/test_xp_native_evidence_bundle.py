from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def test_xp_native_evidence_bundle_packages_valid_x86_evidence(tmp_path: Path) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    assets = tmp_path / "assets"
    assets.mkdir()
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x86", "SP3", tag, names)
    _attach_smoke_evidence_files(tmp_path, evidence_data)
    evidence = tmp_path / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets)
    out_dir = tmp_path / "bundle"

    errors = bundler.make_xp_native_evidence_bundle(
        target=target,
        evidence=evidence,
        candidate_record=candidate,
        assets_dir=assets,
        out_dir=out_dir,
    )

    assert errors == []
    manifest = out_dir / f"xp-native-evidence-bundle-{target}-{tag}.json"
    archive = out_dir / f"xp-native-evidence-bundle-{target}-{tag}.zip"
    sidecar = out_dir / f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["target"] == target
    assert data["release_tag"] == tag
    assert data["bundle_type"] == "windows-xp-native-host-evidence"
    assert data["host_identity"] == evidence_data["host_identity"]
    assert data["candidate_record"]["file"] == candidate.name
    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
    assert data["release_asset_urls"] == candidate_data["release_asset_urls"]
    assert data["validated_commands"] == [
        (
            "python scripts/check_xp_native_evidence.py "
            f"--evidence {evidence.as_posix()} --assets-dir {assets.as_posix()}"
        ),
        (
            "python scripts/check_platform_promotion_artifacts.py "
            f"--target {target} --assets-dir {assets.as_posix()} --tag {tag} --strict"
        ),
        "python scripts/check_platform_verified_evidence.py",
    ]
    assert all("<" not in command and ">" not in command for command in data["validated_commands"])
    assert len(data["artifacts"]) == len(names)
    assert {item["id"] for item in data["smoke_evidence"]} == {
        "cli_launch",
        "gui_or_legacy_host_ui_launch",
        "loopback_profile_dry_run",
        "artifact_manifest_validation",
        "legacy_crypto_profile_scoped",
        "modern_defaults_unchanged",
    }
    with zipfile.ZipFile(archive) as zipped:
        names_in_archive = set(zipped.namelist())
        assert "xp-evidence.json" in names_in_archive
        assert candidate.name in names_in_archive
        assert manifest.name in names_in_archive
        assert "xp-smoke-evidence/cli_launch.txt" in names_in_archive
        assert set(names).issubset(names_in_archive)
    assert f"{_sha256(manifest)}  {manifest.name}" in sidecar.read_text(encoding="utf-8")
    assert f"{_sha256(archive)}  {archive.name}" in sidecar.read_text(encoding="utf-8")


def test_xp_native_evidence_bundle_rejects_target_mismatch(tmp_path: Path) -> None:
    bundler = _load_bundle_script()
    evidence = tmp_path / "xp-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target": "windows-xp-native-x86",
                "release_tag": "v1.0.2",
            }
        ),
        encoding="utf-8",
    )
    candidate = tmp_path / "platform-verified-evidence-windows-xp-native-x86.json"
    candidate.write_text(
        json.dumps(
            {
                "target": "windows-xp-native-x86",
                "release_tag": "v1.0.2",
                "xp_evidence_sha256": _sha256(evidence),
                "xp_smoke_evidence_sha256": {},
                "artifact_sha256": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assets = tmp_path / "assets"
    assets.mkdir()

    errors = bundler.make_xp_native_evidence_bundle(
        target="windows-xp-native-x64",
        evidence=evidence,
        candidate_record=candidate,
        assets_dir=assets,
        out_dir=tmp_path / "bundle",
    )

    assert "bundle target windows-xp-native-x64 must match evidence target 'windows-xp-native-x86'" in errors


def test_xp_native_evidence_bundle_rejects_candidate_mismatch(tmp_path: Path) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    assets = tmp_path / "assets"
    assets.mkdir()
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x86", "SP3", tag, names)
    _attach_smoke_evidence_files(tmp_path, evidence_data)
    evidence = tmp_path / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets)
    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
    candidate_data["xp_evidence_sha256"] = "0" * 64
    candidate.write_text(json.dumps(candidate_data, indent=2) + "\n", encoding="utf-8")

    errors = bundler.make_xp_native_evidence_bundle(
        target=target,
        evidence=evidence,
        candidate_record=candidate,
        assets_dir=assets,
        out_dir=tmp_path / "bundle",
    )

    assert "candidate record xp_evidence_sha256 must match XP evidence file" in errors


def test_xp_native_evidence_bundle_rejects_host_identity_mismatch(tmp_path: Path) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    assets = tmp_path / "assets"
    assets.mkdir()
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x86", "SP3", tag, names)
    _attach_smoke_evidence_files(tmp_path, evidence_data)
    evidence = tmp_path / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets)
    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
    candidate_data["xp_host_identity_sha256"] = "0" * 64
    candidate.write_text(json.dumps(candidate_data, indent=2) + "\n", encoding="utf-8")

    errors = bundler.make_xp_native_evidence_bundle(
        target=target,
        evidence=evidence,
        candidate_record=candidate,
        assets_dir=assets,
        out_dir=tmp_path / "bundle",
    )

    assert "candidate record xp_host_identity_sha256 must match XP host identity" in errors


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
                "python scripts/check_platform_promotion_artifacts.py "
                f"--target {target} --assets-dir native-dist/windows-xp --tag {release_tag}"
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
            "patch_evidence": {
                "tls_minimum_modern_profiles": "TLS 1.2",
                "tls_preferred_modern_profiles": "TLS 1.3",
                "legacy_compatibility_profile": "isolated-opt-in",
                "cve_patch_reviewed": True,
            },
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


def _write_candidate_record(
    path: Path,
    target: str,
    release_tag: str,
    evidence: Path,
    evidence_data: dict[str, Any],
    assets_dir: Path,
) -> None:
    generator = _load_platform_verified_evidence_record_generator()
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=release_tag,
            assets_dir=assets_dir,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}"
            ),
            release_source_workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/54321",
            release_source_artifact_name=f"xp-native-evidence-{target}-{release_tag}",
            workflow_run_url="",
            runner_label=[],
            builder_evidence=None,
            linux_smoke_evidence=None,
            xp_evidence=evidence,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    assert record["xp_host_identity_sha256"] == _json_sha256(evidence_data["host_identity"])
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def _payload_bytes(name: str) -> bytes:
    payload = f"{name}\n".encode()
    with io.BytesIO() as raw:
        with zipfile.ZipFile(raw, mode="w") as archive:
            archive.writestr("Remote Ops Workspace XP native evidence payload.txt", payload)
        return raw.getvalue()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha256(data: dict[str, object]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _load_bundle_script():
    path = Path("scripts/make_xp_native_evidence_bundle.py")
    spec = importlib.util.spec_from_file_location("make_xp_native_evidence_bundle_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_promotion_artifacts_checker():
    path = Path("scripts/check_platform_promotion_artifacts.py")
    spec = importlib.util.spec_from_file_location("check_platform_promotion_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_verified_evidence_record_generator():
    path = Path("scripts/make_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("make_platform_verified_evidence_record", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
