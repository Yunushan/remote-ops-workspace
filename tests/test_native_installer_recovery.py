from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import types
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def helper(monkeypatch):
    module = load(REPO_ROOT / "scripts/native_installer_recovery.py", "transition_successor_test")
    return module


@pytest.mark.skipif(
    os.name != "nt" or shutil.which("pwsh") is None,
    reason="Actual Windows PowerShell 7 DACL provisioning requires its native host",
)
def test_private_fixture_provisions_actual_protected_windows_dacl(helper, tmp_path):
    # Fresh owned directory only: no runner spoof, installers or fixture secrets.
    parent = tmp_path / "private-native-fixture"
    helper.private_parent(parent)
    assert parent.is_dir()


def test_failure_diagnostic_exports_only_fixed_codes(helper):
    for code in helper.TRANSITION_FAILURE_CODES:
        assert helper.failure_code(helper.TransitionValidationError(code)) == code
    for code in helper.PRIVATE_FAILURE_CODES:
        assert helper.failure_code(helper.PrivateFixtureError(code)) == code
    private_text = "private captured output must remain private"
    assert helper.failure_code(ValueError(private_text)) == "unclassified"
    assert helper.failure_code(helper.PrivateFixtureError(private_text)) == "unclassified"
    with pytest.raises(ValueError, match="unknown transition diagnostic"):
        helper.TransitionValidationError(private_text)


@pytest.mark.parametrize("count", (0, 2))
def test_ambiguous_uninstaller_refuses_before_any_command(helper, tmp_path, count):
    for index in range(count):
        (tmp_path / f"unins{index:03}.exe").write_bytes(b"never executed fixture")
    drill = helper.Drill(tmp_path, None)
    drill.command = lambda *_args, **_kwargs: pytest.fail("ambiguous uninstaller launched")
    with pytest.raises(helper.TransitionValidationError) as error:
        drill.uninstall(tmp_path, {})
    assert helper.failure_code(error.value) == "owned-uninstaller-count-mismatch"


def test_successful_vault_command_with_wrong_bytes_is_rejected_and_private_file_removed(
    helper, tmp_path
):
    drill = helper.Drill(tmp_path, None)

    def command(_executable, arguments, _environment):
        if arguments == ["--version"]:
            return "remote-ops-workspace 1.0.24"
        if arguments[0] == "platforms":
            return json.dumps({"release_architectures": [1], "windows_legacy_targets": [1]})
        if arguments[0] == "profile":
            return "[]"
        if arguments[0] == "layout":
            return json.dumps({"splitter_sizes": [[300, 700], [125, 375]]})
        if arguments[0] == "snippet":
            return json.dumps([{"name": "recovery-snippet"}])
        if arguments[0] == "macro":
            return json.dumps({"events": [{"text": "printf saved"}]})
        if arguments[1] == "status":
            return json.dumps({"backend_available": True, "initialized": True, "version": 2})
        if arguments[1] == "list":
            return "recovery-secret\n"
        assert arguments[:2] == ["vault", "get"]
        Path(arguments[-1]).write_text("wrong synthetic value", encoding="utf-8")
        return "command exit success, but not the expected decrypted bytes"

    drill.command = command
    with pytest.raises(helper.TransitionValidationError) as error:
        drill.inspect(Path("never-executed.exe"), tmp_path, "1.0.24", {}, "expected", 2, [])
    assert helper.failure_code(error.value) == "native-vault-secret-mismatch"
    assert not list(tmp_path.glob("private-vault-check-*"))


@pytest.mark.parametrize(
    "change,expected_code",
    (
        ("none", None),
        ("original", "rollback-original-state-mismatch"),
        ("previous", "rollback-previous-snapshot-mismatch"),
        ("candidate", "rollback-candidate-snapshot-mismatch"),
    ),
)
def test_rollback_preservation_detects_actual_byte_changes(
    helper, tmp_path, change, expected_code
):
    recovery = load(REPO_ROOT / "scripts/smoke_workspace_recovery.py", "preservation_oracle_test")
    home = tmp_path / "original"
    home.mkdir()
    state = home / "opaque-state.dat"
    state.write_bytes(b"preserve damaged original")
    previous = tmp_path / "previous.rowbackup"
    candidate = tmp_path / "candidate.rowbackup"
    previous.write_bytes(b"opaque prior ciphertext fixture")
    candidate.write_bytes(b"opaque candidate ciphertext fixture")
    inventory = recovery._tree_summary(home)
    old_hash, new_hash = helper.digest(previous), helper.digest(candidate)
    if change != "none":
        {"original": state, "previous": previous, "candidate": candidate}[change].write_bytes(
            b"unexpected change"
        )
    arguments = (recovery, home, previous, candidate, inventory, old_hash, new_hash)
    if expected_code is None:
        helper.check_rollback_preservation(*arguments)
    else:
        with pytest.raises(helper.TransitionValidationError) as error:
            helper.check_rollback_preservation(*arguments)
        assert helper.failure_code(error.value) == expected_code
    assert home.is_dir() and state.is_file() and previous.is_file() and candidate.is_file()


