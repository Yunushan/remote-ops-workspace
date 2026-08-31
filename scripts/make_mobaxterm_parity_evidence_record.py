from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from remote_ops_workspace.moba_customizer import (  # noqa: E402
    validate_professional_deployment_evidence,
)
from remote_ops_workspace.moba_macros import validate_macro_live_replay_evidence  # noqa: E402
from remote_ops_workspace.moba_mobapt import validate_mobapt_cache_evidence  # noqa: E402
from remote_ops_workspace.moba_servers import validate_moba_server_release_evidence  # noqa: E402
from remote_ops_workspace.moba_smartcards import validate_smartcard_release_evidence  # noqa: E402
from remote_ops_workspace.moba_text import validate_moba_text_release_evidence  # noqa: E402
from remote_ops_workspace.x11 import validate_moba_x_server_release_evidence  # noqa: E402
from scripts.check_moba_transport_terminal_evidence import (  # noqa: E402
    validate_moba_transport_terminal_evidence,
)
from scripts.check_mobaxterm_parity_evidence import (  # noqa: E402
    ARTICLE_SPECS,
    check_candidate_record,
    release_asset_repositories,
)

Validator = Callable[..., Any]

VALIDATORS: dict[str, Validator] = {
    "embedded-x-server": validate_moba_x_server_release_evidence,
    "mobapt-unix-runtime": validate_mobapt_cache_evidence,
    "embedded-server-suite": validate_moba_server_release_evidence,
    "moba-text-editor-diff": validate_moba_text_release_evidence,
    "macro-recorder": validate_macro_live_replay_evidence,
    "ssh-browser-26-4-smartcard": validate_smartcard_release_evidence,
    "professional-deployment": validate_professional_deployment_evidence,
    "shared-authenticated-transport-terminal-grid": validate_moba_transport_terminal_evidence,
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors, record = build_evidence_record(args)
    if errors:
        for error in errors:
            print(f"mobaxterm parity evidence record: {error}", file=sys.stderr)
        return 1
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not args.out:
        print(json.dumps(record, indent=2, sort_keys=True))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a candidate MobaXterm parity evidence record. Candidate generation never accepts "
            "or appends evidence; use finalize_mobaxterm_parity_evidence_record.py after review."
        )
    )
    parser.add_argument("--article-id", required=True, choices=sorted(ARTICLE_SPECS))
    parser.add_argument("--release-tag", required=True, help="release tag such as v1.0.22")
    parser.add_argument("--release-target", required=True, help="release target such as windows-x64")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument(
        "--release-asset-url",
        action="append",
        default=[],
        help="GitHub release asset URL for the artifact carrying this evidence",
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="artifact digest source as release-file-name=local-path",
    )
    parser.add_argument("--out", type=Path, help="write the generated record to this file")
    return parser.parse_args(argv)


def build_evidence_record(args: argparse.Namespace) -> tuple[list[str], dict[str, Any]]:
    article_id = str(args.article_id)
    spec = ARTICLE_SPECS[article_id]
    validator = VALIDATORS.get(article_id)
    if validator is None:
        return [
            f"{article_id} accepted-evidence validator is not implemented; "
            "the parity article remains incomplete"
        ], {}
    assets_dir = args.assets_dir or args.evidence.parent
    errors: list[str] = []
    if not args.evidence.is_file():
        errors.append(f"evidence file missing: {args.evidence}")
    if not assets_dir.is_dir():
        errors.append(f"assets dir missing: {assets_dir}")
    artifact_hashes, artifact_errors = artifact_sha256_map(args.artifact)
    errors.extend(artifact_errors)
    if not args.release_asset_url:
        errors.append("--release-asset-url is required")
    if errors:
        return errors, {}

    validation = validator(args.evidence, assets_dir=assets_dir)
    validation_dict = validation.to_dict()
    if not validation.passed:
        return [f"{article_id} evidence validation failed: {validation.errors}"], {}
    if article_id == "shared-authenticated-transport-terminal-grid":
        validation_summary = validation_dict.get("summary")
        summary = validation_summary if isinstance(validation_summary, dict) else {}
        validated_target = summary.get("release_target")
        validated_tag = summary.get("release_tag")
        validated_repository = summary.get("repository")
        if validated_target != str(args.release_target):
            return [
                f"{article_id} validated release_target {validated_target!r} must match "
                f"--release-target {str(args.release_target)!r}"
            ], {}
        if validated_tag != str(args.release_tag):
            return [
                f"{article_id} validated release_tag {validated_tag!r} must match "
                f"--release-tag {str(args.release_tag)!r}"
            ], {}
        asset_repositories = release_asset_repositories(args.release_asset_url)
        if asset_repositories != {validated_repository}:
            return [
                f"{article_id} validated repository {validated_repository!r} must exactly match "
                f"release asset repository {sorted(asset_repositories)!r}"
            ], {}

    record = {
        "article_id": article_id,
        "status": "candidate",
        "evidence_type": spec.evidence_type,
        "release_tag": str(args.release_tag),
        "release_target": str(args.release_target),
        "validation_command": spec.validation_command,
        "evidence_file_sha256": sha256_file(args.evidence),
        "evidence_assets_sha256": evidence_assets_sha256(assets_dir),
        "release_asset_urls": list(args.release_asset_url),
        "artifact_sha256": artifact_hashes,
        "checks": sorted(spec.required_checks),
        "validation_summary": validation_dict,
    }
    errors.extend(check_candidate_record(record))
    return errors, record


def artifact_sha256_map(items: list[str]) -> tuple[dict[str, str], list[str]]:
    hashes: dict[str, str] = {}
    errors: list[str] = []
    if not items:
        return hashes, ["--artifact is required at least once"]
    for item in items:
        if "=" not in item:
            errors.append(f"--artifact must be release-file-name=local-path: {item}")
            continue
        name, raw_path = item.split("=", 1)
        name = name.strip()
        path = Path(raw_path)
        if not name:
            errors.append(f"--artifact release file name is empty: {item}")
            continue
        if name in hashes:
            errors.append(f"duplicate --artifact release file name: {name}")
            continue
        if not path.is_file():
            errors.append(f"--artifact local path missing: {path}")
            continue
        hashes[name] = sha256_file(path)
    return hashes, errors


def evidence_assets_sha256(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hashes[path.resolve().relative_to(root.resolve()).as_posix()] = sha256_file(path)
    return hashes


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def registry_policy() -> str:
    return (
        "Only accepted evidence records in this file can close strict MobaXterm 26.4 Home/Professional parity "
        "articles. Accepted records must include one unique article_id, status accepted, a vX.Y.Z release_tag, "
        "a release_target, the exact validation command for that article, SHA-256 digests for the validated "
        "evidence JSON and evidence assets, release asset URLs under the same GitHub release tag, per-artifact "
        "SHA-256 digests, required article checks, and a validation summary proving the article evidence passed. "
        "Acceptance additionally requires the exact GitHub repository, source head SHA and tag source head SHA, "
        "the exact source workflow run URL and positive run attempt, reviewer provenance, and hashes of the "
        "published release bytes matching the accepted per-artifact SHA-256 values. Candidate generation cannot "
        "append or accept its own output; a separate reviewed finalization step is mandatory. "
        "Empty means the generated feature-family score remains separate from true product-depth parity."
    )


if __name__ == "__main__":
    raise SystemExit(main())
