from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


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


def test_extended_platform_builder_accepts_matching_i386(monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "i686")
    monkeypatch.setattr(shutil, "which", lambda _tool: f"/usr/bin/{_tool}")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="i686\n"),
    )

    assert checker.check_extended_platform_builder("linux-i386") == []


def test_extended_platform_builder_writes_identity_evidence(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "i686")
    monkeypatch.setattr(shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="i686\n"),
    )
    output = tmp_path / "builder-identity-linux-i386.json"

    assert checker.main(["--target", "linux-i386", "--out", str(output)]) == 0

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["target"] == "linux-i386"
    assert data["platform_machine"] == "i686"
    assert data["uname_machine"] == "i686"
    assert data["required_tools"]["dpkg-deb"] == "/usr/bin/dpkg-deb"


def test_extended_platform_builder_rejects_wrong_arch(monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "x86_64")
    monkeypatch.setattr(shutil, "which", lambda _tool: f"/usr/bin/{_tool}")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="x86_64\n"),
    )

    errors = checker.check_extended_platform_builder("linux-armhf")

    assert any("linux-armhf builder architecture must be one of" in error for error in errors)
    assert any("linux-armhf uname -m must be one of" in error for error in errors)


def _load_script(name: str):
    path = Path("scripts") / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
