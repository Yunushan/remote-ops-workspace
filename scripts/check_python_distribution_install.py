from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SCHEMA = "row.python-distribution-install-evidence.v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install and smoke the built wheel and sdist in isolated virtual environments."
    )
    parser.add_argument("--dist-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    return parser.parse_args(argv)


def find_distribution_artifacts(dist_dir: Path) -> list[tuple[str, Path]]:
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1:
        raise ValueError(f"expected exactly one wheel in {dist_dir}, found {len(wheels)}")
    if len(sdists) != 1:
        raise ValueError(f"expected exactly one sdist in {dist_dir}, found {len(sdists)}")
    return [("wheel", wheels[0]), ("sdist", sdists[0])]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def venv_python(environment: Path) -> Path:
    return (
        environment / "Scripts" / "python.exe"
        if os.name == "nt"
        else environment / "bin" / "python"
    )


def stage_distribution_artifact(artifact: Path, root: Path) -> Path:
    """Copy a build artifact into the isolated smoke root.

    Windows build helpers can create output files with a producer-token-only ACL.
    A virtual-environment child process may then be unable to read the original
    path even though the bytes are valid.  Creating a new file under the smoke
    root makes the access boundary deterministic while the result continues to
    hash and report the original artifact.
    """

    staging = root / "artifacts" / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=True)
    source = artifact.resolve(strict=True)
    # Wheel and sdist installers parse the basename, so uniqueness belongs in
    # the parent directory rather than being prefixed to the artifact itself.
    staged = staging / source.name
    shutil.copyfile(source, staged)
    return staged


