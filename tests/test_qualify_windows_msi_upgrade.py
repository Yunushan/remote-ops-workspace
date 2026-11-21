from __future__ import annotations

import ctypes as c
import hashlib
import os
import subprocess
import sys
from contextlib import contextmanager
from ctypes import wintypes as win
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace.update_channel import UpdatePolicy, authenticate_manifest
from scripts import managed_windows_msi as managed
from scripts import qualify_windows_msi_upgrade as upgrade
from scripts import windows_msi_stage_fixture as fixture
from scripts.inspect_windows_msi import (
    EXPECTED_PREDECESSOR,
    EXPECTED_PREDECESSOR_CONDITION,
    ROLLBACK_ACTIONS,
)


@pytest.mark.skipif(sys.platform != "win32", reason="requires native MSI records")
@pytest.mark.parametrize("preexisting_error", [False, True])
def test_install_decodes_native_action_records_and_clears_callback(tmp_path, preexisting_error):
    native = upgrade.UpgradeInstaller()
    records = native.dll
    records.MsiCreateRecord.argtypes = (c.c_uint,)
    records.MsiCreateRecord.restype = upgrade.HANDLE
    records.MsiRecordSetStringW.argtypes = (upgrade.HANDLE, c.c_uint, win.LPCWSTR)
    records.MsiRecordSetStringW.restype = c.c_uint

    launcher = tmp_path / "row.exe"
    launcher.write_bytes(b"previous")
    handler = None

    def set_handler(callback, mask, context, previous):
        nonlocal handler
        assert context is None and previous is None
        assert mask == ((1 << 8) | (1 << 1) | 1 if callback else 0)
        handler = callback if callback else None
        return records.MsiSetExternalUIRecord(callback, mask, context, previous)

    def message(action, description=""):
        record = records.MsiCreateRecord(3)
        try:
            assert records.MsiRecordSetStringW(record, 1, action) == 0
            assert records.MsiRecordSetStringW(record, 2, description) == 0
            return handler(None, upgrade.ACTION_START, record)
        finally:
            assert records.MsiCloseHandle(record) == 0

    predecessor = "{90F5B145-7705-4EE2-93D8-B69BFB6851AD}"

    def install(_path, properties):
        assert properties == f"REBOOT=ReallySuppress {EXPECTED_PREDECESSOR}={predecessor}"
        assert message("RemoveExistingProducts") == 0
        assert message("InstallFiles") == 0
        launcher.unlink()
        assert message("UnrelatedAction", description="InstallFiles") == 0
        if preexisting_error:
            assert handler(None, upgrade.INSTALL_ERROR, 0) == 0
        assert message("InstallFiles") == (0 if preexisting_error else upgrade.IDCANCEL)
        assert message("InstallFiles") == 0
        return upgrade.INSTALL_USER_EXIT

    native.dll = SimpleNamespace(MsiInstallProductW=install, MsiSetExternalUIRecord=set_handler,
                                 MsiRecordGetStringW=records.MsiRecordGetStringW)
    cancellation = upgrade.Cancellation(launcher)
    assert native.install(
        tmp_path / "fixture.msi", cancellation, expected_predecessor=predecessor,
    ) == upgrade.INSTALL_USER_EXIT
    assert cancellation.requested == (not preexisting_error)
    assert cancellation.error_before_cancel == preexisting_error and handler is None


@pytest.mark.parametrize("encoding", ["ascii", "utf-16-le", None])
def test_rollback_disabled_probe_checks_native_installer_error_and_clears_log(tmp_path, encoding):
    native = object.__new__(upgrade.UpgradeInstaller)
    package = tmp_path / "candidate.msi"
    log = tmp_path / "installer.log"
    events = []

    def enable_logging(mode, destination, attributes):
        events.append((mode, destination, attributes))
        return 0

    def install(path, properties):
        assert path == str(package)
        assert properties == "REBOOT=ReallySuppress DISABLEROLLBACK=1"
        assert events == [(upgrade.LOG_ERRORS, str(log), 0)]
        message = upgrade.ROLLBACK_REQUIRED_MESSAGE if encoding else "Another launch condition failed."
        log.write_bytes(message.encode(encoding or "ascii"))
        return upgrade.INSTALL_FAILURE

    native.dll = SimpleNamespace(MsiEnableLogW=enable_logging, MsiInstallProductW=install)
    assert native.install_without_rollback(package, log) == (upgrade.INSTALL_FAILURE, encoding is not None)
    assert events[-1] == (0, None, 0)


