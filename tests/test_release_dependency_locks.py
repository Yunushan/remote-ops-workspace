from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest


def _checker():
    path = Path("scripts/check_release_dependency_locks.py")
    spec = importlib.util.spec_from_file_location("release_dependency_lock_tests", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_complete_modern_locks_are_consumed_without_mutable_resolution() -> None:
    assert _checker().check_locks() == []


def _release_checkout(tmp_path: Path) -> Path:
    (tmp_path / "configs").mkdir()
    shutil.copyfile("configs/release_dependency_locks.json", tmp_path / "configs/release_dependency_locks.json")
    shutil.copyfile("requirements-release.txt", tmp_path / "requirements-release.txt")
    shutil.copyfile(".gitattributes", tmp_path / ".gitattributes")
    shutil.copytree("requirements-locks", tmp_path / "requirements-locks")
    return tmp_path


def _use_checkout(monkeypatch: pytest.MonkeyPatch, resolver, root: Path) -> None:
    monkeypatch.setattr(resolver, "ROOT", root)
    monkeypatch.setattr(resolver, "CONFIG", root / "configs/release_dependency_locks.json")
    monkeypatch.setattr(resolver, "LOCKS", root / "requirements-locks")


@pytest.mark.parametrize("ending", [b"\r\n", b"\r"])
@pytest.mark.parametrize("relative", [
    "configs/release_dependency_locks.json",
    "requirements-release.txt",
    "requirements-locks/inputs/core.in",
    "requirements-locks/windows-x64.txt",
    "requirements-locks/windows-x64-bootstrap.txt",
])
def test_non_lf_hashed_bytes_fail_even_with_matching_receipt_before_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ending: bytes, relative: str,
) -> None:
    checker = _checker()
    root = _release_checkout(tmp_path)
    path = root / relative
    path.write_bytes(path.read_bytes().replace(b"\n", ending, 1))
    receipt_path = root / "requirements-locks/resolution.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    section = "lock_sha256" if relative.endswith(".txt") and relative.startswith("requirements-locks/") else "input_sha256"
    key = path.name if section == "lock_sha256" else relative
    receipt[section][key] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8", newline="\n")
    receipt_bytes = receipt_path.read_bytes()
    assert checker.check_locks(root, workflows={}) == [
        f"{relative}: byte-hashed release inputs and locks require LF-only line endings; "
        "convert CRLF/lone CR to LF without changing pins, then refresh and review the resolution receipt"
    ]
    _use_checkout(monkeypatch, checker.resolver, root)

    def forbidden_resolution(*args, **kwargs):
        raise AssertionError("the resolver must not run for non-LF release bytes")

    monkeypatch.setattr(checker.resolver.subprocess, "run", forbidden_resolution)
    assert checker.resolver.main(["--uv", str(root / "not-executed")]) == 1
    assert "convert CRLF/lone CR to LF" in capsys.readouterr().err
    assert receipt_path.read_bytes() == receipt_bytes
    assert ending in path.read_bytes()


@pytest.mark.parametrize("rule", [
    "*.json text eol=lf",
    "requirements-release.txt text eol=lf",
    "requirements-locks/*.txt text eol=lf",
    "requirements-locks/inputs/*.in text eol=lf",
])
def test_root_attributes_must_preserve_hashed_release_checkout_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rule: str,
) -> None:
    checker = _checker()
    root = _release_checkout(tmp_path)
    attributes = root / ".gitattributes"
    attributes.write_text(attributes.read_text(encoding="utf-8").replace(rule, ""), encoding="utf-8", newline="\n")
    error = f"root .gitattributes must preserve release receipt bytes with: {rule}"
    assert checker.check_locks(root, workflows={}) == [error]
    _use_checkout(monkeypatch, checker.resolver, root)
    assert checker.resolver.main(["--uv", str(root / "not-executed")]) == 1


