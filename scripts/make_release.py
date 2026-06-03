#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
NAME = "remote-ops-workspace"
RELEASE_TOOLCHAIN = ROOT / "configs" / "release_toolchain.json"
DEFAULT_SOURCE_DATE_EPOCH = 1_704_067_200  # 2024-01-01T00:00:00Z
MIN_ZIP_EPOCH = 315_532_800  # 1980-01-01T00:00:00Z
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:a\d+|b\d+|rc\d+|\.post\d+)?$")

PROJECT_FILES = [
    ".github",
    "apps",
    "configs",
    "docker",
    "docs",
    "installers",
    "scripts",
    "src",
    "tests",
    ".gitignore",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "Makefile",
    "NOTICE",
    "README.md",
    "README.tr.md",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements-release.txt",
    "requirements.txt",
    "SECURITY.md",
]

WEB_FILES = [
    "apps/web/app.js",
    "apps/web/index.html",
    "apps/web/manifest.json",
    "apps/web/styles.css",
    "apps/web/sw.js",
    "LICENSE",
    "NOTICE",
]

EXCLUDED_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}


@dataclass(frozen=True)
class ReleaseTarget:
    key: str
    label: str
    suffix: str
    archive_format: str
    install_command: str
    notes: tuple[str, ...]
    web_only: bool = False