@pytest.fixture
def candidate(helper, tmp_path, monkeypatch):
    helper.ROOT = tmp_path
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    head, tree = "a" * 40, "b" * 40
    monkeypatch.setattr(
        helper,
        "git_output",
        lambda *args: head if args[-1] == "HEAD" else tree if args[-1] == "HEAD^{tree}" else "",
    )
    monkeypatch.setattr(
        helper.subprocess, "check_output", lambda *_args, **_kwargs: b"tracked.py\0"
    )
    (tmp_path / "tracked.py").write_bytes(b"source fixture")
    material = "tracked.py\0" + helper.digest(tmp_path / "tracked.py") + "\n"
    source = {
        "head": head,
        "tree": tree,
        "checkout_bytes_sha256": hashlib.sha256(material.encode()).hexdigest(),
    }
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(
        REPO_ROOT / "scripts/candidate_native_proof.py", scripts / "candidate_native_proof.py"
    )
    for name in ("candidate_windows_owned.py", "smoke_workspace_recovery.py"):
        (scripts / name).write_bytes(b"unused fixture helper")
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/workspace_recovery_fixture.json").write_bytes(b"unused fixture")
    proof = tmp_path / "build/candidate-proof/windows-x64"
    proof.mkdir(parents=True)
    binding_path = tmp_path / "build/native-smoke/windows-x64/candidate-runtime-byte-binding.json"
    binding_path.parent.mkdir(parents=True)
    cli, gui = b"non-executable CLI fixture", b"non-executable GUI fixture"
    expected = {"cli": hashlib.sha256(cli).hexdigest(), "gui": hashlib.sha256(gui).hexdigest()}
    archives = [
        {
            "path": f"build/native/windows/pyinstaller-dist/{'row.exe' if role == 'cli' else 'row-gui.exe'}",
            "artifact_sha256": hash_value,
            "toc": [["fixture"]],
        }
        for role, hash_value in expected.items()
    ]
    helper.save(proof / "pyinstaller-archives.json", archives)
    (proof / "pip-inspect.json").write_text('{"installed":[]}')
    (proof / "pip-inspect.stderr.log").write_bytes(b"")
    paths = [
        "portable/bin/row.exe",
        "exe-install/bin/row.exe",
        "msi-install/bin/row.exe",
        "portable/bin/row-gui.exe",
        "portable/Remote Ops Workspace GUI.exe",
        "exe-install/bin/row-gui.exe",
        "msi-install/bin/row-gui.exe",
    ]
    binding = {
        "schema_version": 1,
        "target": "windows-x64",
        "status": "bound",
        "smoke_complete": True,
        "required_paths": paths,
        "expected_executables": [
            {"role": role, "path": item["path"], "sha256": item["artifact_sha256"]}
            for role, item in zip(("cli", "gui"), archives, strict=True)
        ],
        "observations": [
            {
                "path": path,
                "role": "cli" if path.endswith("/row.exe") else "gui",
                "matched": True,
                "expected_sha256": expected["cli" if path.endswith("/row.exe") else "gui"],
                "observed_sha256": expected["cli" if path.endswith("/row.exe") else "gui"],
            }
            for path in paths
        ],
    }
    helper.save(binding_path, binding)
    assets = tmp_path / "native-dist/windows"
    assets.mkdir(parents=True)
    prefix = "remote-ops-workspace-v1.0.27-windows-x64"
    setup = assets / (prefix + "-setup.exe")
    setup.write_bytes(b"non-executable setup fixture")
    portable = assets / (prefix + "-native.zip")
    with zipfile.ZipFile(portable, "w") as archive:
        archive.writestr("bin/row.exe", cli)
        archive.writestr("bin/row-gui.exe", gui)
    manifest = assets / (prefix + "-native-manifest.json")
    helper.save(
        manifest,
        [
            {"file": path.name, "sha256": helper.digest(path), "size_bytes": path.stat().st_size}
            for path in (setup, portable)
        ],
    )
    sums = assets / (prefix + "-native-SHA256SUMS.txt")
    sums.write_text(
        "".join(
            helper.digest(path) + "  " + path.name + "\n" for path in (setup, portable, manifest)
        )
    )
    finish = {
        "source": source,
        "source_unchanged": True,
        "target": "windows-x64",
        "run_id": "123",
        "run_attempt": "2",
        "native_build_outcome": "success",
        "native_smoke_outcome": "success",
        "native_pyinstaller_inventory_complete": True,
        "installed_project_sources_match_checkout": True,
        "pip_inspect_returncode": 0,
        "pip_inspect_json_valid": True,
        "pip_inspect_sha256": helper.digest(proof / "pip-inspect.json"),
        "pip_inspect_stderr_sha256": helper.digest(proof / "pip-inspect.stderr.log"),
        "native_executable_byte_binding": {
            "status": "bound",
            "report_path": "build/native-smoke/windows-x64/candidate-runtime-byte-binding.json",
            "report_sha256": helper.digest(binding_path),
        },
        "pyinstaller_archive_inventory_sha256": helper.digest(proof / "pyinstaller-archives.json"),
        "assets": [
            {
                "path": str(path.relative_to(tmp_path)),
                "sha256": helper.digest(path),
                "size": path.stat().st_size,
            }
            for path in assets.iterdir()
        ],
    }
    helper.save(proof / "finish.json", finish)
    prior_path = tmp_path / "prior-fixture.whl"
    prior_path.write_bytes(b"never imported wheel fixture")
    pins = tmp_path / "pins.json"
    helper.save(
        pins,
        {
            "assets": [
                {
                    "name": prior_path.name,
                    "size": prior_path.stat().st_size,
                    "digest": "sha256:" + helper.digest(prior_path),
                }
            ]
        },
    )
    rescue = tmp_path / "rescue.exe"
    rescue.write_bytes(cli)
    args = types.SimpleNamespace(
        candidate_source_sha=head,
        candidate_evidence=proof / "finish.json",
        candidate_dir=assets,
        previous_pins=pins,
        owned_runner=scripts / "candidate_windows_owned.py",
    )
    return args, finish, {prior_path.name: prior_path}, rescue