@pytest.mark.parametrize("modified", [False, True])
def test_release_msi_must_pass_provenance_and_keep_verified_bytes(tmp_path, monkeypatch, modified):
    tag, sha = "v1.0.29", "a" * 40
    path = tmp_path / f"remote-ops-workspace-{tag}-windows-x64.msi"
    trace = []

    def run(command, *, check, timeout):
        assert check and timeout > 0
        if command[0] == "gh":
            assert command[1:4] == ["release", "download", tag]
            assert command[4:] == ["--repo", upgrade.REPOSITORY, "--pattern", path.name, "--dir", str(tmp_path)]
            path.write_bytes(b"downloaded")
            trace.append("download")
            return
        assert command[3:] == ["--asset", str(path), "--repository", upgrade.REPOSITORY, "--tag", tag,
                               "--sha", sha, "--verify-platform-signature"]
        trace.append("provenance")
        if modified:
            path.write_bytes(b"tampered")
        else:
            raise subprocess.CalledProcessError(1, command)

    def inspect(package, *, require_transactional_upgrade):
        assert package == path
        assert require_transactional_upgrade
        trace.append("inspect")
        return {}

    def open_file(requested, *, read_only):
        assert requested == str(path) and read_only is True and trace == ["download"]
        trace.append("hold")
        return "native-read-only-file"

    def close(handle):
        assert handle == "native-read-only-file"
        trace.append("close")

    monkeypatch.setattr(upgrade.subprocess, "run", run)
    monkeypatch.setattr(upgrade, "validate_package", lambda *_: None)
    storage = SimpleNamespace(open_file=open_file, close=close)
    with pytest.raises(ValueError if modified else subprocess.CalledProcessError), upgrade.verified_msi(
        SimpleNamespace(inspect=inspect, launcher_payload_digests=lambda _: {
            "launcher_payload_sha256": "a" * 64, "gui_launcher_payload_sha256": "b" * 64,
        }),
        storage, tmp_path, tag, sha, candidate=True,
    ):
        pytest.fail("refused package reached the installer")
    assert trace == ["download", "hold", "provenance", *(["inspect"] if modified else []), "close"]


