"""Stage a digest-pinned Debian Xvfb runtime in the native ROW package."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from remote_ops_workspace.x11 import (  # noqa: E402
    XSERVER_RUNTIME_MANIFEST_NAME,
    build_moba_x_server_runtime_bundle_plan,
    write_moba_x_server_runtime_bundle,
)
from scripts.check_linux_native_elf import validate_elf  # noqa: E402
from scripts.check_release_license_compliance import sha256_file  # noqa: E402
from scripts.debian_native_dependencies import (  # noqa: E402
    dependency_field,
    merge_debian_dependencies,
)
from scripts.debian_release_fixture import (  # noqa: E402
    DEBIAN_TARGETS,
    PRODUCT_PACKAGE,
    unpack_deb_inputs,
)
from scripts.stage_linux_runtime_licenses import (  # noqa: E402
    LICENSE_ROOT,
    SYSTEM_LICENSE_PREFIX,
    SYSTEM_VERSION_FILE,
)

ELF_ARCHES = {"amd64": "x86_64", "arm64": "aarch64"}
RUNTIME_ROOT = Path("usr/lib/remote-ops-workspace/xserver")
NOTICE_ROOT = LICENSE_ROOT / f"{SYSTEM_LICENSE_PREFIX}xvfb"


def stage_xvfb(package: Path, digest: str, root: Path, architecture: str) -> str:
    runtime = root / RUNTIME_ROOT
    notices = root / NOTICE_ROOT
    if any(path.exists() or path.is_symlink() for path in (runtime, notices)):
        raise ValueError("the Xvfb runtime or notice output already exists")
    with TemporaryDirectory(prefix="row-debian-xvfb-", dir=root) as scratch:
        work = Path(scratch)
        snapshot = work / "xvfb.deb"
        shutil.copyfile(package, snapshot)
        if sha256_file(snapshot) != digest:
            raise ValueError("Xvfb archive differs from the selected SHA-256")
        executable = work / "Xvfb"
        notice = work / "copyright"
        source = unpack_deb_inputs(snapshot, "xvfb", architecture, {
            "usr/bin/Xvfb": executable,
            "usr/share/doc/xvfb/copyright": notice,
        })
        validate_elf(executable, ELF_ARCHES[architecture])
        depends = subprocess.check_output(
            ["dpkg-deb", "--field", str(snapshot), "Depends"], text=True, timeout=30,
        ).strip()
        relationships = dependency_field(merge_debian_dependencies(["xauth"], depends))
        bundle = work / "runtime"
        result = write_moba_x_server_runtime_bundle(build_moba_x_server_runtime_bundle_plan(
            bundle, runtime_key="xvfb", source_path=executable, system="linux", release_target=DEBIAN_TARGETS[architecture],
        ))
        manifest = Path(result.manifest_path)
        document = json.loads(manifest.read_bytes())
        document["debian_source"] = {**source, "name": "xvfb", "copyright_sha256": sha256_file(notice)}
        manifest.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        bundle.chmod(0o755)
        runtime.parent.mkdir(parents=True, exist_ok=True)
        notices.mkdir(parents=True)
        shutil.copyfile(notice, notices / notice.name)
        (notices / SYSTEM_VERSION_FILE).write_text(source["version"] + "\n", encoding="utf-8")
        bundle.rename(runtime)
    return relationships


def verify_packaged_xvfb(package: Path, source: Path, digest: str, architecture: str) -> None:
    """Compare the candidate payload against the separately downloaded Debian input."""
    with TemporaryDirectory(prefix="row-verify-debian-xvfb-") as scratch:
        work = Path(scratch)
        expected = work / "expected"
        expected.mkdir()
        try:
            stage_xvfb(source, digest, expected, architecture)
            manifest = RUNTIME_ROOT / XSERVER_RUNTIME_MANIFEST_NAME
            executable = json.loads((expected / manifest).read_bytes())["runtime"]["executable"]
            members = [manifest, RUNTIME_ROOT / executable, NOTICE_ROOT / "copyright", NOTICE_ROOT / SYSTEM_VERSION_FILE]
            extracted = {member.as_posix(): work / member.name for member in members}
            unpack_deb_inputs(package, PRODUCT_PACKAGE, architecture, extracted)
        except (OSError, subprocess.SubprocessError, tarfile.TarError) as exc:
            raise ValueError("could not read the frozen Xvfb input or candidate Debian payload") from exc
        for member in members:
            if sha256_file(extracted[member.as_posix()]) != sha256_file(expected / member):
                raise ValueError(f"candidate DEB Xvfb member differs from the frozen input: {member.as_posix()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xvfb-deb", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--debian-root", required=True, type=Path)
    parser.add_argument("--architecture", required=True, choices=ELF_ARCHES)
    args = parser.parse_args()
    try:
        print(stage_xvfb(args.xvfb_deb, args.sha256, args.debian_root, args.architecture))
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        parser.exit(1, f"Debian Xvfb staging failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
