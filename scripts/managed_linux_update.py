"""Install an authenticated ROW Debian update and retain a verified rollback package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
from contextlib import contextmanager
from itertools import combinations
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile, TemporaryFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from remote_ops_workspace.file_safety import write_json_atomic  # noqa: E402
from remote_ops_workspace.state_lock import exclusive_file_lock  # noqa: E402
from remote_ops_workspace.update_channel import (  # noqa: E402
    POLICY_SCHEMA_V2,
    UpdateError,
    _decode,
    _read_regular,
    _release_version,
    authenticate_manifest,
    load_update_policy,
    recover_update,
    stage_update,
)
from remote_ops_workspace.update_staging import LOCK as STAGE_LOCK  # noqa: E402
from remote_ops_workspace.update_staging import MANIFEST, MAX_ARTIFACT_BYTES  # noqa: E402

PACKAGE = "remote-ops-workspace"
SCHEMA = "row.debian-update.v1"
JOURNAL = "managed-update.json"
PREVIOUS_PACKAGE = "rollback.deb"
CANDIDATE_PACKAGE = "candidate.deb"
LAUNCHER = PurePosixPath("usr/bin/row")
SERVER_ROOT = PurePosixPath("usr/lib/remote-ops-workspace/servers")
SYSTEM_LOCK_ROOT = Path("/var/lib/remote-ops-workspace-managed-update")
DPKG = "/usr/bin/dpkg"
DPKG_DEB = "/usr/bin/dpkg-deb"
DPKG_QUERY = "/usr/bin/dpkg-query"
DPKG_FRONTEND_LOCK = Path("/var/lib/dpkg/lock-frontend")
DEBIAN_TARGETS = {"amd64": "linux-x86_64", "arm64": "linux-arm64", "armhf": "linux-armhf", "i386": "linux-i386"}
COMMAND_ENV = {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}


def require(condition, refusal: str) -> None:
    if not condition:
        raise UpdateError(refusal)


def trusted_path(path: Path, *, directory=False, private=False) -> Path:
    path = Path(os.path.abspath(path))
    for parent in reversed(path.parents):
        metadata = parent.lstat()
        require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == 0 and not metadata.st_mode & 0o022,
                "untrusted-administrator-path")
    info = path.lstat()
    valid_kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    require(valid_kind and info.st_uid == 0 and not info.st_mode & (0o077 if private else 0o022),
            "untrusted-administrator-path")
    return path


@contextmanager
def debian_frontend_lock():
    import fcntl

    trusted_path(DPKG_FRONTEND_LOCK.parent, directory=True)
    descriptor = os.open(DPKG_FRONTEND_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o640)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                and not info.st_mode & 0o022, "untrusted-debian-package-lock")
        try:
            fcntl.lockf(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise UpdateError("debian-package-manager-busy") from exc
        yield
    finally:
        os.close(descriptor)


def native_command(*argv: str, check: bool = True, frontend_locked: bool = False) -> subprocess.CompletedProcess:
    # Run only the fixed system tools above in a clean environment. Output from
    # package metadata and maintainer scripts is never echoed to the operator.
    environment = {**COMMAND_ENV, "DPKG_FRONTEND_LOCKED": "1"} if frontend_locked else COMMAND_ENV
    return subprocess.run(argv, env=environment, cwd="/", stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                          check=check, timeout=300)


def installed_package(architecture: str) -> tuple[str, str]:
    result = native_command(DPKG_QUERY, "--show", "--showformat=${db:Status-Status}\t${Version}\t${Architecture}\n",
                            PACKAGE, check=False)
    fields = result.stdout.rstrip("\n").split("\t")
    require(result.returncode == 0 and len(fields) == 3 and fields[2] == architecture,
            "installed-package-identity-refused")
    status, version, _ = fields
    _release_version(version)
    return status, version


def check_deb(path: Path, architecture: str, version: str) -> None:
    layout = native_command(DPKG_DEB, "--show", "--showformat=${Package}\t${Version}\t${Architecture}\n", str(path))
    require(layout.stdout == f"{PACKAGE}\t{version}\t{architecture}\n", "deb-package-identity-refused")


def stream_sha256(stream) -> str:
    digest = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def deb_runtime_digests(path: Path) -> dict[PurePosixPath, str]:
    with TemporaryFile(dir=path.parent) as payload:
        subprocess.run((DPKG_DEB, "--fsys-tarfile", str(path)), env=COMMAND_ENV, cwd="/",
                       stdin=subprocess.DEVNULL, stdout=payload, stderr=subprocess.DEVNULL,
                       check=True, timeout=300)
        payload.seek(0)
        digests = {}
        directories = set()
        with tarfile.open(fileobj=payload, mode="r:") as archive:
            for entry in archive:
                name = entry.name.removeprefix("./")
                relative = PurePosixPath(name.lstrip("/"))
                if relative != LAUNCHER and not relative.is_relative_to(SERVER_ROOT):
                    continue
                require(
                    name == relative.as_posix() and ".." not in relative.parts
                    and relative not in directories and relative not in digests
                    and entry.uid == 0 and entry.gid == 0 and not entry.mode & 0o7022,
                    "deb-runtime-payload-refused",
                )
                if entry.isdir() and relative != LAUNCHER:
                    directories.add(relative)
                    continue
                require(
                    relative != SERVER_ROOT and entry.isfile() and entry.sparse is None
                    and 0 < entry.size <= MAX_ARTIFACT_BYTES,
                    "deb-runtime-payload-refused",
                )
                with archive.extractfile(entry) as stream:
                    digests[relative] = stream_sha256(stream)
        require(LAUNCHER in digests, "deb-launcher-payload-refused")
        return digests


def installed_launcher_sha256() -> str:
    with trusted_path(Path("/usr/bin/row")).open("rb") as stream:
        return stream_sha256(stream)


def verify_installed_servers(digests: dict[PurePosixPath, str], root: Path = Path("/") / SERVER_ROOT) -> None:
    expected = {Path(path.relative_to(SERVER_ROOT)): sha for path, sha in digests.items() if path != LAUNCHER}
    try:
        if not expected and not root.exists() and not root.is_symlink():
            return
        directories = [root]
        while directories:
            current = trusted_path(directories.pop(), directory=True)
            for path in current.iterdir():
                if stat.S_ISDIR(path.lstat().st_mode):
                    directories.append(path)
                    continue
                digest = expected.pop(path.relative_to(root), None)
                require(digest is not None, "installed-runtime-payload-refused")
                with trusted_path(path).open("rb") as stream:
                    require(
                        0 < os.fstat(stream.fileno()).st_size <= MAX_ARTIFACT_BYTES
                        and stream_sha256(stream) == digest,
                        "installed-runtime-payload-refused",
                    )
        require(not expected, "installed-runtime-payload-refused")
    except OSError as error:
        raise UpdateError("installed-runtime-payload-refused") from error


def load_policy(path: Path):
    policy = load_update_policy(trusted_path(path))
    require(policy.settings["schema"] == POLICY_SCHEMA_V2, "managed-update-requires-v2-policy")
    return policy


def verified_deb(policy, stage: Path, workspace: Path, architecture: str, version: str):
    stage = trusted_path(stage, directory=True, private=True)
    result = recover_update(policy, stage, current_home=workspace, expected_version=version)
    raw = _read_regular(stage / MANIFEST, policy.settings["limits"]["manifest_bytes"])
    require(hashlib.sha256(raw).hexdigest() == result["manifest_sha256"], "stage-manifest-changed")
    manifest = authenticate_manifest(raw, policy, expected_version=version)
    expected = f"{PACKAGE}-v{version}-linux-{architecture}.deb"
    selected = next((row for row in manifest.artifacts if row.name == expected), None)
    require(selected is not None and selected.target == result["selected_target"], "selected-deb-absent")
    return stage / selected.name, selected


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def verify_bytes(path: Path, size: int, digest: str, *, copy_to=None) -> None:
    path = trusted_path(path, private=True)
    actual = hashlib.sha256()
    with path.open("rb") as stream:
        require(os.fstat(stream.fileno()).st_size == size, "installer-size-mismatch")
        remaining = size
        while chunk := stream.read(min(1024 * 1024, remaining + 1)):
            remaining -= len(chunk)
            require(remaining >= 0, "installer-size-mismatch")
            actual.update(chunk)
            if copy_to is not None:
                copy_to.write(chunk)
    require(remaining == 0 and actual.hexdigest() == digest, "installer-digest-mismatch")


def snapshot_matches(dest: Path, artifact) -> bool:
    try:
        dest.lstat()
    except FileNotFoundError:
        return False
    try:
        verify_bytes(dest, artifact.size, artifact.sha256)
    except UpdateError as error:
        raise UpdateError("transaction-snapshot-conflict") from error
    return True


def snapshot_deb(source: Path, artifact, dest: Path) -> None:
    # The administrator-owned directory and transaction locks serialize
    # publishers. A completed snapshot can survive a crash before journaling.
    if snapshot_matches(dest, artifact):
        return
    temporary = NamedTemporaryFile(dir=dest.parent, prefix=".update-", delete=False)
    path = Path(temporary.name)
    try:
        with temporary:
            verify_bytes(source, artifact.size, artifact.sha256, copy_to=temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        if not snapshot_matches(dest, artifact):
            os.replace(path, dest)
        sync_directory(dest.parent)
    finally:
        path.unlink(missing_ok=True)


def journal_write(path: Path, state: dict, phase: str) -> dict:
    next_state = {**state, "phase": phase}
    write_json_atomic(path, next_state, private=True)
    sync_directory(path.parent)
    return next_state


def read_journal(path: Path, architecture: str) -> dict:
    document = _decode(_read_regular(trusted_path(path, private=True), 4096), 4096)
    require(type(document) is dict and set(document) == {
        "schema", "phase", "architecture", "previous_version", "candidate_version",
        "previous_sha256", "previous_size", "candidate_sha256",
        "previous_launcher_sha256", "candidate_launcher_sha256",
    } and document["schema"] == SCHEMA and document["architecture"] == architecture
            and document["phase"] in ("applying", "applied", "rolling-back", "rolled-back"),
            "update-journal-refused")
    require(_release_version(document["previous_version"]) < _release_version(document["candidate_version"])
            and type(document["previous_size"]) is int
            and 0 < document["previous_size"] <= MAX_ARTIFACT_BYTES
            and all(isinstance(document[key], str) and re.fullmatch(r"[0-9a-f]{64}", document[key])
                    for key in ("previous_sha256", "candidate_sha256",
                                "previous_launcher_sha256", "candidate_launcher_sha256")),
            "update-journal-refused")
    return document


def verify_installation(architecture: str, version: str, digests: dict[PurePosixPath, str]) -> None:
    require(installed_package(architecture) == ("installed", version), "installed-package-identity-refused")
    require(installed_launcher_sha256() == digests[LAUNCHER], "installed-launcher-digest-refused")
    verify_installed_servers(digests)


def install_deb(path: Path, architecture: str, version: str, digests: dict[PurePosixPath, str]) -> None:
    check_deb(path, architecture, version)
    native_command(DPKG, "--install", str(path), frontend_locked=True)
    verify_installation(architecture, version, digests)
    launcher = trusted_path(Path("/usr/bin/row"))
    result = native_command(str(launcher), "--version")
    require(result.stdout.strip() == f"{PACKAGE} {version}", "installed-launcher-version-refused")


def retained_runtime(
    path: Path, sha256: str, launcher_sha256: str, size: int | None = None,
) -> dict[PurePosixPath, str]:
    if size is None:
        size = trusted_path(path, private=True).stat().st_size
    require(0 < size <= MAX_ARTIFACT_BYTES, "installer-size-mismatch")
    verify_bytes(path, size, sha256)
    digests = deb_runtime_digests(path)
    require(digests[LAUNCHER] == launcher_sha256, "update-journal-refused")
    return digests


def rollback(journal: Path, state: dict, architecture: str) -> dict:
    previous = state["previous_version"]
    phase = state["phase"]
    candidate = state["candidate_version"]
    if phase == "applied":
        # A completed transaction grants rollback only for the exact
        # installation it verified. Recovery of an interrupted transaction
        # must still tolerate an incomplete launcher or package status.
        candidate_runtime = retained_runtime(
            journal.parent / CANDIDATE_PACKAGE, state["candidate_sha256"], state["candidate_launcher_sha256"],
        )
        verify_installation(architecture, candidate, candidate_runtime)
    elif phase != "rolled-back":
        require(installed_package(architecture)[1] in (previous, candidate), "installed-package-changed")
    retained = journal.parent / PREVIOUS_PACKAGE
    previous_runtime = retained_runtime(
        retained, state["previous_sha256"], state["previous_launcher_sha256"], state["previous_size"],
    )
    if phase == "rolled-back":
        verify_installation(architecture, previous, previous_runtime)
        return state
    state = journal_write(journal, state, "rolling-back")
    install_deb(retained, architecture, previous, previous_runtime)
    return journal_write(journal, state, "rolled-back")


def upgrade_preflight(args, architecture: str, *, expected_previous: str | None = None):
    status, previous = installed_package(architecture)
    if expected_previous is not None:
        require((status, previous) == ("installed", expected_previous), "installed-package-changed")
    require(status == "installed" and _release_version(args.version) > _release_version(previous),
            "update-version-not-newer")
    policy = load_policy(args.policy)
    previous_policy = load_policy(args.previous_policy)
    keys = ("organization", "channel", "public_key", "selected_target")
    require(all(policy.settings[key] == previous_policy.settings[key] for key in keys),
            "rollback-trust-identity-refused")
    require(policy.settings["selected_target"] == DEBIAN_TARGETS[architecture], "managed-update-target-refused")
    require(_release_version(previous) >= _release_version(policy.settings["minimum_version"]),
            "rollback-version-below-policy-minimum")
    return previous, policy, previous_policy


def prepare_upgrade(args, workspace: Path, transaction: Path, architecture: str) -> str:
    stage = trusted_path(args.stage, directory=True, private=True)
    previous_stage = trusted_path(args.previous_stage, directory=True, private=True)
    require(not any(left.is_relative_to(right) or right.is_relative_to(left)
                    for left, right in combinations((stage, previous_stage, transaction, workspace), 2)),
            "managed-update-directories-overlap")
    previous, policy, previous_policy = upgrade_preflight(args, architecture)
    # Recover occupied stages under the current trust policy. Incomplete or
    # changed input is retained for inspection rather than downloaded over.
    for target, root, version in ((previous_policy, previous_stage, previous), (policy, stage, args.version)):
        operation = recover_update if any(path.name != STAGE_LOCK for path in root.iterdir()) else stage_update
        operation(target, root, current_home=workspace, expected_version=version)
    return previous


def apply(args, journal: Path, architecture: str, *, expected_previous: str | None = None) -> dict:
    if journal.exists() or journal.is_symlink():
        state = read_journal(journal, architecture)
        require(state["candidate_version"] == args.version, "existing-update-transaction")
        if state["phase"] == "applied":
            runtime = retained_runtime(
                journal.parent / CANDIDATE_PACKAGE, state["candidate_sha256"], state["candidate_launcher_sha256"],
            )
            verify_installation(architecture, args.version, runtime)
            return state
        return rollback(journal, state, architecture)

    previous, policy, previous_policy = upgrade_preflight(args, architecture, expected_previous=expected_previous)
    source, candidate = verified_deb(policy, args.stage, args.workspace, architecture, args.version)
    old_source, prior = verified_deb(previous_policy, args.previous_stage, args.workspace, architecture, previous)
    old = journal.parent / PREVIOUS_PACKAGE
    new = journal.parent / CANDIDATE_PACKAGE
    snapshot_deb(old_source, prior, old)
    snapshot_deb(source, candidate, new)
    check_deb(old, architecture, previous)
    check_deb(new, architecture, args.version)
    previous_runtime = deb_runtime_digests(old)
    candidate_runtime = deb_runtime_digests(new)
    verify_installation(architecture, previous, previous_runtime)
    state = journal_write(journal, {
        "schema": SCHEMA, "architecture": architecture, "previous_version": previous,
        "candidate_version": args.version, "previous_sha256": prior.sha256, "previous_size": prior.size,
        "candidate_sha256": candidate.sha256,
        "previous_launcher_sha256": previous_runtime[LAUNCHER], "candidate_launcher_sha256": candidate_runtime[LAUNCHER],
    }, "applying")
    try:
        install_deb(new, architecture, args.version, candidate_runtime)
    except (OSError, subprocess.SubprocessError, ValueError):
        return rollback(journal, state, architecture)
    return journal_write(journal, state, "applied")


def run(args) -> dict:
    require(sys.platform == "linux" and os.getuid() == 0 and os.geteuid() == 0, "linux-root-required")
    architecture = native_command(DPKG, "--print-architecture").stdout.strip()
    require(architecture in DEBIAN_TARGETS, "unsupported-debian-architecture")
    if args.action in {"stage-previous", "stage-candidate"}:
        status, version = installed_package(architecture)
        require(status == "installed", "installed-package-identity-refused")
        if args.action == "stage-candidate":
            require(_release_version(args.version) > _release_version(version), "update-version-not-newer")
            version = args.version
        return stage_update(load_policy(args.policy), trusted_path(args.stage, directory=True, private=True),
                            current_home=args.workspace, expected_version=version)
    root = trusted_path(args.transaction, directory=True, private=True)
    workspace = Path(os.path.abspath(args.workspace))
    require(not root.is_relative_to(workspace), "transaction-must-be-outside-workspace")
    trusted_path(SYSTEM_LOCK_ROOT.parent, directory=True)
    SYSTEM_LOCK_ROOT.mkdir(mode=0o700, exist_ok=True)
    system_root = trusted_path(SYSTEM_LOCK_ROOT, directory=True, private=True)
    journal = root / JOURNAL
    with exclusive_file_lock(system_root / JOURNAL), exclusive_file_lock(journal):
        previous = None
        if args.action == "update" and not (journal.exists() or journal.is_symlink()):
            # Leave the package manager available during network transfers.
            previous = prepare_upgrade(args, workspace, root, architecture)
        with debian_frontend_lock():
            if args.action in {"apply", "update"}:
                return apply(args, journal, architecture, expected_previous=previous)
            return rollback(journal, read_journal(journal, architecture), architecture)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    previous = actions.add_parser("stage-previous", help="stage the signed installer for the currently installed version")
    candidate = actions.add_parser("stage-candidate", help="stage the signed installer for the specified newer version")
    upgrade = actions.add_parser("apply", help="apply a signed staged update with a verified rollback package")
    automatic = actions.add_parser("update", help="authenticate both installers, apply the update and recover failures")
    restore = actions.add_parser("rollback", help="restore the retained previous package without network access")
    for action in (previous, candidate, upgrade, automatic, restore):
        action.add_argument("--workspace", required=True, type=Path, help="ROW_HOME excluded from installer staging")
    for action in (previous, candidate, upgrade, automatic):
        action.add_argument("--policy", required=True, type=Path)
        action.add_argument("--stage", required=True, type=Path)
    for action in (upgrade, automatic, restore):
        action.add_argument("--transaction", required=True, type=Path)
    for action in (upgrade, automatic):
        action.add_argument("--previous-policy", required=True, type=Path)
        action.add_argument("--previous-stage", required=True, type=Path)
    for action in (candidate, upgrade, automatic):
        action.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except UpdateError as error:
        print(json.dumps({"phase": "refused", "refusal": str(error)}))
        return 1
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError):
        print(json.dumps({"phase": "refused", "refusal": "managed-debian-update-failed"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    expected = {"stage-previous": "authenticated-staged", "stage-candidate": "authenticated-staged",
                "apply": "applied", "update": "applied", "rollback": "rolled-back"}
    return 0 if result["phase"] == expected[args.action] else 1


if __name__ == "__main__":
    raise SystemExit(main())
