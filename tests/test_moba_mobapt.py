from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

import remote_ops_workspace.moba_mobapt as mobapt
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
    def which(name: str) -> str | None:
        return f"C:/Tools/{name}.exe" if name == "winget" else None

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


def test_mobapt_serializers_cover_runtime_bundle_and_package_results(tmp_path: Path) -> None:
    runtime_root, evidence_path = _write_mobapt_runtime_tree(tmp_path)
    environment = build_mobapt_environment_status(
        system="Windows",
        which=lambda name: "C:/Tools/winget.exe" if name == "winget" else None,
        tools=("ssh",),
        runtime_roots=[runtime_root],
    )
    runtime = build_mobapt_runtime_status(roots=[runtime_root])
    validation = validate_mobapt_cache_evidence(evidence_path, assets_dir=runtime_root)
    bundle_plan = build_mobapt_runtime_bundle_plan(
        tmp_path / "bundle",
        tools=("bash",),
        packages=("htop=3.3",),
        allow_shims=True,
    )
    bundle_result = write_mobapt_runtime_bundle(bundle_plan)
    package_plan = build_mobapt_package_plan(
        "search",
        "htop",
        manager="apt",
        system="Linux",
        which=lambda name: "/usr/bin/apt" if name == "apt" else None,
    )
    package_result = run_mobapt_package_plan(package_plan)

    assert environment.to_dict()["package_managers"][0]["key"] == "winget"
    assert environment.to_dict()["base_tools"][0]["name"] == "ssh"
    assert runtime.to_dict()["candidates"][0]["packages"][0]["name"] == "htop"
    assert validation.to_dict()["passed"] is True
    assert bundle_plan.to_dict()["packages"][0]["version"] == "3.3"
    assert bundle_result.to_dict()["tool_count"] == 1
    assert package_plan.printable() == "/usr/bin/apt search htop"
    assert package_plan.to_dict()["manager"]["key"] == "apt"
    assert package_result.to_dict()["executed"] is False


def test_mobapt_runtime_roots_unavailable_manager_and_plan_rejections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_root = tmp_path / "environment-runtime"
    monkeypatch.setenv(mobapt.MOBAPT_RUNTIME_DIR_ENV, str(env_root))
    assert env_root in mobapt.mobapt_runtime_roots([])

    plan = build_mobapt_package_plan(
        "install",
        "htop",
        manager="apt",
        system="Linux",
        which=lambda name: None,
    )
    assert "not available" in plan.notes[-1]
    result = run_mobapt_package_plan(plan, execute=True)
    assert result.returncode == 127
    assert result.executed is False

    with pytest.raises(ValueError, match="at least one package spec"):
        build_mobapt_runtime_bundle_plan(tmp_path / "empty", tools=("bash",), packages=())

    note_plan = build_mobapt_runtime_bundle_plan(
        tmp_path / "notes",
        tools=("bash",),
        packages=("htop=3.3",),
        copy_host_tools=True,
    )
    assert any("host PATH" in note for note in note_plan.notes)
    assert not any("Shim generation" in note for note in note_plan.notes)
    with pytest.raises(ValueError, match="plan schema"):
        write_mobapt_runtime_bundle(replace(note_plan, schema="wrong"))


def test_mobapt_bundle_uses_supplied_tool_and_package_assets(tmp_path: Path) -> None:
    tool = tmp_path / "bash.exe"
    package = tmp_path / "htop.zip"
    tool.write_bytes(b"real-tool")
    package.write_bytes(b"real-package")
    plan = build_mobapt_runtime_bundle_plan(
        tmp_path / "bundle",
        tools=("bash",),
        packages=("htop=3.3",),
        tool_sources={"bash": tool},
        package_sources={"htop=3.3": package},
    )
    result = write_mobapt_runtime_bundle(plan)

    assert result.shimmed_tools == ()
    assert result.synthetic_packages == ()
    assert not any("require replacement" in note for note in result.notes)
    assert (Path(result.root) / "bin" / "bash").read_bytes() == b"real-tool"
    assert (Path(result.root) / "packages" / "htop-3.3.zip").read_bytes() == b"real-package"


@pytest.mark.parametrize(
    ("manager_key", "action"),
    [
        (manager_key, action)
        for manager_key in (
            "winget",
            "choco",
            "scoop",
            "brew",
            "port",
            "apt",
            "dnf",
            "yum",
            "pacman",
            "zypper",
            "apk",
            "pkg",
            "pkg_add",
        )
        for action in ("search", "install", "update")
    ],
)
def test_mobapt_package_command_matrix(manager_key: str, action: str) -> None:
    manager = mobapt.MobAptPackageManager(
        key=manager_key,
        label=manager_key,
        executable=manager_key,
        available=True,
        system="test",
        notes=[],
    )
    command = mobapt._package_command(manager, action, "htop")
    assert command[0] == manager_key
    assert len(command) >= 2