def test_current_finish_and_zip_bytes_are_consumed(helper, candidate):
    args, finish, _, _ = candidate
    paths, found = helper.candidate_assets(args, "1.0.27")
    assert len(paths) == 4 and found == finish


@pytest.mark.parametrize(
    "change",
    (
        "old-schema",
        "pip-failed",
        "pip-false",
        "pip-invalid-json",
        "binding-unbound",
        "binding-bytes",
        "archive-bytes",
        "pip-bytes",
        "source-bytes",
        "zip-bytes",
    ),
)
def test_failed_or_changed_candidate_proof_is_refused(helper, candidate, change):
    args, finish, _, _ = candidate
    if change == "old-schema":
        finish["native_inventory_complete"] = finish.pop("native_pyinstaller_inventory_complete")
    elif change == "pip-failed":
        finish["pip_inspect_returncode"] = 1
    elif change == "pip-false":
        finish["pip_inspect_returncode"] = False
    elif change == "pip-invalid-json":
        finish["pip_inspect_json_valid"] = False
    elif change == "binding-unbound":
        finish["native_executable_byte_binding"]["status"] = "not-bound"
    elif change == "source-bytes":
        (helper.ROOT / "tracked.py").write_bytes(b"changed source fixture")
    elif change == "zip-bytes":
        next(args.candidate_dir.glob("*.zip")).write_bytes(b"changed ZIP fixture")
    else:
        suffix = {
            "binding-bytes": "native-smoke/windows-x64/candidate-runtime-byte-binding.json",
            "archive-bytes": "candidate-proof/windows-x64/pyinstaller-archives.json",
            "pip-bytes": "candidate-proof/windows-x64/pip-inspect.json",
        }[change]
        (helper.ROOT / "build" / suffix).write_bytes(b"changed proof fixture")
    helper.save(args.candidate_evidence, finish)
    with pytest.raises(ValueError):
        helper.candidate_assets(args, "1.0.27")


