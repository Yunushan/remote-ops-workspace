"""Record glibc's library selections during offline workloads of an installed DEB."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.linux_frozen_elf import archive_elf_members  # noqa: E402
from scripts.linux_frozen_runpaths import TOOLCACHE_LIB  # noqa: E402

DEBIAN_ARCHITECTURES = {
    "linux-x86_64": "amd64",
    "linux-aarch64": "arm64",
    "linux-i386": "i386",
    "linux-armhf": "armhf",
}
SYSTEM_LIBRARY_ROOTS = (Path("/lib"), Path("/lib64"), Path("/usr/lib"), Path("/usr/lib64"))
GLIBC_TRY = re.compile(r"^[ \t]*\d+:[ \t]+trying file=([^\r\n]+)", re.MULTILINE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def selections(logs: list[Path], temporary: Path, members: dict[str, str]) -> dict:
    bundled = {}
    host = {}
    attempted_archive = set()
    attempted_host = set()
    for trace in logs:
        if trace.stat().st_size > 8 * 1024**2:
            raise ValueError("Unexpected glibc trace size")
        text = trace.read_text(encoding="utf-8")
        if re.search(TOOLCACHE_LIB.pattern + rb"(?=[:/\s)\]]|$)", text.encode()):
            raise ValueError("glibc searched or loaded a hosted toolcache path")
        for name in GLIBC_TRY.findall(text):
            path = Path(os.path.normpath(name.strip()))
            if path.is_relative_to(temporary):
                relative = path.relative_to(temporary)
                if len(relative.parts) >= 2 and relative.parts[0].startswith("_MEI"):
                    attempted_archive.add("/".join(relative.parts[1:]))
                    continue
            elif any(path.is_relative_to(root) for root in SYSTEM_LIBRARY_ROOTS):
                attempted_host.add(path.as_posix())
                continue
            raise ValueError(f"Unexpected glibc library search path: {name}")
        for name in re.findall(r"^\s*\d+:\s+calling init:\s+(\S.*?)\s*$", text, re.MULTILINE):
            path = Path(name)
            if path.is_relative_to(temporary):
                relative = path.relative_to(temporary)
                if len(relative.parts) < 2 or not relative.parts[0].startswith("_MEI"):
                    raise ValueError(f"Unexpected temporary library: {name}")
                member = "/".join(relative.parts[1:])
                if member not in members:
                    raise ValueError(f"Loaded library absent from the frozen archive: {member}")
                bundled[member] = members[member]
            elif path.is_absolute() and path.parts[1:2] in {("lib",), ("lib64",), ("usr",)}:
                actual = path.resolve(strict=True)
                if not any(
                    actual.is_relative_to(root) for root in SYSTEM_LIBRARY_ROOTS
                ):
                    raise ValueError(f"Unexpected host library: {name}")
                if path.name in members and path.name != "libz.so.1":
                    raise ValueError(
                        f"Host supplied a library present in the extraction root: {name}"
                    )
                host[str(path)] = sha256(actual)
            else:
                raise ValueError(f"Unknown glibc library origin: {name}")
    return {
        "archive_members": dict(sorted(bundled.items())),
        "host_files": dict(sorted(host.items())),
        "attempted_paths": {"extraction": sorted(attempted_archive), "host": sorted(attempted_host)},
    }


def qualify(
    executable: Path, deb: Path, target: str, source_sha: str | None, staged_report: Path | None
) -> dict:
    arch = DEBIAN_ARCHITECTURES[target]
    if subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip() != arch:
        raise ValueError("Debian userland architecture does not match the qualification target")
    if (
        subprocess.check_output(["dpkg-deb", "-f", str(deb), "Architecture"], text=True).strip()
        != arch
    ):
        raise ValueError("Debian package architecture does not match the qualification target")
    probes = {}
    with tempfile.TemporaryDirectory(prefix="row-loader-") as stage:
        work = Path(stage).resolve()
        package = work / "deb"
        subprocess.run(["dpkg-deb", "-x", str(deb), str(package)], check=True, timeout=60)
        exact = sha256(executable)
        if exact != sha256(package / "usr/bin/row"):
            raise ValueError("Installed launcher does not match the packaged launcher")
        members = {
            name: hashlib.sha256(raw).hexdigest() for name, raw in archive_elf_members(executable)
        }
        changes = None
        if staged_report is not None:
            changes = json.loads(staged_report.read_bytes())
            for member, change in changes.items():
                if (
                    change["staged_sha256"] != members.get(member)
                    or change["input_sha256"] == change["staged_sha256"]
                ):
                    raise ValueError(
                        f"Staged RUNPATH change does not match the packaged ELF member: {member}"
                    )
        home = work / "home"
        home.mkdir(mode=0o700)
        for name, args in (
            ("version", ["--version"]),
            ("platforms", ["platforms", "--json"]),
            ("vault-init", ["vault", "init"]),
        ):
            trace = work / name
            env = {
                "HOME": str(home),
                "ROW_HOME": str(home / "state"),
                "TMPDIR": str(work),
                "PATH": "/usr/bin:/bin",
                "LC_ALL": "C",
                "LD_DEBUG": "libs",
                "LD_DEBUG_OUTPUT": str(trace),
                "ROW_VAULT_PASSWORD": secrets.token_urlsafe(32),
            }
            probe = subprocess.run(
                [str(executable), *args],
                env=env,
                cwd=home,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=60,
                check=True,
            )
            if name == "platforms" and not json.loads(probe.stdout):
                raise ValueError("Empty platform inventory")
            loaded = selections(sorted(work.glob(name + ".*")), work, members)
            names = set(loaded["archive_members"])
            host_names = {Path(p).name for p in loaded["host_files"]}
            if (
                not {"libc.so.6", "libz.so.1"} <= host_names
                or "libz.so.1" not in names
                or not any(n.startswith("libpython") for n in names)
                or not all(loaded["attempted_paths"].values())
            ):
                raise ValueError(
                    f"Incomplete host/bootstrap or extracted-Python glibc trace for {name}"
                )
            if name == "vault-init" and not any(
                n.startswith("cryptography/") and "_rust." in n for n in names
            ):
                raise ValueError("Vault workload did not load the packaged cryptography extension")
            probes[name] = loaded
    return {
        "schema_version": 1,
        "scope": "Observed glibc library lookups and initializations for three offline CLI workloads. "
        "Lookup paths may be absent. Archive hashes identify packaged member bytes. "
        "Host hashes identify the observed filesystem providers."
        + (" Installed-package inspection without a build-time staging report." if staged_report is None else ""),
        "target": target,
        "kernel_machine": platform.machine(),
        "glibc": os.confstr("CS_GNU_LIBC_VERSION"),
        "deb": deb.name,
        "deb_sha256": sha256(deb),
        "launcher_sha256": exact,
        "staged_runpath_changes": changes,
        "source_sha": source_sha,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "probes": probes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=DEBIAN_ARCHITECTURES, required=True)
    parser.add_argument("--deb", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-sha")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged-elf-report", type=Path, help="validate the packaging build's ELF report")
    mode.add_argument("--inspect-installed", action="store_true", help="inspect an installed DEB without a build report")
    args = parser.parse_args()
    if args.source_sha and not re.fullmatch("[0-9a-f]{40}", args.source_sha):
        parser.error("--source-sha must be a complete Git commit ID")
    result = qualify(
        args.executable.resolve(),
        args.deb.resolve(),
        args.target,
        args.source_sha or None,
        args.staged_elf_report,
    )
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