@pytest.mark.parametrize(("defect", "message"), [
    ("valid", ""),
    ("wrong-digest", "locked MSI does not match"),
    ("wrong-size", "locked MSI does not match"),
    ("untrusted-signer", "signature failed"),
])
def test_sealed_candidate_msi_binds_exact_bytes_and_signature_through_installer(
    tmp_path, monkeypatch, defect, message,
):
    tag, sha = "v1.0.29", "b" * 40
    path = tmp_path / f"remote-ops-workspace-{tag}-windows-x64.msi"
    path.write_bytes(b"candidate")
    fingerprint = upgrade.fingerprint(path)
    pointer = upgrade.InventoryPointer(42, 43, "sha256:" + "a" * 64)
    trace = []
    monkeypatch.setenv("GH_TOKEN", "fixture")

    def client(repository, token, *, api_url):
        assert (repository, token, api_url) == (upgrade.REPOSITORY, "fixture", "https://api.github.com")
        return "github-client"

    def materialize(client, repository, directory, selected_tag, selected_sha, coordinates, *, kind):
        assert (client, repository, directory, selected_tag, selected_sha, coordinates) == (
            "github-client", upgrade.REPOSITORY, tmp_path, tag, sha, pointer,
        )
        assert kind == "windows-msi"
        trace.append("materialize")
        return path, {"sha256": "c" * 64 if defect == "wrong-digest" else fingerprint,
                      "size": path.stat().st_size + (defect == "wrong-size")}, {"kind": "sealed-candidate"}

    def hold(requested, *, read_only):
        assert requested == str(path) and read_only is True and trace == ["materialize"]
        trace.append("hold")
        return "lease"

    def commands(requested, *, registered_sdk):
        assert requested == path and registered_sdk is True and trace == ["materialize", "hold"]
        return ["signature-command"]

    def verify(command):
        assert command == ["signature-command"]
        trace.append("signature")
        if defect == "untrusted-signer":
            raise RuntimeError("signature failed")

    def inspect(requested, *, require_transactional_upgrade):
        assert requested == path and require_transactional_upgrade is True and trace[-1] == "signature"
        trace.append("inspect")
        return {"version": "1.0.29"}

    def close(lease):
        assert lease == "lease"
        trace.append("close")

    monkeypatch.setattr(upgrade, "GitHubClient", client)
    monkeypatch.setattr(upgrade, "materialize_asset", materialize)
    monkeypatch.setattr(upgrade, "native_installer_signature_commands", commands)
    monkeypatch.setattr(upgrade, "verify_platform_signature", verify)
    monkeypatch.setattr(upgrade, "validate_package", lambda *_: None)
    monkeypatch.setattr(upgrade.subprocess, "run", lambda *_a, **_k: pytest.fail("fell back to a release download"))
    def payload(requested):
        assert requested == path and trace[-1] == "inspect"
        trace.append("launcher")
        return {"launcher_payload_sha256": "d" * 64, "gui_launcher_payload_sha256": "e" * 64}

    storage = SimpleNamespace(open_file=hold, close=close)
    native = SimpleNamespace(inspect=inspect, launcher_payload_digests=payload)
    scope = upgrade.verified_msi(native, storage, tmp_path, tag, sha, candidate=True, inventory=pointer)
    if message:
        with pytest.raises((ValueError, RuntimeError), match=message), scope:
            pytest.fail("refused package reached the installer")
    else:
        with scope as (locked, package):
            assert locked == path and package["sha256"] == fingerprint and package["source"]["kind"] == "sealed-candidate"
            assert package["launcher_payload_sha256"] == "d" * 64
            assert package["gui_launcher_payload_sha256"] == "e" * 64
            assert trace == ["materialize", "hold", "signature", "inspect", "launcher"]
    assert trace[-1] == "close"


