from __future__ import annotations

import hashlib
import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from remote_ops_workspace.windows_private_storage import PrivateStorageError, _Native
from scripts import managed_windows_msi as msi
from scripts.inspect_windows_msi import EXPECTED_PREDECESSOR, EXPECTED_PREDECESSOR_CONDITION


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows file sharing")
def test_read_only_handle_refuses_writers_but_allows_verification(tmp_path):
    path = tmp_path / "candidate.msi"
    path.write_bytes(b"candidate")
    native = _Native()
    with path.open("r+b"):
        with pytest.raises(PrivateStorageError, match="^native-file-open-refused$"):
            native.open_file(str(path), read_only=True)
        assert native.c.get_last_error() == 32

    handle = native.open_file(str(path), read_only=True)
    try:
        assert path.read_bytes() == b"candidate"
        with pytest.raises(PermissionError) as exc:
            path.open("r+b")
        assert exc.value.errno == 13
    finally:
        native.close(handle)
    with path.open("r+b") as writer:
        assert writer.read() == b"candidate"


@pytest.mark.parametrize("scenario", ["accepted", "wrong-target", "unsigned", "invalid-msi", "bad-cabinet", "missing-gui"])
def test_package_identity_checks_the_exact_selected_asset(tmp_path, monkeypatch, scenario):
    name = "remote-ops-workspace-v1.0.29-windows-x64.msi"
    artifact = SimpleNamespace(name=name, target="linux-x86_64" if scenario == "wrong-target" else "windows-x64",
                               sha256="a" * 64, size=1024)
    manifest = SimpleNamespace(version="1.0.29", artifacts=[artifact])
    trace = []

    def signature_commands(path, *, registered_sdk):
        assert registered_sdk and path == tmp_path / name
        return [["signtool", "verify"]]

    def verify(commands):
        assert commands == [["signtool", "verify"]]
        trace.append("signature")
        if scenario == "unsigned":
            raise RuntimeError("invalid signature")

    def inspect(path, *, require_transactional_upgrade):
        assert path == tmp_path / name and require_transactional_upgrade is True
        trace.append("identity")
        return {"upgrade_sequence": {}, "disable_rollback": ""}

    def validate(_package, architecture, version):
        assert (architecture, version) == ("x64", manifest.version)
        if scenario == "invalid-msi":
            raise ValueError("invalid identity")

    monkeypatch.setattr(msi, "native_installer_signature_commands", signature_commands)
    monkeypatch.setattr(msi, "verify_platform_signature", verify)
    monkeypatch.setattr(msi, "validate_package", validate)
    def payload(path):
        assert path == tmp_path / name and trace == ["signature", "identity"]
        trace.append("launcher")
        if scenario == "bad-cabinet":
            raise ValueError("no launcher in cabinet")
        digests = {"launcher_payload_sha256": "b" * 64}
        if scenario != "missing-gui":
            digests["gui_launcher_payload_sha256"] = "c" * 64
        return digests

    native = SimpleNamespace(inspect=inspect, launcher_payload_digests=payload)
    refusal = {"wrong-target": "selected-msi-absent", "unsigned": "msi-authenticode-refused",
               "invalid-msi": "msi-package-identity-refused", "bad-cabinet": "msi-package-identity-refused",
               "missing-gui": "msi-gui-launcher-payload-required"}.get(scenario)
    if refusal:
        with pytest.raises(msi.UpdateError, match=refusal):
            msi.package_identity(native, tmp_path, manifest, candidate=True)
    else:
        result = msi.package_identity(native, tmp_path, manifest, candidate=True)
        assert (result["asset"], result["sha256"], result["size_bytes"]) == (name, artifact.sha256, artifact.size)
        assert result["launcher_payload_sha256"] == "b" * 64
        assert result["gui_launcher_payload_sha256"] == "c" * 64
    assert trace == {"wrong-target": [], "unsigned": ["signature"], "invalid-msi": ["signature", "identity"],
                     "bad-cabinet": ["signature", "identity", "launcher"],
                     "accepted": ["signature", "identity", "launcher"],
                     "missing-gui": ["signature", "identity", "launcher"]}[scenario]


