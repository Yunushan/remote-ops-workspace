from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "native_installer_smoke.json"
MATRIX_PATH = ROOT / "configs" / "release_matrix.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
REQUIRED_LIFECYCLE_STEPS = ("install", "verify", "upgrade", "uninstall")
REQUIRED_FORMATS = {"exe", "msi", "dmg", "pkg", "deb", "rpm", "AppImage"}
FORMAT_SUFFIXES = {
    "exe": "-setup.exe",
    "msi": ".msi",
    "dmg": ".dmg",
    "pkg": ".pkg",
    "deb": ".deb",
    "rpm": ".rpm",
    "AppImage": ".AppImage",
}


def main() -> int:
    errors: list[str] = []
    config = load_json(CONFIG_PATH, errors)
    matrix = load_json(MATRIX_PATH, errors)
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8") if WORKFLOW_PATH.exists() else ""
    if not workflow:
        errors.append("missing .github/workflows/release.yml")

    if config:
        errors.extend(check_config_schema(config))
        errors.extend(check_scripts_exist(config))
        if workflow:
            errors.extend(check_workflow_wiring(config, workflow))
        errors.extend(check_docs(config))
    if config and matrix:
        errors.extend(check_release_matrix_formats(config, matrix))

    if errors:
        for error in errors:
            print(f"native installer smoke: {error}", file=sys.stderr)
        return 1
    print("native installer smoke contract passed")
    return 0