@pytest.mark.parametrize(
    "change", ("none", "source", "finish", "input", "candidate", "prior", "rescue")
)
def test_final_revalidation_refuses_late_mutation(helper, candidate, change):
    args, finish, prior, rescue = candidate
    paths, _ = helper.candidate_assets(args, "1.0.27")
    before = helper.byte_records(helper.proof_input_paths(args))
    rescue_hash = helper.digest(rescue)
    if change == "source":
        (helper.ROOT / "tracked.py").write_bytes(b"late source mutation")
    elif change == "finish":
        updated = copy.deepcopy(finish)
        updated["changed-during-run"] = True
        helper.save(args.candidate_evidence, updated)
    elif change == "input":
        args.owned_runner.write_bytes(b"late helper mutation")
    elif change == "candidate":
        next(path for path in paths.values() if path.name.endswith("-setup.exe")).write_bytes(
            b"late candidate mutation"
        )
    elif change == "prior":
        next(iter(prior.values())).write_bytes(b"late prior mutation")
    elif change == "rescue":
        rescue.write_bytes(b"late rescue mutation")
    if change == "none":
        result = helper.revalidate_end(
            args, "1.0.27", finish, before, paths, prior, rescue, rescue_hash
        )
        assert result["source_unchanged"] and result["proof_inputs_unchanged"]
    else:
        with pytest.raises(ValueError):
            helper.revalidate_end(args, "1.0.27", finish, before, paths, prior, rescue, rescue_hash)


def test_complete_profile_expectations_match_known_prior_and_current_semantics(helper):
    fixture = json.loads((REPO_ROOT / "configs/workspace_recovery_fixture.json").read_text())
    previous = helper.profile_expectations(fixture)
    current = helper.profile_expectations(fixture, include_current=True)
    assert all(len(row) == 15 for row in current)
    assert len(previous) == 2 and len(current) == 3
    inherited = next(row for row in previous if row["name"] == "recovery-inherited")
    explicit = next(row for row in previous if row["name"] == "recovery-explicit")
    assert inherited["port"] is None and inherited["options"] == {
        "x11": "false",
        "compression": "true",
    }
    assert (
        explicit["port"] == 2201
        and explicit["username"] == "explicit-user"
        and explicit["tags"] == ["recovery"]
    )
    added = next(row for row in current if row["name"] == "current-only")
    assert added["username"] == "inherited-user" and added["options"] == {"x11": "false"}


@pytest.mark.parametrize(
    "field,value",
    (
        ("host", "wrong.invalid"),
        ("port", 23),
        ("tags", ["changed"]),
        ("description", "changed"),
        ("credential_ref", "changed"),
    ),
)
def test_full_native_profile_comparison_catches_formerly_unchecked_fields(
    helper, tmp_path, field, value
):
    fixture = json.loads((REPO_ROOT / "configs/workspace_recovery_fixture.json").read_text())
    expected = helper.profile_expectations(fixture)
    actual = copy.deepcopy(expected)
    actual[0][field] = value
    drill = helper.Drill(tmp_path, None)
    responses = iter(
        (
            "row 1.0.24",
            '{"release_architectures":[1],"windows_legacy_targets":[1]}',
            json.dumps(actual),
        )
    )
    drill.command = lambda *_args, **_kwargs: next(responses)
    with pytest.raises(ValueError, match="complete profile records"):
        drill.inspect(Path("unused.exe"), tmp_path, "1.0.24", {}, "never-decrypted", 2, expected)