@pytest.mark.parametrize(("scenario", "refusal"), [
    ("accepted", None),
    ("publisher-mismatch", "rollback-trust-identity-refused"),
    ("floor", "rollback-version-below-policy-minimum"),
    ("same-package", "major-upgrade-identity-refused"),
    ("extra-related-product", "msi-related-products-refused"),
    ("wrong-registration", "msi-registration-refused"),
    ("changed-launcher", "msi-launcher-bytes-refused"),
])
def test_preflight_holds_both_verified_stages_through_installed_registration(
    tmp_path, monkeypatch, scenario, refusal,
):
    launcher = tmp_path / "Remote Ops Workspace" / "bin" / "row.exe"
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(b"installed")
    args = SimpleNamespace(previous_stage=tmp_path / "old", stage=tmp_path / "new", previous_version="1.0.28",
                           version="1.0.29", previous_policy=tmp_path / "previous.json")
    trusted = {"organization": "org", "channel": "stable", "public_key": "key", "selected_target": "windows-x64",
               "minimum_version": "1.0.29" if scenario == "floor" else "1.0.28"}
    old_policy = SimpleNamespace(settings={**trusted, "public_key": "wrong" if scenario == "publisher-mismatch" else "key"})
    new_policy = SimpleNamespace(settings=trusted)
    held = []
    checks = []

    @contextmanager
    def verified(policy, stage, *, current_home, expected_version, check_consumer_deadline):
        assert check_consumer_deadline is True
        expected = {args.previous_stage: (old_policy, args.previous_version), args.stage: (new_policy, args.version)}
        assert expected[stage] == (policy, expected_version) and current_home == tmp_path
        held.append(stage)
        try:
            yield stage, expected_version, {"phase": "authenticated-staged"}
        finally:
            assert held.pop() == stage

    def package(_native, stage, version, *, candidate):
        assert held == [args.previous_stage, args.stage]
        assert candidate == (stage == args.stage)
        code = args.previous_version if scenario == "same-package" else version
        payload = b"different" if scenario == "changed-launcher" else b"installed"
        return {"product_code": code, "package_code": code, "version": version, "upgrade_code": "stock-family",
                "launcher_payload_sha256": hashlib.sha256(payload).hexdigest(), "asset": "candidate.msi"}

    def related(upgrade_code):
        assert len(held) == 2 and upgrade_code == "stock-family"
        return (args.previous_version, "another-product") if scenario == "extra-related-product" else (args.previous_version,)

    def registration(_native, package, state):
        assert len(held) == 2
        checks.append((package["version"], state))
        if state == "installed":
            if scenario == "wrong-registration":
                raise ValueError("package code mismatch")
            return {"row_path": str(launcher)}
        return {"state": "absent"}

    monkeypatch.setattr(msi, "load_policy", lambda path: old_policy)
    monkeypatch.setattr(msi, "Installer", lambda: SimpleNamespace(related_products=related))
    monkeypatch.setattr(msi, "verified_recovered_stage", verified)
    monkeypatch.setattr(msi, "package_identity", package)
    monkeypatch.setattr(msi, "inspect_registration", registration)
    monkeypatch.setattr(msi, "program_files", lambda: tmp_path)
    if refusal:
        with pytest.raises(msi.UpdateError, match=refusal):
            msi.preflight(args, new_policy, tmp_path)
    else:
        result = msi.preflight(args, new_policy, tmp_path)
        assert result["phase"] == "msi-preflight-passed" and result["install_permitted"] is False
        assert result["previous_launcher_sha256"] == hashlib.sha256(b"installed").hexdigest()
        assert checks == [(args.previous_version, "installed"), (args.version, "absent")]
    assert held == []