def test_mobapt_manager_selection_and_fallback_platform_definitions() -> None:
    unavailable = mobapt.MobAptPackageManager(
        key="first",
        label="first",
        executable="first",
        available=False,
        system="test",
        notes=[],
    )
    available = replace(unavailable, key="second", available=True)

    assert mobapt._select_manager((unavailable, available), None).key == "second"
    assert mobapt._select_manager((unavailable,), None).key == "first"
    with pytest.raises(ValueError, match="no package manager definitions"):
        mobapt._select_manager((), None)
    with pytest.raises(ValueError, match="unsupported package manager for this platform"):
        mobapt._select_manager((unavailable, available), "missing")
    with pytest.raises(ValueError, match="unsupported package manager"):
        mobapt._package_command(replace(unavailable, key="unknown"), "search", "htop")
    assert {definition[0] for definition in mobapt._manager_definitions("plan9")} == {
        "pkg",
        "pkg_add",
    }


def test_mobapt_name_version_specs_and_probe_validation() -> None:
    with pytest.raises(ValueError, match="tool name contains unsupported"):
        mobapt._tool_name("bad/tool")
    with pytest.raises(ValueError, match="must not contain whitespace"):
        mobapt._package_name("bad package")
    with pytest.raises(ValueError, match="contains unsupported"):
        mobapt._package_name("$bad")
    with pytest.raises(ValueError, match="must not contain whitespace"):
        mobapt._package_version("1 2")
    with pytest.raises(ValueError, match="path separators"):
        mobapt._package_version("1/2")
    with pytest.raises(ValueError, match="at least one Unix tool"):
        mobapt._unique_tool_names([])
    assert mobapt._unique_tool_names(["bash", "bash", "sh"]) == ("bash", "sh")
    with pytest.raises(ValueError, match="name=version"):
        mobapt._bundle_package_specs(["htop"], {})
    with pytest.raises(ValueError, match="action must be one of"):
        mobapt._action("remove")

    package = mobapt.MobAptBundlePackageSpec("htop", "3.3")
    assert mobapt._default_terminal_probe(("sh",), (package,)) == "sh -lc htop --version"
    assert mobapt._default_terminal_probe(("busybox",), (package,)) == "busybox --version"
    assert mobapt._safe_bundle_filename("...") == "asset"


def test_mobapt_runtime_tool_source_host_copy_shim_and_required_paths(tmp_path: Path) -> None:
    source = tmp_path / "source-tool"
    source.write_bytes(b"tool")
    assert (
        mobapt._write_runtime_tool(
            "bash",
            tmp_path / "supplied",
            source_path=source,
            copy_host_tools=False,
            allow_shims=False,
            which=lambda name: None,
        )
        == "supplied"
    )
    with pytest.raises(ValueError, match="tool source.*is missing"):
        mobapt._write_runtime_tool(
            "bash",
            tmp_path / "missing-target",
            source_path=tmp_path / "missing-source",
            copy_host_tools=False,
            allow_shims=False,
            which=lambda name: None,
        )

    assert (
        mobapt._write_runtime_tool(
            "bash",
            tmp_path / "host-copy",
            source_path=None,
            copy_host_tools=True,
            allow_shims=False,
            which=lambda name: str(source),
        )
        == "host-path"
    )
    assert (
        mobapt._write_runtime_tool(
            "bash",
            tmp_path / "fallback-shim",
            source_path=None,
            copy_host_tools=True,
            allow_shims=True,
            which=lambda name: str(tmp_path / "not-a-file"),
        )
        == "shim"
    )
    with pytest.raises(ValueError, match="tool source.*is required"):
        mobapt._write_runtime_tool(
            "bash",
            tmp_path / "required",
            source_path=None,
            copy_host_tools=True,
            allow_shims=False,
            which=lambda name: None,
        )


