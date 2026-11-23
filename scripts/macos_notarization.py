"""Bind Apple notarization to the submitted and stapled release files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

SHA256 = re.compile(r"[0-9a-f]{64}")
RECEIPT_FIELDS = {"archive", "status", "submission_id", "submitted_sha256", "stapled_sha256"}
MAX_LOG_BYTES = 20 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def submission_id(value: object) -> str:
    if isinstance(value, str):
        parsed = UUID(value)
        canonical = str(parsed)
        if canonical == value.lower() and parsed.int:
            return canonical
    raise ValueError("invalid Apple notarization submission ID")


def read_object(raw: bytes) -> dict[str, Any]:
    def unique(pairs):
        result = dict(pairs)
        if len(pairs) != len(result):
            raise ValueError("duplicate keys in Apple notarization JSON")
        return result

    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("Apple notarization response must be a JSON object")
    return value


def check_release_receipt(value: object, *, archive: str, stapled_sha256: object) -> str:
    if (
        not isinstance(value, dict) or value.keys() != RECEIPT_FIELDS
        or value["archive"] != archive or value["status"] != "Accepted"
        or not isinstance(value["submitted_sha256"], str) or not SHA256.fullmatch(value["submitted_sha256"])
        or not isinstance(value["stapled_sha256"], str) or not SHA256.fullmatch(value["stapled_sha256"])
        or value["stapled_sha256"] != stapled_sha256
    ):
        raise ValueError("Apple notarization receipt must bind the accepted upload and the verified stapled file")
    return submission_id(value["submission_id"])


def notarize(artifact: Path, *, profile: str, keychain: str = "") -> dict[str, str]:
    if artifact.suffix not in {".dmg", ".pkg"} or artifact.is_symlink() or not artifact.is_file():
        raise ValueError("notarization requires a regular DMG or PKG file")
    profile_args = ["--keychain-profile", profile]
    if keychain:
        profile_args += ["--keychain", keychain]
    submitted_sha256 = sha256_file(artifact)
    response = subprocess.run(
        ["xcrun", "notarytool", "submit", str(artifact), *profile_args, "--wait", "--output-format", "json"],
        stdout=subprocess.PIPE, check=True,
    )
    submission = read_object(response.stdout)
    if submission.get("status") != "Accepted":
        raise ValueError(f"Apple did not accept notarization for {artifact.name}")
    accepted_id = submission_id(submission.get("id"))
    with tempfile.TemporaryDirectory(prefix="row-macos-notary-") as scratch:
        log_path = Path(scratch) / "apple-notary.json"
        subprocess.run(["xcrun", "notarytool", "log", accepted_id, *profile_args, str(log_path)], check=True)
        with log_path.open("rb") as stream:
            raw = stream.read(MAX_LOG_BYTES + 1)
        if len(raw) > MAX_LOG_BYTES:
            raise ValueError("Apple notarization log exceeds the size limit")
        log = read_object(raw)
    if (
        type(log.get("logFormatVersion")) is not int or log["logFormatVersion"] != 1
        or type(log.get("statusCode")) is not int or log["statusCode"] != 0
        or log.get("status") != "Accepted" or submission_id(log.get("jobId")) != accepted_id
        or log.get("archiveFilename") != artifact.name or log.get("sha256") != submitted_sha256
    ):
        raise ValueError(f"Apple notarization log does not match the accepted upload for {artifact.name}")
    if sha256_file(artifact) != submitted_sha256:
        raise ValueError(f"{artifact.name} changed after submission to Apple")

    subprocess.run(["xcrun", "stapler", "staple", str(artifact)], check=True)
    stapled_sha256 = sha256_file(artifact)
    subprocess.run(["xcrun", "stapler", "validate", str(artifact)], check=True)
    if artifact.suffix == ".pkg":
        subprocess.run(["pkgutil", "--check-signature", str(artifact)], check=True)
        subprocess.run(["spctl", "--assess", "--type", "install", "--verbose=2", str(artifact)], check=True)
    else:
        subprocess.run(["codesign", "--verify", "--strict", "--verbose=2", str(artifact)], check=True)
        subprocess.run(
            ["spctl", "--assess", "--type", "open", "--context", "context:primary-signature", "--verbose=2", str(artifact)],
            check=True,
        )
    if sha256_file(artifact) != stapled_sha256:
        raise ValueError(f"{artifact.name} changed during stapled signature verification")
    return {
        "archive": artifact.name,
        "status": "Accepted",
        "submission_id": accepted_id,
        "submitted_sha256": submitted_sha256,
        "stapled_sha256": stapled_sha256,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        profile = os.environ.get("ROW_MACOS_NOTARY_PROFILE")
        if not profile:
            raise ValueError("ROW_MACOS_NOTARY_PROFILE is required")
        receipt = notarize(args.artifact, profile=profile, keychain=os.environ.get("ROW_MACOS_SIGNING_KEYCHAIN", ""))
        with args.receipt.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, sort_keys=True)
            stream.write("\n")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"macOS notarization: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
