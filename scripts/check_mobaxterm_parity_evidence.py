from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "configs" / "mobaxterm_parity_evidence.json"

SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
RELEASE_TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
GITHUB_REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
GITHUB_RELEASE_ASSET_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/releases/download/"
    r"(v\d+\.\d+\.\d+)/([A-Za-z0-9][A-Za-z0-9._+-]*)$"
)
GITHUB_WORKFLOW_RUN_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/actions/runs/([1-9]\d*)$"
)
GITHUB_REVIEW_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/"
    r"(?:pull/([1-9]\d*)#(?:pullrequestreview|issuecomment)-([1-9]\d*)|"
    r"issues/([1-9]\d*)#issuecomment-([1-9]\d*))$"
)
GITHUB_LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
UTC_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


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
    "shared-authenticated-transport-terminal-grid": ArticleSpec(
        article_id="shared-authenticated-transport-terminal-grid",
        evidence_type="moba-shared-transport-terminal-grid-release",
        validation_command=(
            "python scripts/check_moba_transport_terminal_evidence.py "
            "--evidence <evidence.json> --assets-dir <artifact-dir>"
        ),
        required_checks=frozenset(
            {
                "shared_authenticated_transport",
                "structured_connection_state",
                "real_terminal_grid",
                "alternate_screen_semantics",
                "cursor_color_mode_mouse_semantics",
                "real_connected_session",
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
    if registry.get("schema_version") != 2:
        errors.append("configs/mobaxterm_parity_evidence.json schema_version must be 2")
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
        "exact GitHub repository",
        "source head SHA",
        "run attempt",
        "reviewer provenance",
        "published release bytes",
    ):
        if snippet not in policy:
            errors.append(f"mobaxterm parity evidence policy missing required wording: {snippet}")
    if not isinstance(registry.get("accepted_evidence"), list):
        errors.append("mobaxterm parity evidence accepted_evidence must be a list")
    return errors


def check_record(row: dict[str, Any]) -> list[str]:
    return check_article_record(row, expected_status="accepted", require_acceptance_provenance=True)


def check_candidate_record(row: dict[str, Any]) -> list[str]:
    """Validate generator output without treating it as accepted evidence."""

    return check_article_record(row, expected_status="candidate", require_acceptance_provenance=False)


def check_article_record(
    row: dict[str, Any],
    *,
    expected_status: str,
    require_acceptance_provenance: bool,
) -> list[str]:
    article_id = str(row.get("article_id", ""))
    spec = ARTICLE_SPECS.get(article_id)
    if spec is None:
        return [f"accepted_evidence article_id is unknown: {article_id}"]
    errors: list[str] = []
    if row.get("status") != expected_status:
        errors.append(f"{article_id} status must be {expected_status}")
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
    if article_id == "shared-authenticated-transport-terminal-grid":
        errors.extend(
            check_transport_terminal_validation_identity(
                row,
                require_acceptance_provenance=require_acceptance_provenance,
            )
        )
    errors.extend(check_release_assets(article_id, release_tag, row.get("release_asset_urls"), row.get("artifact_sha256")))
    if require_acceptance_provenance:
        errors.extend(check_acceptance_provenance(article_id, release_tag, row))
    return errors


def check_acceptance_provenance(article_id: str, release_tag: str, row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    source = row.get("release_source")
    if not isinstance(source, dict):
        return [f"{article_id} release_source must be an object"]
    repository = source.get("repository")
    if not isinstance(repository, str) or not GITHUB_REPOSITORY_RE.fullmatch(repository):
        errors.append(f"{article_id} release_source.repository must be an exact GitHub owner/name value")
        repository = ""
    source_tag = source.get("release_tag")
    if source_tag != release_tag:
        errors.append(f"{article_id} release_source.release_tag must match release_tag {release_tag}")
    head_sha = source.get("head_sha")
    if not isinstance(head_sha, str) or not GIT_SHA_RE.fullmatch(head_sha):
        errors.append(f"{article_id} release_source.head_sha must be a 40-character lowercase Git SHA")
        head_sha = ""
    tag_source_head_sha = source.get("tag_source_head_sha")
    if not isinstance(tag_source_head_sha, str) or not GIT_SHA_RE.fullmatch(tag_source_head_sha):
        errors.append(f"{article_id} release_source.tag_source_head_sha must be a 40-character lowercase Git SHA")
    elif head_sha and tag_source_head_sha != head_sha:
        errors.append(f"{article_id} release_source.tag_source_head_sha must match release_source.head_sha")
    workflow_run_url = source.get("workflow_run_url")
    workflow_match = (
        GITHUB_WORKFLOW_RUN_RE.fullmatch(workflow_run_url)
        if isinstance(workflow_run_url, str)
        else None
    )
    if workflow_match is None:
        errors.append(f"{article_id} release_source.workflow_run_url must be an exact GitHub Actions run URL")
    elif repository and workflow_match.group(1) != repository:
        errors.append(
            f"{article_id} release_source.workflow_run_url repository must match "
            f"release_source.repository {repository}"
        )
    run_attempt = source.get("run_attempt")
    if not isinstance(run_attempt, int) or isinstance(run_attempt, bool) or run_attempt < 1:
        errors.append(f"{article_id} release_source.run_attempt must be a positive integer")

    asset_repositories = release_asset_repositories(row.get("release_asset_urls"))
    if repository and asset_repositories != {repository}:
        errors.append(
            f"{article_id} release asset repository must exactly match "
            f"release_source.repository {repository}, got {sorted(asset_repositories)}"
        )

    review = row.get("acceptance_review")
    reviewer = ""
    reviewed_at = ""
    if not isinstance(review, dict):
        errors.append(f"{article_id} acceptance_review must be an object")
    else:
        raw_reviewer = review.get("reviewer")
        if not isinstance(raw_reviewer, str) or not GITHUB_LOGIN_RE.fullmatch(raw_reviewer):
            errors.append(f"{article_id} acceptance_review.reviewer must be an exact GitHub login")
        else:
            reviewer = raw_reviewer
        review_url = review.get("review_url")
        review_match = GITHUB_REVIEW_RE.fullmatch(review_url) if isinstance(review_url, str) else None
        if review_match is None:
            errors.append(f"{article_id} acceptance_review.review_url must be an exact GitHub review URL")
        elif repository and review_match.group(1) != repository:
            errors.append(
                f"{article_id} acceptance_review.review_url repository must match "
                f"release_source.repository {repository}"
            )
        raw_reviewed_at = review.get("reviewed_at")
        if not valid_utc_timestamp(raw_reviewed_at):
            errors.append(f"{article_id} acceptance_review.reviewed_at must be an exact UTC RFC3339 timestamp")
        else:
            reviewed_at = str(raw_reviewed_at)

    byte_proof = row.get("release_asset_bytes")
    if not isinstance(byte_proof, dict):
        errors.append(f"{article_id} release_asset_bytes must be an object")
    else:
        if byte_proof.get("verified") is not True:
            errors.append(f"{article_id} release_asset_bytes.verified must be true")
        if reviewer and byte_proof.get("verified_by") != reviewer:
            errors.append(f"{article_id} release_asset_bytes.verified_by must match acceptance reviewer")
        if reviewed_at and byte_proof.get("verified_at") != reviewed_at:
            errors.append(f"{article_id} release_asset_bytes.verified_at must match acceptance review time")
        byte_hashes = byte_proof.get("sha256")
        errors.extend(check_sha_map(byte_hashes, f"{article_id} release_asset_bytes.sha256"))
        artifact_hashes = row.get("artifact_sha256")
        if isinstance(byte_hashes, dict) and isinstance(artifact_hashes, dict) and byte_hashes != artifact_hashes:
            errors.append(
                f"{article_id} release_asset_bytes.sha256 must exactly match artifact_sha256"
            )
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


def check_transport_terminal_validation_identity(
    row: dict[str, Any],
    *,
    require_acceptance_provenance: bool,
) -> list[str]:
    article_id = "shared-authenticated-transport-terminal-grid"
    validation = row.get("validation_summary")
    summary = validation.get("summary") if isinstance(validation, dict) else None
    if not isinstance(summary, dict):
        return [f"{article_id} validation_summary.summary must bind source provenance"]
    errors: list[str] = []
    repository = summary.get("repository")
    if not isinstance(repository, str) or not GITHUB_REPOSITORY_RE.fullmatch(repository):
        errors.append(f"{article_id} validation summary repository must be an exact GitHub owner/name")
        repository = ""
    if summary.get("release_tag") != row.get("release_tag"):
        errors.append(f"{article_id} validation summary release_tag must match record release_tag")
    if summary.get("release_target") != row.get("release_target"):
        errors.append(f"{article_id} validation summary release_target must match record release_target")
    source_head_sha = summary.get("source_head_sha")
    if not isinstance(source_head_sha, str) or not GIT_SHA_RE.fullmatch(source_head_sha):
        errors.append(f"{article_id} validation summary source_head_sha must be a lowercase Git SHA")
        source_head_sha = ""
    workflow_run_url = summary.get("workflow_run_url")
    workflow_match = (
        GITHUB_WORKFLOW_RUN_RE.fullmatch(workflow_run_url)
        if isinstance(workflow_run_url, str)
        else None
    )
    if workflow_match is None:
        errors.append(f"{article_id} validation summary workflow_run_url must be exact")
    elif repository and workflow_match.group(1) != repository:
        errors.append(f"{article_id} validation summary workflow_run_url repository must match")
    run_attempt = summary.get("run_attempt")
    if not isinstance(run_attempt, int) or isinstance(run_attempt, bool) or run_attempt < 1:
        errors.append(f"{article_id} validation summary run_attempt must be a positive integer")
    if require_acceptance_provenance:
        source = row.get("release_source")
        if not isinstance(source, dict):
            errors.append(f"{article_id} release_source must bind validated source provenance")
        else:
            expected = {
                "repository": repository,
                "release_tag": summary.get("release_tag"),
                "head_sha": source_head_sha,
                "workflow_run_url": workflow_run_url,
                "run_attempt": run_attempt,
            }
            for key, value in expected.items():
                if source.get(key) != value:
                    errors.append(
                        f"{article_id} release_source.{key} must match validation summary provenance"
                    )
    return errors


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


def release_asset_repositories(raw_urls: Any) -> set[str]:
    if not isinstance(raw_urls, list):
        return set()
    repositories: set[str] = set()
    for value in raw_urls:
        if not isinstance(value, str):
            continue
        match = GITHUB_RELEASE_ASSET_RE.fullmatch(value)
        if match:
            repositories.add(match.group(1))
    return repositories


def valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not UTC_TIMESTAMP_RE.fullmatch(value):
        return False
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return parsed.tzinfo is None


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
