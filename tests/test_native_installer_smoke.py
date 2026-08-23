from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def test_native_installer_smoke_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_native_installer_smoke_contract_covers_required_formats() -> None:
    config = json.loads(Path("configs/native_installer_smoke.json").read_text(encoding="utf-8"))
    formats = {
        item["format"]
        for platform in config["platforms"].values()
        for item in platform["formats"]
    }

    assert config["schema_version"] == 2
    assert formats == {"exe", "msi", "dmg", "pkg", "deb", "rpm", "AppImage"}
    assert config["runtime_resource_probe"] == {
        "command": "platforms --json",
        "required_json_arrays": ["release_architectures", "windows_legacy_targets"],
        "lifecycle_steps": ["verify", "upgrade"],
    }
    for platform in config["platforms"].values():
        for item in platform["formats"]:
            assert "platforms --json" in item["lifecycle"]["verify"]
            assert "platforms --json" in item["lifecycle"]["upgrade"]


def test_native_installer_smoke_checker_rejects_weakened_runtime_resource_probe() -> None:
    checker = _load_checker()
    config = json.loads(Path("configs/native_installer_smoke.json").read_text(encoding="utf-8"))
    config["runtime_resource_probe"]["command"] = "--version"
    config["platforms"]["windows"]["formats"][0]["lifecycle"]["upgrade"] = (
        "rerun setup without consuming packaged resources"
    )

    errors = checker.check_config_schema(config)

    assert "runtime_resource_probe command must be 'platforms --json'" in errors
    assert (
        "windows exe lifecycle upgrade must execute platforms --json from the installed artifact"
        in errors
    )


def test_native_installer_smoke_scripts_consume_installed_runtime_resources() -> None:
    windows = Path("scripts/smoke_windows_native.ps1").read_text(encoding="utf-8")
    linux = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")
    macos = Path("scripts/smoke_macos_native.sh").read_text(encoding="utf-8")
    macos_builder = Path("scripts/make_macos_native.sh").read_text(encoding="utf-8")

    for source in (windows, linux, macos):
        assert "platforms --json" in source
        assert "release_architectures" in source
        assert "windows_legacy_targets" in source
        assert "native installer smoke runtime resources:" in source
    assert "Test-RowRuntimeResources" in windows
    assert "verify_row_runtime_resources" in linux
    assert "verify_app_runtime_resources" in macos
    assert "Contents/MacOS" in macos
    assert "sys.argv[1:]" in macos_builder
    assert 'main(arguments or ["gui"])' in macos_builder


