from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "configs" / "release_matrix.json"
EVIDENCE_PATH = ROOT / "configs" / "platform_verified_evidence.json"
MOBAXTERM_EVIDENCE_PATH = ROOT / "configs" / "mobaxterm_parity_evidence.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
EXPECTED_CHECKSUM_SUFFIX = "SHA256SUMS.txt"
XP_NATIVE_EVIDENCE_TARGETS = {"windows-xp-native-x86", "windows-xp-native-x64"}
PLATFORM_GOAL_TARGETS = (
    "linux-i386",
    "linux-armhf",
    "windows-xp-native-x86",
    "windows-xp-native-x64",
)
FINAL_ACCEPTED_RECORD_RE = re.compile(
    r"^platform-verified-evidence-(linux-i386|linux-armhf|windows-xp-native-x86|windows-xp-native-x64)-final\.json$"
)
GATED_NATIVE_PATTERNS = {
    "linux-i386": (
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-i386\.deb$",
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-i686\.",
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-i686-native-",
    ),
    "linux-armhf": (
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-armhf\.deb$",
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-armv7hl\.",
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-armhf\.",
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-armhf-native-",
    ),
    "windows-xp-native-x86": (
        r"remote-ops-workspace-v\d+\.\d+\.\d+-windows-xp-x86-native",
    ),
    "windows-xp-native-x64": (
        r"remote-ops-workspace-v\d+\.\d+\.\d+-windows-xp-x64-native",
    ),
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    evidence_registry = read_evidence_registry()
    mobaxterm_registry = read_mobaxterm_evidence_registry()
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    errors = check_publish_contract(
        matrix,
        workflow,
        tag=args.tag,
        evidence_registry=evidence_registry,
        mobaxterm_parity_registry=mobaxterm_registry,
        require_platform_goal_targets=args.require_platform_goal_targets,
        require_mobaxterm_parity_complete=args.require_mobaxterm_parity_complete,
    )
    if args.assets_dir is not None:
        errors.extend(
            check_release_assets(
                args.assets_dir,
                matrix,
                tag=args.tag,
                evidence_registry=evidence_registry,
                mobaxterm_parity_registry=mobaxterm_registry,
                require_platform_goal_targets=args.require_platform_goal_targets,
                require_mobaxterm_parity_complete=args.require_mobaxterm_parity_complete,
            )
        )
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
        help="Expected release tag, for example v1.0.2. Defaults to the matrix release tag.",
    )
    parser.add_argument(
        "--require-platform-goal-targets",
        action="store_true",
        help=(
            "fail unless Linux i386, Linux armhf, Windows XP native x86, "
            "and Windows XP native x64 all have accepted platform evidence"
        ),
    )
    parser.add_argument(
        "--require-mobaxterm-parity-complete",
        action="store_true",
        help="fail unless every strict MobaXterm parity article has accepted release evidence",
    )
    return parser.parse_args(argv)


