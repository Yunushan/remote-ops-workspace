#!/usr/bin/env python3
"""Write deterministic, boundary-aware GitHub release notes.

Release assets are only useful when a consumer can tell which channel they are
getting and which compatibility claims are actually proven.  This helper is
called by the release workflow after the asset gate and before attestation so
the release page cannot silently omit that context.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG_RE = re.compile(r"v\d+\.\d+\.\d+\Z")
GOAL_TARGETS = (
    "linux-i386",
    "linux-armhf",
    "windows-xp-native-x86",
    "windows-xp-native-x64",
)


def load_json(root: Path, relative: str) -> dict[str, object]:
    value = json.loads((root / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{relative} must contain a JSON object")
    return value


def accepted_target_ids(registry: dict[str, object]) -> set[str]:
    accepted = registry.get("accepted_evidence", [])
    if not isinstance(accepted, list):
        return set()
    result: set[str] = set()
    for item in accepted:
        if isinstance(item, dict) and isinstance(item.get("target"), str):
            result.add(item["target"])
    return result


def moba_counts(root: Path, registry: dict[str, object]) -> tuple[int, int]:
    checker_path = root / "scripts" / "check_mobaxterm_parity_evidence.py"
    spec = importlib.util.spec_from_file_location("moba_parity_checker_for_release_notes", checker_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load MobaXterm parity article catalog")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    required = getattr(module, "ARTICLE_SPECS", {})
    required_count = len(required) if isinstance(required, dict) else 0
    accepted = registry.get("accepted_evidence", [])
    accepted_count = (
        sum(1 for item in accepted if isinstance(item, dict) and item.get("status") == "accepted")
        if isinstance(accepted, list)
        else 0
    )
    return accepted_count, required_count


def write_notes(
    *, tag: str, channel: str, repository: str, output: Path, root: Path | None = None
) -> None:
    if not TAG_RE.fullmatch(tag):
        raise ValueError(f"release tag must be vX.Y.Z, got {tag!r}")
    if channel not in {"production-signed", "unsigned-preview"}:
        raise ValueError(f"unsupported release channel: {channel!r}")
    if not repository or "/" not in repository or repository.startswith("/"):
        raise ValueError("repository must be owner/name")

    source_root = (root or ROOT).resolve()
    matrix = load_json(source_root, "configs/release_matrix.json")
    platform_registry = load_json(source_root, "configs/platform_verified_evidence.json")
    moba_registry = load_json(source_root, "configs/mobaxterm_parity_evidence.json")
    accepted_platform = accepted_target_ids(platform_registry)
    missing_platform = [target for target in GOAL_TARGETS if target not in accepted_platform]
    moba_accepted_count, moba_required_count = moba_counts(source_root, moba_registry)

    default_release = matrix.get("default_github_release", {})
    if not isinstance(default_release, dict):
        raise ValueError("release matrix default_github_release must be an object")
    source = default_release.get("source_and_python", {})
    native = default_release.get("native_jobs", [])
    source_bundles = source.get("target_bundles", []) if isinstance(source, dict) else []
    native_jobs = native if isinstance(native, list) else []
    source_names = ", ".join(
        str(item.get("target", item)) if isinstance(item, dict) else str(item)
        for item in source_bundles
    ) or "source/Python bundles"
    native_names = ", ".join(
        str(item.get("job", item.get("platform", item))) if isinstance(item, dict) else str(item)
        for item in native_jobs
    ) or "native installers"

    if channel == "production-signed":
        channel_section = (
            "**Channel: production-signed.** Windows artifacts are Authenticode-signed and "
            "macOS artifacts are signed/notarized by the protected release environment. "
            "Verify the published checksums, SBOM, and GitHub artifact attestation before deployment."
        )
    else:
        channel_section = (
            "**Channel: unsigned preview.** Signing/notarization material was unavailable. "
            "Native installers are for testing only and must not be treated as trusted production artifacts. "
            "Use a signed release for production deployment."
        )

    lines = [
        f"# {tag}",
        "",
        channel_section,
        "",
        "## Included release families",
        "",
        f"- Source/Python: {source_names}.",
        f"- Native jobs: {native_names}.",
        "- Every published file is validated against the release matrix and accompanied by SHA-256 checksums; the source/Python environment also includes an SBOM.",
        "",
        "## Support boundaries",
        "",
        "- The default release does not claim verified native-host readiness for Linux i386, Linux armhf, or Windows XP x86/x64.",
        f"- Protected platform evidence accepted for this source is {len(accepted_platform)}/{len(GOAL_TARGETS)} targets; missing: {', '.join(missing_platform) or 'none'}.",
        "- Legacy XP compatibility remains isolated and opt-in; modern platform security defaults are not weakened.",
        f"- Strict MobaXterm parity evidence accepted for this source is {moba_accepted_count}/{moba_required_count} tracked articles.",
        "",
        "## Verification",
        "",
        f"- Release page: https://github.com/{repository}/releases/tag/{tag}",
        f"- Verify the source and release matrix with `python scripts/verify.py --quick --no-cli-smoke --release-tag {tag}`.",
        "- For protected-platform promotion, run the evidence source-ref, accepted-record, release-asset, and remote byte-provenance gates documented in `docs/PLATFORM_SUPPORT.md`; do not substitute candidate builds for accepted host evidence.",
        "",
        "This release note is generated from the checked-in release and evidence registries. It intentionally reports missing evidence instead of inferring support from a successful candidate build.",
        "",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--channel", choices=("production-signed", "unsigned-preview"), required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--root",
        type=Path,
        help="immutable release-source checkout containing configs/ and scripts/",
    )
    args = parser.parse_args()
    write_notes(
        tag=args.tag,
        channel=args.channel,
        repository=args.repository,
        output=args.out,
        root=args.root,
    )
    print(f"wrote release notes: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
