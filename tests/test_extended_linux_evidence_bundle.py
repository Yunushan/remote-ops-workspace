from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def test_extended_linux_evidence_bundle_packages_valid_i386_evidence(tmp_path: Path) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "assets"
    assets.mkdir()
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder = tmp_path / "builder-identity-linux-i386.json"
    builder.write_text(json.dumps(_builder_identity(target), indent=2) + "\n", encoding="utf-8")
    smoke = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(smoke, target, _smoke_artifact_hashes(assets, names))
    candidate = tmp_path / "platform-verified-evidence-linux-i386.json"
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            runner_label=["self-hosted", "linux", "i386"],
            builder_evidence=builder,
            linux_smoke_evidence=smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    out_dir = tmp_path / "bundle"

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=out_dir,
    )

    assert errors == []
    manifest = out_dir / f"extended-linux-evidence-bundle-{target}-{tag}.json"
    archive = out_dir / f"extended-linux-evidence-bundle-{target}-{tag}.zip"
    sidecar = out_dir / f"extended-linux-evidence-bundle-{target}-{tag}-SHA256SUMS.txt"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["target"] == target
    assert data["release_tag"] == tag
    assert data["bundle_type"] == "extended-linux-native-evidence"
    assert len(data["artifacts"]) == len(names)
    assert data["release_asset_urls"] == record["release_asset_urls"]
    assert data["workflow_inputs"]["target"] == target
    assert data["security_patch_evidence"]["tls_minimum_modern_profiles"] == "TLS 1.2"
    assert data["security_patch_evidence"]["cve_patch_reviewed"] is True
    assert data["validated_commands"] == [
        record["native_build_command"],
        record["native_smoke_command"],
        record["artifact_validation_command"],
        "python scripts/check_platform_verified_evidence.py",
    ]
    assert all("<" not in command and ">" not in command for command in data["validated_commands"])
    assert data["smoke_evidence"] == [
        {
            "id": "native_smoke",
            "file": smoke.name,
            "size_bytes": smoke.stat().st_size,
            "sha256": _sha256(smoke),
        }
    ]
    with zipfile.ZipFile(archive) as zipped:
        names_in_archive = set(zipped.namelist())
        assert manifest.name in names_in_archive
        assert builder.name in names_in_archive
        assert smoke.name in names_in_archive
        assert candidate.name in names_in_archive
        assert set(names).issubset(names_in_archive)
    sidecar_text = sidecar.read_text(encoding="utf-8")
    assert f"{_sha256(manifest)}  {manifest.name}" in sidecar_text
    assert f"{_sha256(archive)}  {archive.name}" in sidecar_text


def test_extended_linux_evidence_bundle_rejects_artifact_hash_mismatch(tmp_path: Path) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "assets"
    assets.mkdir()
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder = tmp_path / "builder-identity-linux-i386.json"
    builder.write_text(json.dumps(_builder_identity(target), indent=2) + "\n", encoding="utf-8")
    smoke = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(smoke, target, _smoke_artifact_hashes(assets, names))
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            runner_label=["self-hosted", "linux", "i386"],
            builder_evidence=builder,
            linux_smoke_evidence=smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    record["artifact_sha256"][names[0]] = "0" * 64
    candidate = tmp_path / "platform-verified-evidence-linux-i386.json"
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=tmp_path / "bundle",
    )

    assert "candidate artifact_sha256 must match current artifact files" in errors


def test_extended_linux_evidence_bundle_rejects_unscoped_evidence_file_names(tmp_path: Path) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "assets"
    assets.mkdir()
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder = tmp_path / "builder-identity-linux-i386.json"
    builder.write_text(json.dumps(_builder_identity(target), indent=2) + "\n", encoding="utf-8")
    smoke = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(smoke, target, _smoke_artifact_hashes(assets, names))
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            runner_label=["self-hosted", "linux", "i386"],
            builder_evidence=builder,
            linux_smoke_evidence=smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    candidate = tmp_path / "platform-verified-evidence-linux-i386.json"
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    wrong_builder = tmp_path / "builder.json"
    wrong_builder.write_bytes(builder.read_bytes())
    wrong_smoke = tmp_path / "native-smoke.log"
    wrong_smoke.write_bytes(smoke.read_bytes())
    wrong_candidate = tmp_path / "candidate.json"
    wrong_candidate.write_bytes(candidate.read_bytes())

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=wrong_builder,
        smoke_evidence=wrong_smoke,
        candidate_record=wrong_candidate,
        out_dir=tmp_path / "bundle",
    )

    assert "builder evidence file name must be builder-identity-linux-i386.json, got 'builder.json'" in errors
    assert "smoke evidence file name must be native-smoke-linux-i386.log, got 'native-smoke.log'" in errors
    assert (
        "candidate evidence record file name must be platform-verified-evidence-linux-i386.json, "
        "got 'candidate.json'"
    ) in errors