def test_runtime_resource_script_checker_rejects_missing_installed_probe(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    script = tmp_path / "smoke_windows_native.ps1"
    script.write_text("install verify upgrade uninstall", encoding="utf-8")

    errors = checker.check_runtime_resource_script("windows", script, script.read_text())

    assert any("installed CLI platform catalog invocation" in error for error in errors)
    assert any("release architecture resource assertion" in error for error in errors)


def test_linux_rpm_smoke_uses_nodeps_on_ubuntu_runner() -> None:
    config = json.loads(Path("configs/native_installer_smoke.json").read_text(encoding="utf-8"))
    script = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")
    rpm_lifecycle = next(
        item["lifecycle"]
        for item in config["platforms"]["linux"]["formats"]
        if item["format"] == "rpm"
    )

    assert "--nodeps" in rpm_lifecycle["install"]
    assert "--nodeps" in rpm_lifecycle["upgrade"]
    assert "--nodeps" in rpm_lifecycle["uninstall"]
    assert "rpm -Uvh --nodeps --replacepkgs" in script
    assert "rpm -e --nodeps remote-ops-workspace" in script


def test_linux_smoke_requires_source_head_sha_for_target_bound_evidence() -> None:
    script = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")

    assert "--source-head-sha is required with --target" in script
    assert "--source-head-sha requires --target" in script
    assert "--source-head-sha must be a 40-character lowercase Git SHA" in script
    assert "native installer smoke source head sha: $SOURCE_HEAD_SHA" in script


def test_linux_smoke_binds_source_head_sha_to_git_checkout_for_target_bound_evidence() -> None:
    script = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")

    assert 'SMOKE_GIT_HEAD_SHA="$(git rev-parse HEAD 2>/dev/null || true)"' in script
    assert "target $TARGET requires git rev-parse HEAD for source head binding" in script
    assert "does not match git HEAD $SMOKE_GIT_HEAD_SHA" in script
    assert "native installer smoke git head sha: $SMOKE_GIT_HEAD_SHA" in script


def test_linux_smoke_requires_workflow_run_attempt_for_target_bound_evidence() -> None:
    script = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")

    assert "--workflow-run-attempt is required with --target" in script
    assert "--workflow-run-attempt requires --target" in script
    assert "--workflow-run-attempt must be a positive integer" in script
    assert "native installer smoke workflow run attempt: $WORKFLOW_RUN_ATTEMPT" in script


def test_linux_smoke_requires_builder_evidence_for_target_bound_evidence() -> None:
    script = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")

    assert "--builder-evidence is required with --target" in script
    assert "--builder-evidence requires --target" in script
    assert "target $TARGET builder evidence file missing" in script
    assert "BUILDER_BINDING_TSV" in script
    assert 'require_builder_match "target"' in script
    assert 'require_builder_match "release_tag"' in script
    assert 'require_builder_match "workflow_run_url"' in script
    assert 'require_builder_match "workflow_run_attempt"' in script
    assert 'require_builder_match "source_head_sha"' in script
    assert 'require_builder_match "observed_git_head_sha"' in script
    assert 'require_builder_match "security_patch_evidence.python_ssl_openssl"' in script
    assert 'require_builder_match "security_patch_evidence.openssl_cli_version"' in script
    assert 'require_builder_value "security_patch_evidence.security_update_channel"' in script
    assert 'require_builder_value "security_patch_evidence.cve_review_reference"' in script
    assert 'require_builder_match "security_patch_evidence.security_update_channel"' in script
    assert 'require_builder_match "security_patch_evidence.cve_review_reference"' in script
    assert "native installer smoke builder evidence: $BUILDER_EVIDENCE" in script


def test_linux_smoke_binds_github_actions_environment_when_available() -> None:
    script = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")

    assert "--workflow-run-url must be canonical without surrounding whitespace or trailing slash" in script
    assert "--workflow-run-url must be a GitHub Actions run URL" in script
    assert 'REQUESTED_WORKFLOW_RUN_ID="$WORKFLOW_RUN_URL"' in script
    assert 'REQUESTED_WORKFLOW_RUN_ID="${WORKFLOW_RUN_URL%/}"' not in script
    assert "[^/[:space:]]+" in script
    assert 'REQUESTED_WORKFLOW_REPOSITORY="${WORKFLOW_RUN_URL#https://github.com/}"' in script
    assert "GITHUB_SHA" in script
    assert "must match --source-head-sha" in script
    assert "GITHUB_RUN_ATTEMPT" in script
    assert "must match --workflow-run-attempt" in script
    assert "GITHUB_RUN_ID" in script
    assert "GITHUB_REPOSITORY" in script
    assert "must match --workflow-run-url" in script


def test_linux_smoke_binds_runtime_architecture_for_protected_targets() -> None:
    script = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")

    assert 'SMOKE_UNAME_MACHINE="$(uname -m)"' in script
    assert 'SMOKE_DPKG_ARCH="$(dpkg --print-architecture)"' in script
    assert 'SMOKE_USERLAND_BITS="$(getconf LONG_BIT)"' in script
    assert "target $TARGET must smoke on dpkg architecture i386" in script
    assert "target $TARGET must smoke on dpkg architecture armhf" in script
    assert "target $TARGET must smoke on a 32-bit userland" in script
    assert "native installer smoke uname machine: $SMOKE_UNAME_MACHINE" in script
    assert "native installer smoke dpkg architecture: $SMOKE_DPKG_ARCH" in script
    assert "native installer smoke userland bits: $SMOKE_USERLAND_BITS" in script


def test_linux_smoke_emits_sanitized_identity_for_target_bound_evidence() -> None:
    script = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")

    assert 'SMOKE_OBSERVED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"' in script
    assert 'REQUESTED_WORKFLOW_RUN_ID="$WORKFLOW_RUN_URL"' in script
    assert "native installer smoke host label: $SMOKE_HOST_LABEL" in script
    assert "native installer smoke evidence run id: $SMOKE_EVIDENCE_RUN_ID" in script
    assert "native installer smoke observed at utc: $SMOKE_OBSERVED_AT_UTC" in script


def test_linux_smoke_binds_security_lines_to_builder_evidence() -> None:
    script = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")

    assert "openssl version | tr '[:upper:]' '[:lower:]'" in script
    assert 'SMOKE_SECURITY_UPDATE_CHANNEL="distribution-security-updates"' in script
    assert 'SMOKE_CVE_REVIEW_REFERENCE="distribution-security-tracker-and-release-notes"' in script
    assert 'BUILDER_SECURITY_UPDATE_CHANNEL="$value"' in script
    assert 'BUILDER_CVE_REVIEW_REFERENCE="$value"' in script
    assert "SMOKE_SECURITY_UPDATE_CHANNEL" in script
    assert "SMOKE_CVE_REVIEW_REFERENCE" in script
    assert "native installer smoke security update channel: $SMOKE_SECURITY_UPDATE_CHANNEL" in script
    assert "native installer smoke CVE review reference: $SMOKE_CVE_REVIEW_REFERENCE" in script


def test_native_installer_smoke_checker_requires_linux_canonical_workflow_url() -> None:
    checker = _load_checker()
    script = Path("scripts/smoke_linux_native.sh")
    text = script.read_text(encoding="utf-8").replace(
        "--workflow-run-url must be canonical without surrounding whitespace or trailing slash",
        "--workflow-run-url permits trailing slash",
    )

    errors = checker.check_linux_smoke_source_binding(script, text)

    assert (
        "scripts/smoke_linux_native.sh missing Linux smoke workflow run URL canonical validation: "
        "--workflow-run-url must be canonical without surrounding whitespace or trailing slash"
    ) in errors


def test_native_installer_smoke_checker_requires_linux_smoke_identity_contract(tmp_path: Path) -> None:
    checker = _load_checker()
    script = tmp_path / "smoke_linux_native.sh"
    text = """
--workflow-run-url must be canonical without surrounding whitespace or trailing slash
--workflow-run-url must be a GitHub Actions run URL
REQUESTED_WORKFLOW_RUN_ID="$WORKFLOW_RUN_URL"
REQUESTED_WORKFLOW_REPOSITORY="${WORKFLOW_RUN_URL#https://github.com/}"
GITHUB_SHA
must match --source-head-sha
GITHUB_RUN_ATTEMPT
must match --workflow-run-attempt
GITHUB_RUN_ID
GITHUB_REPOSITORY
must match --workflow-run-url
"""

    errors = checker.check_linux_smoke_source_binding(script, text)

    assert any(
        error.endswith(
            "missing Linux smoke target/architecture mismatch failure: "
            "target $TARGET does not match smoke arch $ARCH"
        )
        for error in errors
    )
    assert any(
        error.endswith(
            "missing Linux smoke UTC observation timestamp capture: "
            'SMOKE_OBSERVED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"'
        )
        for error in errors
    )
    assert any(
        error.endswith(
            "missing Linux smoke builder evidence requirement: "
            "--builder-evidence is required with --target"
        )
        for error in errors
    )
    assert any(
        error.endswith(
            "missing Linux smoke builder-bound smoke host label: "
            "native installer smoke host label: $SMOKE_HOST_LABEL"
        )
        for error in errors
    )
    assert any(
        error.endswith(
            "missing Linux smoke builder-bound smoke evidence run id: "
            "native installer smoke evidence run id: $SMOKE_EVIDENCE_RUN_ID"
        )
        for error in errors
    )
    assert any(
        error.endswith(
            "missing Linux smoke UTC observation timestamp evidence line: "
            "native installer smoke observed at utc: $SMOKE_OBSERVED_AT_UTC"
        )
        for error in errors
    )


def _load_checker():
    path = Path("scripts/check_native_installer_smoke.py")
    spec = importlib.util.spec_from_file_location("native_installer_smoke_checker", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
