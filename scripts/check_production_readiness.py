"""Run the strict certification gate for a published release."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

IDENTITIES = {
    "RELEASE_TAG": (r"v[0-9]+\.[0-9]+\.[0-9]+", "the exact release tag (vX.Y.Z)"),
    "RELEASE_REPOSITORY": (r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", "the GitHub owner/repository"),
    "RELEASE_SHA": (r"[0-9a-f]{40}", "the full lowercase tagged commit SHA"),
    "RELEASE_MOBAXTERM_REGISTRY_COMMIT": (r"[0-9a-fA-F]{40}", "the full reviewed parity registry commit SHA"),
}
DIRECTORIES = {
    "RELEASE_ASSETS_DIR": "the downloaded release assets directory",
    "RELEASE_LICENSE_EVIDENCE_ROOT": "the closed-world evidence bundle directory",
    "RELEASE_PLATFORM_SOURCE_ARCHIVES": "the retained original Actions ZIP directory",
    "RELEASE_MOBAXTERM_EVIDENCE_ROOT": "the reviewed parity evidence directory",
}
FILES = {
    "RELEASE_LICENSE_EVIDENCE": "the signed approval JSON",
    "RELEASE_LICENSE_SIGNATURE": "the detached approval signature JSON",
    "RELEASE_CANDIDATE_INVENTORY": "the sealed build-candidate inventory JSON",
    "RELEASE_PLATFORM_EVIDENCE_REGISTRY": "the signed protected-platform registry JSON",
    "RELEASE_TAG_GOVERNANCE_ATTESTATION": "the signed tag ruleset snapshot JSON",
    "RELEASE_TAG_GOVERNANCE_SIGNATURE": "the detached tag-governance signature JSON",
}


def read_inputs(environment: Mapping[str, str]) -> tuple[dict[str, str], list[str]]:
    inputs = {"RELEASE_ASSETS_DIR": "release-assets", **environment}
    errors = [
        f"{key} must identify {description}"
        for key, (pattern, description) in IDENTITIES.items()
        if re.fullmatch(pattern, inputs.get(key, "")) is None
    ]
    if not inputs.get("RELEASE_PROFESSIONAL_UPDATE_ORIGINS", "").split():
        errors.append("RELEASE_PROFESSIONAL_UPDATE_ORIGINS must list the approved HTTPS origins")
    for key, description in DIRECTORIES.items():
        value = inputs.get(key, "")
        path = ROOT / value
        if not value or not path.is_dir():
            errors.append(f"{key} must point to {description}")
        inputs[key] = str(path)
    for key, description in FILES.items():
        value = inputs.get(key, "")
        path = ROOT / value
        try:
            valid = bool(value) and path.is_file() and path.stat().st_size > 0
        except OSError:
            valid = False
        if not valid:
            errors.append(f"{key} must point to a nonempty file containing {description}")
        inputs[key] = str(path)
    return inputs, errors


def require_checkout_identity(tag: str, sha: str) -> None:
    for ref, label in ((f"refs/tags/{tag}", "local release tag"), ("HEAD", "checkout HEAD")):
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or result.stdout.strip() != sha:
            raise ValueError(f"{label} must resolve to RELEASE_SHA ({sha})")


def audit_commands(inputs: Mapping[str, str]) -> tuple[list[str], ...]:
    tag = inputs["RELEASE_TAG"]
    sha = inputs["RELEASE_SHA"]
    repository = inputs["RELEASE_REPOSITORY"]
    assets = inputs["RELEASE_ASSETS_DIR"]
    registry = inputs["RELEASE_PLATFORM_EVIDENCE_REGISTRY"]
    return (
        ["check_repository_cleanup.py", "--require-clean"],
        ["check_release_version.py", "--release-tag", tag],
        ["check_release_maturity.py", "--release-tag", tag],
        ["verify.py", "--production-quality", "--release-tag", tag],
        ["check_python315_ci_evidence.py", "--repository", repository, "--branch", "main", "--sha", sha],
        [
            "check_platform_verified_evidence.py", "--registry", registry,
            "--require-goal-targets", "--require-review-bundles", "--release-tag", tag,
        ],
        [
            "check_release_publish_assets.py", "--assets-dir", assets, "--tag", tag,
            "--repository", repository, "--evidence-registry", registry,
            "--require-platform-goal-targets", "--native-release-channel", "production-signed",
        ],
        [
            "check_release_license_compliance.py", "--assets-dir", assets, "--tag", tag,
            "--repository", repository, "--sha", sha,
            "--evidence", inputs["RELEASE_LICENSE_EVIDENCE"],
            "--signature", inputs["RELEASE_LICENSE_SIGNATURE"],
            "--evidence-root", inputs["RELEASE_LICENSE_EVIDENCE_ROOT"],
            "--candidate-inventory", inputs["RELEASE_CANDIDATE_INVENTORY"],
            "--protected-platform-registry", registry,
            "--platform-source-archives", inputs["RELEASE_PLATFORM_SOURCE_ARCHIVES"],
            "--tag-governance-attestation", inputs["RELEASE_TAG_GOVERNANCE_ATTESTATION"],
            "--tag-governance-signature", inputs["RELEASE_TAG_GOVERNANCE_SIGNATURE"],
            "--verify-published-release",
        ],
        [
            "check_release_mobaxterm_parity.py", "--repository", repository, "--tag", tag, "--sha", sha,
            "--registry-commit", inputs["RELEASE_MOBAXTERM_REGISTRY_COMMIT"],
            "--assets-dir", assets, "--evidence-root", inputs["RELEASE_MOBAXTERM_EVIDENCE_ROOT"],
        ],
        ["check_repository_governance.py", "--repository", repository, "--branch", "main", "--sha", sha,
         "--release-tag", tag],
        ["check_published_release_notes.py", "--repository", repository, "--tag", tag, "--channel", "production-signed"],
    )


def run_gate(command: list[str]) -> None:
    script, *args = command
    subprocess.run([sys.executable, f"scripts/{script}", *args], cwd=ROOT, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit the exact published release using the RELEASE_* inputs documented in docs/PRODUCTION_READINESS.md."
    )
    parser.parse_args(argv)
    try:
        inputs, errors = read_inputs(os.environ)
        if errors:
            for error in errors:
                print(f"production readiness: {error}", file=sys.stderr)
            return 2
        tag = inputs["RELEASE_TAG"]
        sha = inputs["RELEASE_SHA"]
        require_checkout_identity(tag, sha)
        for command in audit_commands(inputs):
            run_gate(command)
        require_checkout_identity(tag, sha)
        run_gate(["check_repository_cleanup.py", "--require-clean"])
    except subprocess.CalledProcessError as error:
        print(f"production readiness: {Path(error.cmd[1]).name} failed with exit code {error.returncode}", file=sys.stderr)
        return error.returncode if error.returncode > 0 else 1
    except (ValueError, OSError) as error:
        print(f"production readiness: {error}", file=sys.stderr)
        return 2
    print("production readiness: 100/100 gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
