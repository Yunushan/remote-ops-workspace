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


@pytest.mark.parametrize("target", ["linux-i386", "linux-armhf"])
def test_protected_linux_uses_exact_hash_locked_build_inputs(target: str) -> None:
    checker = _checker()
    assert checker.check_protected_linux_locks(checker.ROOT) == []
    compliance = checker.compliance
    workflow = compliance.EXTENDED_WORKFLOW_PATH.read_text(encoding="utf-8")
    job = f"{target}-native-evidence"
    block = compliance.workflow_job_block(workflow, job)
    lock_dir = compliance.PROTECTED_LINUX_LOCK_DIR
    options = {
        "bootstrap_lock_path": f"{lock_dir}/{target}-bootstrap.txt",
        "source_bootstrap_lock_path": compliance.PROTECTED_LINUX_CFFI_LOCK,
    }
    assert compliance.check_native_job_lock_usage(block, job, target, f"{lock_dir}/{target}.txt", **options) == []

    without_cffi_bootstrap = "\n".join(line for line in block.splitlines() if compliance.PROTECTED_LINUX_CFFI_LOCK not in line)
    errors = compliance.check_native_job_lock_usage(
        without_cffi_bootstrap, job, target, f"{lock_dir}/{target}.txt", **options,
    )
    assert any("must install" in error and "linux-32bit-cffi.txt" in error for error in errors)


def test_macos_lock_resolution_uses_the_native_installer_minimum(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    resolver = _checker().resolver
    config = json.loads(resolver.CONFIG.read_text(encoding="utf-8"))
    minimum = config["macos_deployment_target"]
    installer = Path("scripts/make_macos_native.sh").read_text(encoding="utf-8")
    assert f'MACOS_MINIMUM_VERSION="{minimum}.0"' in installer
    monkeypatch.setenv("MACOSX_DEPLOYMENT_TARGET", "13.0")
    _use_checkout(monkeypatch, resolver, _release_checkout(tmp_path))
    observed = {}

    def capture(command, *, cwd, env, check):
        output = Path(command[command.index("--output-file") + 1])
        observed[output.stem] = env["MACOSX_DEPLOYMENT_TARGET"]
        output.write_text(f"sample==1.0 --hash=sha256:{'a' * 64}\n", encoding="utf-8")

    monkeypatch.setattr(resolver.subprocess, "run", capture)
    for target in ("macos-x64", "macos-arm64", "windows-x64"):
        resolver.compile_lock(Path("uv"), config, target, config["targets"][target], system_certs=False)
    assert observed == {"macos-x64": minimum, "macos-arm64": minimum, "windows-x64": "13.0"}


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


def test_signed_native_release_requires_isolated_python_before_lock_install() -> None:
    checker = _checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    workflow = workflow.replace("python -m venv ", "python -m venv --system-site-packages ")
    errors = checker.check_locks(workflows={"release.yml": workflow})
    for job in ("windows-native", "macos-native", "linux-native"):
        assert f"release.yml {job} must create an isolated Python environment before installing its lock" in errors


def test_signed_native_runtime_report_must_use_matrix_lock() -> None:
    checker = _checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    workflow = workflow.replace('RELEASE_DEPENDENCY_LOCK: ${{ matrix.lock }}', 'RELEASE_DEPENDENCY_LOCK: ${{ matrix.bootstrap_lock }}')
    errors = checker.check_locks(workflows={"release.yml": workflow})
    for job in ("windows-native", "macos-native", "linux-native"):
        assert f"release.yml {job} must verify its installed inventory against the matrix lock" in errors


def test_signed_native_runtime_report_requires_exact_locked_versions(tmp_path: Path) -> None:
    checker = _checker()
    report = tmp_path / "pip-inspect.json"
    lock = tmp_path / "hashed-lock.txt"
    lock.write_text(f"setuptools==84.0.0 --hash=sha256:{'a' * 64}\n", encoding="utf-8")
    project = {"name": "remote_ops_workspace", "version": "1.0.27"}
    pinned = {"name": "setuptools", "version": "84.0.0"}

    def install(*distributions: dict[str, str]) -> None:
        payload = {"version": "1", "installed": [{"metadata": item} for item in distributions]}
        report.write_text(json.dumps(payload), encoding="utf-8")

    install(project, pinned)
    assert checker.main(["--runtime-report", str(report), "--lock", str(lock)]) == 0

    install(project, {"name": "setuptools", "version": "83.0.0"}, {"name": "wheel", "version": "0.48.0"})
    errors = checker.check_runtime_report(report, lock)
    assert len(errors) == 1
    assert "unexpected=['wheel'], version-mismatched=['setuptools']" in errors[0]

    install(project)
    assert "missing=['setuptools']" in checker.check_runtime_report(report, lock)[0]
    install(pinned)
    assert "missing the installed remote-ops-workspace" in checker.check_runtime_report(report, lock)[0]


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
