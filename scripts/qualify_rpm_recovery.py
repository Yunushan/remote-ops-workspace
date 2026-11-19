"""Exercise an exact x86-64 RPM upgrade and rollback in an offline container."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

PACKAGE = "remote-ops-workspace"
ARCH = "x86_64"
ROW = Path("/usr/bin/row")
RPM = "/usr/bin/rpm"
RPM_QUERY = r"%{NAME}\t%{EPOCHNUM}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\t%{FILEDIGESTALGO}\n[%{FILENAMES}\t%{FILEDIGESTS}\n]"
SHA256 = re.compile(r"[0-9a-f]{64}")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C.UTF-8", "HOME": "/root"}
ORIGINAL = "rollback-original"
ADDED = "candidate-only"


@dataclass(frozen=True)
class RPMIdentity:
    version: str
    release: str
    architecture: str
    package_sha256: str
    launcher_sha256: str


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(*args: str | Path, env: dict[str, str] = ENV) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def checked(step: str, *args: str | Path, env: dict[str, str] = ENV) -> str:
    result = run(*args, env=env)
    if result.returncode:
        raise RuntimeError(f"{step} failed with exit code {result.returncode}")
    return result.stdout.strip()


def parse_identity(query: str, package_sha256: str) -> RPMIdentity:
    header, _, files = query.partition("\n")
    name, epoch, version, release, architecture, digest_algorithm = header.split("\t")
    if (
        (name, epoch, architecture, digest_algorithm) != (PACKAGE, "0", ARCH, "8")
        or not VERSION.fullmatch(version)
        or not re.fullmatch(r"1(?:\.[A-Za-z0-9_]+)*", release)
    ):
        raise ValueError("Unexpected RPM header identity")
    digests = [
        digest
        for path, _, digest in (line.partition("\t") for line in files.splitlines())
        if path == ROW.as_posix()
    ]
    if len(digests) != 1 or not SHA256.fullmatch(digests[0]):
        raise ValueError("Missing or ambiguous SHA-256 for the packaged launcher")
    return RPMIdentity(version, release, architecture, package_sha256, digests[0])


def read_package(path: Path, expected: str) -> RPMIdentity:
    if not SHA256.fullmatch(expected) or sha256(path) != expected:
        raise ValueError("RPM does not match the expected SHA-256")
    identity = parse_identity(
        checked("RPM metadata query", RPM, "-qp", "--qf", RPM_QUERY, path), expected
    )
    if path.name != f"{PACKAGE}-v{identity.version}-linux-{ARCH}.rpm":
        raise ValueError("RPM filename does not match its header")
    return identity


def validate_container() -> None:
    if (
        sys.platform != "linux"
        or os.geteuid() != 0
        or not Path("/.dockerenv").is_file()
        or {entry.name for entry in Path("/sys/class/net").iterdir()} != {"lo"}
    ):
        raise RuntimeError("Run in a fresh root Docker container with --network none")
    if checked("RPM architecture query", RPM, "--eval", "%{_arch}") != ARCH:
        raise RuntimeError("Use an x86-64 container for this drill")
    query = run(RPM, "--query", PACKAGE)
    if (
        query.returncode != 1
        or query.stdout.strip() != f"package {PACKAGE} is not installed"
        or ROW.exists()
        or ROW.is_symlink()
    ):
        raise RuntimeError(
            "The container needs a healthy RPM database and no existing ROW installation"
        )


def verify_installed(expected: RPMIdentity) -> None:
    identity = parse_identity(
        checked("Installed RPM ownership query", RPM, "-qf", "--qf", RPM_QUERY, ROW),
        expected.package_sha256,
    )
    if identity != expected or ROW.is_symlink() or sha256(ROW) != expected.launcher_sha256:
        raise RuntimeError("The RPM owner or installed launcher bytes differ from the input")
    if checked("Installed version query", ROW, "--version") != f"{PACKAGE} {expected.version}":
        raise RuntimeError("The launcher reported an unexpected version")


def extract_rescue(package: Path, expected: RPMIdentity, root: Path) -> Path:
    # The predecessor can read the workspace but predates the backup command.
    # Retain one file from the verified candidate without installing the RPM.
    archive = root / "candidate.tar"
    with package.open("rb") as source, archive.open("xb") as target:
        result = subprocess.run(
            ["/usr/bin/rpm2archive", "-n", "-"],
            env=ENV,
            stdin=source,
            stdout=target,
            stderr=subprocess.DEVNULL,
            timeout=180,
            check=False,
        )
    if result.returncode:
        raise RuntimeError("Candidate archive conversion failed")
    rescue = root / "row-rescue"
    with tarfile.open(archive, mode="r:") as payload:
        launchers = [entry for entry in payload.getmembers() if entry.name == f".{ROW.as_posix()}"]
        if len(launchers) != 1 or not launchers[0].isfile():
            raise ValueError("Candidate archive must contain one regular launcher")
        with payload.extractfile(launchers[0]) as source, rescue.open("xb") as target:
            shutil.copyfileobj(source, target)
    archive.unlink()
    if sha256(rescue) != expected.launcher_sha256 or sha256(package) != expected.package_sha256:
        raise RuntimeError("Candidate launcher or package digest mismatch after extraction")
    rescue.chmod(0o700)
    return rescue


def seed(env: dict[str, str], name: str, secret: str) -> None:
    checked(
        "Create SSH profile",
        ROW,
        "profile",
        "add",
        "--name",
        name,
        "--protocol",
        "ssh",
        "--host",
        f"{name}.invalid",
        "--group",
        "recovery",
        env=env,
    )
    checked(
        "Save synthetic vault secret",
        ROW,
        "vault",
        "set",
        name,
        "--secret-env",
        "ROW_RPM_DRILL_SECRET",
        env={**env, "ROW_RPM_DRILL_SECRET": secret},
    )


def verify_workspace(root: Path, env: dict[str, str], expected: dict[str, str]) -> None:
    profiles = json.loads(checked("Read SSH profiles", ROW, "profile", "list", "--json", env=env))
    actual = sorted((row["name"], row["protocol"], row["host"], row["group"]) for row in profiles)
    if actual != [(name, "ssh", f"{name}.invalid", "recovery") for name in sorted(expected)]:
        raise RuntimeError("Installed CLI returned different profiles")
    if checked("List vault entries", ROW, "vault", "list", env=env).splitlines() != sorted(
        expected
    ):
        raise RuntimeError("Installed CLI returned different vault entries")
    for name, secret in expected.items():
        destination = root / "private-vault-readback"
        try:
            checked(
                "Read synthetic vault secret",
                ROW,
                "vault",
                "get",
                name,
                "--out",
                destination,
                env=env,
            )
            if destination.read_text(encoding="utf-8") != secret:
                raise RuntimeError("Installed CLI returned a different decrypted value")
        finally:
            destination.unlink(missing_ok=True)


def state_digests(home: Path) -> dict[str, str]:
    return {name: sha256(home / name) for name in ("profiles.json", "vault.json")}


def verify_downgrade_refusal(
    result: subprocess.CompletedProcess[str], current: RPMIdentity, previous: RPMIdentity
) -> None:
    current_label = f"{PACKAGE}-{current.version}-{current.release}.{current.architecture}"
    previous_label = f"{PACKAGE}-{previous.version}-{previous.release}.{previous.architecture}"
    diagnostic = (
        f"package {current_label} (which is newer than {previous_label}) is already installed"
    )
    if result.returncode not in {1, 2} or diagnostic not in result.stderr:
        raise RuntimeError("RPM did not refuse the downgrade for the expected reason")


def drill(args: argparse.Namespace, root: Path) -> dict:
    validate_container()
    runtime = {
        "rpm_version": checked("RPM version query", RPM, "--version"),
        "distribution": platform.freedesktop_os_release()["PRETTY_NAME"],
    }
    old = read_package(args.previous_rpm, args.previous_sha256)
    new = read_package(args.candidate_rpm, args.candidate_sha256)
    if tuple(map(int, old.version.split("."))) >= tuple(map(int, new.version.split("."))):
        raise ValueError("The predecessor RPM must be older than the candidate")
    rescue = extract_rescue(args.candidate_rpm, new, root)
    home, restored, backup = root / "original", root / "restored", root / "pre-upgrade.rowbackup"
    environment = {
        **ENV,
        "HOME": str(root),
        "ROW_HOME": str(home),
        "ROW_VAULT_PASSWORD": secrets.token_urlsafe(32),
        "ROW_RECOVERY_PASSWORD": secrets.token_urlsafe(32),
    }
    first = {ORIGINAL: secrets.token_urlsafe(32)}
    upgraded = {**first, ADDED: secrets.token_urlsafe(32)}

    checked("Install predecessor", RPM, "--upgrade", args.previous_rpm)
    verify_installed(old)
    checked("Initialize vault", ROW, "vault", "init", env=environment)
    seed(environment, ORIGINAL, first[ORIGINAL])
    verify_workspace(root, environment, first)
    before = state_digests(home)
    checked(
        "Create encrypted pre-upgrade backup",
        rescue,
        "workspace",
        "backup",
        "--out",
        backup,
        "--offline",
        "--passphrase-env",
        "ROW_RECOVERY_PASSWORD",
        env=environment,
    )
    backup_hash = sha256(backup)
    if backup.stat().st_size == 0 or state_digests(home) != before:
        raise RuntimeError("Pre-upgrade backup was empty or changed the original workspace")

    checked("Upgrade to candidate", RPM, "--upgrade", args.candidate_rpm)
    verify_installed(new)
    verify_workspace(root, environment, first)
    if state_digests(home) != before:
        raise RuntimeError("The upgrade changed the pre-existing profiles or vault")
    seed(environment, ADDED, upgraded[ADDED])
    verify_workspace(root, environment, upgraded)
    after = state_digests(home)

    verify_downgrade_refusal(run(RPM, "--upgrade", args.previous_rpm), new, old)
    verify_installed(new)
    checked(
        "Restore backup into a private sibling",
        ROW,
        "workspace",
        "restore",
        "--backup",
        backup,
        "--destination",
        restored,
        "--offline",
        "--passphrase-env",
        "ROW_RECOVERY_PASSWORD",
        env=environment,
    )
    if state_digests(restored) != before or state_digests(home) != after:
        raise RuntimeError(
            "The restore changed the upgraded workspace or returned different saved bytes"
        )

    checked("Downgrade to predecessor", RPM, "--upgrade", "--oldpackage", args.previous_rpm)
    verify_installed(old)
    verify_workspace(root, {**environment, "ROW_HOME": str(restored)}, first)
    if (
        state_digests(restored) != before
        or state_digests(home) != after
        or sha256(backup) != backup_hash
        or sha256(rescue) != new.launcher_sha256
        or sha256(args.previous_rpm) != old.package_sha256
        or sha256(args.candidate_rpm) != new.package_sha256
    ):
        raise RuntimeError(
            "Rollback modified the backup, package inputs, or either saved workspace"
        )
    return {
        "schema": "remote-ops-workspace/rpm-recovery/v1",
        **runtime,
        "previous": asdict(old),
        "candidate": asdict(new),
        "backup_sha256": backup_hash,
        "backup_created_with": "verified-candidate-launcher-before-upgrade",
        "upgrade_preserved_profiles_and_vault": True,
        "downgrade_refused_without_oldpackage": True,
        "explicit_downgrade_restored_previous_launcher": True,
        "restored_profiles_and_vault_read_by_previous_launcher": True,
        "upgraded_workspace_preserved": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-rpm", required=True, type=Path)
    parser.add_argument("--previous-sha256", required=True)
    parser.add_argument("--candidate-rpm", required=True, type=Path)
    parser.add_argument("--candidate-sha256", required=True)
    args = parser.parse_args()
    try:
        with TemporaryDirectory(prefix="row-rpm-recovery-") as temp:
            receipt = drill(args, Path(temp))
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    except (KeyError, OSError, ValueError, subprocess.TimeoutExpired, tarfile.TarError) as exc:
        print(
            f"RPM recovery failed during input or runtime validation ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