@pytest.mark.parametrize(("scenario", "error"), [
    ("success", None),
    ("unexpected-rollback-refusal", "must fail its rollback launch condition"),
    ("predecessor-changed-on-refusal", "registered launcher bytes differ from the exact MSI payload"),
    ("too-early", "must return user exit after removal"),
    ("wrong-result", "must return user exit after removal"),
    ("wrong-rollback-bytes", "registered launcher bytes differ from the exact MSI payload"),
    ("wrong-rollback-gui", "Installed MSI GUI launcher bytes differ"),
    ("candidate-still-registered", "candidate still registered"),
    ("modified-candidate", "MSI bytes changed"),
    ("wrong-preflight-launcher", "managed preflight did not verify the reinstalled predecessor"),
    ("wrong-preflight-gui", "managed preflight did not verify the reinstalled predecessor"),
    ("wrong-restored-workspace", "workspace restore verification failed"),
])
def test_qualification_requires_actual_removal_and_exact_restoration(tmp_path, monkeypatch, scenario, error):
    launcher = tmp_path / "Program Files" / "Remote Ops Workspace" / "bin" / "row.exe"
    gui = launcher.with_name("row-gui.exe")
    home = tmp_path / "workspace"
    home.mkdir()
    restored = tmp_path / "restored"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user"))

    def make_package(role, version):
        path = tmp_path / f"{role}.msi"
        path.write_text(role)
        return path, {
            "product_code": role, "package_code": f"{role}-package", "version": version,
            "row_component_code": "row-exe", "sha256": upgrade.fingerprint(path),
            "launcher_payload_sha256": hashlib.sha256(role.encode()).hexdigest(),
            "gui_launcher_payload_sha256": hashlib.sha256(f"{role}-gui".encode()).hexdigest(),
            "upgrade_sequence": dict(zip(ROLLBACK_ACTIONS, (1400, 1500, 1501, 1600, 4000, 6600), strict=True)),
            "disable_rollback": "", "upgrade_code": upgrade.STOCK_UPGRADE,
            "major_upgrade": {
                "launch_conditions": [EXPECTED_PREDECESSOR_CONDITION],
                "secure_properties": [EXPECTED_PREDECESSOR], "authored_expected_predecessor": False,
            },
        }

    previous = make_package("previous", "1.0.28")
    candidate = make_package("candidate", "1.0.29")
    packages = {"previous": previous[1], "candidate": candidate[1]}
    registered = set()
    operations = []

    def registration(_native, package, state):
        code = package["product_code"]
        if state == "absent":
            upgrade.require(code not in registered, f"{code} still registered")
            return {"state": "absent"}
        upgrade.require(code in registered, f"{code} registration missing")
        return {"state": "installed", "package_code": package["package_code"], "version": package["version"],
                "row_path": str(launcher)}

    def install(path, cancellation=None, *, expected_predecessor=None):
        operations.append(path.stem if cancellation is None else "cancel")
        if cancellation is not None:
            assert expected_predecessor == "previous"
            assert cancellation.observe("InstallFiles") == 0
            assert cancellation.observe("RemoveExistingProducts") == 0
            if scenario != "too-early":
                launcher.unlink()
                assert cancellation.observe("InstallFiles") == upgrade.IDCANCEL
            launcher.write_bytes(b"changed" if scenario == "wrong-rollback-bytes" else b"previous")
            gui.write_bytes(b"candidate-gui" if scenario == "wrong-rollback-gui" else b"previous-gui")
            if scenario == "candidate-still-registered":
                registered.add("candidate")
            return 1 if scenario == "wrong-result" else upgrade.INSTALL_USER_EXIT
        registered.clear()
        registered.add(path.stem)
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_bytes(path.stem.encode())
        gui.write_bytes(f"{path.stem}-gui".encode())
        if scenario == "modified-candidate" and path.stem == "previous":
            candidate[0].write_bytes(b"changed before execution")
        return 0

    def guarded_install(path, expected_predecessor):
        assert path == candidate[0] and expected_predecessor == "previous" and registered == {"previous"}
        return install(path)

    def related(upgrade_code):
        assert upgrade_code == upgrade.STOCK_UPGRADE
        return tuple(sorted(registered))

    def refuse_upgrade(path, log):
        assert path == candidate[0] and log.parent.is_dir()
        assert registered == {"previous"}
        operations.append("refuse")
        if scenario == "predecessor-changed-on-refusal":
            launcher.write_bytes(b"changed")
        return upgrade.INSTALL_FAILURE, scenario != "unexpected-rollback-refusal"

    def uninstall(product_code):
        assert registered == {product_code}
        operations.append(f"uninstall-{product_code}")
        registered.clear()
        launcher.unlink()
        gui.unlink()

    def no_products():
        assert not registered

    held_files = set()

    def hold_launcher(path, *, read_only):
        assert not held_files and path == str(launcher) and read_only
        held_files.add(path)
        return path

    storage = SimpleNamespace(open_file=hold_launcher, close=held_files.remove)

    def cli(command, *, cwd, env, text, timeout):
        assert command == [str(launcher), "--version"] and cwd in (home, restored) and env["ROW_HOME"] == str(cwd)
        role = "previous" if "previous" in registered else "candidate"
        assert held_files == {str(launcher)}
        assert upgrade.fingerprint(launcher) == packages[role]["launcher_payload_sha256"]
        return f"remote-ops-workspace {packages[role]['version']}\n"

    monkeypatch.setattr(upgrade.subprocess, "check_output", cli)
    monkeypatch.setattr(upgrade, "inspect_registration", registration)
    monkeypatch.setattr(managed, "inspect_registration", registration)
    native = SimpleNamespace(require_no_related_products=no_products, install=install, uninstall=uninstall,
                             install_without_rollback=refuse_upgrade, install_upgrade=guarded_install,
                             related_products=related)
    update_actions = []

    def update(action):
        update_actions.append(action)
        if action == "preflight":
            assert registered == {"previous"}
            digest = "a" * 64 if scenario == "wrong-preflight-launcher" else upgrade.fingerprint(launcher)
            gui_digest = "b" * 64 if scenario == "wrong-preflight-gui" else upgrade.fingerprint(gui)
            return {"phase": "msi-preflight-passed", "previous_launcher_sha256": digest,
                    "previous_gui_launcher_sha256": gui_digest}
        assert action == "update"
        assert registered == ({"previous"} if len(update_actions) == 1 else {"candidate"})
        return managed.apply_verified_pair(native, previous[1], candidate[1], candidate[0], launcher)

    workspace_operations = []

    def workspace_action(phase):
        def run(path, sha):
            assert path == launcher and sha == upgrade.fingerprint(launcher)
            workspace_operations.append(phase)
            if phase == "verify-restored":
                if scenario == "wrong-restored-workspace":
                    raise ValueError("workspace restore verification failed")
                return {"restored_matches_pre_upgrade": True}
            return None
        return run

    recovery = SimpleNamespace(home=home, restored=restored, seed_and_backup=workspace_action("backup"),
                               verify_original=workspace_action("verify-original"),
                               restore_with_candidate=workspace_action("restore-with-candidate"),
                               verify_restored=workspace_action("verify-restored"))
    report = {}
    phases = []

    def save():
        phases.append(report["phase"])
    if error:
        with pytest.raises(ValueError, match=error):
            upgrade.exercise(native, previous, candidate, launcher, recovery, report, save,
                             filesystem=storage, update=update)
        if scenario in ("wrong-preflight-launcher", "wrong-preflight-gui", "wrong-restored-workspace"):
            assert operations == ["previous", "refuse", "cancel", "candidate", "uninstall-candidate", "previous"]
            assert report["phase"] == ("preflight-retained-stages" if scenario.startswith("wrong-preflight-")
                                       else "verify-restored-workspace")
        else:
            assert "candidate" not in operations
        assert "status" not in report
    else:
        upgrade.exercise(native, previous, candidate, launcher, recovery, report, save,
                             filesystem=storage, update=update)
        assert report["status"] == "passed" and report["phase"] == "complete"
        assert report["previous_restored"] == report["previous_installed"]
        assert report["previous_reinstalled"] == report["previous_installed"]
        assert report["previous_restored"]["gui_launcher_sha256"] == previous[1]["gui_launcher_payload_sha256"]
        assert report["candidate_installed"]["gui_launcher_sha256"] == candidate[1]["gui_launcher_payload_sha256"]
        assert report["managed_preflight"]["phase"] == "msi-preflight-passed"
        assert update_actions == ["update", "update", "preflight"]
        assert report["managed_apply"]["phase"] == "msi-applied"
        assert report["managed_retry"]["phase"] == "msi-already-applied"
        assert report["workspace_recovery"] == {"restored_matches_pre_upgrade": True}
        assert report["rollback_disabled_upgrade"] == {
            "exit_code": upgrade.INSTALL_FAILURE, "launch_condition_refused_upgrade": True,
            "previous_preserved": True, "candidate_absent": True, "workspace_preserved": True,
        }
        assert workspace_operations == [
            "backup", "verify-original", "verify-original", "restore-with-candidate", "verify-restored",
        ]
        assert operations == [
            "previous", "refuse", "cancel", "candidate", "uninstall-candidate", "previous", "uninstall-previous",
        ]
        assert phases[-1] == "complete"
    assert not held_files