def check_publish_contract(
    matrix: dict[str, Any],
    workflow: str,
    *,
    tag: str | None = None,
    evidence_registry: dict[str, Any] | None = None,
    mobaxterm_parity_registry: dict[str, Any] | None = None,
    require_platform_goal_targets: bool = False,
    require_mobaxterm_parity_complete: bool = False,
) -> list[str]:
    errors: list[str] = []
    release_tag = tag or matrix_tag(matrix)
    expected = expected_release_assets(matrix, tag=release_tag)
    errors.extend(
        validate_mobaxterm_parity_registry(
            mobaxterm_parity_registry or read_mobaxterm_evidence_registry(),
            require_complete=require_mobaxterm_parity_complete,
        )
    )
    if require_platform_goal_targets:
        errors.extend(
            validate_platform_goal_evidence_registry(
                evidence_registry or read_evidence_registry(),
                release_tag=tag or matrix_tag(matrix),
            )
        )
    errors.extend(
        check_gated_native_assets_have_evidence(
            expected,
            evidence_registry=evidence_registry,
            tag=release_tag,
            label="default release matrix",
        )
    )
    if len(expected) < 20:
        errors.append(f"release matrix expected asset set is unexpectedly small: {len(expected)}")
    checksum_assets = [asset for asset in expected if asset.endswith(EXPECTED_CHECKSUM_SUFFIX)]
    if len(checksum_assets) < 6:
        errors.append("release matrix must include source and per-native checksum sidecars")
    errors.extend(check_platform_evidence_import_job(workflow))
    publish_block = workflow_job_block(workflow, "publish")
    if not publish_block:
        return [*errors, "release workflow missing publish job"]
    required_snippets = {
        "actions/download-artifact@v8": "artifact download",
        "merge-multiple: true": "merged downloaded artifact directory",
        "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag": "publish asset validation",
        "--require-platform-goal-targets": "protected platform goal publish gate",
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
    if "- accepted-platform-evidence-assets" not in publish_block:
        errors.append("publish job must depend on accepted-platform-evidence-assets")
    return errors


def check_platform_evidence_import_job(workflow: str) -> list[str]:
    block = workflow_job_block(workflow, "accepted-platform-evidence-assets")
    if not block:
        return ["release workflow missing accepted-platform-evidence-assets job"]
    errors: list[str] = []
    required_snippets = {
        "needs: release-preflight": "release preflight dependency",
        "actions: read": "Actions artifact read permission",
        "contents: read": "read-only repository permission",
        "uses: actions/checkout@v6": "repository checkout",
        "persist-credentials: false": "checkout credential isolation",
        "uses: actions/setup-python@v6": "Python setup",
        "GH_TOKEN: ${{ github.token }}": "GitHub token for gh artifact download",
        "python scripts/import_platform_evidence_artifacts.py --release-tag": "platform evidence artifact importer",
        "--require-goal-targets": "strict protected target import",
        "--out-dir release-assets": "release asset import directory",
        "python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets": (
            "imported platform review bundle validator"
        ),
        "actions/upload-artifact@v7": "imported artifact upload",
        "name: release-platform-evidence-assets": "platform evidence release artifact name",
        "path: release-assets/*": "platform evidence release artifact path",
        "if-no-files-found: error": "missing imported asset failure",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"accepted-platform-evidence-assets job missing {label}: {snippet}")
    import_index = block.find("scripts/import_platform_evidence_artifacts.py")
    review_bundle_index = block.find("scripts/check_platform_review_bundle_artifacts.py")
    upload_index = block.find("actions/upload-artifact@v7")
    if import_index < 0 or upload_index < 0 or import_index > upload_index:
        errors.append("platform evidence import must run before imported artifact upload")
    if review_bundle_index < 0 or upload_index < 0 or review_bundle_index > upload_index:
        errors.append("platform review bundle validation must run before imported artifact upload")
    if import_index >= 0 and review_bundle_index >= 0 and import_index > review_bundle_index:
        errors.append("platform review bundle validation must run after platform evidence import")
    if re.search(r"(?m)^\s+(actions|contents):\s+write\s*$", block):
        errors.append("accepted-platform-evidence-assets job must not request write permissions")
    return errors


def check_release_assets(
    assets_dir: Path,
    matrix: dict[str, Any],
    *,
    tag: str | None,
    evidence_registry: dict[str, Any] | None = None,
    mobaxterm_parity_registry: dict[str, Any] | None = None,
    require_platform_goal_targets: bool = False,
    require_mobaxterm_parity_complete: bool = False,
) -> list[str]:
    errors: list[str] = []
    errors.extend(check_release_asset_directory(assets_dir))
    if errors:
        return errors
    root = assets_dir.resolve()
    if not root.is_dir():
        return [f"release asset directory missing: {assets_dir}"]
    errors.extend(
        validate_mobaxterm_parity_registry(
            mobaxterm_parity_registry or read_mobaxterm_evidence_registry(),
            require_complete=require_mobaxterm_parity_complete,
        )
    )
    if require_platform_goal_targets:
        errors.extend(
            validate_platform_goal_evidence_registry(
                evidence_registry or read_evidence_registry(),
                release_tag=tag or matrix_tag(matrix),
            )
        )
    release_tag = tag or matrix_tag(matrix)
    registry = evidence_registry or read_evidence_registry()
    expected = expected_release_assets(matrix, tag=release_tag) | accepted_platform_release_assets(
        registry,
        tag=release_tag,
    )
    errors.extend(check_release_asset_symlinks(root))
    errors.extend(check_release_asset_root_entries(root))
    actual = {path.name for path in root.iterdir() if path.is_file()}
    errors.extend(
        check_gated_native_assets_have_evidence(
            actual,
            evidence_registry=registry,
            tag=release_tag,
            label="release asset directory",
        )
    )
    errors.extend(
        check_platform_evidence_asset_hashes(
            root,
            actual,
            tag=release_tag,
            evidence_registry=registry,
        )
    )
    errors.extend(
        check_platform_review_bundle_artifacts(
            root,
            tag=release_tag,
            evidence_registry=registry,
        )
    )
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"release assets missing expected files: {missing}")
    if extra:
        errors.append(f"release assets include unexpected files: {extra}")
    errors.extend(check_checksum_sidecars(root, expected))
    errors.extend(check_release_manifest(root, matrix, tag=tag))
    return errors


