from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "configs" / "release_matrix.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
EXPECTED_CHECKSUM_SUFFIX = "SHA256SUMS.txt"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    errors = check_publish_contract(matrix, workflow)
    if args.assets_dir is not None:
        errors.extend(check_release_assets(args.assets_dir, matrix, tag=args.tag))
    if errors:
        for error in errors:
            print(f"release publish assets: {error}", file=sys.stderr)
        return 1
    print("release publish asset checks passed")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate GitHub release publish asset completeness.")
    parser.add_argument(
        "--assets-dir",
        type=Path,
        help="Downloaded release asset directory to validate before publish.",
    )
    parser.add_argument(
        "--tag",
        help="Expected release tag, for example v1.0.1. Defaults to the matrix release tag.",
    )
    return parser.parse_args(argv)


def check_publish_contract(matrix: dict[str, Any], workflow: str) -> list[str]:
    errors: list[str] = []
    expected = expected_release_assets(matrix)
    if len(expected) < 20:
        errors.append(f"release matrix expected asset set is unexpectedly small: {len(expected)}")
    checksum_assets = [asset for asset in expected if asset.endswith(EXPECTED_CHECKSUM_SUFFIX)]
    if len(checksum_assets) < 6:
        errors.append("release matrix must include source and per-native checksum sidecars")
    publish_block = workflow_job_block(workflow, "publish")
    if not publish_block:
        return [*errors, "release workflow missing publish job"]
    required_snippets = {
        "actions/download-artifact@v8": "artifact download",
        "merge-multiple: true": "merged downloaded artifact directory",
        "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag": "publish asset validation",
        "softprops/action-gh-release@v3": "GitHub release upload",
        "fail_on_unmatched_files: true": "strict GitHub release upload",
    }
    for snippet, label in required_snippets.items():
        if snippet not in publish_block:
            errors.append(f"publish job missing {label}: {snippet}")
    validate_index = publish_block.find("scripts/check_release_publish_assets.py")
    upload_index = publish_block.find("softprops/action-gh-release")
    if validate_index < 0 or upload_index < 0 or validate_index > upload_index:
        errors.append("publish asset validation must run before GitHub release upload")
    return errors


def check_release_assets(assets_dir: Path, matrix: dict[str, Any], *, tag: str | None) -> list[str]:
    errors: list[str] = []
    root = assets_dir.resolve()
    if not root.is_dir():
        return [f"release asset directory missing: {assets_dir}"]
    expected = expected_release_assets(matrix, tag=tag)
    actual = {path.name for path in root.iterdir() if path.is_file()}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"release assets missing expected files: {missing}")
    if extra:
        errors.append(f"release assets include unexpected files: {extra}")
    errors.extend(check_checksum_sidecars(root, expected))
    errors.extend(check_release_manifest(root, matrix, tag=tag))
    return errors


def expected_release_assets(matrix: dict[str, Any], *, tag: str | None = None) -> set[str]:
    version = version_from_tag(tag or matrix_tag(matrix))
    source = matrix["default_github_release"]["source_and_python"]
    assets = {
        normalize_version(str(item), version)
        for item in [*source["artifacts"], *source["target_bundles"]]
    }
    for job in matrix["default_github_release"]["native_jobs"]:
        for pattern in job["asset_patterns"]:
            for expanded in expand_asset_pattern(str(pattern)):
                assets.add(normalize_version(expanded, version))
    return assets


def check_checksum_sidecars(root: Path, expected: set[str]) -> list[str]:
    errors: list[str] = []
    checksum_files = sorted(asset for asset in expected if asset.endswith(EXPECTED_CHECKSUM_SUFFIX))
    for checksum_name in checksum_files:
        path = root / checksum_name
        if not path.is_file():
            continue
        try:
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except UnicodeDecodeError:
            errors.append(f"{checksum_name} must be UTF-8 text")
            continue
        if not lines:
            errors.append(f"{checksum_name} must contain checksum entries")
            continue
        for line in lines:
            match = re.fullmatch(r"([0-9a-f]{64})\s+(.+)", line.strip())
            if not match:
                errors.append(f"{checksum_name} has invalid checksum line: {line}")
                continue
            referenced = Path(match.group(2)).name
            if referenced not in expected:
                errors.append(f"{checksum_name} references unexpected file: {referenced}")
                continue
            referenced_path = root / referenced
            if not referenced_path.is_file():
                errors.append(f"{checksum_name} references missing file: {referenced}")
                continue
            if sha256_file(referenced_path) != match.group(1):
                errors.append(f"{checksum_name} checksum mismatch for {referenced}")
    return errors


def check_release_manifest(root: Path, matrix: dict[str, Any], *, tag: str | None) -> list[str]:
    errors: list[str] = []
    manifests = sorted(root.glob("remote-ops-workspace-v*-release-manifest.json"))
    if len(manifests) != 1:
        return [f"expected exactly one release manifest, found {len(manifests)}"]
    try:
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{manifests[0].name} is not valid JSON: {exc}"]
    artifact_files = {Path(str(item.get("file", ""))).name for item in manifest.get("artifacts", []) if isinstance(item, dict)}
    source_expected = expected_source_manifest_artifacts(matrix, tag=tag)
    missing = sorted(source_expected - artifact_files)
    if missing:
        errors.append(f"{manifests[0].name} missing source/Python artifact records: {missing}")
    for item in manifest.get("artifacts", []):
        if not isinstance(item, dict):
            errors.append(f"{manifests[0].name} artifact entries must be objects")
            continue
        filename = Path(str(item.get("file", ""))).name
        if filename not in source_expected:
            errors.append(f"{manifests[0].name} includes unexpected artifact record: {filename}")
        if not isinstance(item.get("size_bytes"), int) or int(item.get("size_bytes", 0)) <= 0:
            errors.append(f"{manifests[0].name} artifact {filename} missing positive size_bytes")
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            errors.append(f"{manifests[0].name} artifact {filename} missing sha256")
    return errors


def expected_source_manifest_artifacts(matrix: dict[str, Any], *, tag: str | None = None) -> set[str]:
    version = version_from_tag(tag or matrix_tag(matrix))
    source = matrix["default_github_release"]["source_and_python"]
    return {
        normalize_version(str(item), version)
        for item in [*source["artifacts"], *source["target_bundles"]]
        if not str(item).endswith("-release-manifest.json") and not str(item).endswith(EXPECTED_CHECKSUM_SUFFIX)
    }


def expand_asset_pattern(pattern: str) -> list[str]:
    match = re.search(r"<([^>]+)>", pattern)
    if not match:
        return [pattern]
    choices = match.group(1).split("|")
    return [pattern[: match.start()] + choice + pattern[match.end() :] for choice in choices]


def normalize_version(filename: str, version: str) -> str:
    filename = re.sub(r"remote-ops-workspace-v\d+\.\d+\.\d+", f"remote-ops-workspace-v{version}", filename)
    filename = re.sub(r"remote_ops_workspace-\d+\.\d+\.\d+", f"remote_ops_workspace-{version}", filename)
    return filename


def matrix_tag(matrix: dict[str, Any]) -> str:
    for item in matrix["default_github_release"]["source_and_python"]["artifacts"]:
        match = re.search(r"remote-ops-workspace-(v\d+\.\d+\.\d+)-release-manifest\.json", str(item))
        if match:
            return match.group(1)
    raise ValueError("release matrix does not contain a release manifest tag")


def version_from_tag(tag: str) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError(f"release tag must look like vX.Y.Z: {tag}")
    return tag[1:]


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
