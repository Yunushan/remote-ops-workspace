"""Runner-only Windows x64 Inno transition drill; default action prints its plan.

This prototype does not assert publisher trust or certification. Its run mode
refuses local and self-hosted computers before creating files or launching tools.
Only the sanitized report is suitable for artifact upload. The private work tree
contains synthetic decrypted fixture state, vault output and installer logs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd().resolve()
HERE = Path(__file__).resolve().parent
REPO = "Yunushan/remote-ops-workspace"
PREVIOUS = "1.0.24"
SCHEMA = "row.windows-inno-upgrade-rollback.v2"
PLAN = (
    "Refuse local/self-hosted/non-Windows/non-x64 execution before mutation.",
    "Bind clean candidate checkout, hosted runner, workflow run ID/attempt, finish evidence and exact artifact bytes.",
    "Re-query prior release/tag identities and verify five pinned GitHub asset IDs, sizes and SHA256 values before loading bytes.",
    "Provision a fresh private test parent; verify prior manifest and checksum metadata agree with downloaded bytes.",
    "Install actual prior Inno native package into a private test install directory; match installed CLI/GUI hashes to pinned ZIP members.",
    "Seed complete synthetic prior state with the pinned released wheel, then use the installed prior CLI to read profiles, layouts, snippets, macros and decrypt its vault.",
    "Use a separately copied bound candidate recovery executable to make an encrypted pre-upgrade full-state snapshot.",
    "Install the different-version candidate Inno package into the same installation, prove exact candidate CLI/GUI bytes and preserved state.",
    "Mutate state through the installed candidate CLI; require its vault mutation to upgrade version 2 to version 3.",
    "Make an encrypted candidate-state snapshot; prove wrong-password, tampering and in-place recovery are refused without changing originals or snapshots.",
    "Restore candidate snapshot to a fresh sibling and verify exact inventory plus installed-candidate semantic/decryption checks.",
    "Uninstall candidate, reinstall the exact prior native installer, then use the retained candidate rescue CLI to restore the pre-upgrade snapshot to a fresh sibling.",
    "Prove the reinstalled prior CLI/GUI match original released bytes and the prior CLI reads/decrypts the exact pre-upgrade restored state.",
    "Verify corrupted original and both encrypted snapshots remain unchanged; uninstall only this drill installation; revalidate source, proof inputs and every candidate/prior artifact before reporting success.",
)


class PrivateFixtureError(RuntimeError):
    """Static diagnostic code; never expose captured fixture output."""

    def __init__(self, code: str):
        super().__init__(code)
        self.failure_code = code


TRANSITION_FAILURE_CODES = frozenset(
    (
        "native-vault-secret-mismatch",
        "owned-uninstaller-count-mismatch",
        "rollback-native-summary-mismatch",
        "rollback-original-state-mismatch",
        "rollback-previous-snapshot-mismatch",
        "rollback-candidate-snapshot-mismatch",
    )
)
PRIVATE_FAILURE_CODES = frozenset(
    ("private-fixture-powershell7-unavailable", "private-fixture-dacl-provisioning-failed")
)


class TransitionValidationError(ValueError):
    """Allowlisted static code; private output never becomes a diagnostic."""

    def __init__(self, code: str):
        if code not in TRANSITION_FAILURE_CODES:
            raise ValueError("unknown transition diagnostic code")
        super().__init__(code)
        self.failure_code = code


def failure_code(exc: Exception) -> str:
    if type(exc) not in (PrivateFixtureError, TransitionValidationError):
        return "unclassified"
    code = exc.failure_code
    if type(code) is str and code in PRIVATE_FAILURE_CODES | TRANSITION_FAILURE_CODES:
        return code
    return "unclassified"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("required helper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def clean_environment(home: Path, password: str, backup_password: str) -> dict[str, str]:
    environment = dict(os.environ)
    for name in list(environment):
        if name.upper() in {
            "PYTHONPATH",
            "PYTHONHOME",
            "ROW_HOME",
            "ROW_VAULT_PASSWORD",
            "ROW_RECOVERY_PASSWORD",
            "QT_QPA_PLATFORM",
        }:
            environment.pop(name)
    environment.update(
        ROW_HOME=str(home), ROW_VAULT_PASSWORD=password, ROW_RECOVERY_PASSWORD=backup_password
    )
    return environment


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def assert_hosted_workspace() -> None:
    workspace = os.environ.get("GITHUB_WORKSPACE", "")
    if not workspace or not Path(workspace).is_absolute() or Path(workspace).resolve() != ROOT:
        raise RuntimeError("native transition source root differs from the exact hosted checkout")


def registered_product(key_name: str, display_name: str, install_location: str) -> bool:
    """Mirror adopted smoke's text-only classification of untrusted metadata."""
    if key_name.casefold() == "{5c887096-f4e5-4ab8-8d6f-65052d08d284}_is1":
        return True
    if re.match(r"^Remote Ops Workspace(?:$|[\s(\-])", display_name, re.IGNORECASE):
        return True
    location = install_location.strip().strip("\"'").rstrip("\\/")
    parts = [part for part in re.split(r"[\\/]+", location) if part]
    return bool(parts and parts[-1].strip().casefold() == "remote ops workspace")