def test_local_execution_gate_refuses_before_input_read(helper, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    with pytest.raises(RuntimeError, match="disposable GitHub-hosted"):
        helper.run(types.SimpleNamespace(candidate_source_sha="a" * 40))


@pytest.mark.parametrize(
    "change,expected_success,accepted",
    (
        ("none", True, True),
        ("negative", False, True),
        ("removed-uninstaller", True, True),
        ("timeout", False, False),
        ("active-child", True, False),
        ("job-open", True, False),
        ("wait-failed", False, False),
        ("unrelated-exit", False, False),
    ),
)
def test_owned_command_requires_exact_exit_and_cleanup_and_freezes_hash_before_launch(
    helper, tmp_path, change, expected_success, accepted
):
    owned = load(REPO_ROOT / "scripts/candidate_windows_owned.py", "transition_owned_test")
    executable = tmp_path / "uninstaller.exe"
    executable.write_bytes(b"never executed fixture")
    expected_hash = helper.digest(executable)

    def fake_run(exe, _arguments, _environment, output, _timeout):
        output.with_suffix(".log").write_text("fixture output")
        record = {
            "child_created": True,
            "job_assigned": True,
            "wait_result": 0,
            "exit_code": 0 if expected_success else 1,
            "owned_parent_cleanup_wait": 0,
            "active_owned_processes_after_cleanup": 0,
            "job_closed": True,
            "cleanup_errors": [],
        }
        if change == "removed-uninstaller":
            exe.unlink()
        elif change == "timeout":
            record.update(wait_result=258, exit_code=None, error="TimeoutError: mocked")
        elif change == "active-child":
            record["active_owned_processes_after_cleanup"] = 1
        elif change == "job-open":
            record["job_closed"] = False
        elif change == "wait-failed":
            record["wait_result"] = 0xFFFFFFFF
        elif change == "unrelated-exit":
            record["exit_code"] = 2
        return record

    owned.run_owned = fake_run
    drill = helper.Drill(tmp_path, owned)
    if accepted:
        assert (
            drill.command(executable, [], {}, expected_success=expected_success) == "fixture output"
        )
    else:
        with pytest.raises(RuntimeError):
            drill.command(executable, [], {}, expected_success=expected_success)
    assert drill.calls[0]["exe_sha256"] == expected_hash
    assert (tmp_path / "command-1.json").is_file()


class ReadOnlyRegistry:
    HKEY_LOCAL_MACHINE = "machine"
    HKEY_CURRENT_USER = "user"
    KEY_READ = 0x20019
    KEY_WOW64_64KEY = 0x100
    KEY_WOW64_32KEY = 0x200
    uninstall = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    upgrade = r"SOFTWARE\Classes\Installer\UpgradeCodes\4B12A8F884E6A1B4F9D59B73E381700D"
    other_upgrade = r"SOFTWARE\Microsoft\Installer\UpgradeCodes\4B12A8F884E6A1B4F9D59B73E381700D"

    def __init__(self):
        self.keys = {}
        self.opens = []
        self.disappear = False
        self.deny = False

    class Handle:
        def __init__(self, identity):
            self.identity = identity

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def OpenKey(self, hive, path, reserved, access):
        assert reserved == 0
        assert access in (
            self.KEY_READ | self.KEY_WOW64_64KEY,
            self.KEY_READ | self.KEY_WOW64_32KEY,
        )
        if isinstance(hive, self.Handle):
            old_hive, old_view, old_path = hive.identity
            identity = (old_hive, old_view, old_path + "\\" + path)
            if self.disappear:
                raise FileNotFoundError("mock enumerated child disappeared")
        else:
            identity = (hive, access & 0x300, path)
        self.opens.append(identity)
        if self.deny:
            raise PermissionError("mock read-only preflight access denied")
        if identity not in self.keys:
            raise FileNotFoundError("mock absent registry key")
        return self.Handle(identity)

    def QueryInfoKey(self, handle):
        return len(self.keys[handle.identity].get("children", [])), 0, 0

    def EnumKey(self, handle, index):
        return self.keys[handle.identity]["children"][index]

    def QueryValueEx(self, handle, name):
        values = self.keys[handle.identity]
        if name not in values:
            raise FileNotFoundError("mock missing optional value")
        return values[name], 1


@pytest.fixture
def install_guard_environment(monkeypatch):
    for key in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("workspace", ("missing", "different", "relative", "matching"))
def test_exact_hosted_workspace_gate(helper, tmp_path, monkeypatch, workspace):
    helper.ROOT = tmp_path.resolve()
    if workspace == "missing":
        monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    else:
        value = (
            str(tmp_path)
            if workspace == "matching"
            else "."
            if workspace == "relative"
            else str(tmp_path / "different")
        )
        monkeypatch.setenv("GITHUB_WORKSPACE", value)
    if workspace == "matching":
        helper.assert_hosted_workspace()
    else:
        with pytest.raises(RuntimeError, match="exact hosted checkout"):
            helper.assert_hosted_workspace()


def test_workspace_refusal_precedes_fixture_reads_and_downloads(helper, tmp_path, monkeypatch):
    helper.ROOT = tmp_path
    for key, value in {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Windows",
        "RUNNER_ARCH": "X64",
        "GITHUB_REPOSITORY": helper.REPO,
        "GITHUB_WORKSPACE": str(tmp_path / "different"),
    }.items():
        monkeypatch.setenv(key, value)
    calls = []
    monkeypatch.setattr(helper, "byte_records", lambda *_args: calls.append("fixture-read"))
    monkeypatch.setattr(helper, "private_parent", lambda *_args: calls.append("fixture-created"))
    monkeypatch.setattr(helper, "previous_assets", lambda *_args: calls.append("download"))
    with pytest.raises(RuntimeError, match="exact hosted checkout"):
        helper.run(types.SimpleNamespace(candidate_source_sha="a" * 40))
    assert calls == [] and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "key_name,display,location,expected",
    (
        ("{5C887096-F4E5-4AB8-8D6F-65052D08D284}_is1", "", "", True),
        ("unrelated", "Remote Ops Workspace (x64)", "", True),
        ("unrelated", "remote ops workspace-tools", "", True),
        ("unrelated", "Other tool", '  "C:/odd?directory/Remote Ops Workspace/"  ', True),
        ("unrelated", "Other tool", "C:\\NUL\x00bad?directory\\Other", False),
        ("unrelated", "Remote Ops Workspaces", "C:/Other", False),
    ),
)
def test_registered_product_uses_text_only_metadata(
    helper, monkeypatch, key_name, display, location, expected
):
    monkeypatch.setattr(
        helper,
        "Path",
        lambda *_args: pytest.fail("untrusted registry metadata was parsed as a filesystem path"),
    )
    assert helper.registered_product(key_name, display, location) is expected


