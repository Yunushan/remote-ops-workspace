from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "configs" / "mobaxterm_parity_evidence.json"

SHA256_RE = re.compile(r"[0-9a-f]{64}")
RELEASE_TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
GITHUB_RELEASE_ASSET_RE = re.compile(
    r"^https://github\.com/([^/]+/[^/]+)/releases/download/(v\d+\.\d+\.\d+)/.+"
)


@dataclass(frozen=True)
class ArticleSpec:
    article_id: str
    evidence_type: str
    validation_command: str
    required_checks: frozenset[str]


ARTICLE_SPECS: dict[str, ArticleSpec] = {
    "embedded-x-server": ArticleSpec(
        article_id="embedded-x-server",
        evidence_type="moba-xserver-release",
        validation_command=(
            "python scripts/check_moba_xserver_release_evidence.py "
            "--evidence <evidence.json> --assets-dir <artifact-dir>"
        ),
        required_checks=frozenset(
            {
                "packaged_runtime_hashes",
                "x11_smoke_passed",
                "forwarded_gui_screenshot_hashes",
                "release_asset_attachment",
            }
        ),
    ),
    "mobapt-unix-runtime": ArticleSpec(
        article_id="mobapt-unix-runtime",
        evidence_type="mobapt-cache-release",
        validation_command=(
            "python scripts/check_mobapt_cache_evidence.py "
            "--evidence <evidence.json> --assets-dir <artifact-dir>"
        ),
        required_checks=frozenset(
            {
                "runtime_manifest_hash",
                "offline_package_archives",
                "install_test_passed",
                "terminal_probe_passed",
                "release_asset_attachment",
            }
        ),
    ),
    "embedded-server-suite": ArticleSpec(
        article_id="embedded-server-suite",
        evidence_type="moba-server-release",
        validation_command=(
            "python scripts/check_moba_server_release_evidence.py "
            "--evidence <evidence.json> --assets-dir <artifact-dir>"
        ),
        required_checks=frozenset(
            {
                "packaged_daemon_hashes",
                "auth_hardening_policy",
                "real_client_proof",
                "all_required_services",
                "release_asset_attachment",
            }
        ),
    ),
    "moba-text-editor-diff": ArticleSpec(
        article_id="moba-text-editor-diff",
        evidence_type="moba-text-remote-edit-release",
        validation_command=(
            "python scripts/check_moba_text_remote_edit_evidence.py "
            "--evidence <evidence.json> --assets-dir <artifact-dir>"
        ),
        required_checks=frozenset(
            {
                "editor_tab_open_proof",
                "save_conflict_review",
                "upload_proof",
                "real_connected_session",
                "release_asset_attachment",
            }
        ),
    ),
    "macro-recorder": ArticleSpec(
        article_id="macro-recorder",
        evidence_type="moba-macro-live-release",
        validation_command=(
            "python scripts/check_moba_macro_live_evidence.py "
            "--evidence <evidence.json> --assets-dir <artifact-dir>"
        ),
        required_checks=frozenset(
            {
                "gui_capture_controls",
                "confirmation_cancel_review",
                "real_connected_replay",
                "per_keystroke_timing",
                "release_asset_attachment",
            }
        ),
    ),
    "ssh-browser-26-4-smartcard": ArticleSpec(
        article_id="ssh-browser-26-4-smartcard",
        evidence_type="moba-smartcard-26-4-release",
        validation_command=(
            "python scripts/check_moba_smartcard_evidence.py "
            "--evidence <evidence.json> --assets-dir <artifact-dir>"
        ),
        required_checks=frozenset(
            {
                "smartcard_management_ui",
                "openssh_public_key_retrieval",
                "expert_certificate_selection",
                "mobagent_handoff",
                "same_parameters_sftp",
                "real_connected_session",
                "release_asset_attachment",
            }
        ),
    ),
    "professional-deployment": ArticleSpec(
        article_id="professional-deployment",
        evidence_type="moba-professional-deployment-release",
        validation_command=(
            "python scripts/check_moba_professional_deployment_evidence.py "
            "--evidence <evidence.json> --assets-dir <artifact-dir>"
        ),
        required_checks=frozenset(
            {
                "branded_windows_exe",
                "branded_windows_msi",
                "all_policy_surfaces",
                "signed_organization_update_channel",
                "bundle_manifest_sha256",
                "release_asset_attachment",
            }
        ),
    ),
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    registry = read_json(args.registry)
    errors = check_mobaxterm_parity_evidence(registry=registry, require_complete=args.require_complete)
    if errors:
        for error in errors:
            print(f"mobaxterm parity evidence: {error}", file=sys.stderr)
        return 1
    accepted = accepted_article_ids(registry)
    missing = sorted(set(ARTICLE_SPECS) - accepted)
    if args.json:
        print(
            json.dumps(
                {
                    "passed": True,
                    "accepted_count": len(accepted),
                    "article_count": len(ARTICLE_SPECS),
                    "missing_articles": missing,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            "mobaxterm parity evidence checks passed "
            f"({len(accepted)}/{len(ARTICLE_SPECS)} accepted; missing: {', '.join(missing) or 'none'})"
        )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate accepted MobaXterm parity evidence records.")
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--require-complete", action="store_true", help="fail unless every parity article has accepted evidence")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def check_mobaxterm_parity_evidence(
    *,
    registry: dict[str, Any] | None = None,
    require_complete: bool = False,
) -> list[str]:
    data = registry if registry is not None else read_json(REGISTRY_PATH)
    errors: list[str] = []
    errors.extend(check_schema(data))
    if errors:
        return errors
    rows = data.get("accepted_evidence", [])
    for row in rows:
        if not isinstance(row, dict):
            errors.append("accepted_evidence entries must be objects")
            continue
        errors.extend(check_record(row))
    errors.extend(check_registry_consistency(data, require_complete=require_complete))
    return errors


def check_schema(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if registry.get("schema_version") != 1:
        errors.append("configs/mobaxterm_parity_evidence.json schema_version must be 1")
    policy = str(registry.get("policy", ""))
    for snippet in (
        "Only accepted evidence records",
        "strict MobaXterm 26.4 Home/Professional parity",
        "unique article_id",
        "release_tag",
        "validation command",
        "SHA-256",
        "release asset URLs",
        "per-artifact SHA-256",
    ):
        if snippet not in policy:
            errors.append(f"mobaxterm parity evidence policy missing required wording: {snippet}")
    if not isinstance(registry.get("accepted_evidence"), list):
        errors.append("mobaxterm parity evidence accepted_evidence must be a list")
    return errors


def check_record(row: dict[str, Any]) -> list[str]:
    article_id = str(row.get("article_id", ""))
    spec = ARTICLE_SPECS.get(article_id)
    if spec is None:
        return [f"accepted_evidence article_id is unknown: {article_id}"]
    errors: list[str] = []
    if row.get("status") != "accepted":
        errors.append(f"{article_id} status must be accepted")
    if row.get("evidence_type") != spec.evidence_type:
        errors.append(f"{article_id} evidence_type must be {spec.evidence_type}")
    release_tag = str(row.get("release_tag", ""))
    if not RELEASE_TAG_RE.fullmatch(release_tag):
        errors.append(f"{article_id} release_tag must look like vX.Y.Z")
    if not str(row.get("release_target", "")).strip():
        errors.append(f"{article_id} release_target must be set")
    if row.get("validation_command") != spec.validation_command:
        errors.append(f"{article_id} validation_command must be {spec.validation_command!r}")
    errors.extend(check_sha(row.get("evidence_file_sha256"), f"{article_id} evidence_file_sha256"))
    errors.extend(check_sha_map(row.get("evidence_assets_sha256"), f"{article_id} evidence_assets_sha256"))
    errors.extend(check_required_checks(row, spec))
    errors.extend(check_validation_summary(article_id, row.get("validation_summary")))
    errors.extend(check_release_assets(article_id, release_tag, row.get("release_asset_urls"), row.get("artifact_sha256")))
    return errors


def check_required_checks(row: dict[str, Any], spec: ArticleSpec) -> list[str]:
    raw_checks = row.get("checks")
    if not isinstance(raw_checks, list):
        return [f"{spec.article_id} checks must be a list"]
    checks = {str(check) for check in raw_checks}
    missing = sorted(spec.required_checks - checks)
    if missing:
        return [f"{spec.article_id} evidence missing required checks: {missing}"]
    return []


def check_validation_summary(article_id: str, summary: Any) -> list[str]:
    if not isinstance(summary, dict) or not summary:
        return [f"{article_id} validation_summary must be a non-empty object"]
    if summary.get("passed") is not True:
        return [f"{article_id} validation_summary.passed must be true"]
    if not isinstance(summary.get("summary"), dict):
        return [f"{article_id} validation_summary.summary must be an object"]
    errors = summary.get("errors")
    if errors not in ([], None):
        return [f"{article_id} validation_summary.errors must be empty"]
    return []


def check_release_assets(article_id: str, release_tag: str, raw_urls: Any, raw_hashes: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw_urls, list) or not raw_urls:
        errors.append(f"{article_id} release_asset_urls must be a non-empty list")
        raw_urls = []
    if not isinstance(raw_hashes, dict) or not raw_hashes:
        errors.append(f"{article_id} artifact_sha256 must be a non-empty object")
        raw_hashes = {}
    hashes = {str(name): str(value) for name, value in raw_hashes.items()} if isinstance(raw_hashes, dict) else {}
    repositories: set[str] = set()
    seen_names: set[str] = set()
    for url in raw_urls:
        text = str(url)
        match = GITHUB_RELEASE_ASSET_RE.fullmatch(text)
        if not match:
            errors.append(f"{article_id} release asset URL is not a GitHub release asset URL: {text}")
            continue
        repositories.add(match.group(1))
        url_release_tag = match.group(2)
        if release_tag and url_release_tag != release_tag:
            errors.append(f"{article_id} release asset URL tag must match release_tag {release_tag}: {text}")
        name = Path(text).name
        if name in seen_names:
            errors.append(f"{article_id} release_asset_urls contain duplicate file: {name}")
        seen_names.add(name)
        if name not in hashes:
            errors.append(f"{article_id} artifact_sha256 missing release asset file: {name}")
    if len(repositories) > 1:
        errors.append(f"{article_id} release_asset_urls must use one GitHub repository, got {sorted(repositories)}")
    for name, digest in sorted(hashes.items()):
        if not SHA256_RE.fullmatch(digest):
            errors.append(f"{article_id} artifact_sha256 for {name} must be a SHA-256 hex digest")
    unexpected = sorted(set(hashes) - seen_names)
    if seen_names and unexpected:
        errors.append(f"{article_id} artifact_sha256 references files not in release_asset_urls: {unexpected}")
    return errors


def check_sha(value: Any, label: str) -> list[str]:
    if not SHA256_RE.fullmatch(str(value or "")):
        return [f"{label} must be a SHA-256 hex digest"]
    return []


def check_sha_map(value: Any, label: str) -> list[str]:
    if not isinstance(value, dict) or not value:
        return [f"{label} must be a non-empty object"]
    errors: list[str] = []
    for name, digest in sorted((str(key), str(raw)) for key, raw in value.items()):
        if Path(name).is_absolute() or ".." in Path(name).parts:
            errors.append(f"{label} path must be relative and stay inside the evidence root: {name}")
        if not SHA256_RE.fullmatch(digest):
            errors.append(f"{label} for {name} must be a SHA-256 hex digest")
    return errors


def check_registry_consistency(registry: dict[str, Any], *, require_complete: bool) -> list[str]:
    rows = registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return []
    errors: list[str] = []
    seen: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        article_id = str(row.get("article_id", ""))
        if article_id:
            seen[article_id] = seen.get(article_id, 0) + 1
    for article_id, count in sorted(seen.items()):
        if count > 1:
            errors.append(f"accepted_evidence article_id must be unique: {article_id}")
    missing = sorted(set(ARTICLE_SPECS) - set(seen))
    if require_complete and missing:
        errors.append(f"accepted_evidence missing required MobaXterm parity articles: {missing}")
    return errors


def accepted_article_ids(registry: dict[str, Any]) -> set[str]:
    rows = registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return set()
    return {str(row.get("article_id", "")) for row in rows if isinstance(row, dict) and row.get("status") == "accepted"}


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path} root must be a JSON object")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
