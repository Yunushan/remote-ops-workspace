"""Stage the exact reviewed MobApt runtime, cache and notices into a Debian package."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_linux_native_elf import validate_elf  # noqa: E402
from scripts.check_mobapt_cache_evidence import (  # noqa: E402
    INSTALLED_CACHE,
    check_runtime_and_cache,
    validate_mobapt_cache_evidence,
)
from scripts.check_release_license_compliance import (  # noqa: E402
    bound_evidence_file,
    read_json_object,
)
from scripts.debian_release_fixture import DEBIAN_TARGETS  # noqa: E402

EVIDENCE = "mobapt-cache-evidence.json"
REVIEW = "mobapt-debian-review.json"
ELF_ARCHES = {"amd64": "x86_64", "arm64": "aarch64", "i386": "i686", "armhf": "armhf"}


def stage_cache(bundle: Path, root: Path, architecture: str, review_sha256: str) -> list[Path]:
    review = bound_evidence_file(bundle, REVIEW, review_sha256, "MobApt review manifest")
    _, metadata = read_json_object(review, "MobApt review manifest")
    evidence = bound_evidence_file(bundle, EVIDENCE, metadata.get("assembly_sha256"), "MobApt assembly")
    checked = validate_mobapt_cache_evidence(evidence, assets_dir=bundle)
    if not checked.passed:
        raise ValueError(f"invalid MobApt assembly: {checked.errors}")
    _, data = read_json_object(evidence, "MobApt assembly")
    if data["release_target"] != DEBIAN_TARGETS[architecture]:
        raise ValueError("MobApt cache release target differs from the Debian architecture")
    tools, packages = check_runtime_and_cache(bundle, data)
    if "bin/bash" not in tools or not packages:
        raise ValueError("Debian MobApt cache requires bundled Bash and at least one package")

    notices = metadata.get("notices")
    components = {Path(tool).name for tool in tools} | set(packages)
    if not isinstance(notices, dict) or set(notices) != {f"{name}.copyright" for name in components}:
        raise ValueError("MobApt review must bind a copyright notice for each tool and cached package")
    assets = {
        EVIDENCE: evidence,
        data["runtime"]["manifest"]: bundle / data["runtime"]["manifest"],
        data["package_cache"]["index"]: bundle / data["package_cache"]["index"],
        **{name: bundle / name for name in tools},
        **{entry["archive"]: bundle / entry["archive"] for entry in packages.values()},
    }
    for receipt in (*data["install_tests"], data["terminal_probe"]):
        name = receipt["evidence_file"]
        assets[name] = bound_evidence_file(bundle, name, receipt["evidence_sha256"], "MobApt assembly receipt")
    copyright_files = {
        name: bound_evidence_file(bundle, f"notices/{name}", digest, "MobApt copyright notice")
        for name, digest in notices.items()
    }

    cache = root / INSTALLED_CACHE.lstrip("/")
    doc = root / "usr/share/doc/remote-ops-workspace/mobapt-notices"
    if any(path.exists() or path.is_symlink() for path in (cache, doc)):
        raise ValueError("Debian MobApt payload already exists")
    with TemporaryDirectory(prefix="mobapt-stage-", dir=root) as scratch:
        staged = Path(scratch) / "cache"
        licenses = Path(scratch) / "notices"
        licenses.mkdir(mode=0o755)
        for name, source in assets.items():
            destination = staged / name
            destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            destination.chmod(0o755 if name in tools else 0o644)
        for name, source in copyright_files.items():
            shutil.copyfile(source, licenses / name)
            (licenses / name).chmod(0o644)
            bound_evidence_file(licenses, name, notices[name], "staged MobApt copyright notice")
        shutil.copyfile(review, licenses / REVIEW)
        (licenses / REVIEW).chmod(0o644)
        bound_evidence_file(licenses, REVIEW, review_sha256, "staged MobApt review manifest")
        bound_evidence_file(staged, EVIDENCE, metadata["assembly_sha256"], "staged MobApt assembly")
        checked = validate_mobapt_cache_evidence(staged / EVIDENCE, assets_dir=staged)
        if not checked.passed:
            raise ValueError(f"invalid staged MobApt assembly: {checked.errors}")
        check_runtime_and_cache(staged, data)
        for name in sorted(tools):
            validate_elf(staged / name, ELF_ARCHES[architecture])
        for name, package in packages.items():
            fields = subprocess.check_output(
                ["dpkg-deb", "--field", str(staged / package["archive"]), "Package", "Version", "Architecture"],
                text=True, timeout=30,
            )
            prefix = f"Package: {name}\nVersion: {package['version']}\n"
            if fields not in {prefix + f"Architecture: {architecture}\n", prefix + "Architecture: all\n"}:
                raise ValueError(f"cached Debian package metadata differs from the reviewed package: {name}")
        cache.parent.mkdir(parents=True, exist_ok=True)
        doc.parent.mkdir(parents=True, exist_ok=True)
        staged.rename(cache)
        licenses.rename(doc)
    return [cache / name for name in sorted(tools)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--debian-root", required=True, type=Path)
    parser.add_argument("--architecture", required=True, choices=DEBIAN_TARGETS)
    parser.add_argument("--review-sha256", required=True)
    args = parser.parse_args()
    try:
        for executable in stage_cache(args.bundle, args.debian_root, args.architecture, args.review_sha256):
            print(executable)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Debian MobApt cache: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