@pytest.mark.parametrize(("scenario", "refusal"), [
    ("accepted", None),
    ("preexisting-stage", "both stage leaves to be absent"),
    ("missing-request", "unexpected HTTPS requests"),
    ("wrong-manifest", "candidate stage evidence differs"),
])
def test_update_fixture_binds_the_single_empty_stage_command(tmp_path, monkeypatch, scenario, refusal):
    pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    home = tmp_path / "workspace"
    home.mkdir()
    if scenario == "preexisting-stage":
        (tmp_path / "candidate-stage").mkdir()
    packages = {}
    for role, version in (("previous", "1.0.27"), ("candidate", "1.0.28")):
        path = tmp_path / f"remote-ops-workspace-v{version}-windows-x64.msi"
        payload = role.encode()
        path.write_bytes(payload)
        packages[role] = (path, {"version": version, "name_on_release": path.name, "size_bytes": len(payload),
                                 "sha256": hashlib.sha256(payload).hexdigest()})
    calls, trace = [], []
    feed_bodies, feed_requests = {}, []
    origin = "https://127.0.0.1:43433"
    ca = tmp_path / "fixture-ca.pem"

    @contextmanager
    def https(root, bodies, requests):
        nonlocal feed_bodies, feed_requests
        assert root == tmp_path
        feed_bodies, feed_requests = bodies, requests
        trace.append("opened")
        try:
            yield origin, ca
        finally:
            trace.append("closed")

    @contextmanager
    def private(root):
        assert root == tmp_path
        yield SimpleNamespace(create_private_file=lambda path: os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))

    def run(workspace, action, argv, *, ca):
        assert workspace == home and action == "update" and ca == tmp_path / "fixture-ca.pem"
        assert trace == ["opened"]
        calls.append(argv)
        flags = dict(zip(argv[::2], argv[1::2], strict=True))
        result = {"phase": "msi-applied"}
        for role, (artifact, item) in packages.items():
            prefix = "--previous-" if role == "previous" else "--"
            assert flags[prefix + "version"] == item["version"]
            assert Path(flags[prefix + "stage"]) == tmp_path / f"{role}-stage"
            assert not Path(flags[prefix + "stage"]).exists()
            policy = UpdatePolicy(Path(flags[prefix + "policy"]).read_bytes())
            routes = (f"/{role}/manifest.json", f"/{role}/{artifact.name}")
            raw = feed_bodies[routes[0]]
            manifest = authenticate_manifest(raw, policy, expected_version=item["version"])
            assert manifest.artifacts[0].sha256 == item["sha256"] and feed_bodies[routes[1]] == artifact.read_bytes()
            feed_requests.extend(routes[:1] if scenario == "missing-request" and role == "candidate" else routes)
            result[f"{role}_stage"] = {
                "phase": "authenticated-staged", "manifest_sha256": (
                    "0" * 64 if scenario == "wrong-manifest" and role == "candidate" else hashlib.sha256(raw).hexdigest()
                ),
                "trust_policy_sha256": policy.digest, "version": item["version"], "selected_target": fixture.TARGET,
                "selected_files": [artifact.name], "artifact_count": 1, "artifact_total_bytes": item["size_bytes"],
                "whole_declared_asset_set_verified": True, "windows_dacl_metadata_verified": True,
                "install_permitted": False,
            }
        return result

    monkeypatch.setattr(fixture, "serve_https_fixture", https)
    monkeypatch.setattr(fixture, "private_stage_guard", private)
    monkeypatch.setattr(fixture, "run_managed_msi", run)
    if refusal:
        with pytest.raises(ValueError, match=refusal):
            fixture.update_unstaged_pair(tmp_path, home, packages["previous"], packages["candidate"])
        assert len(calls) == (0 if scenario == "preexisting-stage" else 1)
    else:
        arguments, staged, result = fixture.update_unstaged_pair(tmp_path, home, packages["previous"], packages["candidate"])
        assert calls == [arguments] and result["phase"] == "msi-applied"
        assert staged["initial_command"] == "update" and staged["initial_stages_absent"] is True
        assert staged["https_requests"] == list(feed_bodies) and staged["feed_closed_before_retry"] is True
    assert trace == ["opened", "closed"]