def check_release_asset_directory(assets_dir: Path) -> list[str]:
    if assets_dir.is_symlink():
        return [f"release asset directory must not be a symlink: {assets_dir}"]
    return check_path_parent_symlinks(assets_dir, "release asset directory")


def check_release_asset_symlinks(root: Path) -> list[str]:
    symlinks = sorted(path.name for path in root.iterdir() if path.is_symlink())
    if symlinks:
        return [f"release assets must not contain symlinks: {symlinks}"]
    return []


def check_release_asset_root_entries(root: Path) -> list[str]:
    directories = sorted(path.name for path in root.iterdir() if path.is_dir() and not path.is_symlink())
    unsupported = sorted(
        path.name
        for path in root.iterdir()
        if not path.is_file() and not path.is_dir() and not path.is_symlink()
    )
    errors: list[str] = []
    if directories:
        errors.append(f"release assets must contain root files only, found directories: {directories}")
    if unsupported:
        errors.append(f"release assets contain unsupported entries: {unsupported}")
    return errors


def check_platform_review_bundle_artifacts(
    root: Path,
    *,
    tag: str,
    evidence_registry: dict[str, Any],
) -> list[str]:
    rows = evidence_registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return ["platform verified evidence accepted_evidence must be a list"]
    accepted_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("status") == "accepted"
        and row.get("readiness_percent") == 100.0
        and row.get("release_tag") == tag
    ]
    if not accepted_rows:
        return []
    checker = load_platform_review_bundle_artifact_checker()
    scoped_registry = {**evidence_registry, "accepted_evidence": accepted_rows}
    return checker.check_platform_review_bundle_artifacts(
        registry=scoped_registry,
        bundle_dir=root,
    )


def check_gated_native_assets_have_evidence(
    assets: set[str],
    *,
    evidence_registry: dict[str, Any] | None = None,
    tag: str,
    label: str,
) -> list[str]:
    accepted = accepted_evidence_targets(
        evidence_registry or read_evidence_registry(),
        release_tag=tag,
    )
    errors: list[str] = []
    for asset in sorted(assets):
        gated_targets = gated_native_targets_for_asset(asset)
        for target in sorted(gated_targets):
            if target in XP_NATIVE_EVIDENCE_TARGETS:
                missing_xp = sorted(XP_NATIVE_EVIDENCE_TARGETS - accepted)
                if missing_xp:
                    errors.append(
                        f"{label} includes gated Windows XP native asset {asset} but XP native "
                        f"promotion requires accepted evidence for both targets for release_tag {tag}; "
                        f"missing {missing_xp}"
                    )
                continue
            if target not in accepted:
                errors.append(
                    f"{label} includes gated native asset {asset} for {target} "
                    f"without accepted platform evidence for release_tag {tag}"
                )
    return errors