@pytest.mark.parametrize(("scenario", "phase", "refusal"), [
    ("normal", "msi-applied", None),
    ("retry", "msi-already-applied", None),
    ("retry-with-stale-gui", None, "msi-gui-launcher-bytes-refused"),
    ("rollback", "msi-previous-preserved", None),
    ("busy", "msi-installer-busy", None),
    ("reboot", "msi-reboot-required", None),
    ("mixed-state", "msi-state-unverified", "msi-related-products-refused"),
    ("bad-launcher", "msi-state-unverified", "msi-launcher-bytes-refused"),
    ("bad-gui", "msi-state-unverified", "msi-gui-launcher-bytes-refused"),
    ("api-failure", "msi-state-unverified", "msi-installer-call-failed"),
    ("unrelated-product", None, "msi-related-products-refused"),
    ("changed-stage", None, "msi-candidate-bytes-refused"),
    ("missing-predecessor-guard", None, "msi-managed-predecessor-guard-refused"),
])
def test_apply_keeps_both_stages_locked_and_rechecks_native_state(tmp_path, monkeypatch, scenario, phase, refusal):
    launcher = tmp_path / "Remote Ops Workspace" / "bin" / "row.exe"
    launcher.parent.mkdir(parents=True)
    previous_stage, candidate_stage = tmp_path / "old", tmp_path / "new"
    candidate_stage.mkdir()
    installer = candidate_stage / "update.msi"
    installer.write_bytes(b"MSI input" if scenario != "changed-stage" else b"changed")
    args = SimpleNamespace(previous_stage=previous_stage, stage=candidate_stage, previous_version="1.0.28",
                           version="1.0.29", previous_policy=tmp_path / "previous-policy.json")
    policy = SimpleNamespace(settings={"organization": "org", "channel": "stable", "public_key": "key",
                                       "selected_target": "windows-x64", "minimum_version": "1.0.28"})
    old = {"product_code": "previous-product", "package_code": "previous-package", "upgrade_code": "stock-family",
           "gui_launcher_payload_sha256": hashlib.sha256(b"previous-gui").hexdigest(),
           "launcher_payload_sha256": hashlib.sha256(b"previous").hexdigest()}
    new = {"product_code": "new-product", "package_code": "new-package", "upgrade_code": "stock-family",
           "asset": installer.name, "sha256": hashlib.sha256(b"MSI input").hexdigest(),
           "gui_launcher_payload_sha256": hashlib.sha256(b"new-gui").hexdigest(),
           "launcher_payload_sha256": hashlib.sha256(b"new").hexdigest(),
           "major_upgrade": {
               "launch_conditions": [] if scenario == "missing-predecessor-guard" else [EXPECTED_PREDECESSOR_CONDITION],
               "secure_properties": [EXPECTED_PREDECESSOR], "authored_expected_predecessor": False,
           }}
    retry = scenario in {"retry", "retry-with-stale-gui"}
    products = [new["product_code"]] if retry else [old["product_code"]]
    if scenario == "unrelated-product":
        products.append("unrelated")
    launcher.write_bytes(b"new" if retry else b"previous")
    gui = launcher.with_name("row-gui.exe")
    gui.write_bytes(b"new-gui" if scenario == "retry" else b"previous-gui")
    held, installs = [], []
    related_calls = 0

    @contextmanager
    def verified(config, root, *, current_home, expected_version, check_consumer_deadline):
        assert config == policy and current_home == tmp_path and check_consumer_deadline is False
        held.append(root)
        try:
            yield root, expected_version, {"phase": "authenticated-staged"}
        finally:
            assert held.pop() == root

    def package(_native, root, version, *, candidate):
        assert held == [previous_stage, candidate_stage] and version == (args.version if candidate else args.previous_version)
        assert root == (candidate_stage if candidate else previous_stage)
        return new if candidate else old

    def related(upgrade_code):
        nonlocal related_calls
        assert held == [previous_stage, candidate_stage] and upgrade_code == "stock-family"
        related_calls += 1
        return tuple(products)

    def register(_native, selected, state):
        assert held == [previous_stage, candidate_stage]
        assert (selected["product_code"] in products) == (state == "installed")
        return {"row_path": str(launcher)} if state == "installed" else {"state": "absent"}

    def install(path, expected_predecessor):
        assert held == [previous_stage, candidate_stage] and path == installer
        assert products == [expected_predecessor] == [old["product_code"]]
        installs.append(path)
        if scenario == "api-failure":
            raise OSError("native call failed")
        if scenario in {"busy", "reboot", "rollback"}:
            return {"busy": 1618, "reboot": 3010, "rollback": 1603}[scenario]
        products[:] = [new["product_code"]]
        if scenario == "mixed-state":
            products.append(old["product_code"])
        launcher.write_bytes(b"wrong" if scenario == "bad-launcher" else b"new")
        if scenario != "bad-gui":
            gui.write_bytes(b"new-gui")
        return 0

    native = SimpleNamespace(related_products=related, install_upgrade=install)
    monkeypatch.setattr(msi, "Installer", lambda: native)
    monkeypatch.setattr(msi, "load_policy", lambda _: policy)
    monkeypatch.setattr(msi, "verified_recovered_stage", verified)
    monkeypatch.setattr(msi, "package_identity", package)
    monkeypatch.setattr(msi, "inspect_registration", register)
    monkeypatch.setattr(msi, "program_files", lambda: tmp_path)
    if phase is None:
        with pytest.raises(msi.UpdateError, match=refusal):
            msi.apply(args, policy, tmp_path)
        assert not installs
    else:
        result = msi.apply(args, policy, tmp_path)
        assert result["phase"] == phase and result.get("refusal") == refusal
        assert result["previous_msi"] is old and result["candidate_msi"] is new
        assert installs == ([] if scenario == "retry" else [installer])
        if scenario in {"busy", "reboot", "api-failure"}:
            assert related_calls == 2 and "installed_launcher_sha256" not in result
        if scenario in {"normal", "retry", "rollback"}:
            assert result["installed_launcher_sha256"] == (old if scenario == "rollback" else new)["launcher_payload_sha256"]
    assert not held


