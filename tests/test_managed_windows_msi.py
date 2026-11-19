from __future__ import annotations

import hashlib
import sys
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from remote_ops_workspace.windows_private_storage import PrivateStorageError, _Native
from scripts import managed_windows_msi as msi


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


@pytest.mark.parametrize("scenario", ["accepted", "wrong-target", "unsigned", "invalid-msi", "bad-cabinet"])
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
        return "b" * 64

    native = SimpleNamespace(inspect=inspect, launcher_payload_sha256=payload)
    refusal = {"wrong-target": "selected-msi-absent", "unsigned": "msi-authenticode-refused",
               "invalid-msi": "msi-package-identity-refused", "bad-cabinet": "msi-package-identity-refused"}.get(scenario)
    if refusal:
        with pytest.raises(msi.UpdateError, match=refusal):
            msi.package_identity(native, tmp_path, manifest, candidate=True)
    else:
        result = msi.package_identity(native, tmp_path, manifest, candidate=True)
        assert (result["asset"], result["sha256"], result["size_bytes"]) == (name, artifact.sha256, artifact.size)
        assert result["launcher_payload_sha256"] == "b" * 64
    assert trace == {"wrong-target": [], "unsigned": ["signature"], "invalid-msi": ["signature", "identity"],
                     "bad-cabinet": ["signature", "identity", "launcher"],
                     "accepted": ["signature", "identity", "launcher"]}[scenario]


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
    def verified(policy, stage, *, current_home, expected_version):
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
                "launcher_payload_sha256": hashlib.sha256(payload).hexdigest()}

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