def test_extended_linux_evidence_bundle_rejects_weak_smoke_log(tmp_path: Path) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "assets"
    assets.mkdir()
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    builder = tmp_path / "builder-identity-linux-i386.json"
    builder.write_text(json.dumps(_builder_identity(target), indent=2) + "\n", encoding="utf-8")
    valid_smoke = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(valid_smoke, target, _smoke_artifact_hashes(assets, names))
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            runner_label=["self-hosted", "linux", "i386"],
            builder_evidence=builder,
            linux_smoke_evidence=valid_smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    weak_smoke = valid_smoke
    weak_smoke.write_text("linux-i386 native smoke passed\n", encoding="utf-8")
    smoke_sha = _sha256(weak_smoke)
    record["linux_smoke_evidence_sha256"] = {"native_smoke": smoke_sha}
    _sync_linux_source_record(record, "native_smoke", smoke_sha, weak_smoke.stat().st_size)
    candidate = tmp_path / "platform-verified-evidence-linux-i386.json"
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=builder,
        smoke_evidence=weak_smoke,
        candidate_record=candidate,
        out_dir=tmp_path / "bundle",
    )

    assert any(
        "linux-i386 linux_smoke_evidence missing required line: "
        "native installer smoke command: bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux "
        "--target linux-i386 --workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345"
        in error
        for error in errors
    )


def _builder_identity(target: str) -> dict[str, object]:
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": "v1.0.2",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "source_head_sha": "a" * 40,
        "host_identity": _linux_host_identity(target),
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
        "security_patch_evidence": {
            "python_ssl_openssl": "OpenSSL 3.0.13",
            "openssl_cli_version": "OpenSSL 3.0.13",
            "tls_minimum_modern_profiles": "TLS 1.2",
            "tls_preferred_modern_profiles": "TLS 1.3",
            "legacy_compatibility_profile": "isolated-opt-in",
            "cve_patch_reviewed": True,
        },
    }


def _linux_host_identity(target: str, release_tag: str = "v1.0.2") -> dict[str, object]:
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "host_label": f"{target}-builder",
        "evidence_run_id": f"{target}-{release_tag.removeprefix('v').replace('.', '-')}-run-12345",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "operator_private_data_redacted": True,
    }


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
    if name.endswith(".deb"):
        return b"!<arch>\nlinux i386 deb payload\n"
    if name.endswith(".rpm"):
        return bytes.fromhex("edabeedb") + b"linux i386 rpm payload\n"
    if name.endswith(".AppImage"):
        return b"\x7fELFlinux i386 appimage payload\n"
    if name.endswith(".tar.gz"):
        return _tar_gz_bytes(name)
    return f"{name}\n".encode()


def _tar_gz_bytes(name: str) -> bytes:
    payload = f"{name}\n".encode()
    with io.BytesIO() as raw:
        with tarfile.open(fileobj=raw, mode="w:gz") as archive:
            info = tarfile.TarInfo("Remote Ops Workspace Linux evidence payload.txt")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        return raw.getvalue()


def _sync_linux_source_record(
    record: dict[str, object],
    key: str,
    sha256: str,
    size_bytes: int,
) -> None:
    sources = record.get("linux_evidence_sources")
    if isinstance(sources, dict) and isinstance(sources.get(key), dict):
        source = sources[key]
        source["sha256"] = sha256
        source["size_bytes"] = size_bytes


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_script(name: str):
    path = Path("scripts") / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
