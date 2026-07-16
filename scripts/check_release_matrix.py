from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "configs" / "release_matrix.json"
PLATFORM_TARGETS_PATH = ROOT / "configs" / "platform_targets.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"

STALE_DEFAULT_ARTIFACT_SNIPPETS = (
    "remote-ops-workspace-v1.0.6-linux-<i386|amd64|armhf|arm64>.deb",
    "remote-ops-workspace-v1.0.6-linux-<i686|x86_64|armv7hl|aarch64>.rpm",
    "remote-ops-workspace-v1.0.6-linux-<i686|x86_64|armhf|aarch64>.AppImage",
    "remote-ops-workspace-v1.0.6-linux-<i686|x86_64|armhf|aarch64>-native.tar.gz",
)
SCRIPT_TARGET_BUILDER_REQUIREMENT_SNIPPETS = {
    "linux-i386": (
        "32-bit",
        "dpkg --print-architecture=i386",
        "getconf LONG_BIT=32",
        "rpm",
        "sudo -n true",
        "dpkg",
        "getconf",
    ),
    "linux-armhf": (
        "32-bit",
        "dpkg --print-architecture=armhf",
        "getconf LONG_BIT=32",
        "rpm",
        "sudo -n true",
        "dpkg",
        "getconf",
    ),
}


def main() -> int:
    errors: list[str] = []
    matrix = load_json(MATRIX_PATH, errors)
    platform_targets = load_json(PLATFORM_TARGETS_PATH, errors)
    if matrix and platform_targets:
        errors.extend(check_schema(matrix))
        errors.extend(check_workflow_native_jobs(matrix))
        errors.extend(check_source_and_python_assets(matrix))
        errors.extend(check_release_asset_pattern_versions(matrix))
        errors.extend(check_platform_target_alignment(matrix, platform_targets))
        errors.extend(check_release_docs(matrix))
        errors.extend(check_release_helper_packaging())
    if errors:
        for error in errors:
            print(f"release matrix: {error}", file=sys.stderr)
        return 1
    print("release matrix policy passed")
    return 0


