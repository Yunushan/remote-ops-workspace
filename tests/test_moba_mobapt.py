from __future__ import annotations

import hashlib
import json
from pathlib import Path

from remote_ops_workspace.cli import build_parser
from remote_ops_workspace.moba_mobapt import (
    build_mobapt_environment_status,
    build_mobapt_package_plan,
    build_mobapt_runtime_bundle_plan,
    build_mobapt_runtime_status,
    discover_mobapt_embedded_runtimes,
    run_mobapt_package_plan,
    validate_mobapt_cache_evidence,
    write_mobapt_runtime_bundle,
)


def test_mobapt_status_discovers_host_package_managers_and_unix_tools() -> None:
    def which(name: str) -> str | None:
        if name in {"winget", "ssh", "tar", "grep"}:
            return f"C:/Tools/{name}.exe"
        return None

    status = build_mobapt_environment_status(
        system="Windows",
        which=which,
        tools=("ssh", "tar", "grep", "awk"),
    )

    assert status.adapter_mode is True
    assert status.embedded_runtime_available is False
    assert status.package_managers[0].key == "winget"
    assert status.package_managers[0].available is True
    assert {tool.name: tool.available for tool in status.base_tools} == {
        "ssh": True,
        "tar": True,
        "grep": True,
        "awk": False,
    }


def test_mobapt_runtime_status_detects_row_owned_cache(tmp_path: Path) -> None:
    root, evidence = _write_mobapt_runtime_tree(tmp_path)

    candidates = discover_mobapt_embedded_runtimes(roots=[root])
    runtime = build_mobapt_runtime_status(roots=[root])
    environment = build_mobapt_environment_status(
        system="Windows",
        which=lambda name: None,
        tools=("ssh",),
        runtime_roots=[root],
    )

    assert candidates[0].available is True
    assert candidates[0].packages[0].name == "htop"
    assert runtime.embedded_runtime_available is True
    assert runtime.selected_runtime == "ROW Unix Runtime"
    assert environment.embedded_runtime_available is True
    assert evidence.is_file()


def test_mobapt_runtime_bundle_writer_creates_verifiable_release_tree(tmp_path: Path) -> None:
    out_dir = tmp_path / "bundle"

    plan = build_mobapt_runtime_bundle_plan(
        out_dir,
        tools=("bash", "grep"),
        packages=("htop=3.3",),
        release_target="windows-x64",
        allow_shims=True,
    )
    result = write_mobapt_runtime_bundle(plan)
    runtime = build_mobapt_runtime_status(roots=[out_dir])
    evidence = validate_mobapt_cache_evidence(Path(result.evidence_path), assets_dir=out_dir)

    assert result.tool_count == 2
    assert result.package_count == 1
    assert result.shimmed_tools == ("bash", "grep")
    assert result.synthetic_packages == ("htop",)
    assert runtime.embedded_runtime_available is True
    assert evidence.passed is True
    assert "mobapt-runtime.json" in result.files
    assert "mobapt-cache-evidence.json" in result.files


def test_mobapt_install_plan_uses_safe_argv_for_apt() -> None:
    plan = build_mobapt_package_plan(
        "install",
        "htop",
        manager="apt",
        system="Linux",
        which=lambda name: "/usr/bin/apt" if name == "apt" else None,
    )

    assert plan.action == "install"
    assert plan.package == "htop"
    assert plan.manager.available is True
    assert plan.command == ["/usr/bin/apt", "install", "htop"]
    assert plan.execute_required is True


def test_mobapt_search_and_update_plans_are_available_for_winget() -> None:
    which = lambda name: f"C:/Tools/{name}.exe" if name == "winget" else None
    search = build_mobapt_package_plan(
        "search",
        "OpenSSH.Beta",
        manager="winget",
        system="Windows",
        which=which,
    )
    update = build_mobapt_package_plan(
        "update",
        manager="winget",
        system="Windows",
        which=which,
    )

    assert search.command == ["C:/Tools/winget.exe", "search", "OpenSSH.Beta"]
    assert update.package == ""
    assert update.command == ["C:/Tools/winget.exe", "upgrade", "--all"]


def test_mobapt_dry_run_does_not_call_external_runner() -> None:
    plan = build_mobapt_package_plan(
        "install",
        "rsync",
        manager="brew",
        system="Darwin",
        which=lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None,
    )
    calls: list[list[str]] = []

    result = run_mobapt_package_plan(
        plan,
        runner=lambda command, **kwargs: calls.append(command),
    )

    assert result.executed is False
    assert result.ok is True
    assert calls == []


def test_mobapt_execute_uses_external_runner() -> None:
    plan = build_mobapt_package_plan(
        "search",
        "rsync",
        manager="brew",
        system="Darwin",
        which=lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None,
    )
    captured: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> _FakeCompletedProcess:
        captured.append(command)
        return _FakeCompletedProcess(0, "rsync\n", "")

    result = run_mobapt_package_plan(plan, execute=True, runner=runner)

    assert result.executed is True
    assert result.ok is True
    assert result.stdout == "rsync\n"
    assert captured == [["/opt/homebrew/bin/brew", "search", "rsync"]]