def gated_native_targets_for_asset(filename: str) -> set[str]:
    targets: set[str] = set()
    for target, patterns in GATED_NATIVE_PATTERNS.items():
        if any(re.search(pattern, filename) for pattern in patterns):
            targets.add(target)
    return targets


def accepted_evidence_targets(
    evidence_registry: dict[str, Any],
    *,
    release_tag: str | None = None,
) -> set[str]:
    if validate_accepted_evidence_registry(evidence_registry):
        return set()
    rows = evidence_registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return set()
    return {
        str(item.get("target", ""))
        for item in rows
        if isinstance(item, dict)
        and item.get("status") == "accepted"
        and item.get("readiness_percent") == 100.0
        and (release_tag is None or item.get("release_tag") == release_tag)
    }


def check_platform_evidence_asset_hashes(
    root: Path,
    assets: set[str],
    *,
    tag: str,
    evidence_registry: dict[str, Any],
) -> list[str]:
    registry_errors = validate_accepted_evidence_registry(evidence_registry)
    if registry_errors:
        return registry_errors
    rows = evidence_registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return ["platform verified evidence accepted_evidence must be a list"]
    accepted = {
        str(item.get("target", "")): item
        for item in rows
        if isinstance(item, dict)
        and item.get("status") == "accepted"
        and item.get("readiness_percent") == 100.0
        and item.get("release_tag") == tag
    }
    errors: list[str] = []
    for target, record in sorted(accepted.items()):
        if record.get("release_tag") != tag:
            continue
        hashes = record.get("artifact_sha256")
        if not isinstance(hashes, dict):
            errors.append(f"{target} accepted evidence artifact_sha256 must be an object")
            continue
        release_urls = record.get("release_asset_urls")
        if not isinstance(release_urls, list):
            errors.append(f"{target} accepted evidence release_asset_urls must be a list")
            continue
        url_assets: set[str] = set()
        for url in release_urls:
            if not isinstance(url, str):
                continue
            filename = release_asset_url_filename(url)
            if not filename:
                errors.append(
                    f"{target} accepted evidence release_asset_urls file name must be an exact safe file name: {url}"
                )
                continue
            url_assets.add(filename)
        expected_assets = {str(asset) for asset in hashes}
        if url_assets != expected_assets:
            errors.append(
                f"{target} accepted evidence release_asset_urls must match artifact_sha256 files"
            )
        for asset, expected_sha in sorted(hashes.items()):
            asset_name = str(asset)
            if asset_name not in assets:
                errors.append(
                    f"{target} accepted evidence release asset missing from release directory: "
                    f"{asset_name}"
                )
                continue
            actual_sha = sha256_file(root / asset_name)
            if actual_sha != str(expected_sha):
                errors.append(
                    f"release asset {asset_name} SHA-256 does not match accepted evidence for {target}"
                )
        review_bundle = record.get("review_bundle")
        if not isinstance(review_bundle, dict):
            errors.append(f"{target} accepted evidence review_bundle must be an object")
            continue
        for bundle_key in ("manifest", "archive", "sha256s"):
            bundle_record = review_bundle.get(bundle_key)
            if not isinstance(bundle_record, dict):
                errors.append(f"{target} accepted evidence review_bundle {bundle_key} must be an object")
                continue
            bundle_name = str(bundle_record.get("file", ""))
            if not checksum_reference_name_is_safe(bundle_name):
                errors.append(
                    f"{target} accepted evidence review_bundle {bundle_key}.file "
                    f"must be an exact safe file name: {bundle_name!r}"
                )
                continue
            if bundle_name not in assets:
                errors.append(
                    f"{target} accepted evidence review bundle asset missing from release directory: "
                    f"{bundle_name}"
                )
                continue
            bundle_path = root / bundle_name
            expected_size = bundle_record.get("size_bytes")
            if bundle_path.is_file() and expected_size != bundle_path.stat().st_size:
                errors.append(
                    f"release review bundle asset {bundle_name} size does not match accepted evidence for {target}"
                )
            expected_sha = str(bundle_record.get("sha256", ""))
            if bundle_path.is_file() and sha256_file(bundle_path) != expected_sha:
                errors.append(
                    f"release review bundle asset {bundle_name} SHA-256 does not match accepted evidence for {target}"
                )
        final_record_name = accepted_record_source_file(target)
        if final_record_name not in assets:
            errors.append(
                f"{target} accepted evidence finalized record asset missing from release directory: "
                f"{final_record_name}"
            )
        else:
            errors.extend(
                check_final_accepted_record_asset(
                    root / final_record_name,
                    target=target,
                    record=record,
                )
            )
    for asset in sorted(assets):
        for target in sorted(gated_native_targets_for_asset(asset)):
            record = accepted.get(target)
            if record is None:
                continue
            hashes = record.get("artifact_sha256")
            if not isinstance(hashes, dict):
                errors.append(f"{target} accepted evidence artifact_sha256 must be an object")
                continue
            expected_sha = str(hashes.get(asset, ""))
            if not expected_sha:
                errors.append(
                    f"release asset {asset} is gated for {target} but accepted evidence "
                    "artifact_sha256 has no entry"
                )
                continue
            actual_sha = sha256_file(root / asset)
            if actual_sha != expected_sha:
                errors.append(
                    f"release asset {asset} SHA-256 does not match accepted evidence for {target}"
                )
    return errors