def check_schema(matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if matrix.get("schema_version") != 1:
        errors.append("configs/release_matrix.json schema_version must be 1")
    if matrix.get("workflow") != ".github/workflows/release.yml":
        errors.append("configs/release_matrix.json workflow must point at .github/workflows/release.yml")
    default = require_mapping(matrix, "default_github_release", errors)
    if default:
        require_mapping(default, "source_and_python", errors)
        native_jobs = require_list(default, "native_jobs", errors)
        if not native_jobs:
            errors.append("configs/release_matrix.json default_github_release.native_jobs must not be empty")
    promotion = require_mapping(matrix, "protected_platform_promotion", errors)
    if promotion:
        if promotion.get("workflow_input") != "include_protected_platform_evidence":
            errors.append("protected_platform_promotion.workflow_input must be include_protected_platform_evidence")
        if promotion.get("evidence_job") != "accepted-platform-evidence-assets":
            errors.append("protected_platform_promotion.evidence_job must be accepted-platform-evidence-assets")
        if promotion.get("publish_job") != "publish-protected-platform-evidence":
            errors.append("protected_platform_promotion.publish_job must be publish-protected-platform-evidence")
        targets = {str(target) for target in require_list(promotion, "targets", errors)}
        expected_targets = {"linux-i386", "linux-armhf", "windows-xp-native-x86", "windows-xp-native-x64"}
        if targets != expected_targets:
            errors.append(
                "protected_platform_promotion.targets must list Linux i386/armhf and Windows XP native x86/x64"
            )
    require_list(matrix, "script_supported_native", errors)
    require_list(matrix, "source_or_remote_only", errors)
    return errors


def check_workflow_native_jobs(matrix: dict[str, Any]) -> list[str]:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    native_jobs = require_list(require_mapping(matrix, "default_github_release", []), "native_jobs", [])
    errors: list[str] = []
    for raw_job in native_jobs:
        if not isinstance(raw_job, dict):
            errors.append("default_github_release.native_jobs entries must be objects")
            continue
        job_name = str(raw_job.get("job", ""))
        expected_arches = {str(arch) for arch in raw_job.get("arches", [])}
        block = workflow_job_block(workflow, job_name)
        if not block:
            errors.append(f"release workflow missing default native job: {job_name}")
            continue
        found_arches = set(re.findall(r"(?m)^\s+- arch:\s*([A-Za-z0-9_]+)\s*$", block))
        if found_arches != expected_arches:
            errors.append(f"{job_name} arch matrix {sorted(found_arches)} must equal {sorted(expected_arches)}")
        prefix = str(raw_job.get("upload_artifact_prefix", ""))
        expected_upload_name = f"name: {prefix}${{{{ matrix.arch }}}}"
        if expected_upload_name not in block:
            errors.append(f"{job_name} upload artifact name must be {expected_upload_name}")
    return errors


def check_source_and_python_assets(matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    version = read_project_version(errors)
    if not version:
        return errors
    source_and_python = require_mapping(
        require_mapping(matrix, "default_github_release", errors),
        "source_and_python",
        errors,
    )
    if not source_and_python:
        return errors

    expected_artifacts = {
        f"remote_ops_workspace-{version}-py3-none-any.whl",
        f"remote_ops_workspace-{version}.tar.gz",
        f"remote-ops-workspace-v{version}-release-manifest.json",
        f"remote-ops-workspace-v{version}-SHA256SUMS.txt",
    }
    actual_artifacts = {str(item) for item in require_list(source_and_python, "artifacts", errors)}
    if actual_artifacts != expected_artifacts:
        errors.append(
            "source_and_python.artifacts must match current Python/source release outputs "
            f"(expected {sorted(expected_artifacts)}, got {sorted(actual_artifacts)})"
        )

    expected_bundles = expected_target_bundle_names(version, errors)
    actual_bundles = {str(item) for item in require_list(source_and_python, "target_bundles", errors)}
    if expected_bundles and actual_bundles != expected_bundles:
        errors.append(
            "source_and_python.target_bundles must match scripts/make_release.py TARGETS "
            f"(expected {sorted(expected_bundles)}, got {sorted(actual_bundles)})"
        )
    return errors


def check_release_asset_pattern_versions(matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    version = read_project_version(errors)
    if not version:
        return errors
    expected = f"v{version}"
    for label, pattern in release_asset_patterns(matrix):
        if expected not in pattern:
            errors.append(
                f"{label} asset pattern must use current project version {expected}: {pattern}"
            )
    return errors


def release_asset_patterns(matrix: dict[str, Any]) -> list[tuple[str, str]]:
    patterns: list[tuple[str, str]] = []
    default = require_mapping(matrix, "default_github_release", [])
    for raw_job in require_list(default, "native_jobs", []):
        if not isinstance(raw_job, dict):
            continue
        job_name = str(raw_job.get("job", "default-native"))
        for pattern in raw_job.get("asset_patterns", []):
            patterns.append((job_name, str(pattern)))
    for raw_item in require_list(matrix, "script_supported_native", []):
        if not isinstance(raw_item, dict):
            continue
        target_id = str(raw_item.get("platform_target_id", "script-supported"))
        for pattern in raw_item.get("asset_patterns", []):
            patterns.append((target_id, str(pattern)))
    return patterns


def check_platform_target_alignment(matrix: dict[str, Any], platform_targets: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rows = {
        str(item.get("id")): item
        for item in platform_targets.get("release_architectures", [])
        if isinstance(item, dict)
    }

    default_ids = set()
    for raw_job in require_list(require_mapping(matrix, "default_github_release", errors), "native_jobs", errors):
        if isinstance(raw_job, dict):
            default_ids.update(str(item) for item in raw_job.get("platform_target_ids", []))

    script_ids = {
        str(item.get("platform_target_id"))
        for item in require_list(matrix, "script_supported_native", errors)
        if isinstance(item, dict)
    }
    for raw_item in require_list(matrix, "script_supported_native", errors):
        if not isinstance(raw_item, dict):
            continue
        target_id = str(raw_item.get("platform_target_id"))
        builder_requirement = str(raw_item.get("builder_requirement", ""))
        for snippet in SCRIPT_TARGET_BUILDER_REQUIREMENT_SNIPPETS.get(target_id, ()):
            if snippet not in builder_requirement:
                errors.append(f"{target_id} builder_requirement must mention {snippet}")
        asset_patterns = raw_item.get("asset_patterns")
        if not isinstance(asset_patterns, list) or not asset_patterns:
            errors.append(f"{target_id} asset_patterns must list script-supported release artifacts")
        else:
            normalized_patterns = [str(pattern) for pattern in asset_patterns]
            duplicate_patterns = sorted(
                {
                    pattern
                    for pattern in normalized_patterns
                    if normalized_patterns.count(pattern) > 1
                }
            )
            if duplicate_patterns:
                errors.append(f"{target_id} asset_patterns contains duplicates: {duplicate_patterns}")
            if not any(pattern.endswith("-native-SHA256SUMS.txt") for pattern in normalized_patterns):
                errors.append(f"{target_id} asset_patterns must include native SHA256SUMS sidecar")
            catalog_row = rows.get(target_id)
            catalog_assets = catalog_row.get("assets") if isinstance(catalog_row, dict) else None
            if isinstance(catalog_assets, list):
                expected_assets = {str(asset) for asset in catalog_assets}
                actual_assets = set(normalized_patterns)
                if actual_assets != expected_assets:
                    errors.append(
                        f"{target_id} asset_patterns must match platform_targets assets "
                        f"(expected {sorted(expected_assets)}, got {sorted(actual_assets)})"
                    )
    source_web_ids = set()
    legacy_versions = set()
    for raw_item in require_list(matrix, "source_or_remote_only", errors):
        if not isinstance(raw_item, dict):
            continue
        source_web_ids.update(str(item) for item in raw_item.get("platform_target_ids", []))
        legacy_versions.update(str(item) for item in raw_item.get("windows_legacy_target_versions", []))

    if default_ids & script_ids:
        errors.append(f"targets cannot be both default native and script-supported: {sorted(default_ids & script_ids)}")
    for target_id in sorted(default_ids):
        row = rows.get(target_id)
        if not row:
            errors.append(f"default native target {target_id} missing from configs/platform_targets.json")
            continue
        if row.get("release_tier") != "native":
            errors.append(f"{target_id} release_tier must be native for default native releases")
        if row.get("github_release_channel") != "default-native":
            errors.append(f"{target_id} github_release_channel must be default-native")

    for target_id in sorted(script_ids):
        row = rows.get(target_id)
        if not row:
            errors.append(f"script-supported native target {target_id} missing from configs/platform_targets.json")
            continue
        if row.get("release_tier") != "script-supported-native":
            errors.append(f"{target_id} release_tier must be script-supported-native")
        if row.get("github_release_channel") != "manual-script-native":
            errors.append(f"{target_id} github_release_channel must be manual-script-native")

    source_web_channels = {
        "termux-web": "default-termux-web",
        "web-pwa": "default-web-pwa",
    }
    for target_id in sorted(source_web_ids):
        row = rows.get(target_id)
        if not row:
            errors.append(f"source/Web release target {target_id} missing from configs/platform_targets.json")
            continue
        release_tier = str(row.get("release_tier"))
        expected_channel = source_web_channels.get(release_tier)
        if expected_channel is None:
            errors.append(f"{target_id} release_tier must be one of {sorted(source_web_channels)}")
            continue
        if row.get("github_release_channel") != expected_channel:
            errors.append(f"{target_id} github_release_channel must be {expected_channel}")

    declared_legacy = {
        str(item.get("version"))
        for item in platform_targets.get("windows_legacy_targets", [])
        if isinstance(item, dict)
    }
    if legacy_versions and legacy_versions != declared_legacy:
        errors.append(
            "windows legacy release matrix versions must match configs/platform_targets.json "
            f"(expected {sorted(declared_legacy)}, got {sorted(legacy_versions)})"
        )
    return errors


def check_release_docs(matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    docs = {
        "README.md": read("README.md"),
        "README.tr.md": read("README.tr.md"),
        "docs/PLATFORM_PROMOTION_RUNBOOK.md": read("docs/PLATFORM_PROMOTION_RUNBOOK.md"),
        "docs/PLATFORM_SUPPORT.md": read("docs/PLATFORM_SUPPORT.md"),
        "docs/RELEASE_STRATEGY.md": read("docs/RELEASE_STRATEGY.md"),
        "docs/VERIFYING.md": read("docs/VERIFYING.md"),
    }
    for path, text in docs.items():
        if "configs/release_matrix.json" not in text:
            errors.append(f"{path} must mention configs/release_matrix.json")

    combined = "\n".join(normalize_markdown_pipes(text) for text in docs.values())
    searchable = re.sub(r"\s+", " ", combined)
    for snippet in (
        "default GitHub release",
        "script-supported",
        "not uploaded by the default GitHub release workflow",
        "python scripts/check_release_matrix.py",
    ):
        if snippet not in searchable:
            errors.append(f"release matrix docs missing required wording: {snippet}")
    version = read_project_version(errors)
    for _, pattern in release_asset_patterns(matrix):
        variants = release_asset_doc_variants(str(pattern), version)
        if not any(variant in combined for variant in variants):
            errors.append(f"release docs missing matrix asset pattern: {pattern}")
    for snippet in STALE_DEFAULT_ARTIFACT_SNIPPETS:
        if snippet in combined:
            errors.append(f"release docs still advertise stale default artifact pattern: {snippet}")
    return errors


def release_asset_doc_variants(pattern: str, version: str) -> set[str]:
    variants = {pattern}
    if version:
        variants.add(pattern.replace(f"v{version}", "v<project.version>"))
    return variants


def check_release_helper_packaging() -> list[str]:
    helper = read("scripts/make_release.py")
    if '    "configs",' not in helper:
        return ["scripts/make_release.py source bundles must include configs/release_matrix.json through configs/"]
    return []


def expected_target_bundle_names(version: str, errors: list[str]) -> set[str]:
    make_release = load_make_release(errors)
    if make_release is None:
        return set()
    return {
        f"{make_release.NAME}-v{version}-{target.suffix}.{target.archive_format}"
        for target in make_release.TARGETS
    }


def load_make_release(errors: list[str]) -> ModuleType | None:
    path = ROOT / "scripts" / "make_release.py"
    spec = importlib.util.spec_from_file_location("make_release_for_matrix_check", path)
    if spec is None or spec.loader is None:
        errors.append("cannot import scripts/make_release.py")
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_project_version(errors: list[str]) -> str:
    pyproject = read("pyproject.toml")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject)
    if not match:
        errors.append("pyproject.toml does not define project.version")
        return ""
    return match.group(1)


def load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing {repo_path(path)}")
        return {}
    except json.JSONDecodeError as exc:
        errors.append(f"{repo_path(path)} is not valid JSON: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{repo_path(path)} must contain a JSON object")
        return {}
    return data


def require_mapping(parent: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"configs/release_matrix.json {key} must be an object")
        return {}
    return value


def require_list(parent: dict[str, Any], key: str, errors: list[str]) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        errors.append(f"configs/release_matrix.json {key} must be a list")
        return []
    return value


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


def normalize_markdown_pipes(text: str) -> str:
    return text.replace("\\|", "|")


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def repo_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