@pytest.mark.parametrize(("role", "field"), [
    ("previous", "trust_policy_sha256"),
    ("candidate", "transaction_id"),
    ("candidate", "sha256"),
    ("previous", "product_code"),
])
def test_managed_receipt_binds_each_command_to_the_verified_stages(role, field):
    staged = {
        "previous": {"trust_policy_sha256": "c" * 64, "transaction_id": "a" * 64},
        "candidate": {"trust_policy_sha256": "d" * 64, "transaction_id": "b" * 64},
    }
    sources = {
        name: {"name_on_release": f"{name}.msi", "product_code": f"{name}-product",
               "package_code": f"{name}-package", "version": version, "size_bytes": 64,
               "sha256": sha * 64, "launcher_payload_sha256": sha.upper() * 64}
        for name, version, sha in (("previous", "1.0.27", "a"), ("candidate", "1.0.28", "b"))
    }
    receipt = {"target": "windows-x64", "authenticode_and_timestamp_checked": True}
    for name, source in sources.items():
        receipt[f"{name}_stage"] = dict(staged[name])
        receipt[f"{name}_msi"] = {**source, "asset": source["name_on_release"]}

    upgrade.require_same_inputs(receipt, staged, **sources)
    section = "stage" if field in staged[role] else "msi"
    receipt[f"{role}_{section}"][field] = "changed"
    with pytest.raises(ValueError, match=f"used different {role} inputs"):
        upgrade.require_same_inputs(receipt, staged, **sources)