def assert_no_preexisting_installations(registry=None) -> None:
    """Read-only mirror of adopted Windows smoke's directory/registry guard."""
    for name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
        directory = os.environ.get(name)
        if not directory:
            continue
        location = Path(directory) / "Remote Ops Workspace"
        try:
            location.lstat()
        except FileNotFoundError:
            continue
        raise RuntimeError(
            "runner already has a canonical ROW install directory; refusing replacement"
        )
    if registry is None:
        import winreg as registry
    uninstall_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    upgrade_paths = (
        r"SOFTWARE\Classes\Installer\UpgradeCodes\4B12A8F884E6A1B4F9D59B73E381700D",
        r"SOFTWARE\Microsoft\Installer\UpgradeCodes\4B12A8F884E6A1B4F9D59B73E381700D",
    )
    for hive in (registry.HKEY_LOCAL_MACHINE, registry.HKEY_CURRENT_USER):
        for view in (registry.KEY_WOW64_64KEY, registry.KEY_WOW64_32KEY):
            access = registry.KEY_READ | view
            for upgrade_path in upgrade_paths:
                try:
                    with registry.OpenKey(hive, upgrade_path, 0, access):
                        raise RuntimeError(
                            "runner already has a ROW MSI UpgradeCode; refusing replacement"
                        )
                except FileNotFoundError:
                    pass
            try:
                uninstall = registry.OpenKey(hive, uninstall_path, 0, access)
            except FileNotFoundError:
                continue
            with uninstall:
                count = registry.QueryInfoKey(uninstall)[0]
                for index in range(count):
                    name = registry.EnumKey(uninstall, index)
                    try:
                        entry = registry.OpenKey(uninstall, name, 0, access)
                    except FileNotFoundError as exc:
                        raise RuntimeError(
                            "installed registration disappeared during read-only preflight"
                        ) from exc
                    with entry:
                        values = []
                        for field in ("DisplayName", "InstallLocation"):
                            try:
                                value = registry.QueryValueEx(entry, field)[0]
                            except FileNotFoundError:
                                value = ""
                            values.append(str(value or ""))
                        if registered_product(name, *values):
                            raise RuntimeError(
                                "runner already has a registered ROW product; refusing replacement"
                            )