def accepted_platform_release_assets(evidence_registry: dict[str, Any], *, tag: str) -> set[str]:
    if validate_accepted_evidence_registry(evidence_registry):
        return set()
    rows = evidence_registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return set()
    assets: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "accepted" or row.get("readiness_percent") != 100.0:
            continue
        if row.get("release_tag") != tag:
            continue
        for url in row.get("release_asset_urls", []):
            filename = release_asset_url_filename(str(url))
            if filename:
                assets.add(filename)
        hashes = row.get("artifact_sha256")
        if isinstance(hashes, dict):
            assets.update(str(name) for name in hashes)
        review_bundle = row.get("review_bundle")
        if isinstance(review_bundle, dict):
            for bundle_key in ("manifest", "archive", "sha256s"):
                bundle_record = review_bundle.get(bundle_key)
                if isinstance(bundle_record, dict):
                    filename = str(bundle_record.get("file", ""))
                    if checksum_reference_name_is_safe(filename):
                        assets.add(filename)
        target = str(row.get("target", ""))
        if target in PLATFORM_GOAL_TARGETS:
            assets.add(accepted_record_source_file(target))
    return assets


def accepted_record_source_file(target: str) -> str:
    return f"platform-verified-evidence-{target}-final.json"


def check_final_accepted_record_asset(
    path: Path,
    *,
    target: str,
    record: dict[str, Any],
) -> list[str]:
    if path.is_symlink():
        return [f"{target} accepted evidence finalized record asset must not be a symlink: {path.name}"]
    if not path.is_file():
        return [f"{target} accepted evidence finalized record asset missing from release directory: {path.name}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{target} accepted evidence finalized record asset is not readable JSON: {path.name}: {exc}"]
    if not isinstance(data, dict):
        return [f"{target} accepted evidence finalized record asset must contain a JSON object: {path.name}"]
    if data != public_record(record):
        return [f"{target} accepted evidence finalized record asset must match accepted registry record: {path.name}"]
    return []


def public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if not str(key).startswith("_")}


def validate_accepted_evidence_registry(evidence_registry: dict[str, Any]) -> list[str]:
    module = load_platform_verified_evidence_checker()
    return module.check_platform_verified_evidence(
        registry=evidence_registry,
        require_review_bundles=True,
    )


def validate_platform_goal_evidence_registry(
    evidence_registry: dict[str, Any],
    *,
    release_tag: str,
) -> list[str]:
    module = load_platform_verified_evidence_checker()
    return module.check_platform_verified_evidence(
        registry=evidence_registry,
        required_targets=PLATFORM_GOAL_TARGETS,
        required_release_tag=release_tag,
        require_review_bundles=True,
    )