def test_mobapt_rejects_unsafe_package_names() -> None:
    try:
        build_mobapt_package_plan(
            "install",
            "-rf",
            manager="apt",
            system="Linux",
            which=lambda name: "/usr/bin/apt" if name == "apt" else None,
        )
    except ValueError as exc:
        assert "package name" in str(exc)
    else:
        raise AssertionError("unsafe package names must be rejected")


def test_mobapt_cli_commands_are_registered() -> None:
    parser = build_parser()
    status = parser.parse_args(["mobapt", "status", "--json"])
    runtime = parser.parse_args(["mobapt", "runtime-status", "--json"])
    bundle = parser.parse_args(
        ["mobapt", "bundle-runtime", "--out", "bundle", "--tool", "bash", "--package", "htop=3.3", "--json"]
    )
    verify = parser.parse_args(["mobapt", "cache-verify", "--evidence", "mobapt-cache.json", "--json"])
    search = parser.parse_args(["mobapt", "search", "htop", "--manager", "apt", "--json"])
    install = parser.parse_args(["mobapt", "install", "htop", "--manager", "apt", "--execute"])
    update = parser.parse_args(["mobapt", "update", "--manager", "apt", "--json"])

    assert status.func.__name__ == "cmd_mobapt_status"
    assert runtime.func.__name__ == "cmd_mobapt_runtime_status"
    assert bundle.func.__name__ == "cmd_mobapt_bundle_runtime"
    assert verify.func.__name__ == "cmd_mobapt_cache_verify"
    assert search.func.__name__ == "cmd_mobapt_package"
    assert search.action == "search"
    assert install.action == "install"
    assert update.action == "update"


def test_mobapt_cache_evidence_verifies_offline_package_and_terminal_probe(
    tmp_path: Path,
) -> None:
    root, evidence = _write_mobapt_runtime_tree(tmp_path)

    result = validate_mobapt_cache_evidence(evidence, assets_dir=root)

    assert result.passed is True
    assert result.errors == []
    assert result.summary["package_count"] == 1
    assert result.summary["install_test_count"] == 1
    assert result.summary["terminal_probe"] == "bash -lc htop --version"


def test_mobapt_cache_evidence_rejects_missing_install_proof(tmp_path: Path) -> None:
    root, evidence = _write_mobapt_runtime_tree(tmp_path)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["install_tests"] = []
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_mobapt_cache_evidence(evidence, assets_dir=root)

    assert result.passed is False
    assert "install_tests missing package proof for: htop" in result.errors


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _write_mobapt_runtime_tree(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "mobapt-runtime"
    bin_dir = root / "bin"
    package_dir = root / "packages"
    evidence_dir = root / "evidence"
    bin_dir.mkdir(parents=True)
    package_dir.mkdir()
    evidence_dir.mkdir()
    bash = bin_dir / "bash"
    archive = package_dir / "htop-3.3.rowpkg"
    package_index = package_dir / "index.json"
    install_evidence = evidence_dir / "htop-install.txt"
    terminal_evidence = evidence_dir / "terminal-htop.txt"
    bash.write_bytes(b"fake-bash-runtime")
    archive.write_bytes(b"fake-htop-package")
    package_index.write_text(json.dumps({"packages": ["htop"]}), encoding="utf-8")
    install_evidence.write_text("installed htop 3.3\n", encoding="utf-8")
    terminal_evidence.write_text("htop 3.3\n", encoding="utf-8")
    manifest = root / "mobapt-runtime.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "row.mobapt.runtime.v1",
                "runtime": {
                    "name": "ROW Unix Runtime",
                    "version": "1.0.0",
                    "binaries": [
                        {
                            "name": "bash",
                            "path": "bin/bash",
                            "sha256": _sha256(bash),
                        }
                    ],
                },
                "packages": [
                    {
                        "name": "htop",
                        "version": "3.3",
                        "archive": "packages/htop-3.3.rowpkg",
                        "sha256": _sha256(archive),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    evidence = root / "mobapt-cache-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "row.mobapt.offline-cache-evidence.v1",
                "release_target": "windows-x64",
                "runtime": {
                    "manifest": "mobapt-runtime.json",
                    "manifest_sha256": _sha256(manifest),
                },
                "package_cache": {
                    "index": "packages/index.json",
                    "index_sha256": _sha256(package_index),
                    "packages": [
                        {
                            "name": "htop",
                            "version": "3.3",
                            "archive": "packages/htop-3.3.rowpkg",
                            "sha256": _sha256(archive),
                        }
                    ],
                },
                "install_tests": [
                    {
                        "package": "htop",
                        "command": "bash -lc htop --version",
                        "status": "passed",
                        "evidence_file": "evidence/htop-install.txt",
                        "evidence_sha256": _sha256(install_evidence),
                    }
                ],
                "terminal_probe": {
                    "command": "bash -lc htop --version",
                    "status": "passed",
                    "evidence_file": "evidence/terminal-htop.txt",
                    "evidence_sha256": _sha256(terminal_evidence),
                },
            }
        ),
        encoding="utf-8",
    )
    return root, evidence


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
