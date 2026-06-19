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
MOBA_PARITY_POLICY = (
    "Only accepted evidence records in this file can close strict MobaXterm 26.4 Home/Professional parity "
    "articles. Accepted records must include one unique article_id, status accepted, a vX.Y.Z release_tag, "
    "a release_target, the exact validation command for that article, SHA-256 digests for the validated "
    "evidence JSON and evidence assets, release asset URLs under the same GitHub release tag, per-artifact "
    "SHA-256 digests, required article checks, and a validation summary proving the article evidence passed. "
    "Empty means the generated feature-family score remains separate from true product-depth parity."
)


def test_release_publish_asset_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main([]) == 0


def test_expected_release_assets_expand_default_matrix() -> None:
    checker = _load_checker()
    matrix = _load_matrix()

    assets = checker.expected_release_assets(matrix)

    assert "remote_ops_workspace-1.0.2-py3-none-any.whl" in assets
    assert "remote-ops-workspace-v1.0.2-windows-x86-setup.exe" in assets
    assert "remote-ops-workspace-v1.0.2-macos-arm64.pkg" in assets
    assert "remote-ops-workspace-v1.0.2-linux-amd64.deb" in assets
    assert "remote-ops-workspace-v1.0.2-linux-aarch64-native-SHA256SUMS.txt" in assets
    assert "remote-ops-workspace-v1.0.2-linux-i386.deb" not in assets
    assert "remote-ops-workspace-v1.0.2-linux-armhf.deb" not in assets


def test_publish_contract_rejects_gated_default_asset_without_evidence() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.2-linux-i386.deb")

    errors = checker.check_publish_contract(matrix, workflow, evidence_registry=_empty_evidence_registry())

    assert any("gated native asset remote-ops-workspace-v1.0.2-linux-i386.deb" in error for error in errors)


def test_publish_contract_allows_gated_default_asset_with_accepted_evidence() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.2-linux-i386.deb")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        evidence_registry=_accepted_evidence_registry("linux-i386"),
    )

    assert not any("gated native asset remote-ops-workspace-v1.0.2-linux-i386.deb" in error for error in errors)


def test_publish_contract_rejects_malformed_accepted_evidence_for_gated_asset() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.2-linux-i386.deb")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        evidence_registry={
            "schema_version": 1,
            "policy": POLICY,
            "accepted_evidence": [
                {
                    "target": "linux-i386",
                    "status": "accepted",
                    "readiness_percent": 100.0,
                }
            ],
        },
    )

    assert any("gated native asset remote-ops-workspace-v1.0.2-linux-i386.deb" in error for error in errors)


def test_publish_contract_rejects_xp_asset_without_complete_xp_pair() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    windows_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "windows-native")
    windows_job["asset_patterns"].append("remote-ops-workspace-v1.0.2-windows-xp-x86-native.zip")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        evidence_registry=_accepted_evidence_registry("windows-xp-native-x86"),
    )

    assert any("XP native promotion requires accepted evidence for both targets" in error for error in errors)


def test_publish_contract_requires_validation_before_upload() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag",
        "python scripts/check_release_matrix.py # disabled publish asset validation",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert any("publish asset validation" in error for error in errors)


def test_publish_contract_rejects_malformed_mobaxterm_parity_registry() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        mobaxterm_parity_registry={"schema_version": 1, "policy": "", "accepted_evidence": []},
    )

    assert any("mobaxterm parity evidence policy missing" in error for error in errors)


def test_publish_contract_can_require_complete_mobaxterm_parity_registry() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        mobaxterm_parity_registry=_empty_mobaxterm_parity_registry(),
        require_mobaxterm_parity_complete=True,
    )

    assert any("missing required MobaXterm parity articles" in error for error in errors)


def test_publish_contract_allows_complete_synthetic_mobaxterm_parity_registry() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        mobaxterm_parity_registry=_complete_mobaxterm_parity_registry(),
        require_mobaxterm_parity_complete=True,
    )

    assert not any("mobaxterm parity evidence" in error for error in errors)
    assert not any("MobaXterm parity" in error for error in errors)