def run_checked(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        output = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        tail = "\n".join(output.splitlines()[-20:])
        raise RuntimeError(
            f"command failed with exit code {result.returncode}: {' '.join(command)}\n{tail}"
        )
    return result


def project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = re.search(r"(?ms)^\[project\]\s*(?P<body>.*?)(?=^\[|\Z)", text)
    version = re.search(
        r'^version\s*=\s*["\'](?P<version>[^"\']+)["\']\s*$',
        project.group("body") if project else "",
        re.MULTILINE,
    )
    if version is None:
        raise ValueError("pyproject.toml [project] table must declare version")
    return version.group("version")


GUI_SOURCE_MODULES = ("gui_terminal", "gui_processes", "gui_values", "terminal_output", "gui_workspace")
GUI_ARCHIVE_LIMIT = 64 * 1024 * 1024
GUI_EXPANDED_LIMIT = 128 * 1024 * 1024
GUI_SOURCE_LIMIT = 2 * 1024 * 1024
GUI_MEMBER_LIMIT = 10000


def _gui_regular_bytes(path: Path, maximum: int) -> bytes:
    """Observe bounded regular bytes and identity changes during this read.

    Repeated stat/open checks are observations, not atomic protection against a
    hostile host replacing paths. No installed/runtime closure is asserted.
    """
    import stat

    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= maximum:
        raise ValueError("gui-source-file-bound-or-type")
    fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
    shared_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    def identity(item):
        return tuple(getattr(item, key) for key in fields)
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if tuple(getattr(opened, key) for key in shared_fields) != tuple(getattr(before, key) for key in shared_fields):
            raise ValueError("gui-source-file-changed")
        raw = stream.read(before.st_size + 1)
        after_fd = os.fstat(stream.fileno())
    if len(raw) != before.st_size or identity(after_fd) != identity(opened) or identity(path.lstat()) != identity(before):
        raise ValueError("gui-source-file-changed")
    return raw


def _gui_member_alias(name: str) -> str:
    import posixpath
    import unicodedata

    if not isinstance(name, str) or not name or len(name) > 1024 or "\x00" in name:
        raise ValueError("gui-source-member-name-bound")
    normalized = posixpath.normpath(name.replace("\\", "/"))
    return unicodedata.normalize("NFC", "/".join(part.rstrip(" .") for part in normalized.split("/") if part not in {"", ".", ".."})).casefold()


def _validate_distribution_gui_sources(kind: str, artifact: Path, source_root: Path) -> dict[str, Any]:
    """Assert five literal source members, without extraction/import or closure claims."""
    import gzip
    import io
    import stat
    import struct
    import tarfile
    import zipfile

    if kind not in {"wheel", "sdist"}:
        raise ValueError("gui-source-distribution-kind")
    names = {module: f"remote_ops_workspace/{module}.py" for module in GUI_SOURCE_MODULES}
    expected = {module: _gui_regular_bytes(source_root / "src" / name, GUI_SOURCE_LIMIT) for module, name in names.items()}
    raw = _gui_regular_bytes(artifact, GUI_ARCHIVE_LIMIT)
    digest = hashlib.sha256(raw).hexdigest()
    root = "" if kind == "wheel" else artifact.name.removesuffix(".tar.gz") + "/src/"
    wanted = {root + name: module for module, name in names.items()}
    aliases = {_gui_member_alias(name): name for name in wanted}
    found: dict[str, dict[str, Any]] = {}

    def observe(name, size, regular, read_member):
        key = _gui_member_alias(name)
        canonical = aliases.get(key)
        if canonical is None:
            return
        if name != canonical or canonical in found or not regular or type(size) is not int or size != len(expected[wanted[canonical]]):
            raise ValueError("gui-source-member-missing-duplicate-type-or-size")
        content = read_member(size + 1)
        if content != expected[wanted[canonical]]:
            raise ValueError("gui-source-member-bytes-mismatch")
        found[canonical] = {"source_path": "src/" + names[wanted[canonical]], "member_path": canonical, "size": size, "sha256": hashlib.sha256(content).hexdigest()}

    if kind == "wheel":
        # Refuse ZIP64/multidisk and bound central entry count before ZipFile allocates its table.
        end = raw.rfind(b"PK\x05\x06", max(0, len(raw) - 65557))
        if end < 0 or len(raw) - end < 22:
            raise ValueError("gui-source-wheel-directory-bound")
        _, disk, directory_disk, count_disk, count, directory_size, directory_offset, comment = struct.unpack_from("<4s4H2LH", raw, end)
        if disk or directory_disk or count_disk != count or count > GUI_MEMBER_LIMIT or end + 22 + comment != len(raw) or directory_offset + directory_size != end:
            raise ValueError("gui-source-wheel-directory-bound")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) != count or sum(item.file_size for item in entries) > GUI_EXPANDED_LIMIT:
                raise ValueError("gui-source-archive-expanded-or-count-bound")
            for item in entries:
                file_type = stat.S_IFMT(item.external_attr >> 16)
                regular = not item.is_dir() and file_type in {0, stat.S_IFREG} and item.flag_bits & 1 == 0
                literal_name = item.orig_filename
                alias = _gui_member_alias(literal_name)
                if alias in aliases:
                    if not regular or literal_name != aliases[alias]:
                        raise ValueError("gui-source-member-missing-duplicate-type-or-size")
                    with archive.open(item) as stream:
                        observe(literal_name, item.file_size, regular, stream.read)
                else:
                    _gui_member_alias(literal_name)
    else:
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,199}\.tar\.gz", artifact.name) is None:
            raise ValueError("gui-source-sdist-name")
        chunks = []
        total = 0
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
            while True:
                chunk = compressed.read(min(1024 * 1024, GUI_EXPANDED_LIMIT - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > GUI_EXPANDED_LIMIT:
                    raise ValueError("gui-source-archive-expanded-or-count-bound")
                chunks.append(chunk)
        with tarfile.open(fileobj=io.BytesIO(b"".join(chunks)), mode="r:") as archive:
            declared = 0
            for index, item in enumerate(archive):
                declared += item.size
                if index >= GUI_MEMBER_LIMIT or declared > GUI_EXPANDED_LIMIT:
                    raise ValueError("gui-source-archive-expanded-or-count-bound")
                if _gui_member_alias(item.name) in aliases:
                    regular = item.type in {tarfile.REGTYPE, tarfile.AREGTYPE} and item.sparse is None
                    stream = archive.extractfile(item) if regular else None
                    if stream is None:
                        observe(item.name, item.size, False, lambda _size: b"")
                    else:
                        with stream:
                            observe(item.name, item.size, regular, stream.read)
                else:
                    _gui_member_alias(item.name)
    if set(found) != set(wanted):
        raise ValueError("gui-source-required-member-missing")
    if _gui_regular_bytes(artifact, GUI_ARCHIVE_LIMIT) != raw or any(_gui_regular_bytes(source_root / "src" / names[module], GUI_SOURCE_LIMIT) != expected[module] for module in names):
        raise ValueError("gui-source-input-changed")
    return {"scope": "five literal Python source members only; no imports, extraction, compiled-code equality, runtime closure or approval", "artifact_sha256": digest, "members": [found[name] for name in sorted(found)], "passed": True}


def validate_distribution_gui_sources(kind: str, artifact: Path, source_root: Path) -> dict[str, Any]:
    """Keep archive-parser failures bounded without exposing archive diagnostics."""
    import struct
    import tarfile
    import zipfile
    import zlib

    try:
        return _validate_distribution_gui_sources(kind, artifact, source_root)
    except (EOFError, UnicodeError, RuntimeError, NotImplementedError, struct.error, tarfile.TarError, zipfile.BadZipFile, zlib.error):
        raise ValueError("gui-source-archive-malformed") from None


def smoke_distribution(
    kind: str,
    artifact: Path,
    *,
    expected_version: str,
    timeout_seconds: int,
    root: Path,
) -> dict[str, Any]:
    source_members = validate_distribution_gui_sources(kind, artifact, ROOT)
    environment = root / kind
    staged_artifact = stage_distribution_artifact(artifact, root)
    staged_members = validate_distribution_gui_sources(kind, staged_artifact, ROOT)
    if staged_members != source_members:
        raise ValueError("gui-source-staged-input-changed")
    command_env = os.environ.copy()
    command_env.pop("PYTHONPATH", None)
    command_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    command_env["PIP_NO_CACHE_DIR"] = "1"
    command_env["ROW_HOME"] = str(root / f"{kind}-row-home")
    run_checked(
        [sys.executable, "-m", "venv", str(environment)],
        cwd=ROOT,
        env=command_env,
        timeout_seconds=timeout_seconds,
    )
    python = venv_python(environment)
    if sha256_file(staged_artifact) != source_members["artifact_sha256"]:
        raise ValueError("gui-source-staged-input-changed")

    run_checked(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-cache-dir",
            str(staged_artifact.resolve()),
        ],
        cwd=root,
        env=command_env,
        timeout_seconds=timeout_seconds,
    )
    run_checked(
        [str(python), "-m", "pip", "check"],
        cwd=root,
        env=command_env,
        timeout_seconds=timeout_seconds,
    )
    probe_source = (
        "import importlib.metadata as metadata, json, pathlib, platform, sys; "
        "import remote_ops_workspace as package; "
        "from remote_ops_workspace.features import feature_manifest_path; "
        "from remote_ops_workspace.paths import runtime_web_dir; "
        "manifest = feature_manifest_path(); web = runtime_web_dir(); "
        "assert manifest.is_file(), manifest; assert web.is_dir(), web; "
        "print(json.dumps({'distribution_version': metadata.version('remote-ops-workspace'), "
        "'package_version': package.__version__, 'python_version': platform.python_version(), "
        "'releaselevel': sys.version_info.releaselevel, "
        "'feature_manifest': str(manifest), 'web_dir': str(web)}, sort_keys=True))"
    )
    probe = run_checked(
        [str(python), "-I", "-c", probe_source],
        cwd=root,
        env=command_env,
        timeout_seconds=timeout_seconds,
    )
    probe_payload = json.loads(probe.stdout.strip())
    for key in ("distribution_version", "package_version"):
        if probe_payload.get(key) != expected_version:
            raise RuntimeError(
                f"{kind} installed {key}={probe_payload.get(key)!r}, expected {expected_version!r}"
            )
    feature_smoke = run_checked(
        [
            str(python),
            "-I",
            "-m",
            "remote_ops_workspace",
            "features",
            "--coverage",
            "--json",
        ],
        cwd=root,
        env=command_env,
        timeout_seconds=timeout_seconds,
    )
    coverage_payload = json.loads(feature_smoke.stdout)
    required_sections = {
        "adapter_ready_coverage",
        "evidence_summary",
        "feature_family_mapping",
        "platform_verified_readiness",
        "production_parity_coverage",
    }
    missing_sections = sorted(required_sections - set(coverage_payload))
    if missing_sections:
        raise RuntimeError(
            f"{kind} feature coverage smoke missing sections: {', '.join(missing_sections)}"
        )
    if validate_distribution_gui_sources(kind, artifact, ROOT) != source_members or sha256_file(staged_artifact) != source_members["artifact_sha256"]:
        raise ValueError("gui-source-input-changed")
    return {
        "gui_source_members": source_members,
        "kind": kind,
        "filename": artifact.name,
        "bytes": artifact.stat().st_size,
        "sha256": sha256_file(artifact),
        "probe": probe_payload,
        "feature_coverage_sha256": hashlib.sha256(
            feature_smoke.stdout.encode("utf-8")
        ).hexdigest(),
        "passed": True,
    }


def write_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    expected_version = project_version()
    results: list[dict[str, Any]] = []
    try:
        artifacts = find_distribution_artifacts(args.dist_dir)
        temporary_parent = ROOT / ".tmp"
        temporary_parent.mkdir(parents=True, exist_ok=True)
        root = temporary_parent / f"row-python-dist-smoke-{uuid.uuid4().hex}"
        try:
            for kind, artifact in artifacts:
                results.append(
                    smoke_distribution(
                        kind,
                        artifact,
                        expected_version=expected_version,
                        timeout_seconds=args.timeout_seconds,
                        root=root,
                    )
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)
        payload = {
            "schema": EVIDENCE_SCHEMA,
            "expected_project_version": expected_version,
            "producer_python": {
                "executable": sys.executable,
                "version": sys.version,
            },
            "artifacts": results,
            "passed": True,
        }
        write_evidence(args.out, payload)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError, EOFError) as exc:
        payload = {
            "schema": EVIDENCE_SCHEMA,
            "expected_project_version": expected_version,
            "artifacts": results,
            "passed": False,
            "error": str(exc),
        }
        write_evidence(args.out, payload)
        print(f"Python distribution install: {exc}", file=sys.stderr)
        return 1
    print(
        "Python distribution install passed: "
        + ", ".join(result["filename"] for result in results)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