@pytest.mark.parametrize("hive", ("machine", "user"))
@pytest.mark.parametrize("view", (0x100, 0x200))
@pytest.mark.parametrize("kind", ("inno", "msi-classes", "msi-microsoft", "display", "location"))
def test_every_registry_view_scope_and_product_identity_refuses_install(
    helper, install_guard_environment, hive, view, kind
):
    registry = ReadOnlyRegistry()
    if kind.startswith("msi-"):
        path = registry.upgrade if kind == "msi-classes" else registry.other_upgrade
        registry.keys[hive, view, path] = {}
    else:
        name = (
            "{5C887096-F4E5-4AB8-8D6F-65052D08D284}_is1"
            if kind == "inno"
            else "arbitrary-product-key"
        )
        registry.keys[hive, view, registry.uninstall] = {"children": [name]}
        registry.keys[hive, view, registry.uninstall + "\\" + name] = {
            "DisplayName": "Remote Ops Workspace" if kind == "display" else "Other app",
            "InstallLocation": "C:/custom/Remote Ops Workspace"
            if kind == "location"
            else "C:/Other app",
        }
    with pytest.raises(RuntimeError, match="refusing replacement"):
        helper.assert_no_preexisting_installations(registry)


def test_empty_registry_checks_both_hives_views_and_upgrade_paths(
    helper, install_guard_environment
):
    registry = ReadOnlyRegistry()
    helper.assert_no_preexisting_installations(registry)
    assert len(registry.opens) == 12
    assert {(hive, view) for hive, view, _path in registry.opens} == {
        ("machine", 0x100),
        ("machine", 0x200),
        ("user", 0x100),
        ("user", 0x200),
    }


@pytest.mark.parametrize("fault", ("disappear", "deny"))
def test_registry_uncertainty_refuses_preflight(helper, install_guard_environment, fault):
    registry = ReadOnlyRegistry()
    registry.keys["machine", 0x100, registry.uninstall] = {"children": ["entry"]}
    registry.keys["machine", 0x100, registry.uninstall + "\\entry"] = {"DisplayName": "Other app"}
    setattr(registry, fault, True)
    with pytest.raises((RuntimeError, PermissionError)):
        helper.assert_no_preexisting_installations(registry)


@pytest.mark.parametrize(
    "environment_key", ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA")
)
def test_any_canonical_row_directory_refuses_even_without_executable(
    helper, install_guard_environment, tmp_path, monkeypatch, environment_key
):
    (tmp_path / "Remote Ops Workspace").mkdir()
    monkeypatch.setenv(environment_key, str(tmp_path))
    registry = ReadOnlyRegistry()
    with pytest.raises(RuntimeError, match="canonical ROW install directory"):
        helper.assert_no_preexisting_installations(registry)
    assert registry.opens == []