def load_platform_verified_evidence_checker() -> Any:
    checker_path = ROOT / "scripts" / "check_platform_verified_evidence.py"
    spec = importlib.util.spec_from_file_location("check_platform_verified_evidence", checker_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load platform verified evidence checker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_platform_review_bundle_artifact_checker() -> Any:
    checker_path = ROOT / "scripts" / "check_platform_review_bundle_artifacts.py"
    spec = importlib.util.spec_from_file_location("check_platform_review_bundle_artifacts", checker_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load platform review bundle artifact checker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_mobaxterm_parity_registry(
    registry: dict[str, Any],
    *,
    require_complete: bool,
) -> list[str]:
    checker_path = ROOT / "scripts" / "check_mobaxterm_parity_evidence.py"
    spec = importlib.util.spec_from_file_location("check_mobaxterm_parity_evidence", checker_path)
    if spec is None or spec.loader is None:
        return ["cannot load MobaXterm parity evidence checker"]
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.check_mobaxterm_parity_evidence(registry=registry, require_complete=require_complete)


def read_evidence_registry() -> dict[str, Any]:
    if not EVIDENCE_PATH.exists():
        return {"schema_version": 1, "accepted_evidence": []}
    try:
        data = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": 1, "accepted_evidence": []}
    return data if isinstance(data, dict) else {"schema_version": 1, "accepted_evidence": []}


def read_mobaxterm_evidence_registry() -> dict[str, Any]:
    if not MOBAXTERM_EVIDENCE_PATH.exists():
        return {"schema_version": 1, "policy": "", "accepted_evidence": []}
    try:
        data = json.loads(MOBAXTERM_EVIDENCE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": 1, "policy": "", "accepted_evidence": []}
    return data if isinstance(data, dict) else {"schema_version": 1, "policy": "", "accepted_evidence": []}


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
    final_record_assets = {asset for asset in expected if FINAL_ACCEPTED_RECORD_RE.fullmatch(asset)}
    expected_references = set(expected - set(checksum_files) - final_record_assets)
    referenced_assets: set[str] = set()
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
            raw_reference = match.group(2)
            if not checksum_reference_name_is_safe(raw_reference):
                errors.append(
                    f"{checksum_name} reference must be an exact safe file name: {raw_reference!r}"
                )
                continue
            referenced = raw_reference
            if referenced not in expected:
                errors.append(f"{checksum_name} references unexpected file: {referenced}")
                continue
            referenced_path = root / referenced
            if not referenced_path.is_file():
                errors.append(f"{checksum_name} references missing file: {referenced}")
                continue
            if sha256_file(referenced_path) != match.group(1):
                errors.append(f"{checksum_name} checksum mismatch for {referenced}")
                continue
            referenced_assets.add(referenced)
    missing_references = sorted(expected_references - referenced_assets)
    if missing_references:
        errors.append(f"checksum sidecars missing references for expected files: {missing_references}")
    return errors


def checksum_reference_name_is_safe(name: str) -> bool:
    if not name or name.strip() != name or "/" in name or "\\" in name:
        return False
    if name in (".", ".."):
        return False
    windows_path = PureWindowsPath(name)
    posix_path = PurePosixPath(name)
    return not windows_path.drive and not windows_path.is_absolute() and not posix_path.is_absolute()


def release_asset_url_filename(url: str) -> str:
    parts = urlsplit(url)
    if parts.query or parts.fragment:
        return ""
    path_segments = parts.path.split("/")
    if (
        len(path_segments) != 7
        or path_segments[0] != ""
        or path_segments[3:5] != ["releases", "download"]
        or not path_segments[-1]
    ):
        return ""
    filename = unquote(path_segments[-1])
    return filename if checksum_reference_name_is_safe(filename) else ""


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


def check_path_parent_symlinks(path: Path, label: str) -> list[str]:
    check_path = path if path.is_absolute() else Path.cwd() / path
    for parent in reversed(check_path.parents):
        if parent == Path("."):
            continue
        if parent.is_symlink():
            return [f"{label} path must not contain symlinked directories: {parent}"]
    return []


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