TARGETS = [
    ReleaseTarget(
        key="source",
        label="Portable source bundle",
        suffix="source",
        archive_format="zip",
        install_command='python -m pip install -e ".[desktop,security]"',
        notes=(
            "Full source archive for packagers, contributors, and custom deployments.",
            "Includes tests, CI metadata, docs, installers, the CLI/GUI code, and the Web/PWA shell.",
        ),
    ),
    ReleaseTarget(
        key="windows",
        label="Windows",
        suffix="windows",
        archive_format="zip",
        install_command=r".\installers\install.ps1",
        notes=(
            "Targets Windows 10/11 and Windows Server 2012-2025 for modern local installs.",
            "Windows 8.1/8/7/Vista/XP are documented as best-effort source or remote-target tiers.",
            "Includes PowerShell and batch installers.",
            "Protocol sessions use system tools such as OpenSSH, MSTSC, PuTTY, VcXsrv, and VNC clients.",
        ),
    ),
    ReleaseTarget(
        key="linux",
        label="Linux",
        suffix="linux",
        archive_format="tar.gz",
        install_command="./installers/install.sh",
        notes=(
            "Targets Linux CLI, GUI, and Web/PWA deployments.",
            "Native package scripts map i386/i686, x86_64/amd64, armv7l/armhf, and aarch64/arm64 when run on matching builders.",
            "Protocol sessions use system tools such as OpenSSH, FreeRDP, TigerVNC, Remmina-compatible clients, and Xorg.",
        ),
    ),
    ReleaseTarget(
        key="macos",
        label="macOS",
        suffix="macos",
        archive_format="tar.gz",
        install_command="./installers/install.sh",
        notes=(
            "Targets macOS Intel and Apple Silicon.",
            "Protocol sessions use system tools such as OpenSSH, XQuartz, Microsoft Remote Desktop/FreeRDP, and VNC clients.",
        ),
    ),
    ReleaseTarget(
        key="bsd",
        label="BSD",
        suffix="bsd",
        archive_format="tar.gz",
        install_command="./installers/install.sh",
        notes=(
            "Targets FreeBSD, OpenBSD, NetBSD, and DragonFlyBSD.",
            "CLI and Web/PWA are first-class; GUI support depends on local Python/Qt packages.",
        ),
    ),
    ReleaseTarget(
        key="solaris",
        label="Solaris/illumos",
        suffix="solaris",
        archive_format="tar.gz",
        install_command="./installers/install.sh",
        notes=(
            "Targets Solaris and illumos environments with Python 3.10+.",
            "CLI and Web/PWA are first-class; GUI support depends on local Python/Qt packages.",
        ),
    ),
    ReleaseTarget(
        key="android",
        label="Android/Termux",
        suffix="android-termux",
        archive_format="tar.gz",
        install_command="./installers/install-termux.sh",
        notes=(
            "Targets Android ARMv7 and ARM64 through Termux CLI and browser/PWA workflows.",
            "The Termux installer uses the security extra and OpenSSH-oriented tools.",
        ),
    ),
    ReleaseTarget(
        key="web",
        label="Web/PWA",
        suffix="web-pwa",
        archive_format="zip",
        install_command="Serve the extracted static files with any web server.",
        notes=(
            "Static Web/PWA bundle for internal portals, static hosting, and browser/mobile workflows.",
            "No Python runtime is required for this asset unless you choose to serve it with Python.",
        ),
        web_only=True,
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build release archives for supported targets.")
    parser.add_argument(
        "--target",
        action="append",
        choices=[target.key for target in TARGETS],
        help="Build only the selected target. May be passed more than once.",
    )
    parser.add_argument(
        "--dist",
        type=Path,
        default=DIST,
        help="Output directory for generated release artifacts.",
    )
    parser.add_argument(
        "--skip-python-package",
        action="store_true",
        help="Skip Phase 1 Python wheel and sdist artifacts.",
    )
    args = parser.parse_args()

    version = read_project_version()
    validate_github_tag(version)
    dist = resolve_dist(args.dist)
    reset_dist(dist)

    selected = [target for target in TARGETS if not args.target or target.key in args.target]
    artifacts: list[dict[str, object]] = []
    if not args.skip_python_package:
        artifacts.extend(build_python_package(version, dist))
    artifacts.extend(build_target(target, version, dist) for target in selected)
    manifest = write_manifest(version, artifacts, dist)
    checksums = write_checksums(version, artifacts, ROOT / manifest, dist)

    for artifact in artifacts:
        print(f"created {artifact['file']}")
    print(f"created {manifest}")
    print(f"created {checksums}")
    return 0


def read_project_version() -> str:
    pyproject = ROOT / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("pyproject.toml does not define project.version")
    version = match.group(1)
    validate_version(version)
    return version


def validate_version(version: str) -> None:
    if not VERSION_RE.fullmatch(version):
        raise SystemExit(f"project version must be release-like semantic version, got: {version!r}")


def validate_github_tag(version: str) -> None:
    tag = os.environ.get("GITHUB_REF_NAME")
    if tag and tag != f"v{version}":
        raise SystemExit(f"GITHUB_REF_NAME={tag!r} does not match project version v{version}")


def resolve_dist(path: Path) -> Path:
    dist = path.resolve()
    root = ROOT.resolve()
    if dist == root:
        raise SystemExit("--dist must not be the repository root")
    if dist == Path.home().resolve():
        raise SystemExit("--dist must not be the current user's home directory")
    if root not in dist.parents:
        raise SystemExit("--dist must be inside the repository")
    return dist


def reset_dist(dist: Path) -> None:
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)


def build_python_package(version: str, dist: Path) -> list[dict[str, object]]:
    build_metadata = [ROOT / "build", ROOT / "src" / "remote_ops_workspace.egg-info"]
    existing_metadata = {path for path in build_metadata if path.exists()}

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                "--sdist",
                "--wheel",
                "--outdir",
                str(dist),
            ],
            cwd=ROOT,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"python package build failed with exit code {exc.returncode}") from exc
    finally:
        cleanup_generated_metadata(build_metadata, existing_metadata)

    wheel = dist / f"remote_ops_workspace-{version}-py3-none-any.whl"
    sdist = dist / f"remote_ops_workspace-{version}.tar.gz"
    missing = [path.name for path in (wheel, sdist) if not path.exists()]
    if missing:
        raise SystemExit(f"python package build did not create expected artifacts: {', '.join(missing)}")

    return [
        artifact_record(
            phase="phase-1-python-package",
            target="python-wheel",
            label="Python wheel",
            path=wheel,
            format="whl",
            install_command=f"python -m pip install {wheel.name}",
            notes=[
                "Phase 1 package artifact for Python users and package indexes.",
                "Installs the CLI package; optional GUI/security extras still depend on target platform dependencies.",
            ],
        ),
        artifact_record(
            phase="phase-1-python-package",
            target="python-sdist",
            label="Python source distribution",
            path=sdist,
            format="sdist",
            install_command=f"python -m pip install {sdist.name}",
            notes=[
                "Phase 1 source distribution for Python build backends and package indexes.",
                "Useful for reproducible package publication and downstream repackaging.",
            ],
        ),
    ]


