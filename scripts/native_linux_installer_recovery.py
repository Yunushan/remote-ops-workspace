"""Hosted Ubuntu24.04 x64 DEB transition draft; default action prints a plan.

Only the allowlisted receipt is public. Private fixture output stays outside
artifact upload paths. Leader completion/timeout is not descendant cleanup proof.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path.cwd().resolve()
HERE = Path(__file__).resolve().parent
REPO = "Yunushan/remote-ops-workspace"
PREVIOUS = "1.0.24"
TARGET = "linux-x86_64"
PACKAGE = "remote-ops-workspace"
SCHEMA = "row.linux-deb-upgrade-rollback.v1"
MAX_FILE = 150 * 1024 * 1024
MAX_PAYLOAD = 180 * 1024 * 1024
REPORT = Path("build/native-smoke/linux-x86_64/native-upgrade-rollback.json")
PINS = Path("configs/native_linux_previous_release_pins.json")
ROW = Path("/usr/bin/row")
DOCS = Path("/usr/share/doc/remote-ops-workspace")
FILES = (
    "usr/bin/row",
    *(
        "usr/share/doc/remote-ops-workspace/" + name
        for name in (
            "LICENSE",
            "NOTICE",
            "THIRD_PARTY_NOTICES.md",
            "README.md",
            "RELEASE_TARGET.md",
        )
    ),
)
DIRECTORIES = {
    ".",
    "usr",
    "usr/bin",
    "usr/share",
    "usr/share/doc",
    "usr/share/doc/remote-ops-workspace",
}
STORES = (
    "profiles.json",
    "vault.json",
    "layouts.json",
    "snippets.json",
    "moba-macros.json",
    "xserver-state.json",
    *(
        f"servers/{name}-server-state.json"
        for name in ("http", "ftp", "tftp", "ssh", "sftp", "telnet", "vnc", "nfs")
    ),
)
KNOWN_LOCKS = {
    (PurePosixPath(name).parent / ("." + PurePosixPath(name).name + ".lock")).as_posix()
    for name in STORES
}
PLAN = (
    "Refuse local/self-hosted/non-Ubuntu24.04/non-x64 execution and preexisting dpkg/RPM/path ownership before mutation.",
    "Bind clean exact source, current finish, pip inventory, original CArchive, per-probe smoke receipt and every candidate asset.",
    "Re-query immutable prior input pins; bounded download and DEB control/payload inspection before privileged installation.",
    "Install genuine prior DEB; pinned wheel seeds complete synthetic state; actual prior native decrypts vault v2.",
    "Bound candidate rescue snapshots prior state; actual newer candidate DEB replaces prior and reads unchanged v2 state.",
    "Installed candidate mutates to vault v3; full-state encrypted recovery and exact negative restore probes preserve originals.",
    "Remove verified candidate; reinstall exact prior DEB; rescue restores pre-upgrade v2 snapshot to fresh sibling; prior native decrypts it.",
    "Remove only verified owned package; revalidate every input/source/asset; report actual cleanup facts and hosted-disposal process-tree boundary.",
)


def load_module(path: Path, name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("helper-unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


native = load_module(ROOT / "scripts/native_installer_recovery.py", "row_linux_native_common")
recovery = load_module(ROOT / "scripts/smoke_workspace_recovery.py", "row_linux_recovery_state")


class EvidenceError(RuntimeError):
    """Public static code; captured command/state text is never forwarded."""


def regular(path: Path, limit=MAX_FILE) -> bytes:
    if any(parent.is_symlink() for parent in path.parents):
        raise EvidenceError("unexpected-file-parent-link")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit or before.st_nlink != 1:
        raise EvidenceError("unexpected-file-type-or-bound")
    with path.open("rb") as stream:
        actual = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (
            actual.st_dev,
            actual.st_ino,
            actual.st_size,
        ):
            raise EvidenceError("file-identity-changed")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if (
        len(data) > limit
        or len(data) != before.st_size
        or (actual.st_mtime_ns, actual.st_ctime_ns, actual.st_size)
        != (after.st_mtime_ns, after.st_ctime_ns, after.st_size)
    ):
        raise EvidenceError("file-bytes-changed-or-bound")
    return data


def digest(path: Path, limit=MAX_FILE) -> str:
    return hashlib.sha256(regular(path, limit)).hexdigest()


def save(path: Path, value: object) -> None:
    for parent in path.parents:
        if parent == ROOT.parent:
            break
        if parent.is_symlink():
            raise EvidenceError("receipt-or-private-parent-link")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def private_environment(
    home: Path, private: Path, password="", backup_password=""
) -> dict[str, str]:
    # Native children receive no runner token, Python import override or loader
    # injection inherited from the CI/harness environment.
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": str(private),
        "TMPDIR": str(private / "tmp"),
        "ROW_HOME": str(home),
        "ROW_VAULT_PASSWORD": password,
        "ROW_RECOVERY_PASSWORD": backup_password,
    }


class Commands:
    """Bounded output/deadline, retained real Popen leader; no PID/group signals."""

    def __init__(self, private: Path | None = None):
        self.private = private
        self.uncertain = False
        self.calls = []
        self.started = time.monotonic()

    def capture(
        self,
        command: list[str],
        environment=None,
        *,
        timeout=180,
        limit=4 * 1024 * 1024,
        expected=0,
        stdin_payload: bytes | None = None,
    ) -> bytes:
        if self.uncertain:
            raise EvidenceError("command-lifetime-uncertain")
        if stdin_payload is not None and len(stdin_payload) > 65536:
            raise EvidenceError("command-stdin-bound")
        if os.name == "posix":
            import signal

            if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
                raise EvidenceError("default-owned-child-reaping-required")
        remaining = 1500 - (time.monotonic() - self.started)
        if remaining <= 0:
            self.uncertain = True
            raise EvidenceError("harness-deadline")
        timeout = min(timeout, remaining)
        deadline = min(time.monotonic() + timeout, self.started + 1500)
        env = environment or {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        buffers = [bytearray(), bytearray()]
        overflow = threading.Event()
        failed = threading.Event()

        def drain(stream, index, bound):
            try:
                while chunk := stream.read(65536):
                    if len(buffers[index]) + len(chunk) > bound:
                        overflow.set()
                    else:
                        buffers[index].extend(chunk)
            except OSError:
                failed.set()

        child = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if stdin_payload is not None else subprocess.DEVNULL,
            env=env,
            cwd=ROOT,
        )
        threads = []
        reason = None
        cleanup_attempted = False
        cleanup_error = None
        try:
            threads = [
                threading.Thread(target=drain, args=(child.stdout, 0, limit), daemon=True),
                threading.Thread(target=drain, args=(child.stderr, 1, 1024 * 1024), daemon=True),
            ]
            if stdin_payload is not None:

                def feed():
                    try:
                        child.stdin.write(stdin_payload)
                        child.stdin.close()
                    except OSError:
                        failed.set()

                threads.append(threading.Thread(target=feed, daemon=True))
            for thread in threads:
                thread.start()
            while True:
                if overflow.is_set() or failed.is_set():
                    raise EvidenceError("command-output-bound-or-read")
                wait = deadline - time.monotonic()
                if wait <= 0:
                    raise EvidenceError("command-timeout")
                try:
                    exit_code = child.wait(timeout=min(0.1, wait))
                    break
                except subprocess.TimeoutExpired:
                    pass
            if time.monotonic() >= deadline:
                raise EvidenceError("command-late-completed-exit")
            for thread in threads:
                thread.join(max(0, min(1, deadline - time.monotonic())))
            if any(thread.is_alive() for thread in threads) or overflow.is_set() or failed.is_set():
                raise EvidenceError("command-pipe-lifetime-or-bound")
            if time.monotonic() >= deadline:
                raise EvidenceError("command-late-completed-output")
        except BaseException as exc:
            self.uncertain = True
            reason = type(exc).__name__
            # The shared helper signals only this retained owned child. It does
            # not prove grandchildren gone; uncertainty blocks package cleanup.
            cleanup_attempted = True
            try:
                owned = load_module(
                    ROOT / "src/remote_ops_workspace/process_status.py", "row_linux_owned_cleanup"
                )
                owned.terminate_owned_process(child, timeout_seconds=5)
            except Exception as cleanup_exc:
                cleanup_error = type(cleanup_exc).__name__
            raise
        finally:
            self.calls.append(
                {
                    "step": len(self.calls) + 1,
                    "leader_exit_confirmed": child.returncode is not None,
                    "exit_code": child.returncode,
                    "execution_uncertain": self.uncertain,
                    "failure_type": reason,
                    "leader_cleanup_attempted": cleanup_attempted,
                    "leader_cleanup_error_type": cleanup_error,
                    "process_tree_cleanup": "not-proven",
                }
            )
            if not any(thread.is_alive() for thread in threads):
                child.stdout.close()
                child.stderr.close()
                if child.stdin is not None and not child.stdin.closed:
                    child.stdin.close()
        if self.private is not None:
            serial = len(self.calls)
            (self.private / f"command-{serial}.stdout").write_bytes(buffers[0])
            (self.private / f"command-{serial}.stderr").write_bytes(buffers[1])
        if type(exit_code) is not int or exit_code != expected:
            raise EvidenceError("command-unexpected-exit")
        return bytes(buffers[0] + buffers[1])


def git_output(commands: Commands, *args: str) -> str:
    return commands.capture(["/usr/bin/git", *args], timeout=30).decode("utf-8").strip()


def version_tuple(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", value
    ):
        raise EvidenceError("noncanonical-version")
    return tuple(map(int, value.split(".")))


def require_newer_version(value: str) -> None:
    if version_tuple(value) <= version_tuple(PREVIOUS):
        raise EvidenceError("candidate-version-not-newer")


def validate_host_environment(values: dict) -> None:
    expected = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Linux",
        "RUNNER_ARCH": "X64",
        "GITHUB_REPOSITORY": REPO,
    }
    if any(values.get(key) != value for key, value in expected.items()):
        raise EvidenceError("hosted-ubuntu-x64-required")


def validate_host_values(values: dict, sha: str) -> None:
    """Pure predicate for refusal tests; grants no runtime authorization."""
    validate_host_environment(values)
    if (values.get("os_name"), values.get("sys_platform"), values.get("machine")) != (
        "posix",
        "linux",
        "x86_64",
    ):
        raise EvidenceError("native-linux-x64-required")
    if values.get("implementation") != "cpython" or values.get("version_info") != (3, 14, 7):
        raise EvidenceError("pinned-cpython3147-required")
    if (values.get("distro_id"), values.get("distro_version")) != ("ubuntu", "24.04"):
        raise EvidenceError("ubuntu2404-required")
    if values.get("workspace_absolute") is not True or values.get("workspace_resolved") != str(
        ROOT
    ):
        raise EvidenceError("hosted-source-root-mismatch")
    if values.get("controller_resolved") != str(
        ROOT / "scripts/native_linux_installer_recovery.py"
    ):
        raise EvidenceError("canonical-source-controller-required")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or any(
        not re.fullmatch(r"[1-9][0-9]*", values.get(key, ""))
        for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
    ):
        raise EvidenceError("invalid-source-or-run-binding")


def validate_host_claims(sha: str) -> None:
    # Always gather real runtime values. The pure predicate cannot spoof or
    # authorize a run; run/install/uninstall all call this actual wrapper.
    values = {
        key: os.environ.get(key, "")
        for key in (
            "GITHUB_ACTIONS",
            "RUNNER_ENVIRONMENT",
            "RUNNER_OS",
            "RUNNER_ARCH",
            "GITHUB_REPOSITORY",
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
        )
    }
    # Reject untrusted host claims before platform metadata helpers, which can
    # invoke subprocesses on unsupported systems such as Windows.
    validate_host_environment(values)
    if os.name != "posix" or sys.platform != "linux":
        raise EvidenceError("native-linux-x64-required")
    release = platform.freedesktop_os_release()
    workspace = os.environ.get("GITHUB_WORKSPACE", "")
    values.update(
        os_name=os.name,
        sys_platform=sys.platform,
        machine=platform.machine().lower(),
        implementation=sys.implementation.name,
        version_info=sys.version_info[:3],
        distro_id=release.get("ID"),
        distro_version=release.get("VERSION_ID"),
        workspace_absolute=bool(workspace) and Path(workspace).is_absolute(),
        workspace_resolved=str(Path(workspace).resolve()) if workspace else "",
        controller_resolved=str(Path(__file__).resolve()),
    )
    validate_host_values(values, sha)


def package_rows(raw: bytes, rpm=False) -> list[list[str]]:
    rows = []
    for line in raw.decode("utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 4 or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?", fields[0]):
            raise EvidenceError("package-database-query-malformed")
        if rpm and any(not value or re.search(r"\s", value) for value in fields):
            raise EvidenceError("rpm-database-query-malformed")
        rows.append(fields)
    return [row for row in rows if row[0].split(":")[0] == PACKAGE]


def query_packages(commands: Commands) -> tuple[list[list[str]], list[list[str]]]:
    deb = commands.capture(
        [
            "/usr/bin/dpkg-query",
            "-W",
            "-f=${binary:Package}\t${db:Status-Abbrev}\t${Version}\t${Architecture}\n",
        ]
    )
    rpm = commands.capture(
        ["/usr/bin/rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\n"]
    )
    return package_rows(deb), package_rows(rpm, rpm=True)


def assert_absent(commands: Commands) -> None:
    deb, rpm = query_packages(commands)
    if deb or rpm:
        raise EvidenceError("preexisting-or-partial-package-registration")
    for path in (ROW, DOCS):
        if os.path.lexists(path):
            raise EvidenceError("preexisting-or-residual-owned-path")


def runner_gate(sha: str, commands: Commands) -> None:
    validate_host_claims(sha)
    if git_output(commands, "rev-parse", "HEAD") != sha or git_output(
        commands, "status", "--porcelain", "--untracked-files=no"
    ):
        raise EvidenceError("candidate-source-not-exact-clean")
    for tool in (
        "/usr/bin/sudo",
        "/usr/bin/dpkg",
        "/usr/bin/dpkg-query",
        "/usr/bin/dpkg-deb",
        "/usr/bin/rpm",
        "/usr/bin/git",
    ):
        if not Path(tool).is_file():
            raise EvidenceError("fixed-system-tool-unavailable")
    assert_absent(commands)
    commands.capture(["/usr/bin/sudo", "-n", "true"], timeout=10)


def member_name(name: str) -> str:
    if name in {".", "./"}:
        return "."
    if name.startswith("./"):
        name = name[2:]
    name = name.rstrip("/")
    if name == ".":
        return name
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or path.as_posix() != name
        or any(part in {".", ".."} for part in path.parts)
        or re.search(r"[\\\x00-\x1f:]", name)
    ):
        raise EvidenceError("unsafe-package-member-name")
    return name


def control_identity(raw: bytes, version: str) -> None:
    if len(raw) > 1024 * 1024:
        raise EvidenceError("control-archive-bound")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        members = archive.getmembers()
        names = [member_name(item.name) for item in members]
        if len(names) != len(set(names)) or set(names) not in ({"control"}, {".", "control"}):
            raise EvidenceError("unreviewed-package-control-or-script")
        for item, name in zip(members, names, strict=True):
            if (
                item.uid != 0
                or item.gid != 0
                or item.pax_headers
                or (name == "." and (not item.isdir() or item.mode != 0o755))
                or (
                    name == "control"
                    and (item.type != tarfile.REGTYPE or item.mode != 0o644 or item.size > 65536)
                )
            ):
                raise EvidenceError("unreviewed-package-control-or-script")
        control = members[names.index("control")]
        text = archive.extractfile(control).read().decode("utf-8")
    fields = {}
    for line in text.splitlines():
        if line.startswith(" "):
            if "Description" not in fields:
                raise EvidenceError("malformed-control-continuation")
            continue
        if not line or ": " not in line:
            raise EvidenceError("malformed-control-field")
        key, value = line.split(": ", 1)
        if key in fields:
            raise EvidenceError("duplicate-control-field")
        fields[key] = value
    if set(fields) != {
        "Package",
        "Version",
        "Section",
        "Priority",
        "Architecture",
        "Installed-Size",
        "Maintainer",
        "Description",
    } or (fields["Package"], fields["Version"], fields["Architecture"]) != (
        PACKAGE,
        version,
        "amd64",
    ):
        raise EvidenceError("unexpected-package-control-identity")


@dataclass(frozen=True)
class Payload:
    version: str
    files: tuple[tuple[str, int, str, int], ...]

    @property
    def row_sha256(self):
        return next(row[2] for row in self.files if row[0] == "usr/bin/row")


def payload_inventory(raw: bytes, version: str) -> Payload:
    if len(raw) > MAX_PAYLOAD:
        raise EvidenceError("payload-archive-bound")
    seen, rows, total = set(), [], 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for item in archive:
            name = member_name(item.name)
            if (
                name in seen
                or len(seen) >= 30
                or item.uid != 0
                or item.gid != 0
                or item.pax_headers
            ):
                raise EvidenceError("duplicate-or-unexpected-package-member")
            seen.add(name)
            if item.isdir():
                if name not in DIRECTORIES or item.size != 0 or item.mode != 0o755:
                    raise EvidenceError("unexpected-package-directory")
                continue
            expected_mode = 0o755 if name == "usr/bin/row" else 0o644
            bound = MAX_FILE if name == "usr/bin/row" else 4 * 1024 * 1024
            if (
                name not in FILES
                or item.type != tarfile.REGTYPE
                or item.name.endswith("/")
                or item.mode != expected_mode
                or not 0 < item.size <= bound
            ):
                raise EvidenceError("unreviewed-package-file-type-path-or-mode")
            stream = archive.extractfile(item)
            value, size = hashlib.sha256(), 0
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                value.update(chunk)
            total += size
            if size != item.size or total > MAX_PAYLOAD:
                raise EvidenceError("package-expanded-payload-bound")
            rows.append((name, size, value.hexdigest(), expected_mode))
    if {row[0] for row in rows} != set(FILES) or not DIRECTORIES.issubset(seen):
        raise EvidenceError("package-payload-files-incomplete")
    return Payload(version, tuple(sorted(rows)))


def inspect_deb(commands: Commands, path: Path, version: str, expected_hash: str) -> Payload:
    if digest(path) != expected_hash:
        raise EvidenceError("deb-bytes-mismatch-before-inspection")
    control_identity(
        commands.capture(["/usr/bin/dpkg-deb", "--ctrl-tarfile", str(path)], limit=1024 * 1024),
        version,
    )
    payload = payload_inventory(
        commands.capture(["/usr/bin/dpkg-deb", "--fsys-tarfile", str(path)], limit=MAX_PAYLOAD),
        version,
    )
    if digest(path) != expected_hash:
        raise EvidenceError("deb-changed-during-inspection")
    return payload


def installed_identity(commands: Commands, payload: Payload) -> None:
    deb, rpm = query_packages(commands)
    if rpm or len(deb) != 1 or deb[0][1:] != ["ii ", payload.version, "amd64"]:
        raise EvidenceError("owned-installed-package-identity-mismatch")
    verify_payload_files(Path("/"), payload)


def verify_payload_files(root: Path, payload: Payload) -> None:
    for name, size, sha, mode in payload.files:
        path = root / name
        if (
            any(parent.is_symlink() for parent in path.parents)
            or path.stat().st_size != size
            or digest(path) != sha
            or stat.S_IMODE(path.lstat().st_mode) != mode
        ):
            raise EvidenceError("owned-installed-payload-bytes-or-path-mismatch")
    docs = root / "usr/share/doc/remote-ops-workspace"
    if {path.name for path in docs.iterdir()} != {
        PurePosixPath(name).name for name in FILES if name.startswith("usr/share/doc/")
    }:
        raise EvidenceError("owned-documentation-directory-changed")


def inventory(home: Path) -> dict:
    """Explicit relative known-lock set; unknown/nested lock files are state."""
    if not home.is_dir() or home.is_symlink():
        raise EvidenceError("unexpected-state-root")
    rows, directories = [], []
    for path in sorted(home.rglob("*")):
        name = path.relative_to(home).as_posix()
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            directories.append(name)
        elif stat.S_ISREG(metadata.st_mode):
            if name not in KNOWN_LOCKS:
                data = regular(path, MAX_FILE)
                rows.append([name, len(data), hashlib.sha256(data).hexdigest()])
        else:
            raise EvidenceError("unexpected-state-file-type")
    material = json.dumps([directories, rows], separators=(",", ":")).encode()
    return {
        "sha256": hashlib.sha256(material).hexdigest(),
        "file_count": len(rows),
        "directory_count": len(directories),
        "total_bytes": sum(row[1] for row in rows),
    }


def input_paths() -> dict[str, Path]:
    base = ROOT / "build/candidate-proof" / TARGET
    return {
        "finish": base / "finish.json",
        "archives": base / "pyinstaller-archives.json",
        "pip_inspect": base / "pip-inspect.json",
        "pip_stderr": base / "pip-inspect.stderr.log",
        "binding": ROOT / "build/native-smoke" / TARGET / "candidate-runtime-byte-binding.json",
        "proof_verifier": ROOT / "scripts/candidate_native_proof.py",
        "posix_verifier": ROOT / "scripts/candidate_posix_byte_binding.py",
        "shared_native_oracle": ROOT / "scripts/native_installer_recovery.py",
        "worker": ROOT / "scripts/smoke_workspace_recovery.py",
        "linux_builder": ROOT / "scripts/make_linux_native.sh",
        "fixture": ROOT / "configs/workspace_recovery_fixture.json",
        "pins": ROOT / PINS,
        "owned_cleanup": ROOT / "src/remote_ops_workspace/process_status.py",
        "controller": Path(__file__),
        "original_row": ROOT / "build/native/linux/pyinstaller-dist/row",
        "original_launcher": ROOT / "build/native/linux/Remote_Ops_Workspace.AppDir/AppRun",
    }


def byte_records(paths: dict[str, Path]) -> dict:
    return {
        name: {"size": path.stat().st_size, "sha256": digest(path)} for name, path in paths.items()
    }


def checkout_fingerprint(commands: Commands) -> dict:
    names = (
        commands.capture(["/usr/bin/git", "ls-files", "-z"], timeout=30).decode("utf-8").split("\0")
    )
    material = "".join(
        name + "\0" + (digest(ROOT / name) if (ROOT / name).is_file() else "missing") + "\n"
        for name in sorted(names)
        if name
    ).encode()
    return {
        "head": git_output(commands, "rev-parse", "HEAD"),
        "tree": git_output(commands, "rev-parse", "HEAD^{tree}"),
        "checkout_bytes_sha256": hashlib.sha256(material).hexdigest(),
    }


def candidate_assets(commands: Commands, sha: str, version: str) -> tuple[dict, dict, str]:
    paths = input_paths()
    finish = json.loads(regular(paths["finish"], 16 * 1024 * 1024))
    verifier = load_module(paths["proof_verifier"], "row_linux_candidate_proof")
    fresh = checkout_fingerprint(commands)
    if (
        any(
            finish["source"].get(key) != fresh[key]
            for key in ("head", "tree", "checkout_bytes_sha256")
        )
        or fresh["head"] != sha
        or git_output(commands, "status", "--porcelain", "--untracked-files=no")
    ):
        raise EvidenceError("candidate-checkout-evidence-mismatch")
    if (
        finish.get("target") != TARGET
        or str(finish.get("run_id")) != os.environ["GITHUB_RUN_ID"]
        or str(finish.get("run_attempt")) != os.environ["GITHUB_RUN_ATTEMPT"]
    ):
        raise EvidenceError("candidate-run-evidence-mismatch")
    if (
        any(
            finish.get(key) is not True
            for key in (
                "source_unchanged",
                "native_pyinstaller_inventory_complete",
                "installed_project_sources_match_checkout",
                "pip_inspect_json_valid",
            )
        )
        or finish.get("native_build_outcome") != "success"
        or finish.get("native_smoke_outcome") != "success"
        or type(finish.get("pip_inspect_returncode")) is not int
        or finish["pip_inspect_returncode"] != 0
    ):
        raise EvidenceError("candidate-basic-proof-incomplete")
    binding = finish["native_executable_byte_binding"]
    if (
        binding.get("status") != "bound"
        or binding.get("report_path") != paths["binding"].relative_to(ROOT).as_posix()
        or binding.get("report_sha256") != digest(paths["binding"])
    ):
        raise EvidenceError("candidate-per-probe-byte-binding-mismatch")
    for field, name in (
        ("pyinstaller_archive_inventory_sha256", "archives"),
        ("pip_inspect_sha256", "pip_inspect"),
        ("pip_inspect_stderr_sha256", "pip_stderr"),
    ):
        if finish.get(field) != digest(paths[name]):
            raise EvidenceError("candidate-inventory-input-mismatch")
    pip = json.loads(regular(paths["pip_inspect"], 16 * 1024 * 1024))
    if (
        not isinstance(pip, dict)
        or not isinstance(pip.get("installed"), list)
        or not pip["installed"]
    ):
        raise EvidenceError("candidate-pip-inventory-malformed")
    original = ROOT / "build/native/linux/pyinstaller-dist/row"
    archives = json.loads(regular(paths["archives"], 16 * 1024 * 1024))
    actual_archive = verifier.archive_inventory(original)
    if (
        archives != [actual_archive]
        or not actual_archive.get("toc")
        or actual_archive.get("path") != "build/native/linux/pyinstaller-dist/row"
    ):
        raise EvidenceError("candidate-original-carchive-mismatch")
    launchers = [
        {
            "path": "build/native/linux/Remote_Ops_Workspace.AppDir/AppRun",
            "sha256": digest(paths["original_launcher"]),
        }
    ]
    if finish.get("native_packaged_launchers") != launchers:
        raise EvidenceError("candidate-original-launcher-changed")
    verifier.validate_posix_byte_binding(
        json.loads(regular(paths["binding"])), archives, TARGET, finish["assets"], launchers
    )
    suffixes = (
        "linux-amd64.deb",
        "linux-x86_64.rpm",
        "linux-x86_64.AppImage",
        "linux-x86_64-native.tar.gz",
        "linux-x86_64-native-manifest.json",
        "linux-x86_64-native-SHA256SUMS.txt",
    )
    expected_names = {f"remote-ops-workspace-v{version}-{suffix}" for suffix in suffixes}
    assets = {}
    for row in finish["assets"]:
        name = PurePosixPath(row["path"]).name
        if (
            name not in expected_names
            or row["path"] != "native-dist/linux/" + name
            or name in assets
        ):
            raise EvidenceError("candidate-asset-path-set-mismatch")
        path = ROOT / row["path"]
        if path.stat().st_size != row["size"] or digest(path) != row["sha256"]:
            raise EvidenceError("candidate-asset-bytes-mismatch")
        assets[name] = path
    if set(assets) != expected_names:
        raise EvidenceError("candidate-assets-incomplete")
    verify_manifest(assets, version)
    return assets, finish, digest(original)


def verify_manifest(paths: dict[str, Path], version: str) -> None:
    prefix = f"remote-ops-workspace-v{version}-linux-x86_64-native-"
    manifest = json.loads(regular(paths[prefix + "manifest.json"], 1024 * 1024))
    rows = {row["file"]: row for row in manifest}
    if len(rows) != len(manifest) or len(rows) != 4:
        raise EvidenceError("native-manifest-row-set")
    checksums = {}
    for line in regular(paths[prefix + "SHA256SUMS.txt"], 65536).decode("ascii").splitlines():
        sha, name = line.split("  ", 1)
        if not re.fullmatch(r"[0-9a-f]{64}", sha) or name in checksums or Path(name).name != name:
            raise EvidenceError("native-checksum-row-invalid")
        checksums[name] = sha
    for name, path in paths.items():
        if name.endswith(".whl") or name.endswith("SHA256SUMS.txt"):
            continue
        if checksums.get(name) != digest(path):
            raise EvidenceError("native-checksum-bytes-disagree")
        if name.endswith("manifest.json"):
            continue
        row = rows.get("native-dist/linux/" + name)
        if row is None or row["size_bytes"] != path.stat().st_size or row["sha256"] != digest(path):
            raise EvidenceError("native-manifest-bytes-disagree")
    if set(checksums) != {PurePosixPath(name).name for name in rows} | {prefix + "manifest.json"}:
        raise EvidenceError("native-checksum-file-set-mismatch")


def previous_assets(private: Path) -> tuple[dict, dict]:
    pins = json.loads(regular(ROOT / PINS, 65536))
    expected = json.loads(EXPECTED_PINS)
    if pins != expected:
        raise EvidenceError("immutable-prior-pins-changed")
    live = native.api_json("releases/tags/v" + PREVIOUS)
    if live.get("prerelease") is not True or live.get("immutable") is not False:
        raise EvidenceError("prior-publication-channel-changed")
    paths = native.previous_assets(pins, private)
    verify_manifest(paths, PREVIOUS)
    return paths, pins


def bound_deb_hashes(pins: dict, finish: dict, version: str) -> tuple[str, str]:
    old_name = f"remote-ops-workspace-v{PREVIOUS}-linux-amd64.deb"
    new_path = f"native-dist/linux/remote-ops-workspace-v{version}-linux-amd64.deb"
    old = [
        row["digest"].removeprefix("sha256:") for row in pins["assets"] if row["name"] == old_name
    ]
    new = [row["sha256"] for row in finish["assets"] if row["path"] == new_path]
    if (
        len(old) != 1
        or len(new) != 1
        or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in [*old, *new])
    ):
        raise EvidenceError("canonical-bound-deb-digest-missing-or-duplicate")
    return old[0], new[0]


class Drill(native.Drill):
    def __init__(self, private: Path, commands: Commands, sha: str):
        self.root, self.commands, self.sha = private, commands, sha
        self.serial = 0
        self.calls = []
        self.current = None
        self.rescue = None
        self.rescue_hash = None
        self.probes = []
        self.cleanup = {
            "package_cleanup": "not-started",
            "process_tree_cleanup": "not-proven",
            "hosted_disposal_boundary": True,
        }

    def command(self, executable, arguments, environment, *, expected_success=True, timeout=180):
        if executable == ROW:
            if self.current is None:
                raise EvidenceError("unverified-installed-command")
            installed_identity(self.commands, self.current)
            expected_hash = self.current.row_sha256
            role = "installed"
        elif executable == self.rescue:
            expected_hash, role = self.rescue_hash, "retained-rescue"
        else:
            raise EvidenceError("unexpected-native-entrypoint")
        if digest(executable) != expected_hash:
            raise EvidenceError("native-byte-mismatch-before-launch")
        output = self.commands.capture(
            [str(executable), *arguments],
            environment,
            timeout=timeout,
            expected=0 if expected_success else 1,
        )
        self.probes.append(
            {
                "step": len(self.probes) + 1,
                "role": role,
                "expected_sha256": expected_hash,
                "observed_sha256": digest(executable),
                "exit_code": 0 if expected_success else 1,
            }
        )
        if self.probes[-1]["observed_sha256"] != expected_hash:
            raise EvidenceError("native-byte-mismatch-after-launch")
        self.calls.append({"exit_code": 0 if expected_success else 1})
        return output.decode("utf-8")

    def install(self, package: Path, payload: Payload, package_hash: str):
        validate_host_claims(self.sha)
        if git_output(self.commands, "rev-parse", "HEAD") != self.sha or git_output(
            self.commands, "status", "--porcelain", "--untracked-files=no"
        ):
            raise EvidenceError("source-changed-before-privileged-operation")
        if self.current is None:
            assert_absent(self.commands)
        else:
            installed_identity(self.commands, self.current)
        if digest(package) != package_hash:
            raise EvidenceError("package-byte-mismatch-before-install")
        self.cleanup["package_cleanup"] = "uncertain-installation"
        self.commands.capture(
            ["/usr/bin/sudo", "-n", "/usr/bin/dpkg", "--install", str(package)], timeout=300
        )
        installed_identity(self.commands, payload)
        if digest(package) != package_hash:
            raise EvidenceError("package-changed-during-install")
        self.current = payload
        self.cleanup["package_cleanup"] = "verified-owned-installation"

    def uninstall(self):
        if self.commands.uncertain or self.current is None:
            raise EvidenceError("cleanup-owned-package-uncertain")
        validate_host_claims(self.sha)
        if git_output(self.commands, "rev-parse", "HEAD") != self.sha or git_output(
            self.commands, "status", "--porcelain", "--untracked-files=no"
        ):
            raise EvidenceError("source-changed-before-privileged-operation")
        installed_identity(self.commands, self.current)
        self.commands.capture(
            ["/usr/bin/sudo", "-n", "/usr/bin/dpkg", "--purge", PACKAGE], timeout=300
        )
        assert_absent(self.commands)
        self.current = None
        self.cleanup["package_cleanup"] = "verified-package-and-paths-removed"


def backup_arguments(path: Path) -> list[str]:
    return [
        "workspace",
        "backup",
        "--out",
        str(path),
        "--offline",
        "--passphrase-env",
        "ROW_RECOVERY_PASSWORD",
    ]


def restore_arguments(backup: Path, destination: Path) -> list[str]:
    return [
        "workspace",
        "restore",
        "--backup",
        str(backup),
        "--destination",
        str(destination),
        "--offline",
        "--passphrase-env",
        "ROW_RECOVERY_PASSWORD",
    ]


def state_worker(drill: Drill, runtime: Path, home: Path, payload: dict) -> dict:
    """Shared reviewed worker code, with this controller's bounded lifetime."""
    output = drill.commands.capture(
        [sys.executable, "-I", "-c", recovery._WORKER, str(runtime.resolve()), str(home.resolve())],
        private_environment(home, drill.root),
        timeout=180,
        limit=65536,
        stdin_payload=json.dumps(payload).encode("utf-8"),
    )
    result = json.loads(output)
    if (
        not isinstance(result, dict)
        or set(result) != {"version", "semantic_sha256", "vault_version", "counts"}
        or not isinstance(result["semantic_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", result["semantic_sha256"])
        or type(result["vault_version"]) is not int
    ):
        raise EvidenceError("isolated-worker-summary-shape")
    if (
        not isinstance(result["counts"], dict)
        or set(result["counts"])
        != {"profiles", "group_defaults", "layouts", "snippets", "macros", "vault_items"}
        or any(type(value) is not int or value < 0 for value in result["counts"].values())
    ):
        raise EvidenceError("isolated-worker-counts-shape")
    version_tuple(result["version"])
    return result


def validate_fixture_paths(fixture: dict) -> None:
    """Synthetic opaque data must stay inside the new private plugin subtree."""
    if not isinstance(fixture.get("opaque_files"), dict) or not isinstance(
        fixture.get("empty_directories"), list
    ):
        raise EvidenceError("private-fixture-path-shape")
    if len(fixture["opaque_files"]) > 32 or len(fixture["empty_directories"]) > 32:
        raise EvidenceError("private-fixture-path-count-bound")
    for name in [*fixture["opaque_files"], *fixture["empty_directories"]]:
        if (
            not isinstance(name, str)
            or member_name(name) != name
            or not name.startswith("plugins/unrecognized/")
        ):
            raise EvidenceError("private-fixture-path-containment")
    if any(
        not isinstance(value, str) or len(value.encode("utf-8")) > 65536
        for value in fixture["opaque_files"].values()
    ):
        raise EvidenceError("private-fixture-content-bound")


def transition(
    drill: Drill,
    previous: Path,
    candidate: Path,
    old_payload: Payload,
    new_payload: Payload,
    previous_hash: str,
    candidate_hash: str,
    wheel: Path,
    fixture: dict,
    phase,
) -> dict:
    validate_fixture_paths(fixture)
    home = drill.root / "original"
    payload = {
        "fixture": fixture,
        "vault_passphrase": secrets.token_urlsafe(32),
        "secret": secrets.token_urlsafe(48),
        "new_secret": secrets.token_urlsafe(48),
    }
    password = secrets.token_urlsafe(32)
    environment = private_environment(home, drill.root, payload["vault_passphrase"], password)
    old_profiles = native.profile_expectations(fixture)
    new_profiles = native.profile_expectations(fixture, include_current=True)
    phase("previous-native-install-and-inspection")
    drill.install(previous, old_payload, previous_hash)
    seeded = state_worker(drill, wheel, home, {**payload, "mode": "seed"})
    if seeded["version"] != PREVIOUS or seeded["vault_version"] != 2:
        raise EvidenceError("prior-seeding-version-or-vault")
    # Add unrecognized dot-locks even before the shared fixture is expanded.
    for name, data in (
        ("plugins/unrecognized/.plugin.lock", b"opaque-lock\x00\xff"),
        ("plugins/unrecognized/nested/.profiles.json.lock", b"nested-owned-by-plugin"),
    ):
        target = home / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
    prior_native = drill.inspect(
        ROW, home, PREVIOUS, environment, payload["secret"], 2, old_profiles
    )
    before = inventory(home)
    previous_backup = drill.root / "previous.rowbackup"
    drill.command(drill.rescue, backup_arguments(previous_backup), environment)
    previous_backup_hash = digest(previous_backup)
    if inventory(home) != before:
        raise EvidenceError("previous-backup-modified-state")
    phase("candidate-native-upgrade-and-inspection")
    drill.install(candidate, new_payload, candidate_hash)
    candidate_prior = drill.inspect(
        ROW, home, new_payload.version, environment, payload["secret"], 2, old_profiles
    )
    if (
        inventory(home) != before
        or state_worker(drill, ROOT / "src", home, {**payload, "mode": "inspect"})[
            "semantic_sha256"
        ]
        != seeded["semantic_sha256"]
    ):
        raise EvidenceError("native-upgrade-changed-prior-state")
    phase("candidate-state-mutation")
    drill.command(
        ROW,
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
        ROW,
        ["vault", "set", "current-only", "--secret-env", "ROW_NEW_SYNTHETIC_SECRET"],
        dict(environment, ROW_NEW_SYNTHETIC_SECRET=payload["new_secret"]),
    )
    mutated = drill.inspect(
        ROW,
        home,
        new_payload.version,
        environment,
        payload["secret"],
        3,
        new_profiles,
        payload["new_secret"],
    )
    upgraded = state_worker(drill, ROOT / "src", home, {**payload, "mode": "inspect"})
    if upgraded["vault_version"] != 3 or mutated["profiles"] != prior_native["profiles"] + 1:
        raise EvidenceError("native-vault-or-profile-mutation-absent")
    after = inventory(home)
    candidate_backup = drill.root / "candidate.rowbackup"
    drill.command(ROW, backup_arguments(candidate_backup), environment)
    candidate_backup_hash = digest(candidate_backup)
    if inventory(home) != after:
        raise EvidenceError("candidate-backup-modified-state")
    (home / "profiles.json").write_bytes(b"corrupted-after-snapshot")
    for name in fixture["opaque_files"]:
        (home / name).write_bytes(b"corrupted-plugin-after-snapshot")
    (home / "after-snapshot-only.dat").write_bytes(b"not-in-snapshots")
    corrupted = inventory(home)
    tampered = drill.root / "tampered.rowbackup"
    envelope = json.loads(regular(candidate_backup))
    token = envelope["token"]
    envelope["token"] = token[:30] + ("B" if token[30] == "A" else "A") + token[31:]
    save(tampered, envelope)
    phase("negative-and-candidate-restore")
    negatives = {}
    for label, backup, key, destination in (
        (
            "wrong-password",
            candidate_backup,
            secrets.token_urlsafe(32),
            drill.root / "wrong-password",
        ),
        ("tampered", tampered, password, drill.root / "tampered"),
        ("in-place", candidate_backup, password, home),
    ):
        found = drill.command(
            ROW,
            restore_arguments(backup, destination),
            dict(environment, ROW_RECOVERY_PASSWORD=key),
            expected_success=False,
        )
        expected = (
            "restore destination must be a new direct sibling of ROW_HOME"
            if label == "in-place"
            else "invalid backup passphrase or corrupted workspace backup"
        )
        if (
            found.strip() != "error: " + expected
            or (destination != home and destination.exists())
            or inventory(home) != corrupted
            or digest(previous_backup) != previous_backup_hash
            or digest(candidate_backup) != candidate_backup_hash
        ):
            raise EvidenceError("negative-restore-wrong-reason-or-state-changed")
        negatives[label] = True
    restored = drill.root / "restored-candidate"
    drill.command(ROW, restore_arguments(candidate_backup, restored), environment)
    if (
        inventory(restored) != after
        or state_worker(drill, ROOT / "src", restored, {**payload, "mode": "inspect"}) != upgraded
    ):
        raise EvidenceError("candidate-full-state-restore-mismatch")
    restored_native = drill.inspect(
        ROW,
        restored,
        new_payload.version,
        environment,
        payload["secret"],
        3,
        new_profiles,
        payload["new_secret"],
    )
    if restored_native != mutated or inventory(home) != corrupted:
        raise EvidenceError("candidate-native-restore-or-original-mismatch")
    phase("previous-native-rollback-and-inspection")
    drill.uninstall()
    drill.install(previous, old_payload, previous_hash)
    rollback = drill.root / "restored-previous"
    drill.command(drill.rescue, restore_arguments(previous_backup, rollback), environment)
    if (
        inventory(rollback) != before
        or state_worker(drill, wheel, rollback, {**payload, "mode": "inspect"}) != seeded
    ):
        raise EvidenceError("previous-v2-full-state-rollback-mismatch")
    rolled_back = drill.inspect(
        ROW, rollback, PREVIOUS, environment, payload["secret"], 2, old_profiles
    )
    if (
        rolled_back != prior_native
        or inventory(home) != corrupted
        or digest(previous_backup) != previous_backup_hash
        or digest(candidate_backup) != candidate_backup_hash
    ):
        raise EvidenceError("prior-native-rollback-or-preservation-mismatch")
    drill.uninstall()
    return {
        "stages": {
            "previous_installed": prior_native,
            "candidate_read_previous": candidate_prior,
            "candidate_mutated": mutated,
            "candidate_restored": restored_native,
            "previous_reinstalled_and_restored": rolled_back,
        },
        "snapshots": {
            "previous_ciphertext_sha256": previous_backup_hash,
            "candidate_ciphertext_sha256": candidate_backup_hash,
            "previous_inventory": before,
            "candidate_inventory": after,
            "corrupted_original_inventory": corrupted,
        },
        "semantic_checks": {
            "prior_sha256": seeded["semantic_sha256"],
            "candidate_sha256": upgraded["semantic_sha256"],
        },
        "negative_restores": negatives,
    }


def run(args) -> dict:
    commands = Commands()
    runner_gate(args.candidate_source_sha, commands)
    args.authorized = True
    import tomllib

    args.phase = "source-and-candidate-proof"
    version = tomllib.loads(regular(ROOT / "pyproject.toml").decode("utf-8"))["project"]["version"]
    require_newer_version(version)
    inputs_before = byte_records(input_paths())
    candidates, finish, candidate_row_sha = candidate_assets(
        commands, args.candidate_source_sha, version
    )
    old_umask = os.umask(0o077)
    private = ROOT / ".tmp" / ("native-linux-deb-recovery-" + uuid.uuid4().hex)
    try:
        if private.parent.is_symlink() or private.parent.resolve() != ROOT / ".tmp":
            raise EvidenceError("private-parent-root-containment")
        private.parent.mkdir(exist_ok=True)
        private.mkdir(mode=0o700)
        (private / "tmp").mkdir(mode=0o700)
        if private.is_symlink() or stat.S_IMODE(private.stat().st_mode) != 0o700:
            raise EvidenceError("private-parent-not-restricted")
    except BaseException:
        os.umask(old_umask)
        raise
    commands.private = private
    drill = Drill(private, commands, args.candidate_source_sha)
    args.drill = drill
    try:
        import truststore

        truststore.inject_into_ssl()
        args.phase = "previous-input-download-and-deb-inspection"
        prior, pins = previous_assets(private)
        old = prior[f"remote-ops-workspace-v{PREVIOUS}-linux-amd64.deb"]
        new = candidates[f"remote-ops-workspace-v{version}-linux-amd64.deb"]
        old_sha, new_sha = bound_deb_hashes(pins, finish, version)
        old_payload = inspect_deb(commands, old, PREVIOUS, old_sha)
        new_payload = inspect_deb(commands, new, version, new_sha)
        if (
            new_payload.row_sha256 != candidate_row_sha
            or new_payload.row_sha256 == old_payload.row_sha256
        ):
            raise EvidenceError("candidate-original-or-distinct-bytes-mismatch")
        wheel = prior[recovery.EXPECTED_WHEEL_NAME]
        recovery.verify_previous_wheel(wheel)
        fixture = recovery.load_fixture()
        rescue = private / "candidate-rescue"
        shutil.copyfile(ROOT / "build/native/linux/pyinstaller-dist/row", rescue)
        rescue.chmod(0o700)
        if digest(rescue) != candidate_row_sha:
            raise EvidenceError("candidate-rescue-bytes-mismatch")
        drill.rescue, drill.rescue_hash = rescue, candidate_row_sha
        outcomes = transition(
            drill,
            old,
            new,
            old_payload,
            new_payload,
            old_sha,
            new_sha,
            wheel,
            fixture,
            lambda value: setattr(args, "phase", value),
        )
        args.phase = "final-source-input-artifact-revalidation"
        assets_again, finish_again, row_again = candidate_assets(
            commands, args.candidate_source_sha, version
        )
        if (
            assets_again != candidates
            or finish_again != finish
            or row_again != candidate_row_sha
            or byte_records(input_paths()) != inputs_before
            or digest(rescue) != candidate_row_sha
        ):
            raise EvidenceError("final-source-proof-or-candidate-changed")
        for row in pins["assets"]:
            path = prior[row["name"]]
            if path.stat().st_size != row["size"] or digest(path) != row["digest"].removeprefix(
                "sha256:"
            ):
                raise EvidenceError("prior-input-changed-during-transition")
        assert_absent(commands)
        return {
            "schema": SCHEMA,
            "status": "passed",
            "scope": "actual-previous-linux-x86_64-deb-to-unreleased-candidate-upgrade-and-operator-rollback",
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "repository": REPO,
            "source_sha": args.candidate_source_sha,
            "source_tree": finish["source"]["tree"],
            "checkout_bytes_sha256": finish["source"]["checkout_bytes_sha256"],
            "run_id": os.environ["GITHUB_RUN_ID"],
            "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "runner_os": "Ubuntu24.04",
            "runner_arch": "X64",
            "candidate_version": version,
            "previous_release": pins,
            "proof_inputs": inputs_before,
            "candidate_assets": byte_records(candidates),
            "candidate_row_sha256": candidate_row_sha,
            "previous_row_sha256": old_payload.row_sha256,
            "native_probes": drill.probes,
            "commands": commands.calls,
            "cleanup": drill.cleanup,
            **outcomes,
            "final_revalidation": True,
            "limits": LIMITS,
        }
    finally:
        if drill.current is not None:
            try:
                drill.uninstall()
            except (OSError, RuntimeError, ValueError) as cleanup_exc:
                drill.cleanup["package_cleanup"] = "uncertain-refused-or-failed"
                drill.cleanup["package_cleanup_error_type"] = type(cleanup_exc).__name__
        os.umask(old_umask)


LIMITS = [
    "Digest observations immediately before/after pathname launch exclude hostile replacement races and full extracted/external runtime closure.",
    "1500s elapsed budget applies to command calls including spawn/setup; shared downloads use bounded bytes/per-socket timeouts; the outer35min hosted step remains the final disposal boundary.",
    "Ubuntu24.04 x86_64 DEB only; RPM/AppImage/ARM/legacy/other operating system transitions remain unproved.",
    "Actual prior native decrypts v2; rollback restores encrypted pre-upgrade v2 to a fresh sibling, never candidate v3 into old native.",
    "Pinned wheel assists synthetic seeding/semantic equality; native installed CLI must perform actual state and vault reads.",
    "No automatic updater/in-place format downgrade, publisher trust, independent license approval, default XDG/GUI/plugin runtime certification.",
    "Leader exit/timeout is not process-tree cleanup proof; private output and remaining descendants rely on disposable hosted VM disposal.",
    "Environment host assertions prevent accidental local execution; independent matching GitHub run/job metadata is required to corroborate receipts.",
]

# Generated from verified small metadata. The config must match this literal;
# replacing arbitrary pins through a command-line path is unsupported.
EXPECTED_PINS = '{"assets":[{"browser_download_url":"https://github.com/Yunushan/remote-ops-workspace/releases/download/v1.0.24/remote-ops-workspace-v1.0.24-linux-amd64.deb","digest":"sha256:d64ef85359085440798b86515c4751e73ef2633a3cd761f93b6d168d4a8456af","id":544041417,"name":"remote-ops-workspace-v1.0.24-linux-amd64.deb","size":27817068},{"browser_download_url":"https://github.com/Yunushan/remote-ops-workspace/releases/download/v1.0.24/remote-ops-workspace-v1.0.24-linux-x86_64-native-manifest.json","digest":"sha256:06e92c851821df92206ca6236894babc96282e113ada03595c289663922008f5","id":544041401,"name":"remote-ops-workspace-v1.0.24-linux-x86_64-native-manifest.json","size":2533},{"browser_download_url":"https://github.com/Yunushan/remote-ops-workspace/releases/download/v1.0.24/remote-ops-workspace-v1.0.24-linux-x86_64-native-SHA256SUMS.txt","digest":"sha256:54abddbf16b774dba6f8935f99dcae364af231c75a0f5e4466e4e54628f0ab69","id":544041409,"name":"remote-ops-workspace-v1.0.24-linux-x86_64-native-SHA256SUMS.txt","size":591},{"browser_download_url":"https://github.com/Yunushan/remote-ops-workspace/releases/download/v1.0.24/remote_ops_workspace-1.0.24-py3-none-any.whl","digest":"sha256:9fe56c3b4f09365cdc7a21249a41b9b60d5944f2ce0f596f9b45443184db585e","id":544041398,"name":"remote_ops_workspace-1.0.24-py3-none-any.whl","size":542385}],"published_at":"2026-09-04T08:39:52Z","release_id":382583184,"repository":"Yunushan/remote-ops-workspace","schema":"row.previous-native-release-pins.v1","tag":"v1.0.24","tag_commit":"2165989ca9f3ffbd59a8f27a296cda3fb295a404"}'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("plan", "run"), default="plan")
    parser.add_argument("--candidate-source-sha", default="")
    args = parser.parse_args(argv)
    if args.action == "plan":
        print(
            json.dumps(
                {"schema": SCHEMA, "status": "plan-only", "plan": PLAN, "limits": LIMITS}, indent=2
            )
        )
        return 0
    args.authorized, args.phase, args.drill = False, "runner-gate", None
    try:
        report = run(args)
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as exc:
        report = {
            "schema": SCHEMA,
            "status": "failed",
            "phase": args.phase,
            "failure_type": type(exc).__name__,
            "failure_code": str(exc)
            if isinstance(exc, EvidenceError)
            else "private-fixture-or-evidence-failure",
            "scope": "unreleased-hosted-linux-deb-transition",
            "limits": LIMITS,
        }
        if args.drill is not None:
            report.update(
                cleanup=args.drill.cleanup,
                commands=args.drill.commands.calls,
                native_probes=args.drill.probes,
            )
        if args.authorized:
            save(ROOT / REPORT, report)
        print(
            "native Linux transition refused or failed; no private command output published",
            file=sys.stderr,
        )
        return 1
    save(ROOT / REPORT, report)
    print(
        "native Linux DEB upgrade/operator rollback passed; process-tree disposal boundary remains"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