@pytest.mark.parametrize(("previous_state", "candidate_state", "downloads", "refusal"), [
    ("missing", "missing", ("previous", "candidate"), None),
    ("verified", "missing", ("candidate",), None),
    ("missing", "verified", ("previous",), None),
    ("verified", "verified", (), None),
    ("incomplete", "missing", (), "update-stage-refused"),
    ("verified", "incomplete", (), "update-stage-refused"),
])
def test_update_fetches_only_missing_stages_and_holds_the_verified_pair(
    tmp_path, monkeypatch, previous_state, candidate_state, downloads, refusal,
):
    workspace = tmp_path / "home"
    args = SimpleNamespace(previous_stage=tmp_path / "previous", stage=tmp_path / "candidate",
                           previous_version="1.0.28", version="1.0.29", previous_policy=tmp_path / "previous.json")
    settings = {"organization": "org", "channel": "stable", "public_key": "key",
                "selected_target": msi.TARGET, "minimum_version": args.previous_version}
    previous_policy, candidate_policy = SimpleNamespace(settings=settings), SimpleNamespace(settings=settings.copy())
    stages = {
        args.previous_stage: (previous_state, args.previous_version, previous_policy),
        args.stage: (candidate_state, args.version, candidate_policy),
    }
    for root, (state, _, _) in stages.items():
        if state != "missing":
            root.mkdir()
    held, fetched, installed = [], [], []
    native = object()

    def stage(policy, path, *, current_home, expected_version):
        state, version, expected_policy = stages[path]
        assert state == "missing" and policy is expected_policy and current_home == workspace and version == expected_version
        assert held == ([args.previous_stage] if path == args.stage else [])
        path.mkdir()
        fetched.append(path.name)

    @contextmanager
    def recover(policy, path, *, current_home, expected_version, check_consumer_deadline):
        state, version, expected_policy = stages[path]
        assert path.is_dir() and policy is expected_policy and current_home == workspace and version == expected_version
        assert check_consumer_deadline is False
        if state == "incomplete":
            raise msi.UpdateError("update-stage-refused")
        held.append(path)
        try:
            yield path, version, {"phase": "authenticated-staged"}
        finally:
            assert held.pop() == path

    def package(installer, path, version, *, candidate):
        assert installer is native and held == list(stages)
        assert (candidate, version) == (path == args.stage, stages[path][1])
        return {"asset": f"{path.name}.msi", "product_code": version, "package_code": version}

    def install(installer, previous, candidate, path, launcher):
        assert installer is native and held == list(stages)
        assert previous["asset"] == "previous.msi" and candidate["asset"] == "candidate.msi"
        assert path == args.stage / "candidate.msi" and launcher == tmp_path / "row.exe"
        installed.append(path)
        return {"phase": "msi-applied"}

    monkeypatch.setattr(msi, "Installer", lambda: native)
    monkeypatch.setattr(msi, "load_policy", lambda _: previous_policy)
    monkeypatch.setattr(msi, "stage_update", stage)
    monkeypatch.setattr(msi, "verified_recovered_stage", recover)
    monkeypatch.setattr(msi, "package_identity", package)
    monkeypatch.setattr(msi, "apply_verified_pair", install)
    monkeypatch.setattr(msi, "stock_launcher", lambda: tmp_path / "row.exe")
    if refusal:
        with pytest.raises(msi.UpdateError, match=refusal):
            msi.apply(args, candidate_policy, workspace, stage_missing=True)
        assert not installed
    else:
        result = msi.apply(args, candidate_policy, workspace, stage_missing=True)
        assert result["phase"] == "msi-applied" and installed == [args.stage / "candidate.msi"]
    assert fetched == list(downloads) and not held


@pytest.mark.parametrize("action", ["apply", "update"])
@pytest.mark.parametrize(("administrator", "phase", "exit_code"), [
    (False, "refused", 1), (True, "msi-applied", 0), (True, "msi-previous-preserved", 1),
])
def test_apply_cli_requires_elevation_and_reports_the_verified_outcome(
    monkeypatch, tmp_path, capsys, action, administrator, phase, exit_code,
):
    monkeypatch.setattr(msi, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(msi, "get_platform", lambda: "win-amd64")
    monkeypatch.setattr(msi, "is_elevated_administrator", lambda: administrator)
    calls = []
    monkeypatch.setattr(msi, "data_dir", lambda: calls.append("lookup") or tmp_path)
    monkeypatch.setattr(msi, "load_policy", lambda _: calls.append("policy") or object())
    def apply(*_, stage_missing=False):
        assert stage_missing == (action == "update")
        calls.append("apply")
        return {"phase": phase}
    monkeypatch.setattr(msi, "apply", apply)
    result = msi.main([
        action, "--policy", "policy.json", "--stage", "new", "--version", "1.0.29",
        "--previous-policy", "old-policy.json", "--previous-stage", "old", "--previous-version", "1.0.28",
    ])
    assert result == exit_code
    assert json.loads(capsys.readouterr().out)["phase"] == phase
    assert calls == (["lookup", "policy", "apply"] if administrator else [])