def cleanup_generated_metadata(paths: Iterable[Path], existing_paths: set[Path]) -> None:
    for path in paths:
        if path in existing_paths or not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def build_target(target: ReleaseTarget, version: str, dist: Path) -> dict[str, object]:
    root_name = f"{NAME}-v{version}-{target.suffix}"
    output = dist / f"{root_name}.{target.archive_format}"
    files = WEB_FILES if target.web_only else PROJECT_FILES
    release_note = render_target_readme(target, version)

    if target.archive_format == "zip":
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            add_files_to_zip(archive, files, root_name, web_only=target.web_only)
            add_text_to_zip(archive, f"{root_name}/RELEASE_TARGET.md", release_note)
    elif target.archive_format == "tar.gz":
        with output.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=source_date_epoch()) as gz:
                with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    add_files_to_tar(archive, files, root_name, web_only=target.web_only)
                    add_text_to_tar(archive, f"{root_name}/RELEASE_TARGET.md", release_note)
    else:
        raise ValueError(f"unsupported archive format: {target.archive_format}")

    return artifact_record(
        phase="target-source-install-bundle",
        target=target.key,
        label=target.label,
        path=output,
        format=target.archive_format,
        install_command=target.install_command,
        notes=list(target.notes),
    )


def iter_project_paths(entries: Iterable[str], *, web_only: bool) -> Iterable[tuple[Path, str]]:
    for entry in entries:
        path = ROOT / entry
        if not path.exists():
            raise SystemExit(f"release input missing: {entry}")
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if should_skip(child):
                    continue
                if child.is_symlink():
                    raise SystemExit(f"release input must not be a symlink: {child.relative_to(ROOT)}")
                if child.is_file():
                    yield child, archive_name(child, web_only=web_only)
        elif path.is_file() and not should_skip(path):
            if path.is_symlink():
                raise SystemExit(f"release input must not be a symlink: {entry}")
            yield path, archive_name(path, web_only=web_only)


def archive_name(path: Path, *, web_only: bool) -> str:
    relative = path.relative_to(ROOT)
    if web_only and relative.parts[:2] == ("apps", "web"):
        return str(Path(*relative.parts[2:])).replace("\\", "/")
    return str(relative).replace("\\", "/")


def should_skip(path: Path) -> bool:
    return any(part in EXCLUDED_NAMES or part.endswith(".egg-info") for part in path.relative_to(ROOT).parts)


def add_files_to_zip(
    archive: zipfile.ZipFile,
    entries: Iterable[str],
    root_name: str,
    *,
    web_only: bool,
) -> None:
    for source, relative in iter_project_paths(entries, web_only=web_only):
        destination = f"{root_name}/{relative}"
        info = zipfile.ZipInfo(destination, date_time=zip_datetime())
        info.create_system = 3
        mode = 0o755 if source.suffix == ".sh" else 0o644
        info.external_attr = mode << 16
        with source.open("rb") as handle:
            archive.writestr(info, handle.read(), compress_type=zipfile.ZIP_DEFLATED)


def add_files_to_tar(
    archive: tarfile.TarFile,
    entries: Iterable[str],
    root_name: str,
    *,
    web_only: bool,
) -> None:
    for source, relative in iter_project_paths(entries, web_only=web_only):
        destination = f"{root_name}/{relative}"
        info = archive.gettarinfo(str(source), arcname=destination)
        normalize_tar_info(info, executable=source.suffix == ".sh")
        with source.open("rb") as handle:
            archive.addfile(info, handle)


