"""Stage the exact reviewed MobApt runtime, cache and notices into a Debian package."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile

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
    sha256_file,
)
from scripts.debian_release_fixture import DEBIAN_TARGETS, release_deb_version  # noqa: E402
from scripts.debian_server_notices import (  # noqa: E402
    MOBAPT_ASSEMBLY,
    MOBAPT_NOTICE_DIR,
    MOBAPT_REVIEW,
)

EVIDENCE = MOBAPT_ASSEMBLY
REVIEW = MOBAPT_REVIEW
NOTICE_ROOT = MOBAPT_NOTICE_DIR.as_posix()
ELF_ARCHES = {"amd64": "x86_64", "arm64": "aarch64", "i386": "i686", "armhf": "armhf"}


def stage_cache(
    bundle: Path, root: Path, architecture: str, review_sha256: str, *, release_tag: str | None = None,
) -> list[Path]:
    review = bound_evidence_file(bundle, REVIEW, review_sha256, "MobApt review manifest")
    _, metadata = read_json_object(review, "MobApt review manifest")
    if release_tag is not None and metadata.get("release_tag") != release_tag:
        raise ValueError("MobApt review manifest does not match the release tag")
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
    doc = root / NOTICE_ROOT
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
            relative = f"{name.removesuffix('.copyright')}/copyright"
            destination = licenses / relative
            destination.parent.mkdir(mode=0o755)
            shutil.copyfile(source, destination)
            destination.chmod(0o644)
            bound_evidence_file(licenses, relative, notices[name], "staged MobApt copyright notice")
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


def verify_packaged_review(
    package: Path, release_tag: str, review_sha256: str | None, *, capture_root: Path | None = None,
) -> None:
    prefix = INSTALLED_CACHE.lstrip("/")
    review_name = f"{NOTICE_ROOT}/{REVIEW}"
    assembly_name = f"{prefix}/{EVIDENCE}"
    metadata_names = {review_name, assembly_name}
    expected = {}
    data = None
    if capture_root is not None:
        _, data = read_json_object(capture_root / "evidence.json", "reviewed MobApt release evidence")
        target = data["release_target"]
        if release_tag != f"v{release_deb_version(package.name, target)}":
            raise ValueError("the Debian MobApt package must match the reviewed release tag")
        release_asset = {"name": package.name, "sha256": sha256_file(package)}
        if data.get("release_asset") != release_asset:
            raise ValueError("reviewed MobApt release asset differs from the Debian package")
        tools, packages = check_runtime_and_cache(capture_root, data)
        runtime, cache = data["runtime"], data["package_cache"]
        expected = {
            f"{prefix}/{runtime['manifest']}": runtime["manifest_sha256"],
            f"{prefix}/{cache['index']}": cache["index_sha256"],
            **{f"{prefix}/{name}": sha256_file(capture_root / name) for name in tools},
            **{f"{prefix}/{row['archive']}": row["sha256"] for row in packages.values()},
        }

    files: dict[str, bytes] = {}
    verified: set[str] = set()
    try:
        with TemporaryFile() as payload:
            subprocess.run(
                ["dpkg-deb", "--fsys-tarfile", str(package.resolve())], stdout=payload,
                stderr=subprocess.PIPE, check=True, timeout=120,
            )
            payload.seek(0)
            with tarfile.open(fileobj=payload, mode="r:") as archive:
                for entry in archive:
                    name = entry.name.removeprefix("./")
                    if name not in metadata_names and name not in expected:
                        continue
                    if name in verified or not entry.isfile() or entry.sparse is not None or entry.size <= 0:
                        raise ValueError("invalid packaged MobApt review or cache member")
                    with archive.extractfile(entry) as stream:
                        if name in metadata_names:
                            if entry.size > 1024 * 1024:
                                raise ValueError("invalid packaged MobApt review or assembly evidence")
                            files[name] = stream.read()
                        elif hashlib.file_digest(stream, "sha256").hexdigest() != expected[name]:
                            raise ValueError(f"reviewed MobApt cache differs from the Debian package payload: {name}")
                    verified.add(name)
    except (OSError, subprocess.SubprocessError, tarfile.TarError) as exc:
        raise ValueError("could not read the candidate Debian MobApt payload") from exc
    if set(files) != metadata_names:
        raise ValueError("candidate DEB lacks the packaged MobApt review or assembly evidence")
    if missing := expected.keys() - verified:
        raise ValueError(f"candidate DEB lacks reviewed MobApt cache members: {sorted(missing)}")
    review = files[review_name]
    if review_sha256 is not None and hashlib.sha256(review).hexdigest() != review_sha256:
        raise ValueError("packaged MobApt review does not match the frozen SHA-256")
    document = json.loads(review)
    assembly = files[assembly_name]
    if (not isinstance(document, dict) or document.get("release_tag") != release_tag
            or document.get("assembly_sha256") != hashlib.sha256(assembly).hexdigest()):
        raise ValueError("packaged MobApt review does not bind the release tag and assembly")
    if data is not None:
        assembly_data = json.loads(assembly)
        if not isinstance(assembly_data, dict) or any(
            assembly_data.get(key) != data[key] for key in ("release_target", "runtime", "package_cache")
        ):
            raise ValueError("reviewed MobApt cache differs from the release-bound assembly")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--debian-root", required=True, type=Path)
    parser.add_argument("--architecture", required=True, choices=DEBIAN_TARGETS)
    parser.add_argument("--review-sha256", required=True)
    parser.add_argument("--tag")
    args = parser.parse_args()
    try:
        for executable in stage_cache(
            args.bundle, args.debian_root, args.architecture, args.review_sha256, release_tag=args.tag,
        ):
            print(executable)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Debian MobApt cache: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