def test_mobapt_package_archive_source_and_required_paths(tmp_path: Path) -> None:
    package_dir = tmp_path / "packages"
    package_dir.mkdir()
    package = mobapt.MobAptBundlePackageSpec("htop", "3.3")
    assert mobapt._bundle_package_archive_path(package_dir, package).suffix == ".rowpkg"

    invalid_suffix = replace(package, source_path=str(tmp_path / "archive.this-suffix-is-too-long"))
    assert mobapt._bundle_package_archive_path(package_dir, invalid_suffix).suffix == ".rowpkg"

    source = tmp_path / "archive.zip"
    source.write_bytes(b"package")
    supplied = replace(package, source_path=str(source))
    target = mobapt._bundle_package_archive_path(package_dir, supplied)
    assert target.suffix == ".zip"
    assert (
        mobapt._write_bundle_package(
            supplied,
            target,
            source_path=source,
            allow_synthetic=False,
        )
        == "supplied"
    )
    with pytest.raises(ValueError, match="package source.*is missing"):
        mobapt._write_bundle_package(
            supplied,
            package_dir / "missing.rowpkg",
            source_path=tmp_path / "missing.zip",
            allow_synthetic=False,
        )
    with pytest.raises(ValueError, match="package source.*is required"):
        mobapt._write_bundle_package(
            package,
            package_dir / "required.rowpkg",
            source_path=None,
            allow_synthetic=False,
        )


def test_mobapt_chmod_is_best_effort() -> None:
    class BrokenPath:
        class Stat:
            st_mode = 0

        def stat(self) -> Stat:
            return self.Stat()

        def chmod(self, mode: int) -> None:
            raise OSError("blocked")

    mobapt._chmod_executable(BrokenPath())  # type: ignore[arg-type]


def test_mobapt_runtime_candidate_rejects_bad_manifests(tmp_path: Path) -> None:
    missing = mobapt._load_runtime_candidate(tmp_path, tmp_path / "missing.json")
    assert missing.available is False
    assert "cannot be read" in missing.notes[0]

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert mobapt._load_runtime_candidate(tmp_path, invalid).available is False

    list_root = tmp_path / "list.json"
    list_root.write_text("[]", encoding="utf-8")
    list_candidate = mobapt._load_runtime_candidate(tmp_path, list_root)
    assert list_candidate.notes == ["runtime manifest root must be an object"]

    malformed = tmp_path / "malformed.json"
    malformed.write_text(
        json.dumps(
            {
                "schema": "wrong",
                "runtime": {"binaries": [1]},
                "packages": [1],
            }
        ),
        encoding="utf-8",
    )
    candidate = mobapt._load_runtime_candidate(tmp_path, malformed)
    assert candidate.available is False
    assert any("schema must be" in note for note in candidate.notes)
    assert "runtime binary entry must be an object" in candidate.notes
    assert "package entry must be an object" in candidate.notes
    assert "runtime manifest must include at least one binary entry" in candidate.notes
    assert "runtime manifest must include at least one cached package entry" in candidate.notes


def test_mobapt_manifest_asset_validation_failures(tmp_path: Path) -> None:
    notes: list[str] = []
    assert mobapt._manifest_asset_available(tmp_path, "", "a" * 64, notes, "asset") is False
    assert "path is required" in notes[-1]
    assert mobapt._manifest_asset_available(tmp_path, "asset", "bad", notes, "asset") is False
    assert "sha256 must be" in notes[-1]
    assert (
        mobapt._manifest_asset_available(tmp_path, "../escape", "a" * 64, notes, "asset")
        is False
    )
    assert "inside assets_dir" in notes[-1]
    assert mobapt._manifest_asset_available(tmp_path, "missing", "a" * 64, notes, "asset") is False
    assert "file is missing" in notes[-1]
    asset = tmp_path / "asset"
    asset.write_bytes(b"asset")
    assert mobapt._manifest_asset_available(tmp_path, "asset", "a" * 64, notes, "asset") is False
    assert "SHA-256 mismatch" in notes[-1]


def test_mobapt_cache_validator_rejects_unreadable_and_malformed_roots(tmp_path: Path) -> None:
    missing = validate_mobapt_cache_evidence(tmp_path / "missing.json")
    assert "cannot be read" in missing.errors[0]

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    invalid_result = validate_mobapt_cache_evidence(invalid)
    assert "not valid JSON" in invalid_result.errors[0]

    list_root = tmp_path / "list.json"
    list_root.write_text("[]", encoding="utf-8")
    list_result = validate_mobapt_cache_evidence(list_root)
    assert "root must be a JSON object" in list_result.errors[0]


@pytest.mark.parametrize(
    ("manifest_body", "expected_error"),
    [
        ("{", "runtime.manifest cannot be parsed as JSON"),
        ("[]", "runtime.manifest JSON root must be an object"),
        ('{"schema": "wrong"}', "runtime.manifest schema must be"),
    ],
)
def test_mobapt_cache_validator_rejects_bad_runtime_manifest(
    tmp_path: Path,
    manifest_body: str,
    expected_error: str,
) -> None:
    root, evidence = _write_mobapt_runtime_tree(tmp_path)
    manifest = root / "mobapt-runtime.json"
    manifest.write_text(manifest_body, encoding="utf-8")
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["runtime"]["manifest_sha256"] = _sha256(manifest)
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_mobapt_cache_evidence(evidence, assets_dir=root)
    assert any(expected_error in error for error in result.errors)