def test_release_assets_report_missing_expected_files(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert any("missing expected files" in error for error in errors)


def test_release_assets_report_gated_extra_files(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    (tmp_path / "remote-ops-workspace-v1.0.2-linux-armhf.deb").write_text("native\n", encoding="utf-8")

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=_empty_evidence_registry(),
    )

    assert any("gated native asset remote-ops-workspace-v1.0.2-linux-armhf.deb" in error for error in errors)


def test_release_assets_accept_complete_synthetic_directory(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert errors == []


def test_release_assets_reject_checksum_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    checksum = tmp_path / "remote-ops-workspace-v1.0.2-SHA256SUMS.txt"
    checksum.write_text("0" * 64 + "  remote_ops_workspace-1.0.2-py3-none-any.whl\n", encoding="utf-8")

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert any("checksum mismatch" in error for error in errors)


def _write_synthetic_release_assets(checker, matrix: dict[str, object], root: Path) -> None:
    expected = checker.expected_release_assets(matrix, tag="v1.0.2")
    source_manifest_artifacts = checker.expected_source_manifest_artifacts(matrix, tag="v1.0.2")
    release_manifest = "remote-ops-workspace-v1.0.2-release-manifest.json"
    checksum_assets = {asset for asset in expected if asset.endswith("SHA256SUMS.txt")}

    for asset in sorted(expected - checksum_assets - {release_manifest}):
        (root / asset).write_bytes(f"{asset}\n".encode())

    manifest_payload = {
        "schema_version": 1,
        "artifacts": [
            {
                "file": f"dist/{asset}",
                "size_bytes": (root / asset).stat().st_size,
                "sha256": _sha256(root / asset),
            }
            for asset in sorted(source_manifest_artifacts)
        ],
    }
    (root / release_manifest).write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")

    reference_assets = sorted(expected - checksum_assets)
    checksum_lines = "\n".join(f"{_sha256(root / asset)}  {asset}" for asset in reference_assets) + "\n"
    for checksum in checksum_assets:
        (root / checksum).write_text(checksum_lines, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_matrix() -> dict[str, object]:
    return json.loads(Path("configs/release_matrix.json").read_text(encoding="utf-8"))


def _empty_evidence_registry() -> dict[str, object]:
    return {"schema_version": 1, "accepted_evidence": []}


def _empty_mobaxterm_parity_registry() -> dict[str, object]:
    return {
        "schema_version": 1,
        "policy": MOBA_PARITY_POLICY,
        "accepted_evidence": [],
    }


def _complete_mobaxterm_parity_registry() -> dict[str, object]:
    checker = _load_mobaxterm_checker()
    return {
        "schema_version": 1,
        "policy": MOBA_PARITY_POLICY,
        "accepted_evidence": [
            _mobaxterm_parity_record(article_id, spec)
            for article_id, spec in sorted(checker.ARTICLE_SPECS.items())
        ],
    }


def _mobaxterm_parity_record(article_id: str, spec) -> dict[str, object]:
    artifact_name = f"{article_id}-evidence.zip"
    return {
        "article_id": article_id,
        "status": "accepted",
        "evidence_type": spec.evidence_type,
        "release_tag": "v1.0.2",
        "release_target": "windows-x64",
        "validation_command": spec.validation_command,
        "evidence_file_sha256": "a" * 64,
        "evidence_assets_sha256": {f"{article_id}.json": "b" * 64},
        "release_asset_urls": [
            f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/{artifact_name}"
        ],
        "artifact_sha256": {artifact_name: "c" * 64},
        "checks": sorted(spec.required_checks),
        "validation_summary": {
            "passed": True,
            "errors": [],
            "summary": {"article_id": article_id},
        },
    }


def _accepted_evidence_registry(*targets: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [_accepted_evidence_record(target) for target in targets],
    }


def _accepted_evidence_record(target: str) -> dict[str, object]:
    if target in {"linux-i386", "linux-armhf"}:
        return _linux_accepted_evidence(target)
    return _xp_accepted_evidence(target)


def _linux_accepted_evidence(target: str) -> dict[str, object]:
    arch = "i386" if target == "linux-i386" else "armhf"
    rpm_arch = "i686" if target == "linux-i386" else "armv7hl"
    artifact_arch = "i686" if target == "linux-i386" else "armhf"
    artifact = "extended-linux-i386-native-evidence" if target == "linux-i386" else "extended-linux-armhf-native-evidence"
    base_url = "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2"
    release_asset_urls = [
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{arch}.deb",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{rpm_arch}.rpm",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}.AppImage",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}-native.tar.gz",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}-native-manifest.json",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}-native-SHA256SUMS.txt",
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
            "release_asset_base_url": base_url,
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


def _xp_accepted_evidence(target: str) -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    release_asset_urls = [
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-windows-xp-{arch}-native.zip",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-windows-xp-{arch}-native-manifest.json",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-windows-xp-{arch}-native-SHA256SUMS.txt",
    ]
    return {
        "target": target,
        "evidence_type": "windows-xp-native-host",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": "v1.0.2",
        "promotion_config_sha256": _promotion_config_sha256(),
        "architecture": arch,
        "separate_legacy_toolchain": True,
        "current_python_pyqt6_stack": False,
        "xp_evidence_sha256": "b" * 64,
        "xp_evidence_contract_sha256": _xp_native_evidence_contract_sha256(),
        "xp_evidence_summary": {
            "target": target,
            "release_tag": "v1.0.2",
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
            "smoke_ids": sorted(
                [
                    "cli_launch",
                    "gui_or_legacy_host_ui_launch",
                    "loopback_profile_dry_run",
                    "artifact_manifest_validation",
                    "legacy_crypto_profile_scoped",
                    "modern_defaults_unchanged",
                ]
            ),
        },
        "xp_smoke_evidence_sha256": {
            "cli_launch": "c" * 64,
            "gui_or_legacy_host_ui_launch": "d" * 64,
            "loopback_profile_dry_run": "e" * 64,
            "artifact_manifest_validation": "f" * 64,
            "legacy_crypto_profile_scoped": "1" * 64,
            "modern_defaults_unchanged": "2" * 64,
        },
        "native_evidence_validation_command": (
            "python scripts/check_xp_native_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>"
        ),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            "--assets-dir native-dist/windows-xp --tag v1.0.2"
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


def _promotion_config_sha256() -> str:
    data = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _xp_native_evidence_contract_sha256() -> str:
    data = json.loads(Path("configs/xp_native_evidence_contract.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _json_sha256(data: dict[str, object]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


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


def _load_checker():
    path = Path("scripts/check_release_publish_assets.py")
    spec = importlib.util.spec_from_file_location("check_release_publish_assets_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_mobaxterm_checker():
    path = Path("scripts/check_mobaxterm_parity_evidence.py")
    spec = importlib.util.spec_from_file_location("check_mobaxterm_parity_evidence_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
