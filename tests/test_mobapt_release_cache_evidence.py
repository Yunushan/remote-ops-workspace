import json
import shlex
import subprocess
from pathlib import Path

import pytest

from remote_ops_workspace.moba_mobapt import (
    build_mobapt_runtime_bundle_plan,
    validate_mobapt_cache_evidence,
    write_mobapt_runtime_bundle,
)
from scripts import capture_mobapt_offline_evidence as capture
from scripts.check_mobapt_cache_evidence import (
    EXECUTION_SCHEMA,
    NATIVE_PROBE_ARGV,
    NATIVE_PROBE_PATH,
    NATIVE_PROBE_SCHEMA,
    native_install_argv,
    validate_mobapt_offline_execution,
    validate_mobapt_release_cache_evidence,
)
from scripts.check_release_license_compliance import sha256_file


def write_json(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def assemble(tmp_path: Path, *, shims: bool = False) -> Path:
    tool, package = tmp_path / "bash", tmp_path / "tree.deb"
    tool.write_bytes(b"synthetic executable bytes for validator tests")
    package.write_bytes(b"synthetic archive bytes for validator tests")
    plan = build_mobapt_runtime_bundle_plan(
        tmp_path / "bundle", tools=["bash"], packages=["tree=2.2.1"], release_target="linux-x86_64",
        tool_sources={} if shims else {"bash": tool}, package_sources={"tree": package}, allow_shims=shims,
    )
    return Path(write_mobapt_runtime_bundle(plan).evidence_path)


def bind_receipt(evidence: Path, test: dict, receipt: dict) -> None:
    relative = f"evidence/{receipt['kind']}.json"
    path = evidence.parent / relative
    write_json(path, receipt)
    test.update(command=shlex.join(receipt["argv"]), evidence_file=relative, evidence_sha256=sha256_file(path))


@pytest.fixture
def captured_bundle(tmp_path):
    evidence = assemble(tmp_path)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    package = payload["package_cache"]["packages"][0]
    common = {
        "schema": EXECUTION_SCHEMA, "exit_code": 0, "network_disabled": True,
        "package": package["name"], "package_archive_sha256": package["sha256"],
        "runtime_manifest_sha256": payload["runtime"]["manifest_sha256"],
        "stdout": "synthetic output for validator tests", "stderr": "",
    }
    install, terminal = payload["install_tests"][0], payload["terminal_probe"]
    terminal["package"] = package["name"]
    receipts = {
        "offline-install": {**common, "kind": "offline-install", "argv": ["/usr/bin/dpkg", "-i", package["archive"]]},
        "terminal-probe": {**common, "kind": "terminal-probe", "argv": ["bin/bash", "-c", "tree --version"]},
    }
    bind_receipt(evidence, install, receipts["offline-install"])
    bind_receipt(evidence, terminal, receipts["terminal-probe"])
    write_json(evidence, payload)
    return evidence, payload, receipts


@pytest.mark.parametrize(("shims", "expected"), [
    (False, "offline-install receipt must be structured offline execution evidence"),
    (True, "real runtime binaries without shims"),
])
def test_assembly_passes_local_check_but_cannot_certify_release(tmp_path, shims, expected):
    evidence = assemble(tmp_path, shims=shims)
    assert validate_mobapt_cache_evidence(evidence).passed
    result = validate_mobapt_release_cache_evidence(evidence)
    assert not result.passed and expected in result.errors[0]


def test_release_checker_binds_runtime_cache_and_receipts(captured_bundle):
    evidence, _, _ = captured_bundle
    result = validate_mobapt_offline_execution(evidence)
    assert result.passed and result.summary["offline_execution_receipts_verified"] is True
    result = validate_mobapt_release_cache_evidence(evidence)
    assert not result.passed and "requires a native Debian release asset probe" in result.errors[0]


def native_install_result(package):
    return {
        "executed": True, "ok": True, "returncode": 0,
        "plan": {
            "action": "install", "package": package["name"], "cached_package_version": package["version"],
            "cached_archive_sha256": package["sha256"],
            "command": ["/usr/bin/apt", "-o", "Dir::Etc::sourcelist=", "-o", "Dir::Etc::sourceparts=",
                        "install", "--", f"/capture/{package['archive']}"],
        },
    }


@pytest.fixture
def native_capture(captured_bundle, request):
    evidence, payload, receipts = captured_bundle
    if not getattr(request, "param", False):
        package = payload["package_cache"]["packages"][0]
        install = {**receipts["offline-install"], "argv": native_install_argv(package["name"]),
                   "stdout": json.dumps(native_install_result(package))}
        bind_receipt(evidence, payload["install_tests"][0], install)
    payload["release_asset"] = {
        "name": "remote-ops-workspace-v1.0.28-linux-amd64.deb", "sha256": "1" * 64,
    }
    payload["source"] = {
        "repository": "example/workspace", "release_tag": "v1.0.28", "head_sha": "2" * 40,
        "workflow_run_url": "https://github.com/example/workspace/actions/runs/123", "run_attempt": 2,
    }
    write_json(evidence, payload)
    probe = evidence.parent / NATIVE_PROBE_PATH
    receipt = {
        "schema": NATIVE_PROBE_SCHEMA, "argv": NATIVE_PROBE_ARGV, "exit_code": 0, "installed_version": "1.0.28",
        "evidence_sha256": sha256_file(evidence), "release_asset_sha256": "1" * 64, "stderr": "",
        "output": validate_mobapt_cache_evidence(evidence).to_dict(),
    }
    write_json(probe, receipt)
    return evidence, payload, probe, receipt


def test_strict_capture_binds_installer_and_workflow_attempt(native_capture):
    evidence, payload, _, _ = native_capture
    result = validate_mobapt_release_cache_evidence(evidence)
    assert result.passed
    assert result.summary["tested_release_asset"] == payload["release_asset"]
    assert result.summary["source_head_sha"] == payload["source"]["head_sha"]
    assert result.summary["run_attempt"] == 2


@pytest.mark.parametrize("native_capture", [True], indirect=True)
def test_native_capture_rejects_direct_package_manager_receipt(native_capture):
    evidence, _, _, _ = native_capture
    result = validate_mobapt_release_cache_evidence(evidence)
    assert not result.passed and "through the installed row command" in result.errors[0]


@pytest.mark.parametrize(("field", "value"), [
    ("cached_archive_sha256", "a" * 64),
    ("cached_package_version", "9.9"),
    ("command", ["/usr/bin/apt", "install", "/capture/packages/tree-2.2.1.deb"]),
])
def test_native_capture_rejects_an_unbound_or_online_install(native_capture, field, value):
    evidence, payload, _, _ = native_capture
    record = payload["install_tests"][0]
    receipt = json.loads((evidence.parent / record["evidence_file"]).read_bytes())
    result = json.loads(receipt["stdout"])
    result["plan"][field] = value
    receipt["stdout"] = json.dumps(result)
    bind_receipt(evidence, record, receipt)
    write_json(evidence, payload)
    rejected = validate_mobapt_release_cache_evidence(evidence)
    assert not rejected.passed and "executed offline install of the verified package" in rejected.errors[0]


@pytest.mark.parametrize("field", ["evidence_sha256", "release_asset_sha256", "installed_version", "argv"])
def test_strict_capture_rejects_receipt_from_different_execution(native_capture, field):
    evidence, _, probe, receipt = native_capture
    receipt[field] = "different"
    write_json(probe, receipt)
    assert not validate_mobapt_release_cache_evidence(evidence).passed


@pytest.mark.parametrize(("source", "expected"), [
    (None, "requires source and release_asset objects"),
    ({"release_tag": "v1.0.27"}, "must match the exact MobApt release tag"),
    ({"head_sha": "branch"}, "requires exact repository, tag, source SHA and workflow attempt"),
])
def test_local_native_capture_cannot_supply_unverified_release_identity(native_capture, source, expected):
    evidence, payload, probe, receipt = native_capture
    if source is None:
        payload.pop("source")
    else:
        payload["source"].update(source)
    write_json(evidence, payload)
    receipt["evidence_sha256"] = sha256_file(evidence)
    write_json(probe, receipt)
    assert validate_mobapt_offline_execution(evidence).passed
    result = validate_mobapt_release_cache_evidence(evidence)
    assert not result.passed and expected in result.errors[0]


@pytest.mark.parametrize(("kind", "change", "expected"), [
    ("offline-install", {"network_disabled": False}, "successful offline execution"),
    ("offline-install", {"package_archive_sha256": "b" * 64}, "successful offline execution"),
    ("offline-install", {"exit_code": True}, "successful offline execution"),
    ("offline-install", {"argv": ["dpkg", "-i", "unrelated.deb"]}, "argv must name the verified package archive"),
    ("terminal-probe", {"argv": ["/bin/bash", "-c", "tree --version"]}, "invoke a verified bundled runtime"),
    ("terminal-probe", {"stdout": ""}, "receipt requires captured output"),
])
def test_matching_receipt_hash_does_not_excuse_wrong_execution(captured_bundle, kind, change, expected):
    evidence, payload, receipts = captured_bundle
    record = payload["terminal_probe"] if kind == "terminal-probe" else payload["install_tests"][0]
    bind_receipt(evidence, record, {**receipts[kind], **change})
    write_json(evidence, payload)
    result = validate_mobapt_release_cache_evidence(evidence)
    assert not result.passed and expected in result.errors[0]


def test_modified_bundled_tool_fails_release_even_with_intact_receipts(captured_bundle):
    evidence, _, _ = captured_bundle
    (evidence.parent / "bin/bash").write_bytes(b"different executable")
    result = validate_mobapt_release_cache_evidence(evidence)
    assert not result.passed and "bundled runtime executable SHA-256" in result.errors[0]


def test_matching_index_hash_does_not_allow_cache_disagreement(captured_bundle):
    evidence, payload, _ = captured_bundle
    index = evidence.parent / payload["package_cache"]["index"]
    changed = json.loads(index.read_text(encoding="utf-8"))
    changed["packages"][0]["version"] = "9.9.9"
    write_json(index, changed)
    payload["package_cache"]["index_sha256"] = sha256_file(index)
    write_json(evidence, payload)
    result = validate_mobapt_release_cache_evidence(evidence)
    assert not result.passed and "must list the same packages" in result.errors[0]


@pytest.mark.parametrize("probe_passes", [True, False])
def test_capture_publishes_only_validated_execution_receipts(tmp_path, monkeypatch, probe_passes):
    evidence = assemble(tmp_path)
    original = evidence.read_bytes()
    output = tmp_path / "capture"
    monkeypatch.setattr(capture, "require_offline_container", lambda: None)
    calls = []

    def run(arguments, cwd, *, check=True):
        calls.append(arguments)
        binary, *args = arguments
        if args == ["--print-architecture"]:
            return subprocess.CompletedProcess(arguments, 0, "amd64\n", "")
        assert cwd != evidence.parent
        archive = "packages/tree-2.2.1.deb"
        if binary == "dpkg-query" and args[0] == "--show":
            assert check is False
            if any(cmd[:2] == ["dpkg", "--install"] for cmd in calls):
                return subprocess.CompletedProcess(arguments, 0, "install ok installed\n2.2.1", "")
            return subprocess.CompletedProcess(arguments, 1, "", "no packages found")
        if binary == "dpkg-deb":
            assert args == ["--field", archive, "Package", "Version"]
            return subprocess.CompletedProcess(arguments, 0, "Package: tree\nVersion: 2.2.1\n", "")
        if binary == "dpkg":
            assert args == ["--install", "--", archive]
            return subprocess.CompletedProcess(arguments, 0, "Setting up tree", "")
        if args == ["--listfiles", "--", "tree"]:
            return subprocess.CompletedProcess(arguments, 0, f"{tmp_path / 'tree'}\n", "")
        assert binary == "script"
        assert "--return" in args and "bin/bash" in args[args.index("--command") + 1]
        if not probe_passes:
            raise subprocess.CalledProcessError(7, arguments)
        return subprocess.CompletedProcess(arguments, 0, "tree 2.2.1\n", "")

    executable = tmp_path / "tree"
    executable.touch()
    monkeypatch.setattr(capture, "run", run)

    if probe_passes:
        capture.capture(evidence.parent, output, "tree", str(executable), ["--version"])
        result = validate_mobapt_offline_execution(output / "evidence.json")
        assert result.passed and result.summary["offline_execution_receipts_verified"] is True
        assert not list(output.rglob("*.txt"))
    else:
        with pytest.raises(subprocess.CalledProcessError):
            capture.capture(evidence.parent, output, "tree", str(executable), ["--version"])
        assert not output.exists()
        assert not list(tmp_path.glob(".mobapt-capture-*"))
    assert evidence.read_bytes() == original
