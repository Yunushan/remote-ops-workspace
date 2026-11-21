"""Install an authenticated stock x86-64 RPM update and recover it offline."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from remote_ops_workspace.state_lock import exclusive_file_lock  # noqa: E402
from remote_ops_workspace.update_channel import (  # noqa: E402
    UpdateError,
    _decode,
    _read_regular,
    _release_version,
    stage_update,
    verified_recovered_stage,
)
from remote_ops_workspace.update_staging import LOCK as STAGE_LOCK  # noqa: E402
from remote_ops_workspace.update_staging import MAX_ARTIFACT_BYTES  # noqa: E402
from scripts.managed_linux_update import (  # noqa: E402
    JOURNAL as SYSTEM_LOCK,
)
from scripts.managed_linux_update import (  # noqa: E402
    PACKAGE,
    SYSTEM_LOCK_ROOT,
    installed_launcher_sha256,
    journal_write,
    load_policy,
    native_command,
    require,
    trusted_path,
    verify_bytes,
)
from scripts.managed_linux_update import snapshot_deb as snapshot_installer  # noqa: E402
from scripts.stage_linux_runtime_licenses import is_runtime_license_member  # noqa: E402

RPM = "/usr/bin/rpm"
ARCH = "x86_64"
TARGET = "linux-x86_64"
LAUNCHER = Path("/usr/bin/row")
DOCS = PurePosixPath("/usr/share/doc") / PACKAGE
SCHEMA = "row.rpm-update.v1"
JOURNAL = "managed-rpm-update.json"
SHA256 = re.compile(r"[0-9a-f]{64}")
QUERY = (
    "%{NAME}\t%{EPOCHNUM}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\t%{FILEDIGESTALGO}\t%{SHA256HEADER}\n"
    "[%{FILENAMES}\t%{FILEMODES:perms}\t%{FILEUSERNAME}\t%{FILEGROUPNAME}\t%{FILEDIGESTS}\n]"
)
TRUST_IDENTITY = ("organization", "channel", "public_key", "selected_target")
PREVIOUS = "rollback.rpm"
CANDIDATE = "candidate.rpm"


@dataclass(frozen=True)
class Header:
    version: str
    header_sha256: str
    launcher_sha256: str


def rpm_header(*selection: str) -> Header:
    result = native_command(RPM, *selection, "--queryformat", QUERY)
    header, _, files = result.stdout.partition("\n")
    fields = header.split("\t")
    require(len(fields) == 7, "rpm-header-refused")
    name, epoch, version, release, architecture, algorithm, digest = fields
    require((name, epoch, architecture, algorithm) == (PACKAGE, "0", ARCH, "8")
            and re.fullmatch(r"1(?:\.[A-Za-z0-9_]+)*", release) and SHA256.fullmatch(digest),
            "rpm-header-refused")
    _release_version(version)

    launcher_digest = None
    seen = set()
    for line in files.splitlines():
        columns = line.split("\t")
        require(len(columns) == 5, "rpm-payload-refused")
        name, mode, owner, group, checksum = columns
        path = PurePosixPath(name)
        require(path.as_posix() == name and ".." not in path.parts and path not in seen
                and (owner, group) == ("root", "root"),
                "rpm-payload-refused")
        seen.add(path)
        if name == LAUNCHER.as_posix():
            require(mode == "-rwxr-xr-x" and SHA256.fullmatch(checksum), "rpm-payload-refused")
            launcher_digest = checksum
        elif path == DOCS or (mode.startswith("d") and is_runtime_license_member(path, directory=True)):
            require(mode == "drwxr-xr-x" and checksum in ("", "(none)"), "rpm-payload-refused")
        else:
            require(
                (path.parent == DOCS or is_runtime_license_member(path))
                and mode == "-rw-r--r--" and SHA256.fullmatch(checksum),
                "rpm-payload-refused",
            )
    require(launcher_digest is not None, "rpm-launcher-missing")
    return Header(version, digest, launcher_digest)


def installed_header() -> Header:
    return rpm_header("--query", PACKAGE)


def verify_installation(expected: Header) -> None:
    require(installed_header() == expected, "installed-rpm-identity-refused")
    require(rpm_header("--query", "--file", str(LAUNCHER)) == expected, "installed-rpm-owner-refused")
    require(installed_launcher_sha256() == expected.launcher_sha256, "installed-launcher-digest-refused")
    native_command(RPM, "--verify", "--noscripts", PACKAGE)
    output = native_command(str(LAUNCHER), "--version").stdout.strip()
    require(output == f"{PACKAGE} {expected.version}", "installed-launcher-version-refused")


def retain_package(policy, stage: Path, workspace: Path, version: str, destination: Path) -> tuple[dict, Header]:
    if not any(path.name != STAGE_LOCK for path in stage.iterdir()):
        stage_update(policy, stage, current_home=workspace, expected_version=version)
    with verified_recovered_stage(policy, stage, current_home=workspace, expected_version=version) as (root, manifest, _):
        expected = f"{PACKAGE}-v{version}-linux-{ARCH}.rpm"
        asset = next((row for row in manifest.artifacts if (row.target, row.name) == (TARGET, expected)), None)
        require(asset is not None, "selected-rpm-absent")
        snapshot_installer(root / asset.name, asset, destination)
        recorded = {"version": version, "size": asset.size, "sha256": asset.sha256}
    return recorded, retained_header(destination, recorded)


def retained_header(path: Path, record: dict) -> Header:
    verify_bytes(path, record["size"], record["sha256"])
    header = rpm_header("--query", "--package", str(path))
    require(header.version == record["version"], "rpm-version-refused")
    return header


def read_journal(path: Path) -> dict:
    state = _decode(_read_regular(trusted_path(path, private=True), 4096), 4096)
    require(type(state) is dict and set(state) == {"schema", "phase", "previous", "candidate"}
            and state["schema"] == SCHEMA and state["phase"] in ("applying", "applied", "rolling-back", "rolled-back"),
            "rpm-update-journal-refused")
    for key in ("previous", "candidate"):
        record = state[key]
        require(type(record) is dict and set(record) == {"version", "size", "sha256"}
                and type(record["size"]) is int and 0 < record["size"] <= MAX_ARTIFACT_BYTES
                and type(record["sha256"]) is str and SHA256.fullmatch(record["sha256"]),
                "rpm-update-journal-refused")
    require(_release_version(state["previous"]["version"]) < _release_version(state["candidate"]["version"]),
            "rpm-update-journal-refused")
    return state


def rollback(journal: Path, state: dict) -> dict:
    before = journal.parent / PREVIOUS
    previous = retained_header(before, state["previous"])
    phase = state["phase"]
    if phase == "rolled-back":
        verify_installation(previous)
        return state

    candidate = retained_header(journal.parent / CANDIDATE, state["candidate"])
    if phase == "applied":
        verify_installation(candidate)
        current = candidate
    else:
        current = installed_header()
        require(current in (previous, candidate), "installed-rpm-changed")

    if current == previous:
        try:
            verify_installation(previous)
        except (OSError, subprocess.SubprocessError, ValueError):
            command = ("--reinstall",)
        else:
            return journal_write(journal, state, "rolled-back")
    else:
        command = ("--upgrade", "--oldpackage")

    trusted_path(LAUNCHER.parent, directory=True)
    require(native_command(RPM, *command, "--test", str(before), check=False).returncode == 0,
            "rpm-rollback-test-refused")
    require(installed_header() == current, "installed-rpm-changed")
    state = journal_write(journal, state, "rolling-back")
    native_command(RPM, *command, str(before))
    verify_installation(previous)
    return journal_write(journal, state, "rolled-back")


def update(args, journal: Path, workspace: Path) -> dict:
    if os.path.lexists(journal):
        state = read_journal(journal)
        require(state["candidate"]["version"] == args.version, "existing-update-transaction")
        if state["phase"] == "applied":
            verify_installation(retained_header(journal.parent / CANDIDATE, state["candidate"]))
            return state
        return rollback(journal, state)

    old_stage = trusted_path(args.previous_stage, directory=True, private=True)
    stage = trusted_path(args.stage, directory=True, private=True)
    require_disjoint(workspace, journal.parent, old_stage, stage, SYSTEM_LOCK_ROOT)
    installed = installed_header()
    require(_release_version(args.version) > _release_version(installed.version), "update-version-not-newer")
    policy, previous_policy = load_policy(args.policy), load_policy(args.previous_policy)
    settings = policy.settings
    require(all(settings[key] == previous_policy.settings[key] for key in TRUST_IDENTITY),
            "rollback-trust-identity-refused")
    require(settings["selected_target"] == TARGET, "managed-update-target-refused")
    require(_release_version(installed.version) >= _release_version(settings["minimum_version"]),
            "rollback-version-below-policy-minimum")

    old_record, old = retain_package(previous_policy, old_stage, workspace, installed.version, journal.parent / PREVIOUS)
    candidate_path = journal.parent / CANDIDATE
    new_record, new = retain_package(policy, stage, workspace, args.version, candidate_path)
    require(installed == old, "retained-rpm-is-not-installed-predecessor")
    verify_installation(old)
    freshen = (RPM, "--freshen")
    require(native_command(*freshen, "--test", str(candidate_path), check=False).returncode == 0,
            "rpm-upgrade-test-refused")
    require(installed_header() == old, "installed-rpm-changed")
    state = journal_write(journal, {"schema": SCHEMA, "previous": old_record, "candidate": new_record}, "applying")
    try:
        native_command(*freshen, str(candidate_path))
        verify_installation(new)
    except (OSError, subprocess.SubprocessError, ValueError):
        return rollback(journal, state)
    return journal_write(journal, state, "applied")


def require_disjoint(*paths: Path) -> None:
    require(not any(left.is_relative_to(right) or right.is_relative_to(left) for left, right in combinations(paths, 2)),
            "managed-update-directories-overlap")


def run(args) -> dict:
    require(sys.platform == "linux" and os.getuid() == 0 and os.geteuid() == 0, "linux-root-required")
    require(native_command(RPM, "--eval", "%{_arch}").stdout.strip() == ARCH, "unsupported-rpm-architecture")
    workspace = Path(os.path.abspath(args.workspace))
    transaction = trusted_path(args.transaction, directory=True, private=True)
    require_disjoint(workspace, transaction, SYSTEM_LOCK_ROOT)
    trusted_path(SYSTEM_LOCK_ROOT.parent, directory=True)
    SYSTEM_LOCK_ROOT.mkdir(mode=0o700, exist_ok=True)
    system = trusted_path(SYSTEM_LOCK_ROOT, directory=True, private=True)
    journal = transaction / JOURNAL
    with exclusive_file_lock(system / SYSTEM_LOCK), exclusive_file_lock(journal):
        if args.action == "update":
            return update(args, journal, workspace)
        return rollback(journal, read_journal(journal))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    update_command = actions.add_parser("update", help="authenticate both RPMs, then apply the candidate")
    rollback_command = actions.add_parser("rollback", help="restore the retained predecessor offline")
    for action in (update_command, rollback_command):
        action.add_argument("--workspace", required=True, type=Path)
        action.add_argument("--transaction", required=True, type=Path)
    for name in ("policy", "stage", "previous-policy", "previous-stage"):
        update_command.add_argument(f"--{name}", required=True, type=Path)
    update_command.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    try:
        state = run(args)
    except UpdateError as error:
        print(json.dumps({"phase": "refused", "refusal": str(error)}))
        return 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({"phase": "refused", "refusal": "managed-rpm-update-failed"}))
        return 1
    print(json.dumps(state, sort_keys=True))
    return int(state["phase"] != ("applied" if args.action == "update" else "rolled-back"))


if __name__ == "__main__":
    sys.exit(main())
