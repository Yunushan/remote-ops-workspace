from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path


def test_extended_platform_evidence_workflow_passes_current_tree() -> None:
    checker = _load_script("check_extended_platform_evidence")

    assert checker.main() == 0


def test_extended_platform_evidence_rejects_publish_trigger() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow += "\npush:\n"

    errors = checker.check_extended_platform_evidence(workflow)

    assert "extended platform evidence workflow must not run on push" in errors


def test_extended_platform_evidence_requires_candidate_record_generation() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace("python scripts/make_platform_verified_evidence_record.py", "python scripts/removed.py")

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("accepted-evidence record generation" in error for error in errors)


def test_extended_platform_evidence_requires_review_bundle_generation() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace("python scripts/make_extended_linux_evidence_bundle.py", "python scripts/removed.py")

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("review evidence bundle generation" in error for error in errors)


def test_extended_platform_evidence_requires_builder_release_context() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace(
        "          python3 scripts/check_extended_platform_builder.py \\\n"
        "            --target linux-i386 \\\n"
        '            --release-tag "${{ inputs.release_tag }}" \\\n',
        "          python3 scripts/check_extended_platform_builder.py \\\n"
        "            --target linux-i386 \\\n",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("builder identity preflight must bind release_tag and workflow_run_url" in error for error in errors)


def test_extended_platform_evidence_requires_dispatch_input_preflight() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace("python3 scripts/check_extended_platform_dispatch_inputs.py", "python3 scripts/removed.py")

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("dispatch input preflight" in error for error in errors)


def test_extended_platform_dispatch_input_validator_accepts_matching_inputs() -> None:
    checker = _load_script("check_extended_platform_dispatch_inputs")

    errors = checker.check_extended_platform_dispatch_inputs(
        target="linux-i386",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
    )

    assert errors == []


def test_extended_platform_dispatch_input_validator_rejects_release_tag_mismatch() -> None:
    checker = _load_script("check_extended_platform_dispatch_inputs")

    errors = checker.check_extended_platform_dispatch_inputs(
        target="linux-armhf",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.3",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
    )

    assert "release_asset_base_url tag must match release_tag v1.0.2, got v1.0.3" in errors


def test_extended_platform_dispatch_input_validator_rejects_cross_repo_inputs() -> None:
    checker = _load_script("check_extended_platform_dispatch_inputs")

    errors = checker.check_extended_platform_dispatch_inputs(
        target="linux-armhf",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/other/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
    )

    assert (
        "release_asset_base_url repository must match workflow_run_url repository "
        "example/remote-ops-workspace, got other/remote-ops-workspace"
    ) in errors


def test_extended_platform_builder_accepts_matching_i386(monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "i686")
    monkeypatch.setattr(checker, "command_output", _linux_command_output("i686", "i386", "32"))
    monkeypatch.setattr(checker, "command_succeeds", lambda _command: True)
    monkeypatch.setattr(shutil, "which", lambda _tool: f"/usr/bin/{_tool}")

    assert checker.check_extended_platform_builder("linux-i386") == []


def test_extended_platform_builder_rejects_relative_tool_path(monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "i686")
    monkeypatch.setattr(checker, "command_output", _linux_command_output("i686", "i386", "32"))
    monkeypatch.setattr(checker, "command_succeeds", lambda _command: True)
    monkeypatch.setattr(shutil, "which", lambda tool: tool if tool == "bash" else f"/usr/bin/{tool}")

    errors = checker.check_extended_platform_builder("linux-i386")

    assert "linux-i386 builder required tool bash must resolve to an absolute path, got 'bash'" in errors


def test_extended_platform_builder_rejects_interactive_sudo(monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "i686")
    monkeypatch.setattr(checker, "command_output", _linux_command_output("i686", "i386", "32"))
    monkeypatch.setattr(checker, "command_succeeds", lambda command: command != ["sudo", "-n", "true"])
    monkeypatch.setattr(shutil, "which", lambda tool: f"/usr/bin/{tool}")

    errors = checker.check_extended_platform_builder("linux-i386")

    assert "linux-i386 builder sudo must be non-interactive: sudo -n true failed" in errors


def test_extended_platform_builder_writes_identity_evidence(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "i686")
    monkeypatch.setattr(checker, "command_output", _linux_command_output("i686", "i386", "32"))
    monkeypatch.setattr(checker, "command_succeeds", lambda _command: True)
    monkeypatch.setattr(shutil, "which", lambda tool: f"/usr/bin/{tool}")
    output = tmp_path / "builder-identity-linux-i386.json"

    assert (
        checker.main(
            [
                "--target",
                "linux-i386",
                "--release-tag",
                "v1.0.2",
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--out",
                str(output),
            ]
        )
        == 0
    )

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["target"] == "linux-i386"
    assert data["release_tag"] == "v1.0.2"
    assert data["workflow_run_url"] == "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    assert data["host_identity"] == {
        "schema_version": 1,
        "target": "linux-i386",
        "release_tag": "v1.0.2",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "host_label": "linux-i386-builder",
        "evidence_run_id": "linux-i386-1-0-2-run-12345",
        "observed_at_utc": data["host_identity"]["observed_at_utc"],
        "operator_private_data_redacted": True,
    }
    assert data["host_identity"]["observed_at_utc"].endswith("Z")
    assert data["platform_machine"] == "i686"
    assert data["uname_machine"] == "i686"
    assert data["dpkg_architecture"] == "i386"
    assert data["userland_bits"] == "32"
    assert data["required_tools"]["dpkg"] == "/usr/bin/dpkg"
    assert data["required_tools"]["dpkg-deb"] == "/usr/bin/dpkg-deb"
    assert data["required_tools"]["rpm"] == "/usr/bin/rpm"
    assert data["sudo_non_interactive"] is True


def test_extended_platform_builder_requires_release_context_for_identity_output(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "i686")
    monkeypatch.setattr(checker, "command_output", _linux_command_output("i686", "i386", "32"))
    monkeypatch.setattr(checker, "command_succeeds", lambda _command: True)
    monkeypatch.setattr(shutil, "which", lambda tool: f"/usr/bin/{tool}")

    result = checker.main(["--target", "linux-i386", "--out", str(tmp_path / "builder.json")])

    assert result == 1


def test_extended_platform_builder_rejects_wrong_arch(monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "x86_64")
    monkeypatch.setattr(checker, "command_output", _linux_command_output("x86_64", "amd64", "64"))
    monkeypatch.setattr(checker, "command_succeeds", lambda _command: True)
    monkeypatch.setattr(shutil, "which", lambda _tool: f"/usr/bin/{_tool}")

    errors = checker.check_extended_platform_builder("linux-armhf")

    assert any("linux-armhf builder architecture must be one of" in error for error in errors)
    assert any("linux-armhf uname -m must be one of" in error for error in errors)
    assert any("linux-armhf dpkg architecture must be one of" in error for error in errors)
    assert "linux-armhf userland bits must be 32, got 64" in errors


def _linux_command_output(uname: str, dpkg_arch: str, bits: str):
    def _output(command: list[str]) -> str:
        if command == ["uname", "-m"]:
            return uname
        if command == ["dpkg", "--print-architecture"]:
            return dpkg_arch
        if command == ["getconf", "LONG_BIT"]:
            return bits
        if command == ["openssl", "version"]:
            return "openssl 3.0.13"
        return ""

    return _output


def _load_script(name: str):
    path = Path("scripts") / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