def runner_gate(sha: str) -> None:
    # Environment assertions are a defense against accidental local execution,
    # not a cryptographic assertion of runner identity. GitHub run/job metadata
    # must independently corroborate the report before release certification.
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Windows",
        "RUNNER_ARCH": "X64",
        "GITHUB_REPOSITORY": REPO,
    }
    if any(os.environ.get(key) != value for key, value in required.items()):
        raise RuntimeError(
            "execution restricted to the project's disposable GitHub-hosted Windows x64 runner"
        )
    assert_hosted_workspace()
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("native Windows x64 required")
    if sys.implementation.name != "cpython" or sys.version_info[:3] != (3, 14, 7):
        raise RuntimeError("drill harness must use the candidate's pinned CPython 3.14.7")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or git_output("rev-parse", "HEAD") != sha:
        raise RuntimeError("candidate checkout SHA mismatch")
    if git_output("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("candidate tracked tree is not clean")
    if any(
        not re.fullmatch(r"[1-9][0-9]*", os.environ.get(key, ""))
        for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
    ):
        raise RuntimeError("missing GitHub run/attempt binding")
    import ctypes

    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError(
            "disposable runner must already have installer privileges; no elevation bypass is attempted"
        )
    assert_no_preexisting_installations()


def api_json(path: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ROW-native-recovery-evidence",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + "/" + path, headers=headers
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("release metadata exceeds bound")
    return json.loads(raw)


def previous_assets(pins: dict, output: Path) -> dict[str, Path]:
    if (
        pins.get("schema") != "row.previous-native-release-pins.v1"
        or pins.get("repository") != REPO
        or pins.get("tag") != "v" + PREVIOUS
    ):
        raise ValueError("prior native release pins mismatch")
    live = api_json("releases/tags/v" + PREVIOUS)
    tag = api_json("git/ref/tags/v" + PREVIOUS)
    if (live["id"], live["tag_name"], live["published_at"], live["draft"]) != (
        pins["release_id"],
        pins["tag"],
        pins["published_at"],
        False,
    ):
        raise ValueError("prior publication identity changed")
    if tag["object"] != {
        "sha": pins["tag_commit"],
        "type": "commit",
        "url": "https://api.github.com/repos/" + REPO + "/git/commits/" + pins["tag_commit"],
    }:
        raise ValueError("prior native tag identity changed")
    actual = {item["id"]: item for item in live["assets"]}
    result = {}
    for row in pins["assets"]:
        if (
            not re.fullmatch(r"sha256:[0-9a-f]{64}", row["digest"])
            or row["size"] > 150 * 1024 * 1024
        ):
            raise ValueError("invalid prior asset pin")
        if any(
            actual[row["id"]][key] != row[key]
            for key in ("name", "size", "digest", "browser_download_url")
        ):
            raise ValueError("prior native asset identity changed")
        name = row["name"]
        if (
            Path(name).name != name
            or row["browser_download_url"]
            != "https://github.com/" + REPO + "/releases/download/" + pins["tag"] + "/" + name
        ):
            raise ValueError("unexpected prior asset location")
        destination = output / name
        # No authorization header is sent to a redirected asset endpoint.
        with (
            urllib.request.urlopen(row["browser_download_url"], timeout=120) as response,
            destination.open("xb") as stream,
        ):
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > row["size"]:
                    raise ValueError("prior download exceeds pinned size")
                stream.write(chunk)
        if total != row["size"] or digest(destination) != row["digest"].removeprefix("sha256:"):
            raise ValueError("prior downloaded bytes mismatch")
        result[name] = destination
    return result


def zip_entrypoints(path: Path) -> dict[str, str]:
    result = {}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate portable ZIP member")
        for name in ("bin/row.exe", "bin/row-gui.exe"):
            item = archive.getinfo(name)
            if item.file_size > 150 * 1024 * 1024 or item.is_dir():
                raise ValueError("unexpected portable entrypoint")
            result[name] = hashlib.sha256(archive.read(name)).hexdigest()
    return result


def verify_manifest(paths: dict[str, Path], version: str) -> None:
    prefix = f"remote-ops-workspace-v{version}-windows-x64"
    manifest = json.loads(paths[prefix + "-native-manifest.json"].read_text(encoding="utf-8-sig"))
    checksums = paths[prefix + "-native-SHA256SUMS.txt"].read_text(encoding="ascii").splitlines()
    checksum_rows = {}
    for line in checksums:
        hash_value, name = line.split(maxsplit=1)
        if not re.fullmatch(r"[0-9a-f]{64}", hash_value) or name in checksum_rows:
            raise ValueError("invalid native checksum metadata")
        checksum_rows[name] = hash_value
    for name, path in paths.items():
        if not name.startswith(prefix) or name.endswith("SHA256SUMS.txt"):
            continue
        if checksum_rows.get(name) != digest(path):
            raise ValueError("native checksum disagrees with downloaded/bound artifact")
        if name.endswith("manifest.json"):
            continue
        rows = [row for row in manifest if Path(row["file"]).name == name]
        if (
            len(rows) != 1
            or rows[0]["sha256"] != digest(path)
            or rows[0]["size_bytes"] != path.stat().st_size
        ):
            raise ValueError("native manifest disagrees with downloaded/bound artifact")


def candidate_assets(args, version: str) -> tuple[dict[str, Path], dict]:
    if git_output("rev-parse", "HEAD") != args.candidate_source_sha:
        raise ValueError("candidate current checkout HEAD differs from source SHA")
    finish = json.loads(args.candidate_evidence.read_text(encoding="utf-8"))
    expected_tree = git_output("rev-parse", "HEAD^{tree}")
    if (
        finish["source"]["head"] != args.candidate_source_sha
        or finish["source"]["tree"] != expected_tree
        or finish.get("source_unchanged") is not True
    ):
        raise ValueError("candidate source evidence mismatch")
    if (
        finish["target"] != "windows-x64"
        or str(finish["run_id"]) != os.environ["GITHUB_RUN_ID"]
        or str(finish["run_attempt"]) != os.environ["GITHUB_RUN_ATTEMPT"]
    ):
        raise ValueError("candidate workflow evidence mismatch")
    if (
        finish.get("native_build_outcome") != "success"
        or finish.get("native_smoke_outcome") != "success"
        or finish.get("native_pyinstaller_inventory_complete") is not True
        or finish.get("installed_project_sources_match_checkout") is not True
        or type(finish.get("pip_inspect_returncode")) is not int
        or finish.get("pip_inspect_returncode") != 0
        or finish.get("pip_inspect_json_valid") is not True
    ):
        raise ValueError("candidate basic runtime/inventory/source proof did not pass")
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    fingerprint = "".join(
        name + "\0" + (digest(ROOT / name) if (ROOT / name).is_file() else "missing") + "\n"
        for name in sorted(names)
        if name
    ).encode()
    if hashlib.sha256(fingerprint).hexdigest() != finish["source"]["checkout_bytes_sha256"]:
        raise ValueError("candidate checkout bytes differ from build evidence")
    binding_path = ROOT / "build/native-smoke/windows-x64/candidate-runtime-byte-binding.json"
    inventory_path = ROOT / "build/candidate-proof/windows-x64/pyinstaller-archives.json"
    pip_inspect_path = ROOT / "build/candidate-proof/windows-x64/pip-inspect.json"
    pip_stderr_path = ROOT / "build/candidate-proof/windows-x64/pip-inspect.stderr.log"
    binding = finish.get("native_executable_byte_binding", {})
    if (
        binding.get("status") != "bound"
        or binding.get("report_path")
        != "build/native-smoke/windows-x64/candidate-runtime-byte-binding.json"
        or not binding_path.is_file()
        or binding.get("report_sha256") != digest(binding_path)
        or not inventory_path.is_file()
        or finish.get("pyinstaller_archive_inventory_sha256") != digest(inventory_path)
        or not pip_inspect_path.is_file()
        or finish.get("pip_inspect_sha256") != digest(pip_inspect_path)
        or not pip_stderr_path.is_file()
        or finish.get("pip_inspect_stderr_sha256") != digest(pip_stderr_path)
    ):
        raise ValueError(
            "candidate Windows executable binding or inspected archive inventory mismatch"
        )
    verifier = load_module(
        ROOT / "scripts/candidate_native_proof.py", "row_candidate_proof_verifier"
    )
    pip_record = json.loads(pip_inspect_path.read_text(encoding="utf-8"))
    if not isinstance(pip_record, dict) or not isinstance(pip_record.get("installed"), list):
        raise ValueError("candidate pip inspect lacks a valid realized distribution inventory")
    binding_report = json.loads(binding_path.read_text(encoding="utf-8"))
    verifier.validate_windows_byte_binding(
        binding_report, json.loads(inventory_path.read_text(encoding="utf-8")), "windows-x64"
    )
    result = {}
    names = [
        f"remote-ops-workspace-v{version}-windows-x64{suffix}"
        for suffix in (
            "-setup.exe",
            "-native.zip",
            "-native-manifest.json",
            "-native-SHA256SUMS.txt",
        )
    ]
    for name in names:
        path = args.candidate_dir / name
        rows = [row for row in finish["assets"] if Path(row["path"]).name == name]
        if (
            len(rows) != 1
            or path.stat().st_size != rows[0]["size"]
            or digest(path) != rows[0]["sha256"]
        ):
            raise ValueError("candidate artifact bytes mismatch")
        result[name] = path.resolve()
    verify_manifest(result, version)
    expected = {item["role"]: item["sha256"] for item in binding_report["expected_executables"]}
    if zip_entrypoints(result[f"remote-ops-workspace-v{version}-windows-x64-native.zip"]) != {
        "bin/row.exe": expected["cli"],
        "bin/row-gui.exe": expected["gui"],
    }:
        raise ValueError(
            "candidate ZIP entrypoints differ from inspected and smoke-bound executable bytes"
        )
    return result, finish


def proof_input_paths(args) -> dict[str, Path]:
    return {
        "candidate_finish": args.candidate_evidence,
        "candidate_byte_binding": ROOT
        / "build/native-smoke/windows-x64/candidate-runtime-byte-binding.json",
        "candidate_archive_inventory": ROOT
        / "build/candidate-proof/windows-x64/pyinstaller-archives.json",
        "candidate_pip_inspect": ROOT / "build/candidate-proof/windows-x64/pip-inspect.json",
        "candidate_pip_stderr": ROOT / "build/candidate-proof/windows-x64/pip-inspect.stderr.log",
        "candidate_proof_verifier": ROOT / "scripts/candidate_native_proof.py",
        "owned_runner": args.owned_runner,
        "state_worker": ROOT / "scripts/smoke_workspace_recovery.py",
        "state_fixture": ROOT / "configs/workspace_recovery_fixture.json",
        "previous_pins": args.previous_pins,
        "transition_helper": Path(__file__),
    }


def byte_records(paths: dict[str, Path]) -> dict[str, dict]:
    return {
        name: {"size": path.stat().st_size, "sha256": digest(path)} for name, path in paths.items()
    }


def revalidate_end(args, version, finish, inputs_before, candidates, prior, rescue, rescue_hash):
    if git_output("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("candidate tracked tree changed during native transition")
    refreshed, final_finish = candidate_assets(args, version)
    if final_finish != finish or refreshed != candidates:
        raise ValueError("candidate evidence or artifact paths changed during native transition")
    if byte_records(proof_input_paths(args)) != inputs_before:
        raise ValueError("native transition proof inputs changed during execution")
    pins = json.loads(args.previous_pins.read_text(encoding="utf-8"))
    expected_prior = {
        row["name"]: {"size": row["size"], "sha256": row["digest"].removeprefix("sha256:")}
        for row in pins["assets"]
    }
    if byte_records(prior) != expected_prior:
        raise ValueError("previous native release artifact bytes changed during transition")
    if digest(rescue) != rescue_hash:
        raise ValueError("retained candidate rescue executable changed during transition")
    return {
        "source_unchanged": True,
        "candidate_assets_unchanged": True,
        "previous_assets_unchanged": True,
        "proof_inputs_unchanged": True,
        "candidate_rescue_unchanged": True,
        "proof_inputs": inputs_before,
    }


def profile_expectations(fixture, include_current=False):
    """Complete fixed-fixture profile records, independent of observed CLI output."""
    raw_rows = list(fixture["profiles"])
    if include_current:
        raw_rows.append(
            {
                "name": "current-only",
                "protocol": "ssh",
                "host": "current.invalid",
                "group": "recovery",
            }
        )
    rows = []
    for raw in raw_rows:
        row = {
            "name": "",
            "protocol": "",
            "host": None,
            "port": None,
            "username": None,
            "group": "default",
            "tags": [],
            "description": "",
            "path": None,
            "url": None,
            "command": None,
            "credential_ref": None,
            "identity_file": None,
            "tunnels": [],
            "options": {},
        }
        if not set(raw).issubset(row):
            raise ValueError("profile fixture has an unexpected field")
        row.update(raw)
        defaults = fixture["group_defaults"].get(row["group"], {})
        if not set(defaults).issubset({"username", "options"}):
            raise ValueError("profile fixture declares unsupported group defaults")
        if row["username"] is None:
            row["username"] = defaults.get("username")
        row["options"] = {**defaults.get("options", {}), **row["options"]}
        rows.append(row)
    return sorted(rows, key=lambda row: row["name"])


def private_parent(path: Path) -> None:
    # Tighten only a newly created disposable directory, before writing secrets.
    path.mkdir()
    powershell = shutil.which("pwsh")
    if not powershell:
        raise PrivateFixtureError("private-fixture-powershell7-unavailable")
    code = """
$ErrorActionPreference='Stop'
$path=$env:ROW_PROOF_PRIVATE_PARENT
$sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl=New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true,$false)
foreach($identity in @($sid.Value,'S-1-5-18','S-1-5-32-544')) {
 $principal=[System.Security.Principal.SecurityIdentifier]::new($identity)
 $rule=New-Object System.Security.AccessControl.FileSystemAccessRule($principal,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
 $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $path -AclObject $acl
$actual=Get-Acl -LiteralPath $path
if(!$actual.AreAccessRulesProtected){throw 'private directory DACL remained inherited'}
$allowed=@($sid.Value,'S-1-5-18','S-1-5-32-544')
foreach($ace in $actual.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier])) {
 if($ace.AccessControlType -ne 'Allow' -or $ace.IdentityReference.Value -notin $allowed){throw 'unexpected private directory ACE'}
}
"""
    environment = dict(os.environ, ROW_PROOF_PRIVATE_PARENT=str(path))
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", code],
        env=environment,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise PrivateFixtureError("private-fixture-dacl-provisioning-failed")


class Drill:
    def __init__(self, root: Path, owned):
        self.root = root
        self.owned = owned
        self.serial = 0
        self.calls = []
        self.uninstaller_checks = []

    def command(
        self,
        executable: Path,
        arguments: list[str],
        environment: dict[str, str],
        *,
        expected_success=True,
        timeout=180,
        drain_descendants=False,
    ) -> str:
        if type(drain_descendants) is not bool:
            raise ValueError("drain_descendants must be a bool")
        self.serial += 1
        output = self.root / f"command-{self.serial}.json"
        executable_hash = digest(executable)
        drain_options = {"drain_descendants": True} if drain_descendants else {}
        record = self.owned.run_owned(executable, arguments, environment, output, timeout, **drain_options)
        save(output, record)
        self.calls.append(
            {
                "step": self.serial,
                "exe_sha256": executable_hash,
                "expected_exit_code": 0 if expected_success else 1,
                "exit_code": record.get("exit_code"),
                "child_created": record.get("child_created"),
                "job_assigned": record.get("job_assigned"),
                "wait_result": record.get("wait_result"),
                "owned_parent_cleanup_wait": record.get("owned_parent_cleanup_wait"),
                "descendant_drain_required": drain_descendants,
                "descendant_drain_requested": record.get("descendant_drain_requested"),
                "natural_job_drain_confirmed": record.get("natural_job_drain_confirmed"),
                "active_owned_processes_at_parent_exit": record.get("active_owned_processes_at_parent_exit"),
                "active_owned_processes_after_natural_drain": record.get("active_owned_processes_after_natural_drain"),
                "execution_deadline_scope": record.get("execution_deadline_scope"),
                "execution_elapsed_seconds": record.get("execution_elapsed_seconds"),
                "natural_job_drain_elapsed_seconds": record.get("natural_job_drain_elapsed_seconds"),
                "timeout_seconds": record.get("timeout_seconds"),
                "active_owned_processes_before_cleanup": record.get(
                    "active_owned_processes_before_cleanup"
                ),
                "active_owned_processes_after_cleanup": record.get(
                    "active_owned_processes_after_cleanup"
                ),
                "job_closed": record.get("job_closed"),
                "execution_error": bool(record.get("error")),
                "cleanup_errors": len(record["cleanup_errors"]),
            }
        )
        drain_predicate = {"require_descendant_drain": True} if drain_descendants else {}
        if (
            not self.owned.owned_result_succeeded({**record, "exit_code": 0}, **drain_predicate)
            or type(record.get("exit_code")) is not int
        ):
            raise RuntimeError("owned native command failed to start or stop safely")
        if record["exit_code"] != (0 if expected_success else 1):
            raise RuntimeError("native command did not have its expected outcome")
        return output.with_suffix(".log").read_text(encoding="utf-8-sig")

    def setup(self, executable: Path, arguments: list[str], environment: dict[str, str]) -> None:
        self.command(executable, arguments, environment, timeout=300, drain_descendants=True)

    def installed(self, install: Path, hashes: dict[str, str]) -> Path:
        for name, expected in hashes.items():
            if digest(install / name) != expected:
                raise ValueError("installed native entrypoint differs from verified package bytes")
        return install / "bin/row.exe"

    def inspect(
        self,
        row: Path,
        home: Path,
        version: str,
        environment: dict[str, str],
        secret: str,
        vault_version: int,
        expected_profiles: list[dict],
        new_secret: str | None = None,
    ) -> dict:
        environment = dict(environment, ROW_HOME=str(home))
        found = self.command(row, ["--version"], environment).strip()
        if found != "row " + version:
            # Existing releases use remote-ops-workspace VERSION.
            if found != "remote-ops-workspace " + version:
                raise ValueError("installed native version mismatch")
        catalog = json.loads(self.command(row, ["platforms", "--json"], environment))
        if not catalog.get("release_architectures") or not catalog.get("windows_legacy_targets"):
            raise ValueError("installed native catalog missing resources")
        profile_rows = json.loads(self.command(row, ["profile", "list", "--json"], environment))
        canonical_profiles = sorted(profile_rows, key=lambda row: row["name"])
        if canonical_profiles != expected_profiles:
            raise ValueError("installed native complete profile records differ from fixture")
        layout = json.loads(self.command(row, ["layout", "show", "recovery-layout"], environment))
        if layout["splitter_sizes"] != [[300, 700], [125, 375]]:
            raise ValueError("installed native layout splitters changed")
        snippets = json.loads(self.command(row, ["snippet", "list", "--json"], environment))
        macro = json.loads(self.command(row, ["macro", "show", "recovery-macro"], environment))
        if (
            not any(item["name"] == "recovery-snippet" for item in snippets)
            or macro["events"][0]["text"] != "printf saved"
        ):
            raise ValueError("installed native saved snippet/macro changed")
        status = json.loads(self.command(row, ["vault", "status", "--json"], environment))
        if (
            status["backend_available"] is not True
            or status["initialized"] is not True
            or status["version"] != vault_version
        ):
            raise ValueError("installed native vault runtime/format mismatch")
        expected_secrets = {"recovery-secret": secret}
        if vault_version == 3:
            if new_secret is None:
                raise ValueError("candidate vault fixture expectation missing")
            expected_secrets["current-only"] = new_secret
        if self.command(row, ["vault", "list"], environment).splitlines() != sorted(
            expected_secrets
        ):
            raise ValueError("installed native vault entries differ from fixture")
        for name, expected_secret in expected_secrets.items():
            self.serial += 1
            # Both native CLIs require --out. The destination inherits the fresh
            # protected test-parent DACL, is read privately, then is removed even
            # on mismatch. It is never included in published evidence or logs.
            secret_output = self.root / f"private-vault-check-{self.serial}.txt"
            try:
                self.command(row, ["vault", "get", name, "--out", str(secret_output)], environment)
                if secret_output.read_text(encoding="utf-8") != expected_secret:
                    raise TransitionValidationError("native-vault-secret-mismatch")
            finally:
                secret_output.unlink(missing_ok=True)
        return {
            "version": version,
            "catalog_sha256": hashlib.sha256(
                json.dumps(catalog, sort_keys=True).encode()
            ).hexdigest(),
            "profiles": len(profile_rows),
            "profiles_sha256": hashlib.sha256(
                json.dumps(canonical_profiles, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "complete_profile_records_match": True,
            "vault_version": vault_version,
            "vault_decrypted": True,
            "layout_splitters_read": True,
            "saved_snippet_and_macro_read": True,
        }

    def uninstall(self, install: Path, environment: dict[str, str]) -> None:
        paths = list(install.glob("unins*.exe"))
        self.uninstaller_checks.append({"before_step": self.serial + 1, "count": len(paths)})
        if len(paths) != 1:
            raise TransitionValidationError("owned-uninstaller-count-mismatch")
        self.command(
            paths[0], ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], environment,
            timeout=300, drain_descendants=True,
        )
        if (install / "bin/row.exe").exists() or (install / "bin/row-gui.exe").exists():
            raise ValueError("uninstall retained a native entrypoint")


def check_rollback_preservation(
    recovery, home, previous_backup, candidate_backup, original_inventory,
    previous_backup_hash, candidate_backup_hash,
):
    if recovery._tree_summary(home) != original_inventory:
        raise TransitionValidationError("rollback-original-state-mismatch")
    if digest(previous_backup) != previous_backup_hash:
        raise TransitionValidationError("rollback-previous-snapshot-mismatch")
    if digest(candidate_backup) != candidate_backup_hash:
        raise TransitionValidationError("rollback-candidate-snapshot-mismatch")


def run(args) -> dict:
    runner_gate(args.candidate_source_sha)
    import tomllib

    inputs_before = byte_records(proof_input_paths(args))
    args._phase = "source-and-proof-validation"
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    if not isinstance(version, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise ValueError("candidate native version must be canonical numeric X.Y.Z")
    if version == PREVIOUS:
        raise ValueError("candidate must have a different version from the prior native installer")
    candidates, finish = candidate_assets(args, version)
    pins = json.loads(args.previous_pins.read_text(encoding="utf-8"))
    args._phase = "recovery-tools-loading"
    recovery = load_module(
        ROOT / "scripts/smoke_workspace_recovery.py", "row_recovery_fixture_worker"
    )
    owned = load_module(args.owned_runner, "row_native_owned_runner")
    import truststore

    truststore.inject_into_ssl()
    args._phase = "private-fixture-provisioning"
    parent = ROOT / ".tmp"
    parent.mkdir(exist_ok=True)
    private = parent / ("native-inno-recovery-" + uuid.uuid4().hex)
    private_parent(private)
    args._phase = "previous-artifact-validation"
    prior = previous_assets(pins, private)
    verify_manifest(prior, PREVIOUS)
    before_hashes = zip_entrypoints(
        prior[f"remote-ops-workspace-v{PREVIOUS}-windows-x64-native.zip"]
    )
    after_hashes = zip_entrypoints(
        candidates[f"remote-ops-workspace-v{version}-windows-x64-native.zip"]
    )
    if before_hashes == after_hashes:
        raise ValueError("candidate native bytes must differ from prior released entrypoints")
    wheel = prior[recovery.EXPECTED_WHEEL_NAME]
    recovery.verify_previous_wheel(wheel)
    fixture = recovery.load_fixture()
    expected_previous_profiles = profile_expectations(fixture)
    expected_candidate_profiles = profile_expectations(fixture, include_current=True)
    home = private / "original"
    payload = {
        "fixture": fixture,
        "vault_passphrase": secrets.token_urlsafe(32),
        "secret": secrets.token_urlsafe(48),
        "new_secret": secrets.token_urlsafe(48),
    }
    backup_password = secrets.token_urlsafe(32)
    environment = clean_environment(home, payload["vault_passphrase"], backup_password)
    drill = Drill(private, owned)
    args._owned_calls = drill.calls
    args._uninstaller_checks = drill.uninstaller_checks
    install = private / "installation"
    old_setup = prior[f"remote-ops-workspace-v{PREVIOUS}-windows-x64-setup.exe"]
    new_setup = candidates[f"remote-ops-workspace-v{version}-windows-x64-setup.exe"]
    install_args = [
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/NOICONS",
        "/DIR=" + str(install),
    ]
    # Recovery tool is a byte-identical candidate onefile copied from the verified
    # candidate ZIP. It is retained when the installed candidate is uninstalled.
    rescue = private / "candidate-rescue.exe"
    with zipfile.ZipFile(
        candidates[f"remote-ops-workspace-v{version}-windows-x64-native.zip"]
    ) as archive:
        rescue.write_bytes(archive.read("bin/row.exe"))
    if digest(rescue) != after_hashes["bin/row.exe"]:
        raise ValueError("candidate recovery tool bytes mismatch")
    args._phase = "previous-native-install-and-inspection"
    drill.setup(old_setup, install_args, environment)
    installed = drill.installed(install, before_hashes)
    seeded = recovery._worker(wheel, home, {**payload, "mode": "seed"})
    if seeded["version"] != PREVIOUS or seeded["vault_version"] != 2:
        raise ValueError("released wheel did not seed prior state")
    previous_native = drill.inspect(
        installed, home, PREVIOUS, environment, payload["secret"], 2, expected_previous_profiles
    )
    before_tree = recovery._tree_summary(home)
    previous_backup = private / "previous.rowbackup"
    drill.command(
        rescue,
        [
            "workspace",
            "backup",
            "--out",
            str(previous_backup),
            "--offline",
            "--passphrase-env",
            "ROW_RECOVERY_PASSWORD",
        ],
        environment,
    )
    previous_backup_hash = digest(previous_backup)
    args._phase = "candidate-native-upgrade-and-inspection"
    drill.setup(new_setup, install_args, environment)
    installed = drill.installed(install, after_hashes)
    candidate_previous_state = drill.inspect(
        installed, home, version, environment, payload["secret"], 2, expected_previous_profiles
    )
    if recovery._tree_summary(home) != before_tree:
        raise ValueError("native upgrade or read changed prior state")
    args._phase = "candidate-state-mutation"
    drill.command(
        installed,
        [
            "profile",
            "add",
            "--name",
            "current-only",
            "--protocol",
            "ssh",
            "--host",
            "current.invalid",
            "--group",
            "recovery",
        ],
        environment,
    )
    drill.command(
        installed,
        ["vault", "set", "current-only", "--secret-env", "ROW_NEW_SYNTHETIC_SECRET"],
        dict(environment, ROW_NEW_SYNTHETIC_SECRET=payload["new_secret"]),
    )
    candidate_mutated = drill.inspect(
        installed,
        home,
        version,
        environment,
        payload["secret"],
        3,
        expected_candidate_profiles,
        payload["new_secret"],
    )
    if candidate_mutated["profiles"] != previous_native["profiles"] + 1:
        raise ValueError("native candidate profile mutation absent")
    upgraded = recovery._worker(ROOT / "src", home, {**payload, "mode": "inspect"})
    after_tree = recovery._tree_summary(home)
    candidate_backup = private / "candidate.rowbackup"
    drill.command(
        installed,
        [
            "workspace",
            "backup",
            "--out",
            str(candidate_backup),
            "--offline",
            "--passphrase-env",
            "ROW_RECOVERY_PASSWORD",
        ],
        environment,
    )
    candidate_backup_hash = digest(candidate_backup)
    # Damage a synthetic original after both encrypted snapshots. Original bytes
    # must survive every attempted restore and the native package rollback.
    (home / "profiles.json").write_bytes(b"corrupted-after-snapshot")
    (home / "plugins/unrecognized/state.json").write_bytes(b"corrupted-plugin-after-snapshot")
    (home / "after-snapshot-only.dat").write_bytes(b"not-in-snapshots")
    original_corrupted = recovery._tree_summary(home)
    tampered = private / "tampered.rowbackup"
    envelope = json.loads(candidate_backup.read_text(encoding="utf-8"))
    token = envelope["token"]
    envelope["token"] = token[:30] + ("B" if token[30] == "A" else "A") + token[31:]
    save(tampered, envelope)
    args._phase = "negative-and-candidate-restore"
    for label, backup, password, destination in (
        ("wrong-password", candidate_backup, secrets.token_urlsafe(32), private / "wrong-password"),
        ("tampered", tampered, backup_password, private / "tampered"),
        ("in-place", candidate_backup, backup_password, home),
    ):
        failure = drill.command(
            installed,
            [
                "workspace",
                "restore",
                "--backup",
                str(backup),
                "--destination",
                str(destination),
                "--offline",
                "--passphrase-env",
                "ROW_RECOVERY_PASSWORD",
            ],
            dict(environment, ROW_RECOVERY_PASSWORD=password),
            expected_success=False,
        )
        expected_error = (
            "restore destination must be a new direct sibling of ROW_HOME"
            if label == "in-place"
            else "invalid backup passphrase or corrupted workspace backup"
        )
        if failure.strip() != "error: " + expected_error or drill.calls[-1]["exit_code"] != 1:
            raise ValueError("negative recovery probe failed for an unrelated reason")
        if destination != home and destination.exists():
            raise ValueError("failed restore created its destination")
        if recovery._tree_summary(home) != original_corrupted:
            raise ValueError("failed restore modified the original")
    restored = private / "restored-candidate"
    drill.command(
        installed,
        [
            "workspace",
            "restore",
            "--backup",
            str(candidate_backup),
            "--destination",
            str(restored),
            "--offline",
            "--passphrase-env",
            "ROW_RECOVERY_PASSWORD",
        ],
        environment,
    )
    if (
        recovery._tree_summary(restored) != after_tree
        or recovery._worker(ROOT / "src", restored, {**payload, "mode": "inspect"}) != upgraded
    ):
        raise ValueError("candidate full-state restore mismatch")
    candidate_restored_native = drill.inspect(
        installed,
        restored,
        version,
        environment,
        payload["secret"],
        3,
        expected_candidate_profiles,
        payload["new_secret"],
    )
    if candidate_restored_native != candidate_mutated:
        raise ValueError("candidate installed native restored state differs")
    args._phase = "previous-native-rollback-and-inspection"
    drill.uninstall(install, environment)
    args._phase = "previous-native-reinstall"
    drill.setup(old_setup, install_args, environment)
    installed = drill.installed(install, before_hashes)
    rollback = private / "restored-previous"
    drill.command(
        rescue,
        [
            "workspace",
            "restore",
            "--backup",
            str(previous_backup),
            "--destination",
            str(rollback),
            "--offline",
            "--passphrase-env",
            "ROW_RECOVERY_PASSWORD",
        ],
        environment,
    )
    args._phase = "previous-restored-inventory-and-worker-check"
    if (
        recovery._tree_summary(rollback) != before_tree
        or recovery._worker(wheel, rollback, {**payload, "mode": "inspect"}) != seeded
    ):
        raise ValueError("prior full-state rollback mismatch")
    args._phase = "previous-restored-native-inspection"
    rolled_back_native = drill.inspect(
        installed, rollback, PREVIOUS, environment, payload["secret"], 2, expected_previous_profiles
    )
    args._phase = "previous-restored-native-summary-comparison"
    if rolled_back_native != previous_native:
        raise TransitionValidationError("rollback-native-summary-mismatch")
    args._phase = "post-rollback-original-and-snapshot-preservation"
    check_rollback_preservation(
        recovery, home, previous_backup, candidate_backup, original_corrupted,
        previous_backup_hash, candidate_backup_hash,
    )
    args._phase = "final-owned-drill-uninstall"
    drill.uninstall(install, environment)
    args._phase = "final-source-and-artifact-revalidation"
    final_binding = revalidate_end(
        args, version, finish, inputs_before, candidates, prior, rescue, after_hashes["bin/row.exe"]
    )
    report = {
        "schema": SCHEMA,
        "status": "passed",
        "scope": "actual-previous-windows-x64-inno-to-unreleased-candidate-native-upgrade-and-operator-rollback",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": REPO,
        "source_sha": args.candidate_source_sha,
        "source_tree": finish["source"]["tree"],
        "checkout_bytes_sha256": finish["source"]["checkout_bytes_sha256"],
        "candidate_finish_sha256": digest(args.candidate_evidence),
        "final_revalidation": final_binding,
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "runner_os": "Windows",
        "runner_arch": "X64",
        "previous_release": pins,
        "candidate_installer_sha256": digest(new_setup),
        "candidate_rescue_sha256": digest(rescue),
        "uninstaller_checks": drill.uninstaller_checks,
        "candidate_assets": {
            name: {"size": path.stat().st_size, "sha256": digest(path)}
            for name, path in candidates.items()
        },
        "previous_entrypoints": before_hashes,
        "candidate_entrypoints": after_hashes,
        "stages": {
            "previous_installed": previous_native,
            "candidate_read_previous": candidate_previous_state,
            "candidate_mutated": candidate_mutated,
            "candidate_restored": candidate_restored_native,
            "previous_reinstalled_and_restored": rolled_back_native,
        },
        "snapshots": {
            "previous_ciphertext_sha256": previous_backup_hash,
            "candidate_ciphertext_sha256": candidate_backup_hash,
            "previous_inventory": before_tree,
            "candidate_inventory": after_tree,
            "corrupted_original_inventory": original_corrupted,
        },
        "checks": dict.fromkeys(
            (
                "different_native_versions",
                "installed_entrypoint_bytes_match_packages",
                "native_profile_and_vault_reads",
                "complete_native_profile_records_match",
                "candidate_smoke_executable_bytes_bound",
                "end_source_and_artifacts_revalidated",
                "candidate_vault_format_upgraded",
                "candidate_full_state_restored",
                "previous_native_reinstalled",
                "previous_full_state_and_vault_restored",
                "original_preserved",
                "encrypted_snapshots_preserved",
                "wrong_password_refused",
                "tampering_refused",
                "in_place_restore_refused",
                "owned_drill_installation_uninstalled",
            ),
            True,
        ),
        "owned_commands": drill.calls,
        "limits": [
            "Inno x64 only: MSI, ARM, macOS, Linux and mobile native transitions are not proved.",
            "Synthetic complete-state fixture; opaque plugin bytes retained, arbitrary plugin runtime compatibility not asserted.",
            "Prior wheel seeds state and assists semantic equality; actual installed native CLI verifies each native version, catalog, profiles, layout, snippet, macro and vault decryption.",
            "Vault v3 candidate state is not fed to the previous program: rollback restores its encrypted pre-upgrade v2 snapshot.",
            "CLI/GUI hashes are compared to each exact portable ZIP; GUI interactions belong to the separate native candidate smoke proof.",
            "Publisher trust, SAC-enforcing launch, macOS notarization, release approval and production certification are not asserted.",
            "Runner environment values require independent matching GitHub run/job metadata before certification.",
            "Windows owner/admin/SYSTEM private parent provisioned; this drill does not certify all arbitrary user-selected destinations.",
            "Uses a synthetic ROW_HOME override; default APPDATA deployment, automatic updater and arbitrary plugin migrations are separate contracts.",
        ],
    }
    report["harness"] = {
        "python_version": sys.version,
        "implementation": sys.implementation.name,
        "platform": platform.platform(),
        "helper_sha256": digest(Path(__file__)),
        "owned_runner_sha256": digest(args.owned_runner),
        "prior_state_worker_sha256": digest(ROOT / "scripts/smoke_workspace_recovery.py"),
        "fixture_sha256": digest(ROOT / "configs/workspace_recovery_fixture.json"),
        "previous_pins_sha256": digest(args.previous_pins),
        "github_job": os.environ.get("GITHUB_JOB"),
        "runner_name": os.environ.get("RUNNER_NAME"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "workflow_sha": os.environ.get("GITHUB_WORKFLOW_SHA"),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("plan", "run"), nargs="?", default="plan")
    parser.add_argument("--allow-disposable-runner-install", action="store_true")
    parser.add_argument("--candidate-source-sha", default="")
    parser.add_argument("--candidate-dir", type=Path, default=ROOT / "native-dist/windows")
    parser.add_argument(
        "--candidate-evidence",
        type=Path,
        default=ROOT / "build/candidate-proof/windows-x64/finish.json",
    )
    parser.add_argument("--previous-pins", type=Path, default=ROOT / "configs/native_previous_release_pins.json")
    parser.add_argument(
        "--owned-runner",
        type=Path,
        default=ROOT / "scripts/candidate_windows_owned.py",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.phase == "plan":
        save(
            args.out,
            {
                "schema": SCHEMA,
                "status": "not-run",
                "scope": "reviewable-prototype-only",
                "steps": PLAN,
                "previous_release_pins": json.loads(args.previous_pins.read_text(encoding="utf-8")),
                "no_installer_executed": True,
            },
        )
        print("Native upgrade/rollback plan saved; no downloads or installer execution.")
        return 0
    if not args.allow_disposable_runner_install:
        raise RuntimeError("explicit disposable-runner install flag required")
    # Gate precedes report creation too, so accidental local run has no effects.
    runner_gate(args.candidate_source_sha)
    try:
        report = run(args)
    except Exception as exc:
        report = {
            "schema": SCHEMA,
            "status": "failed",
            "scope": "unreleased-disposable-runner-native-transition",
            "source_sha": args.candidate_source_sha,
            "run_id": os.environ["GITHUB_RUN_ID"],
            "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "failure_type": type(exc).__name__,
            "failure_code": failure_code(exc),
            "failed_phase": getattr(args, "_phase", "runner-validated"),
            "owned_commands": getattr(args, "_owned_calls", []),
            "uninstaller_checks": getattr(args, "_uninstaller_checks", []),
            "limits": [
                "No passing native upgrade/rollback evidence was produced; private fixture and installer logs are not uploaded."
            ],
        }
        result = 1
    else:
        result = 0
    save(args.out, report)
    print("Native upgrade/rollback: " + report["status"])
    return result


if __name__ == "__main__":
    raise SystemExit(main())