def test_mobapt_cache_validator_reports_missing_cache_and_terminal_contracts(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "bad-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "wrong",
                "release_target": "test",
                "runtime": {},
                "package_cache": {"packages": []},
                "install_tests": "bad",
                "terminal_probe": {"status": "failed"},
            }
        ),
        encoding="utf-8",
    )
    result = validate_mobapt_cache_evidence(evidence, assets_dir=tmp_path)

    assert f"schema must be {mobapt.MOBAPT_CACHE_EVIDENCE_SCHEMA}" in result.errors
    assert "package_cache.packages must include at least one offline package archive" in result.errors
    assert "install_tests must be a list" in result.errors
    assert "terminal_probe.status must be passed" in result.errors


def test_mobapt_cached_package_and_install_test_validation_edges(tmp_path: Path) -> None:
    errors: list[str] = []
    assert mobapt._validate_cached_packages({}, tmp_path, errors) == set()
    assert "package_cache.packages must be a list" in errors[-1]

    errors = []
    packages = mobapt._validate_cached_packages(
        [
            1,
            {
                "name": "bad package",
                "version": "1",
                "archive": "missing-one",
                "sha256": "a" * 64,
            },
            {
                "name": "",
                "version": "1",
                "archive": "missing-two",
                "sha256": "a" * 64,
            },
            {
                "name": "good",
                "version": "1",
                "archive": "missing-three",
                "sha256": "a" * 64,
            },
            {
                "name": "other",
                "version": "1",
                "archive": "missing-four",
                "sha256": "a" * 64,
            },
        ],
        tmp_path,
        errors,
    )
    assert packages == {"good", "other"}
    assert "package_cache.packages[0] must be an object" in errors
    assert any("name is invalid" in error for error in errors)

    errors = []
    assert mobapt._validate_install_tests({}, tmp_path, errors) == set()
    assert "install_tests must be a list" in errors[-1]
    errors = []
    tested = mobapt._validate_install_tests(
        [
            1,
            {
                "package": "bad package",
                "command": "",
                "status": "failed",
                "evidence_file": "missing-one",
                "evidence_sha256": "a" * 64,
            },
            {
                "package": "",
                "command": "",
                "status": "failed",
                "evidence_file": "missing-two",
                "evidence_sha256": "a" * 64,
            },
            {
                "package": "good",
                "command": "good --version",
                "status": "passed",
                "evidence_file": "missing-three",
                "evidence_sha256": "a" * 64,
            },
            {
                "package": "other",
                "command": "other --version",
                "status": "passed",
                "evidence_file": "missing-four",
                "evidence_sha256": "a" * 64,
            },
        ],
        tmp_path,
        errors,
    )
    assert tested == {"good", "other"}
    assert "install_tests[0] must be an object" in errors
    assert any("package is invalid" in error for error in errors)
    assert "install_tests[1].status must be passed" in errors


def test_mobapt_required_values_and_asset_hash_fail_closed(tmp_path: Path) -> None:
    errors: list[str] = []
    assert mobapt._required_mapping({"section": []}, "section", errors) == {}
    assert errors == ["section must be an object"]
    assert mobapt._required_text({}, "name", errors) == ""
    assert "name is required" in errors[-1]
    assert mobapt._required_text({"name": "bad\x01"}, "name", errors) == "bad\x01"
    assert "name is invalid" in errors[-1]

    assert mobapt._validate_asset_hash("", "", tmp_path, errors, "asset") is None
    assert mobapt._validate_asset_hash("asset", "bad", tmp_path, errors, "asset") is None
    assert "sha256 must be" in errors[-1]
    assert mobapt._validate_asset_hash("../escape", "a" * 64, tmp_path, errors, "asset") is None
    assert "inside assets_dir" in errors[-1]
    assert mobapt._validate_asset_hash("missing", "a" * 64, tmp_path, errors, "asset") is None
    assert "file is missing" in errors[-1]

    asset = tmp_path / "asset"
    asset.write_bytes(b"asset")
    assert mobapt._validate_asset_hash("asset", "a" * 64, tmp_path, errors, "asset") is None
    assert "SHA-256 mismatch" in errors[-1]
    assert mobapt._resolve_evidence_asset(str(asset.resolve()), tmp_path, errors, "asset") == asset


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