def test_generator_rechecks_exact_input_bytes_before_writing_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    resolver = _checker().resolver
    root = _release_checkout(tmp_path)
    _use_checkout(monkeypatch, resolver, root)
    uv = root / "uv"
    uv.write_bytes(b"unused test resolver")
    monkeypatch.setattr(resolver.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="uv 0.12.21\n"))

    def changed_input(*args, **kwargs):
        path = root / "requirements-release.txt"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n", 1))

    monkeypatch.setattr(resolver, "compile_lock", changed_input)
    receipt_path = root / "requirements-locks/resolution.json"
    before = receipt_path.read_bytes()
    assert resolver.main(["--uv", str(uv), "--target", "windows-x86"]) == 1
    assert "LF-only line endings" in capsys.readouterr().err
    assert receipt_path.read_bytes() == before


def test_generator_writes_lf_receipt_bound_to_original_lf_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _checker()
    resolver = checker.resolver
    root = _release_checkout(tmp_path)
    _use_checkout(monkeypatch, resolver, root)
    uv = root / "uv"
    uv.write_bytes(b"unused test resolver")
    monkeypatch.setattr(resolver.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="uv 0.12.21\n"))
    monkeypatch.setattr(resolver, "compile_lock", lambda *args, **kwargs: None)
    assert resolver.main(["--uv", str(uv), "--target", "windows-x86"]) == 0
    assert b"\r" not in (root / "requirements-locks/resolution.json").read_bytes()
    assert checker.check_locks(root, workflows={}) == []


def test_mutable_project_resolution_cannot_hide_after_hashed_dependencies() -> None:
    checker = _checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    workflow = workflow.replace('--no-deps --no-build-isolation ".[${Extras}]"', '".[${Extras}]"')
    errors = checker.check_locks(workflows={"release.yml": workflow})
    assert any("dependency-resolving pip install outside" in error for error in errors)


def test_bootstrap_requires_exact_versions_and_reviewed_artifact_hashes(tmp_path: Path) -> None:
    checker = _checker().compliance
    final = tmp_path / "final.txt"
    bootstrap = tmp_path / "bootstrap.txt"
    final.write_text(f"setuptools==84.0.0 --hash=sha256:{'a' * 64}\n", encoding="utf-8")
    bootstrap.write_text(f"setuptools==84.0.0 --hash=sha256:{'a' * 64}\n", encoding="utf-8")
    assert checker.check_bootstrap_lock_subset(tmp_path, "final.txt", "bootstrap.txt") == []
    for entry in (f"setuptools==84.0.0 --hash=sha256:{'b' * 64}\n", f"setuptools==83.0.0 --hash=sha256:{'a' * 64}\n"):
        bootstrap.write_text(entry, encoding="utf-8")
        assert any("not an exact version/hash subset" in error for error in checker.check_bootstrap_lock_subset(tmp_path, "final.txt", "bootstrap.txt"))


def test_hashed_lock_cannot_add_an_unreviewed_package_index(tmp_path: Path) -> None:
    checker = _checker().compliance
    lock = tmp_path / "lock.txt"
    lock.write_text(f"--extra-index-url https://example.invalid/packages\ncryptography==50.0.1 --hash=sha256:{'a' * 64}\n", encoding="utf-8")
    _, errors = checker.read_hashed_lock_entries(tmp_path, {"file": "lock.txt"}, "test lock")
    assert any("resolver directive" in error for error in errors)


def test_installer_gui_gate_rejects_presence_only_proof() -> None:
    path = Path("scripts/check_native_installer_smoke.py")
    spec = importlib.util.spec_from_file_location("native_gui_lock_tests", path)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    script = Path("scripts/smoke_windows_native.ps1").read_text(encoding="utf-8")
    assert checker.check_gui_runtime_script("windows", script) == []
    for required in ('WaitForExit(25000)', '$Result.frozen -ne $true', 'Get-FileHash -LiteralPath $Image', 'Test-PackagedGui $GuiPath'):
        assert checker.check_gui_runtime_script("windows", script.replace(required, "removed"))