def check_config_schema(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if config.get("schema_version") != 1:
        errors.append("configs/native_installer_smoke.json schema_version must be 1")
    required = {str(item) for item in config.get("required_formats", [])}
    if required != REQUIRED_FORMATS:
        errors.append(
            "required_formats must cover native installer formats "
            f"(expected {sorted(REQUIRED_FORMATS)}, got {sorted(required)})"
        )
    platforms = require_mapping(config, "platforms", errors)
    seen_formats: set[str] = set()
    for platform, raw_platform in platforms.items():
        if not isinstance(raw_platform, dict):
            errors.append(f"platform {platform} smoke config must be an object")
            continue
        for key in ("workflow_job", "script", "dist"):
            if not str(raw_platform.get(key, "")).strip():
                errors.append(f"platform {platform} smoke config missing {key}")
        formats = raw_platform.get("formats")
        if not isinstance(formats, list) or not formats:
            errors.append(f"platform {platform} must define non-empty formats")
            continue
        for raw_format in formats:
            if not isinstance(raw_format, dict):
                errors.append(f"platform {platform} format entries must be objects")
                continue
            format_name = str(raw_format.get("format", ""))
            seen_formats.add(format_name)
            if format_name not in REQUIRED_FORMATS:
                errors.append(f"unknown native installer smoke format: {format_name}")
            artifact_glob = str(raw_format.get("artifact_glob", ""))
            expected_suffix = FORMAT_SUFFIXES.get(format_name)
            if expected_suffix and expected_suffix not in artifact_glob:
                errors.append(f"{platform} {format_name} artifact_glob must include {expected_suffix}")
            lifecycle = raw_format.get("lifecycle")
            if not isinstance(lifecycle, dict):
                errors.append(f"{platform} {format_name} must define lifecycle commands")
                continue
            for step in REQUIRED_LIFECYCLE_STEPS:
                if not str(lifecycle.get(step, "")).strip():
                    errors.append(f"{platform} {format_name} lifecycle missing {step}")
    if seen_formats != REQUIRED_FORMATS:
        errors.append(
            "native installer smoke formats must match required formats "
            f"(expected {sorted(REQUIRED_FORMATS)}, got {sorted(seen_formats)})"
        )
    return errors


def check_scripts_exist(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for platform, raw_platform in config.get("platforms", {}).items():
        if not isinstance(raw_platform, dict):
            continue
        script = ROOT / str(raw_platform.get("script", ""))
        if not script.exists():
            errors.append(f"{platform} smoke script missing: {repo_path(script)}")
            continue
        text = script.read_text(encoding="utf-8")
        for raw_format in raw_platform.get("formats", []):
            if not isinstance(raw_format, dict):
                continue
            format_name = str(raw_format.get("format", ""))
            suffix = FORMAT_SUFFIXES.get(format_name, format_name)
            if suffix not in text and format_name.lower() not in text.lower():
                errors.append(f"{repo_path(script)} must mention smoke format {format_name}")
        for step in REQUIRED_LIFECYCLE_STEPS:
            if step not in text.lower():
                errors.append(f"{repo_path(script)} must mention {step} smoke lifecycle")
        if str(platform) == "linux":
            errors.extend(check_linux_smoke_source_binding(script, text))
    return errors


def check_linux_smoke_source_binding(script: Path, text: str) -> list[str]:
    errors: list[str] = []
    required_snippets = {
        "--workflow-run-url must be canonical without surrounding whitespace or trailing slash": (
            "workflow run URL canonical validation"
        ),
        "--workflow-run-url must be a GitHub Actions run URL": "workflow run URL format validation",
        'REQUESTED_WORKFLOW_RUN_ID="$WORKFLOW_RUN_URL"': "workflow run id parsing",
        'REQUESTED_WORKFLOW_REPOSITORY="${WORKFLOW_RUN_URL#https://github.com/}"': (
            "workflow repository parsing"
        ),
        "GITHUB_SHA": "GitHub source SHA environment binding",
        "must match --source-head-sha": "source SHA mismatch failure",
        "GITHUB_RUN_ATTEMPT": "GitHub run-attempt environment binding",
        "must match --workflow-run-attempt": "run-attempt mismatch failure",
        "GITHUB_RUN_ID": "GitHub run-id environment binding",
        "GITHUB_REPOSITORY": "GitHub repository environment binding",
        "must match --workflow-run-url": "workflow URL mismatch failure",
        "target $TARGET does not match smoke arch $ARCH": "target/architecture mismatch failure",
        "--builder-evidence is required with --target": "builder evidence requirement",
        "--builder-evidence requires --target": "builder evidence target binding",
        "target $TARGET builder evidence file missing": "builder evidence file existence check",
        "BUILDER_BINDING_TSV": "builder evidence JSON parsing",
        "require_builder_match \"target\"": "builder evidence target match",
        "require_builder_match \"release_tag\"": "builder evidence release match",
        "require_builder_match \"workflow_run_url\"": "builder evidence workflow URL match",
        "require_builder_match \"workflow_run_attempt\"": "builder evidence workflow attempt match",
        "require_builder_match \"source_head_sha\"": "builder evidence source SHA match",
        "require_builder_match \"observed_git_head_sha\"": "builder evidence git HEAD match",
        "require_builder_match \"security_patch_evidence.python_ssl_openssl\"": (
            "builder evidence Python OpenSSL security match"
        ),
        "require_builder_match \"security_patch_evidence.openssl_cli_version\"": (
            "builder evidence OpenSSL CLI security match"
        ),
        "require_builder_value \"security_patch_evidence.security_update_channel\"": (
            "builder evidence security update channel presence"
        ),
        "require_builder_value \"security_patch_evidence.cve_review_reference\"": (
            "builder evidence CVE review reference presence"
        ),
        "require_builder_match \"security_patch_evidence.security_update_channel\"": (
            "builder evidence security update channel match"
        ),
        "require_builder_match \"security_patch_evidence.cve_review_reference\"": (
            "builder evidence CVE review reference match"
        ),
        "openssl version | tr '[:upper:]' '[:lower:]'": "builder-compatible OpenSSL CLI normalization",
        'SMOKE_OBSERVED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"': (
            "UTC observation timestamp capture"
        ),
        "SMOKE_WORKFLOW_RUN_ID=\"$REQUESTED_WORKFLOW_RUN_ID\"": "workflow run id reuse in evidence id",
        "native installer smoke builder evidence: $BUILDER_EVIDENCE": "builder evidence path line",
        "native installer smoke host label: $SMOKE_HOST_LABEL": "builder-bound smoke host label",
        "native installer smoke evidence run id: $SMOKE_EVIDENCE_RUN_ID": "builder-bound smoke evidence run id",
        "native installer smoke observed at utc: $SMOKE_OBSERVED_AT_UTC": (
            "UTC observation timestamp evidence line"
        ),
        "native installer smoke security update channel: $SMOKE_SECURITY_UPDATE_CHANNEL": (
            "builder-bound security update channel"
        ),
        "native installer smoke CVE review reference: $SMOKE_CVE_REVIEW_REFERENCE": (
            "builder-bound CVE review reference"
        ),
    }
    for snippet, label in required_snippets.items():
        if snippet not in text:
            errors.append(f"{repo_path(script)} missing Linux smoke {label}: {snippet}")
    return errors


def check_workflow_wiring(config: dict[str, Any], workflow: str) -> list[str]:
    errors: list[str] = []
    for raw_platform in config.get("platforms", {}).values():
        if not isinstance(raw_platform, dict):
            continue
        job_name = str(raw_platform.get("workflow_job", ""))
        script = str(raw_platform.get("script", ""))
        script_variants = {script, script.replace("/", "\\")}
        block = workflow_job_block(workflow, job_name)
        if not block:
            errors.append(f"release workflow missing native smoke job block: {job_name}")
            continue
        build_index = block.find("Build ")
        smoke_index = min((index for item in script_variants if (index := block.find(item)) >= 0), default=-1)
        upload_index = block.find("actions/upload-artifact")
        if smoke_index < 0:
            errors.append(f"{job_name} must run {script}")
            continue
        if build_index < 0 or smoke_index < build_index:
            errors.append(f"{job_name} must run {script} after native build")
        if upload_index < 0 or smoke_index > upload_index:
            errors.append(f"{job_name} must run {script} before artifact upload")
        if "native installer smoke" not in block.lower():
            errors.append(f"{job_name} smoke step name must mention native installer smoke")
    return errors


def check_release_matrix_formats(config: dict[str, Any], matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    configured_formats = formats_by_platform(config)
    native_jobs = (
        matrix.get("default_github_release", {})
        .get("native_jobs", [])
    )
    for raw_job in native_jobs:
        if not isinstance(raw_job, dict):
            continue
        platform = str(raw_job.get("platform", ""))
        job_formats = formats_from_patterns(str(item) for item in raw_job.get("asset_patterns", []))
        smoke_formats = configured_formats.get(platform, set())
        missing = job_formats - smoke_formats
        if missing:
            errors.append(f"{platform} release matrix formats missing smoke coverage: {sorted(missing)}")
    return errors


def check_docs(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    docs = {
        "README.md": read("README.md"),
        "docs/PLATFORM_SUPPORT.md": read("docs/PLATFORM_SUPPORT.md"),
        "docs/RELEASE_STRATEGY.md": read("docs/RELEASE_STRATEGY.md"),
        "docs/VERIFYING.md": read("docs/VERIFYING.md"),
    }
    combined = "\n".join(docs.values())
    for snippet in (
        "configs/native_installer_smoke.json",
        "scripts/check_native_installer_smoke.py",
        "install, verify, upgrade and uninstall",
    ):
        if snippet not in combined:
            errors.append(f"native installer smoke docs missing required wording: {snippet}")
    for raw_platform in config.get("platforms", {}).values():
        if not isinstance(raw_platform, dict):
            continue
        script = str(raw_platform.get("script", ""))
        if script not in combined:
            errors.append(f"native installer smoke docs must mention {script}")
    return errors


def formats_by_platform(config: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for platform, raw_platform in config.get("platforms", {}).items():
        if not isinstance(raw_platform, dict):
            continue
        result[str(platform)] = {
            str(item.get("format"))
            for item in raw_platform.get("formats", [])
            if isinstance(item, dict)
        }
    return result


def formats_from_patterns(patterns: object) -> set[str]:
    formats: set[str] = set()
    for pattern in patterns:
        for format_name, suffix in FORMAT_SUFFIXES.items():
            if suffix in pattern:
                formats.add(format_name)
    return formats


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
        errors.append(f"configs/native_installer_smoke.json {key} must be an object")
        return {}
    return value


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