def add_text_to_zip(archive: zipfile.ZipFile, arcname: str, text: str) -> None:
    info = zipfile.ZipInfo(arcname, date_time=zip_datetime())
    info.create_system = 3
    info.external_attr = 0o644 << 16
    archive.writestr(info, text, compress_type=zipfile.ZIP_DEFLATED)


def add_text_to_tar(archive: tarfile.TarFile, arcname: str, text: str) -> None:
    encoded = text.encode("utf-8")
    info = tarfile.TarInfo(arcname)
    info.size = len(encoded)
    normalize_tar_info(info)
    archive.addfile(info, fileobj=BytesReader(encoded))


def normalize_tar_info(info: tarfile.TarInfo, *, executable: bool = False) -> None:
    info.mtime = source_date_epoch()
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o755 if executable else 0o644


def source_date_epoch() -> int:
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        return DEFAULT_SOURCE_DATE_EPOCH
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit("SOURCE_DATE_EPOCH must be an integer Unix timestamp") from exc
    if value < 0:
        raise SystemExit("SOURCE_DATE_EPOCH must not be negative")
    return value


def zip_datetime() -> tuple[int, int, int, int, int, int]:
    epoch = max(source_date_epoch(), MIN_ZIP_EPOCH)
    return datetime.fromtimestamp(epoch, tz=timezone.utc).timetuple()[:6]


def artifact_record(**values: object) -> dict[str, object]:
    path = Path(values.pop("path"))
    record = dict(values)
    record["file"] = path.relative_to(ROOT).as_posix()
    record.update(file_integrity(path))
    return record


def file_integrity(path: Path) -> dict[str, object]:
    return {
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BytesReader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def render_target_readme(target: ReleaseTarget, version: str) -> str:
    notes = "\n".join(f"- {note}" for note in target.notes)
    return f"""# {target.label} release

Package: {NAME}
Version: v{version}
Target: {target.label}

## Install or run

```text
{target.install_command}
```

## Notes

{notes}

Remote Ops Workspace is an adapter-first project. Release assets include the
application code, target-specific installer entry points, docs, and the static
Web/PWA shell. Native protocol rendering still depends on the external clients
available on the target system.
"""


def write_manifest(version: str, artifacts: list[dict[str, object]], dist: Path) -> str:
    manifest = {
        "schema_version": 1,
        "name": NAME,
        "version": version,
        "tag": f"v{version}",
        "source_date_epoch": source_date_epoch(),
        "build": release_build_metadata(),
        "toolchain": release_toolchain_metadata(),
        "artifacts": artifacts,
    }
    path = dist / f"{NAME}-v{version}-release-manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path.relative_to(ROOT).as_posix()


def release_build_metadata() -> dict[str, str]:
    keys = ("GITHUB_REPOSITORY", "GITHUB_REF_NAME", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
    return {key.lower(): value for key in keys if (value := os.environ.get(key))}


def release_toolchain_metadata() -> dict[str, object]:
    try:
        return json.loads(RELEASE_TOOLCHAIN.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"release toolchain manifest missing: {RELEASE_TOOLCHAIN.relative_to(ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"release toolchain manifest is not valid JSON: {exc}") from exc


def write_checksums(version: str, artifacts: list[dict[str, object]], manifest_path: Path, dist: Path) -> str:
    checksum_path = dist / f"{NAME}-v{version}-SHA256SUMS.txt"
    entries = [ROOT / str(artifact["file"]) for artifact in artifacts]
    entries.append(manifest_path)
    lines = []
    for path in entries:
        relname = path.relative_to(dist).as_posix() if dist in path.parents else path.relative_to(ROOT).as_posix()
        lines.append(f"{sha256_file(path)}  {relname}")
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checksum_path.relative_to(ROOT).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
