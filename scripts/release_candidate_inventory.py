#!/usr/bin/env python3
"""Seal or rehydrate an exact GitHub Actions release-candidate inventory.

The tag workflow uses ``stage`` once, on attempt one, to bind every standard
artifact archive ID/digest and every file inside those archives.  The separate
promotion workflow uses ``promote`` to fetch the inventory artifact and every
candidate artifact by numeric ID, re-check their live GitHub metadata and raw
ZIP digests, and materialize the exact approved bytes.  No artifact is selected
from an ambient run or by a mutable branch head.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import managed_rpm_qualification  # noqa: E402
from scripts import qualify_rpm_candidate as rpm_qualification  # noqa: E402
from scripts.candidate_posix_byte_binding import binding_schema, target_contract  # noqa: E402
from scripts.debian_server_notices import read_verified_debian_notices  # noqa: E402
from scripts.managed_debian_qualification import (  # noqa: E402
    HASH,
    MANAGED_IMAGE,
    REPORT_NAME,
    validate_receipt,
)
from scripts.release_evidence_file import retry_evidence_operation  # noqa: E402

SERVER_BUNDLE_SCHEMA_VERSION = 10
SCHEMA_VERSION = SERVER_BUNDLE_SCHEMA_VERSION
LINUX_INSTALLER_SCHEMA_VERSION = 9
GUI_INSTALLER_SCHEMA_VERSION = 8
GUI_SMOKE_SCHEMA_VERSION = 7
MANAGED_RPM_SCHEMA_VERSION = 6
RPM_SMOKE_SCHEMA_VERSION = 5
RPM_SCHEMA_VERSION = 4
MANAGED_SCHEMA_VERSION = 3
LEGACY_SCHEMA_VERSION = 2
BUILD_WORKFLOW = ".github/workflows/release.yml"
CANDIDATE_INVENTORY_ARTIFACT = "release-candidate-inventory"
MANAGED_DEBIAN_ARTIFACT = "release-managed-debian-update"
MANAGED_DEBIAN_CONTROLLER = Path("scripts/managed_linux_update.py")
RPM_ARTIFACT = "release-linux-rpm-recovery"
RPM_REPORT_NAME = rpm_qualification.REPORT_NAME
RPM_SMOKE_FILES = (rpm_qualification.PROOF.name, rpm_qualification.SMOKE_BINDING.name)
EXPECTED_ARTIFACT_NAMES = (
    "release-source-python",
    "release-windows-native-x64",
    "release-windows-native-x86",
    "release-windows-native-arm64",
    "release-macos-native-x64",
    "release-macos-native-arm64",
    "release-linux-native-x86_64",
    "release-linux-native-aarch64",
)
GUI_SMOKE_ARTIFACT_NAMES = (
    "release-windows-gui-smoke-x64",
    "release-windows-gui-smoke-arm64",
    "release-macos-gui-smoke-x64",
    "release-macos-gui-smoke-arm64",
)
LINUX_SMOKE_ARTIFACT_NAMES = (
    "release-linux-native-smoke-x86_64",
    "release-linux-native-smoke-aarch64",
)
RUNTIME_REPORT_ARTIFACT_NAMES = {
    "windows-x86": "release-runtime-windows-x86",
    "windows-x64": "release-runtime-windows-x64",
    "windows-arm64": "release-runtime-windows-arm64",
    "macos-x64": "release-runtime-macos-x64",
    "macos-arm64": "release-runtime-macos-arm64",
    "linux-x86_64": "release-runtime-linux-x86_64",
    "linux-arm64": "release-runtime-linux-aarch64",
}
RUNTIME_REPORT_NAME = "candidate-pip-inspect.json"
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
SHA_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"sha256:([0-9a-f]{64})")
WINDOWS_DEVICE_NAME_RE = re.compile(r"(?:con|prn|aux|nul|conin\$|conout\$|(?:com|lpt)[1-9¹²³])", re.I)
UNSAFE_FILENAME_RE = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')
RUN_URI_RE = re.compile(
    r"https://github\.com/([^/]+/[^/]+)/actions/runs/([1-9]\d*)/attempts/([1-9]\d*)"
)
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024 * 1024
MAX_EXPANDED_BYTES = 24 * 1024 * 1024 * 1024
MAX_MEMBERS = 20_000
MAX_JSON_BYTES = 10 * 1024 * 1024
MAX_SMOKE_ARCHIVE_BYTES = 64 * 1024 * 1024
LINUX_SMOKE_PROOF_FILE = "finish.json"
GUI_ARCHIVE_PROOF_FILE = "gui-archive-proof.json"
NATIVE_BYTE_BINDING_FILE = "candidate-runtime-byte-binding.json"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Expose redirects so authentication can be removed across origins."""

    def redirect_request(  # type: ignore[override]
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ValueError("GH_TOKEN or GITHUB_TOKEN is required")
        repository = normalize_repository(args.repository)
        release_tag = normalize_tag(args.release_tag)
        release_sha = normalize_sha(args.release_sha)
        run_id = positive_int(args.build_run_id, "build run id")
        run_attempt = positive_int(args.build_run_attempt, "build run attempt")
        client = GitHubClient(repository, token)
        if args.command == "stage":
            if run_attempt != 1:
                raise ValueError(
                    "candidate staging refuses rerun attempts; dispatch a fresh build from the release tag"
                )
            stage(
                client,
                release_tag=release_tag,
                release_sha=release_sha,
                run_id=run_id,
                run_attempt=run_attempt,
                assets_root=args.assets_root,
                output=args.output,
            )
        else:
            inventory_artifact_id = positive_int(
                args.inventory_artifact_id, "candidate inventory artifact id"
            )
            inventory_archive_digest = normalize_digest(
                args.inventory_archive_digest,
                "candidate inventory archive digest",
            )
            promote(
                client,
                release_tag=release_tag,
                release_sha=release_sha,
                run_id=run_id,
                run_attempt=run_attempt,
                inventory_artifact_id=inventory_artifact_id,
                inventory_archive_digest=inventory_archive_digest,
                approved_inventory=args.approved_inventory,
                assets_root=args.assets_root,
                qualification_archives=args.qualification_archives,
            )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"release candidate inventory: {exc}", file=os.sys.stderr)
        return 1
    print(f"release candidate inventory {args.command} passed")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("stage", "promote"):
        child = subparsers.add_parser(command)
        child.add_argument("--repository", required=True)
        child.add_argument("--release-tag", required=True)
        child.add_argument("--release-sha", required=True)
        child.add_argument("--build-run-id", required=True)
        child.add_argument("--build-run-attempt", required=True)
        child.add_argument("--assets-root", required=True, type=Path)
        if command == "stage":
            child.add_argument("--output", required=True, type=Path)
        else:
            child.add_argument("--inventory-artifact-id", required=True)
            child.add_argument("--inventory-archive-digest", required=True)
            child.add_argument("--approved-inventory", required=True, type=Path)
            child.add_argument("--qualification-archives", type=Path, help="retain the verified original qualification ZIPs")
    return parser.parse_args(argv)


class GitHubClient:
    def __init__(self, repository: str, token: str, *, api_url: str | None = None) -> None:
        api_root = (api_url or os.environ.get("GITHUB_API_URL", "https://api.github.com")).rstrip("/")
        self.base = f"{api_root}/repos/{repository}"
        self.api_origin = origin(self.base)
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "remote-ops-release-candidate/1",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def json(self, endpoint: str) -> dict[str, Any]:
        with self._open(endpoint, allow_redirect=False) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_JSON_BYTES:
                raise RuntimeError(f"GitHub JSON response exceeds {MAX_JSON_BYTES} bytes")
            data = response.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            raise RuntimeError(f"GitHub JSON response exceeds {MAX_JSON_BYTES} bytes")
        value = json.loads(data)
        if not isinstance(value, dict):
            raise RuntimeError(f"GitHub API {endpoint} did not return an object")
        return value

    def download(
        self, endpoint: str, destination: Path, *, max_bytes: int = MAX_ARCHIVE_BYTES,
    ) -> str:
        if destination.exists():
            raise ValueError(f"download destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with self._open(endpoint, allow_redirect=True) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise RuntimeError(f"GitHub artifact exceeds {max_bytes} bytes")
            with destination.open("xb") as output:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise RuntimeError(f"GitHub artifact exceeds {max_bytes} bytes")
                    digest.update(chunk)
                    output.write(chunk)
        return f"sha256:{digest.hexdigest()}"

    def _open(self, endpoint: str, *, allow_redirect: bool) -> Any:
        url = endpoint if endpoint.startswith("https://") else f"{self.base}/{endpoint.lstrip('/')}"
        request = urllib.request.Request(url, headers=self.headers)
        opener = urllib.request.build_opener(NoRedirect())
        try:
            return opener.open(request, timeout=120)
        except urllib.error.HTTPError as exc:
            if allow_redirect and exc.code in {301, 302, 303, 307, 308}:
                location = exc.headers.get("Location")
                exc.close()
                if not location:
                    raise RuntimeError(
                        f"GitHub artifact redirect from {url} has no Location"
                    ) from None
                redirected = urljoin(url, location)
                parsed = urlsplit(redirected)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise RuntimeError(
                        "GitHub artifact redirect must be an absolute credential-free HTTPS URL"
                    ) from None
                redirect_headers = {
                    "Accept": "application/octet-stream",
                    "User-Agent": self.headers["User-Agent"],
                }
                redirected_request = urllib.request.Request(
                    redirected,
                    headers=redirect_headers,
                )
                try:
                    return opener.open(redirected_request, timeout=120)
                except urllib.error.HTTPError as redirect_exc:
                    status = redirect_exc.code
                    redirect_exc.close()
                    if status in {301, 302, 303, 307, 308}:
                        raise RuntimeError(
                            "GitHub artifact download returned an unexpected second redirect"
                        ) from None
                    raise RuntimeError(
                        f"GitHub artifact download failed with HTTP {status}"
                    ) from None
                except urllib.error.URLError:
                    raise RuntimeError("GitHub artifact download failed to connect") from None
            detail = exc.read(2000).decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API {url} failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub API {url} failed: {exc.reason}") from exc


def stage(
    client: GitHubClient,
    *,
    release_tag: str,
    release_sha: str,
    run_id: int,
    run_attempt: int,
    assets_root: Path,
    output: Path,
) -> None:
    run = client.json(f"actions/runs/{run_id}")
    check_build_run(
        run,
        release_tag=release_tag,
        release_sha=release_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        require_success=False,
    )
    listing = client.json(f"actions/runs/{run_id}/artifacts?per_page=100")
    raw_artifacts = listing.get("artifacts")
    if not isinstance(raw_artifacts, list):
        raise ValueError("GitHub run artifact listing must contain an artifacts list")
    total_count = listing.get("total_count")
    if type(total_count) is not int or total_count != len(raw_artifacts):
        raise ValueError("GitHub run artifact listing is incomplete or has an invalid total count")
    by_name = unique_artifacts(raw_artifacts)
    actual_names = set(by_name)
    expected_names = (
        set(EXPECTED_ARTIFACT_NAMES) | set(GUI_SMOKE_ARTIFACT_NAMES) | set(LINUX_SMOKE_ARTIFACT_NAMES)
        | set(RUNTIME_REPORT_ARTIFACT_NAMES.values()) | {MANAGED_DEBIAN_ARTIFACT, RPM_ARTIFACT}
    )
    if actual_names != expected_names:
        raise ValueError(
            "staged run artifact names must be exact; "
            f"missing={sorted(expected_names - actual_names)}, "
            f"unexpected={sorted(actual_names - expected_names)}"
        )
    artifact_ids: set[int] = set()
    for name, artifact in by_name.items():
        artifact_id = positive_int(artifact.get("id"), f"artifact {name} id")
        if artifact_id in artifact_ids:
            raise ValueError(f"run artifact ID is duplicated: {artifact_id}")
        artifact_ids.add(artifact_id)
        check_artifact_metadata(
            artifact,
            artifact_id=artifact_id,
            name=name,
            digest=normalize_digest(artifact.get("digest"), f"artifact {name} digest"),
            run_id=run_id,
            release_sha=release_sha,
        )
        positive_int(artifact.get("size_in_bytes"), f"artifact {name} size")

    build_artifacts = {name: by_name[name] for name in EXPECTED_ARTIFACT_NAMES}
    runtime_reports = {
        target: seal_runtime_report(client, by_name[name], name, run_id, release_sha)
        for target, name in sorted(RUNTIME_REPORT_ARTIFACT_NAMES.items())
    }
    report, managed = sealed_json_artifact(
        client, by_name[MANAGED_DEBIAN_ARTIFACT], MANAGED_DEBIAN_ARTIFACT, run_id, release_sha, REPORT_NAME,
    )
    managed["receipt"] = json.loads(report)
    validate_managed_report(
        managed, release_tag, release_sha, run_id, run_attempt,
        require_current=True, require_server_bundle=True, source_root=ROOT,
    )
    if qualification_receipt_bytes(managed["receipt"]) != report:
        raise ValueError("managed Debian receipt must use the canonical JSON format")
    repository = normalize_repository_from_api(run)
    rpm_files, rpm_archive, rpm_records = sealed_json_members(
        client, by_name[RPM_ARTIFACT], RPM_ARTIFACT, run_id, release_sha, (RPM_REPORT_NAME, *RPM_SMOKE_FILES),
    )
    rpm = {**rpm_archive, **rpm_records[RPM_REPORT_NAME], "receipt": json.loads(rpm_files[RPM_REPORT_NAME])}
    _, rpm_sha = validate_rpm_report(
        rpm, repository, release_tag, release_sha, run_id, run_attempt, require_managed=True, source_root=ROOT,
        require_current_managed=True,
    )
    rpm_smoke = {name: rpm_records[name] for name in RPM_SMOKE_FILES}
    validate_rpm_smoke_files(rpm_files, rpm["receipt"], rpm_smoke)
    smoke = {
        name: {
            "artifact_id": by_name[name]["id"],
            "archive_digest": by_name[name]["digest"],
            "size_in_bytes": by_name[name]["size_in_bytes"],
        }
        for name in (*GUI_SMOKE_ARTIFACT_NAMES, *LINUX_SMOKE_ARTIFACT_NAMES)
    }
    observed_installers = verify_sealed_smoke(client, smoke, run_id, release_sha)
    for name, record in smoke.items():
        record["installer_sha256"] = observed_installers[name]
    records = materialize_records(
        client, build_artifacts, assets_root,
        managed_deb=(release_tag, managed["receipt"]),
        release_rpm=(release_tag, rpm_sha),
        smoked_installers=(release_tag, smoke),
    )
    inventory = {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "release_tag": release_tag,
        "release_sha": release_sha,
        "source_ref": f"refs/tags/{release_tag}",
        "workflow": BUILD_WORKFLOW,
        "build_run_id": run_id,
        "build_run_attempt": run_attempt,
        "artifacts": records,
        "runtime_reports": runtime_reports,
        "managed_debian_update": managed,
        "rpm_recovery": rpm,
        "rpm_smoke": rpm_smoke,
        "gui_smoke": {name: smoke[name] for name in GUI_SMOKE_ARTIFACT_NAMES},
        "linux_smoke": {name: smoke[name] for name in LINUX_SMOKE_ARTIFACT_NAMES},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(inventory), encoding="utf-8")


def seal_runtime_report(
    client: GitHubClient, artifact: dict[str, Any], name: str, run_id: int, release_sha: str,
) -> dict[str, Any]:
    report, metadata = sealed_json_artifact(client, artifact, name, run_id, release_sha, RUNTIME_REPORT_NAME)
    validate_runtime_report(report, name)
    return metadata


def sealed_json_artifact(
    client: GitHubClient, artifact: dict[str, Any], name: str, run_id: int, release_sha: str, filename: str,
    *, archive_output: Path | None = None,
) -> tuple[bytes, dict[str, Any]]:
    files, archive, records = sealed_json_members(
        client, artifact, name, run_id, release_sha, (filename,), archive_output=archive_output,
    )
    return files[filename], {**archive, **records[filename]}


def sealed_json_members(
    client: GitHubClient, artifact: dict[str, Any], name: str, run_id: int, release_sha: str,
    filenames: tuple[str, ...], *, archive_output: Path | None = None,
) -> tuple[dict[str, bytes], dict[str, Any], dict[str, dict[str, Any]]]:
    artifact_id = positive_int(artifact.get("id"), f"artifact {name} id")
    digest = normalize_digest(artifact.get("digest"), f"artifact {name} archive digest")
    size = positive_int(artifact.get("size_in_bytes"), f"artifact {name} size")
    if size > MAX_JSON_BYTES:
        raise ValueError(f"{name} archive exceeds the size limit")
    check_artifact_metadata(
        artifact, artifact_id=artifact_id, name=name, digest=digest,
        run_id=run_id, release_sha=release_sha,
    )
    with tempfile.TemporaryDirectory(prefix="row-release-report-") as temporary:
        archive = Path(temporary) / "report.zip"
        downloaded_digest = client.download(
            f"actions/artifacts/{artifact_id}/zip", archive, max_bytes=MAX_JSON_BYTES,
        )
        if downloaded_digest != digest or archive.stat().st_size != size:
            raise ValueError(f"{name} archive does not match GitHub")
        unpacked = Path(temporary) / "unpacked"
        rows = extract_archive(
            archive, unpacked, max_expanded_bytes=MAX_JSON_BYTES,
            only_name=filenames[0] if len(filenames) == 1 else None,
        )
        if {row["path"] for row in rows} != set(filenames):
            raise ValueError(f"{name} archive must contain the exact evidence files")
        files = {filename: (unpacked / filename).read_bytes() for filename in filenames}
        if archive_output is not None:
            with archive.open("rb") as source, archive_output.open("xb") as output:
                shutil.copyfileobj(source, output)
    return files, {"artifact_id": artifact_id, "archive_digest": digest}, {
        row["path"]: {"sha256": row["sha256"], "size_bytes": row["size"]} for row in rows
    }


def qualification_receipt_bytes(receipt: Any) -> bytes:
    return (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_qualification_archive(record: Any, label: str) -> int:
    if not isinstance(record, dict) or record.keys() != {"artifact_id", "archive_digest", "sha256", "size_bytes", "receipt"}:
        raise ValueError(f"{label} receipt is missing or invalid")
    artifact_id = positive_int(record["artifact_id"], f"{label} artifact id")
    normalize_digest(record["archive_digest"], f"{label} archive digest")
    raw = qualification_receipt_bytes(record["receipt"])
    if (
        positive_int(record["size_bytes"], f"{label} report size") != len(raw)
        or len(raw) > MAX_JSON_BYTES or record["sha256"] != hashlib.sha256(raw).hexdigest()
    ):
        raise ValueError(f"{label} receipt bytes do not match the recorded digest and size")
    return artifact_id


def validate_managed_report(
    record: Any, release_tag: str, release_sha: str, run_id: int, run_attempt: int, *, require_current: bool = False,
    require_server_bundle: bool = False, source_root: Path | None = None,
) -> int:
    artifact_id = validate_qualification_archive(record, "managed Debian")
    receipt = record["receipt"]
    if (
        not isinstance(receipt, dict)
        or receipt.get("source_sha") != release_sha
        or receipt.get("run_id") != str(run_id) or receipt.get("run_attempt") != str(run_attempt)
        or receipt.get("container_image") != MANAGED_IMAGE
        or not isinstance(receipt.get("debian_depends"), str)
        or any(not isinstance(receipt.get(key), str) or HASH.fullmatch(receipt[key]) is None
               for key in ("candidate_sha256", "controller_sha256", "source_archive_sha256"))
    ):
        raise ValueError("managed Debian receipt does not match the release source and Actions attempt")
    if source_root is not None and receipt["controller_sha256"] != hashlib.sha256(
        (source_root / MANAGED_DEBIAN_CONTROLLER).read_bytes(),
    ).hexdigest():
        raise ValueError("managed Debian controller digest differs from the release checkout")
    image = receipt.get("drill_image")
    if receipt["debian_depends"]:
        normalize_digest(image, "managed Debian dependency image")
    elif image != MANAGED_IMAGE:
        raise ValueError("managed Debian drill must use the pinned image")
    pins = json.loads((ROOT / "configs/native_linux_previous_release_pins.json").read_bytes())
    previous_name = f'remote-ops-workspace-{pins["tag"]}-linux-amd64.deb'
    previous = next(row["digest"].removeprefix("sha256:") for row in pins["assets"] if row["name"] == previous_name)
    validate_receipt(
        receipt, previous_sha=previous, candidate_sha=receipt["candidate_sha256"], require_current=require_current,
    )
    if require_server_bundle and receipt["candidate_has_server_bundle"] is not True:
        raise ValueError("the production Debian candidate requires the embedded server bundle")
    applied = receipt["receipts"]["candidate-apply"]
    if (
        applied.get("candidate_sha256") != receipt["candidate_sha256"]
        or applied.get("previous_sha256") != previous or applied.get("architecture") != "amd64"
        or applied.get("candidate_version") != release_tag.removeprefix("v")
        or applied.get("previous_version") != pins["tag"].removeprefix("v")
    ):
        raise ValueError("managed Debian apply journal does not match the release installers")
    return artifact_id


def validate_rpm_report(
    record: Any, repository: str, release_tag: str, release_sha: str, run_id: int, run_attempt: int,
    *, require_managed: bool = False, source_root: Path | None = None, require_current_managed: bool = False,
) -> tuple[int, str]:
    artifact_id = validate_qualification_archive(record, "RPM recovery")
    receipt = record["receipt"]
    expected = {
        "target": rpm_qualification.TARGET,
        "source_commit": release_sha,
        "workflow_ref": f"{repository}/{BUILD_WORKFLOW}@refs/tags/{release_tag}",
        "container_image": rpm_qualification.IMAGE,
        "previous_release_asset_id": rpm_qualification.PREVIOUS_ASSET,
        "previous_release_url": rpm_qualification.PREVIOUS_URL,
    }
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") not in (rpm_qualification.SCHEMA, rpm_qualification.NATIVE_ONLY_SCHEMA)
        or any(receipt.get(key) != value for key, value in expected.items())
        or type(receipt.get("run_id")) is not int or receipt["run_id"] != run_id
        or type(receipt.get("run_attempt")) is not int or receipt["run_attempt"] != run_attempt
        or not isinstance(receipt.get("candidate_native_proof_sha256"), str)
        or HASH.fullmatch(receipt["candidate_native_proof_sha256"]) is None
    ):
        raise ValueError("RPM recovery receipt does not match the release source and Actions attempt")
    try:
        native = receipt["receipt"]
        candidate_sha = native["candidate"]["package_sha256"]
        if not HASH.fullmatch(candidate_sha):
            raise ValueError("invalid candidate RPM digest")
        rpm_qualification.verify_receipt(native, release_tag.removeprefix("v"), candidate_sha)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("RPM recovery receipt has invalid package identities or rollback results") from None
    if (require_managed or require_current_managed) and receipt["schema"] != rpm_qualification.SCHEMA:
        raise ValueError("The current RPM recovery receipt requires the managed-update qualification")
    if receipt["schema"] == rpm_qualification.SCHEMA:
        managed_rpm_qualification.verify_receipt(
            receipt.get("managed_update"), native,
            controller_sha256=None if source_root is None else rpm_qualification.sha256(
                source_root / managed_rpm_qualification.CONTROLLER,
            ),
            requirements_sha256=None if source_root is None else hashlib.sha256(
                managed_rpm_qualification.locked_crypto_requirements(source_root),
            ).hexdigest(),
            require_current=require_current_managed,
        )
    return artifact_id, candidate_sha


def validate_rpm_smoke_metadata(records: Any, receipt: dict[str, Any]) -> None:
    if not isinstance(records, dict) or records.keys() != set(RPM_SMOKE_FILES):
        raise ValueError("RPM native smoke evidence is missing or invalid")
    for record in records.values():
        if (
            not isinstance(record, dict) or record.keys() != {"sha256", "size_bytes"}
            or not isinstance(record["sha256"], str) or HASH.fullmatch(record["sha256"]) is None
            or type(record["size_bytes"]) is not int or not 0 < record["size_bytes"] <= MAX_JSON_BYTES
        ):
            raise ValueError("RPM native smoke evidence metadata is invalid")
    if records[RPM_SMOKE_FILES[0]]["sha256"] != receipt["candidate_native_proof_sha256"]:
        raise ValueError("RPM native proof digest differs from the recovery receipt")


def validate_rpm_smoke_files(
    files: dict[str, bytes], receipt: dict[str, Any], records: dict[str, Any],
) -> None:
    validate_rpm_smoke_metadata(records, receipt)
    if files[RPM_REPORT_NAME] != qualification_receipt_bytes(receipt):
        raise ValueError("RPM recovery receipt differs from the sealed evidence")
    for name, record in records.items():
        if len(files[name]) != record["size_bytes"] or hashlib.sha256(files[name]).hexdigest() != record["sha256"]:
            raise ValueError(f"RPM native smoke file differs from the sealed evidence: {name}")

    try:
        proof, binding = (json.loads(files[name]) for name in RPM_SMOKE_FILES)
        candidate = receipt["receipt"]["candidate"]
        asset = rpm_qualification.rpm_proof_asset(
            proof, candidate["version"], receipt["source_commit"], str(receipt["run_id"]), str(receipt["run_attempt"]),
        )
        link = proof["native_executable_byte_binding"]
        if (
            proof.get("workflow_ref") != receipt["workflow_ref"]
            or asset["sha256"] != candidate["package_sha256"]
            or link.get("report_path") != rpm_qualification.SMOKE_BINDING.as_posix()
            or link.get("report_sha256") != records[RPM_SMOKE_FILES[1]]["sha256"]
        ):
            raise ValueError("RPM native proof refers to different workflow, package or smoke bytes")

        target = rpm_qualification.TARGET
        outputs, _, probes = target_contract(target)
        launcher = candidate["launcher_sha256"]
        required = {(phase, probe) for path, phase, probe in probes if path == "rpm/usr/bin/row"}
        rows = [row for row in binding["observations"] if row.get("path") == "rpm/usr/bin/row"]
        if (
            binding.get("target") != target
            or type(binding.get("schema_version")) is not int or binding["schema_version"] != binding_schema(target)
            or binding.get("status") != "bound" or binding.get("smoke_complete") is not True
            or binding.get("expected_executables") != [{"path": outputs["cli"], "role": "cli", "sha256": launcher}]
            or len(rows) != len(required)
            or {(row.get("phase"), row.get("probe")) for row in rows} != required
            or any(
                row.get("role") != "cli" or row.get("matched") is not True
                or row.get("expected_sha256") != launcher or row.get("observed_sha256") != launcher
                for row in rows
            )
        ):
            raise ValueError("RPM smoke did not observe the recovered candidate launcher before every probe")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("RPM native smoke evidence has an invalid shape") from exc


def verify_sealed_rpm_smoke(
    client: GitHubClient, inventory: dict[str, Any], run_id: int, release_sha: str,
    *, archive_output: Path | None = None,
) -> None:
    rpm = inventory["rpm_recovery"]
    metadata = client.json(f'actions/artifacts/{rpm["artifact_id"]}')
    check_artifact_metadata(
        metadata, artifact_id=rpm["artifact_id"], name=RPM_ARTIFACT, digest=rpm["archive_digest"],
        run_id=run_id, release_sha=release_sha,
    )
    files, _, _ = sealed_json_members(
        client, metadata, RPM_ARTIFACT, run_id, release_sha, (RPM_REPORT_NAME, *RPM_SMOKE_FILES),
        archive_output=archive_output,
    )
    validate_rpm_smoke_files(files, rpm["receipt"], inventory["rpm_smoke"])


def verify_sealed_debian_update(
    client: GitHubClient, record: dict[str, Any], run_id: int, release_sha: str, *,
    archive_output: Path | None = None,
) -> None:
    artifact_id = record["artifact_id"]
    metadata = client.json(f"actions/artifacts/{artifact_id}")
    check_artifact_metadata(
        metadata, artifact_id=artifact_id, name=MANAGED_DEBIAN_ARTIFACT, digest=record["archive_digest"],
        run_id=run_id, release_sha=release_sha,
    )
    raw, _ = sealed_json_artifact(
        client, metadata, MANAGED_DEBIAN_ARTIFACT, run_id, release_sha, REPORT_NAME, archive_output=archive_output,
    )
    if raw != qualification_receipt_bytes(record["receipt"]):
        raise ValueError("managed Debian archive receipt does not match the sealed inventory")


def validate_smoke_records(value: Any, ids: set[int], names: tuple[str, ...], label: str) -> None:
    if not isinstance(value, dict) or value.keys() != set(names):
        raise ValueError(f"approved candidate inventory must contain all {label} smoke archives")
    for name, record in value.items():
        fields = {"artifact_id", "archive_digest", "size_in_bytes"}
        if not isinstance(record, dict) or record.keys() not in (fields, fields | {"installer_sha256"}):
            raise ValueError(f"{name} sealed archive identity is invalid")
        artifact_id = positive_int(record["artifact_id"], f"{name} artifact id")
        if artifact_id in ids:
            raise ValueError(f"{name} artifact id is duplicated")
        ids.add(artifact_id)
        normalize_digest(record["archive_digest"], f"{name} archive digest")
        size = positive_int(record["size_in_bytes"], f"{name} archive size")
        if size > MAX_SMOKE_ARCHIVE_BYTES:
            raise ValueError(f"{name} archive exceeds the smoke evidence size limit")


def read_archive_reports(path: Path | io.BytesIO, name: str, filenames: tuple[str, ...]) -> dict[str, bytes]:
    reports = {}
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > MAX_MEMBERS:
            raise ValueError(f"{name} archive exceeds {MAX_MEMBERS} members")
        for filename in filenames:
            matches = [member for member in members if member.orig_filename.casefold() == filename.casefold()]
            if len(matches) != 1 or matches[0].orig_filename != filename:
                raise ValueError(f"{name} archive must contain one root {filename}")
            member = matches[0]
            mode = (member.external_attr >> 16) & 0xFFFF
            if (
                stat.S_IFMT(mode) not in (0, stat.S_IFREG) or member.external_attr & 0x10
                or member.flag_bits & 1 or not 0 < member.file_size <= MAX_JSON_BYTES
            ):
                raise ValueError(f"{name} archive has an invalid {filename}")
            reports[filename] = archive.read(member)
    return reports


def validate_gui_smoke_archive(path: Path | io.BytesIO, name: str) -> Any:
    reports = read_archive_reports(path, name, (GUI_ARCHIVE_PROOF_FILE, NATIVE_BYTE_BINDING_FILE))
    proof = json.loads(reports[GUI_ARCHIVE_PROOF_FILE])
    binding_bytes = reports[NATIVE_BYTE_BINDING_FILE]
    binding = json.loads(binding_bytes)
    target = name.removeprefix("release-").replace("-gui-smoke-", "-", 1)
    if (
        not isinstance(proof, dict) or proof.get("target") != target or proof.get("status") != "passed"
        or proof.get("smoke_binding_sha256") != hashlib.sha256(binding_bytes).hexdigest()
        or DIGEST_RE.fullmatch(f'sha256:{proof.get("artifact_sha256")}') is None
        or not isinstance(binding, dict) or binding.get("target") != target
        or binding.get("status") != "bound" or binding.get("smoke_complete") is not True
    ):
        raise ValueError(f"{name} GUI archive proof does not bind the completed smoke receipt")
    outputs = binding.get("expected_executables")
    if not isinstance(outputs, list) or [
        (output.get("path"), output.get("sha256"))
        for output in outputs if isinstance(output, dict) and output.get("role") == "gui"
    ] != [(proof.get("path"), proof["artifact_sha256"])] or not isinstance(proof.get("path"), str):
        raise ValueError(f"{name} GUI archive proof refers to different executable bytes")

    observations = binding.get("observations")
    gui_observations = [
        row for row in observations if isinstance(row, dict) and row.get("role") == "gui"
    ] if isinstance(observations, list) else []
    if not gui_observations or any(
        row.get("matched") is not True or row.get("expected_sha256") != proof["artifact_sha256"]
        or row.get("observed_sha256") != proof["artifact_sha256"]
        for row in gui_observations
    ):
        raise ValueError(f"{name} installer smoke did not observe the verified GUI executable bytes")
    return binding.get("installer_sha256")


def validate_linux_smoke_archive(path: Path | io.BytesIO, name: str, run_id: int, release_sha: str) -> Any:
    reports = read_archive_reports(path, name, (LINUX_SMOKE_PROOF_FILE, NATIVE_BYTE_BINDING_FILE))
    proof = json.loads(reports[LINUX_SMOKE_PROOF_FILE])
    raw = reports[NATIVE_BYTE_BINDING_FILE]
    binding = json.loads(raw)
    target = name.replace("release-linux-native-smoke-", "linux-", 1)
    source = proof.get("source") if isinstance(proof, dict) else None
    link = proof.get("native_executable_byte_binding") if isinstance(proof, dict) else None
    if (
        not isinstance(source, dict) or source.get("head") != release_sha
        or proof.get("target") != target or proof.get("event_sha") != release_sha
        or proof.get("run_id") != str(run_id) or proof.get("run_attempt") != "1"
        or proof.get("native_build_outcome") != "success" or proof.get("native_smoke_outcome") != "success"
        or proof.get("source_unchanged") is not True or proof.get("native_pyinstaller_inventory_complete") is not True
        or not isinstance(link, dict) or link.get("status") != "bound"
        or link.get("report_path") != f"build/native-smoke/{target}/{NATIVE_BYTE_BINDING_FILE}"
        or link.get("report_sha256") != hashlib.sha256(raw).hexdigest()
        or not isinstance(binding, dict) or binding.get("target") != target
        or binding.get("status") != "bound" or binding.get("smoke_complete") is not True
    ):
        raise ValueError(f"{name} native proof does not bind the completed exact-run installer smoke receipt")
    return binding.get("installer_sha256")


def verify_sealed_smoke(
    client: GitHubClient, records: dict[str, Any], run_id: int, release_sha: str,
    *, archive_root: Path | None = None,
) -> dict[str, Any]:
    installers = {}
    with tempfile.TemporaryDirectory(prefix="row-release-native-smoke-") as temporary:
        for name, record in records.items():
            artifact_id = record["artifact_id"]
            metadata = client.json(f"actions/artifacts/{artifact_id}")
            check_artifact_metadata(
                metadata, artifact_id=artifact_id, name=name, digest=record["archive_digest"],
                run_id=run_id, release_sha=release_sha,
            )
            archive = Path(temporary) / f"{name}.zip"
            downloaded = client.download(
                f"actions/artifacts/{artifact_id}/zip", archive, max_bytes=MAX_SMOKE_ARCHIVE_BYTES,
            )
            if (
                downloaded != record["archive_digest"]
                or archive.stat().st_size != record["size_in_bytes"]
                or metadata.get("size_in_bytes") != record["size_in_bytes"]
            ):
                raise ValueError(f"{name} archive digest or size differs from the sealed inventory")
            installers[name] = check_smoke_archive(archive, name, record, run_id, release_sha)
            if archive_root is not None:
                with archive.open("rb") as source, (archive_root / archive.name).open("xb") as output:
                    shutil.copyfileobj(source, output)
    return installers


def check_smoke_archive(
    archive: Path | io.BytesIO, name: str, record: dict[str, Any], run_id: int, release_sha: str,
) -> Any:
    observed = (
        validate_linux_smoke_archive(archive, name, run_id, release_sha)
        if name in LINUX_SMOKE_ARTIFACT_NAMES else validate_gui_smoke_archive(archive, name)
    )
    if "installer_sha256" in record and observed != record["installer_sha256"]:
        raise ValueError(f"{name} installer smoke hashes differ from the sealed inventory")
    return observed


def verify_retained_qualification_archives(archive_root: Path, inventory: dict[str, Any]) -> None:
    """Replay the qualification archives from an already validated, signed inventory."""
    if archive_root.is_symlink() or not archive_root.is_dir():
        raise ValueError("candidate qualification archives must be in a regular directory")

    managed = inventory.get("managed_debian_update")
    if managed is not None:
        with retained_archive(archive_root, MANAGED_DEBIAN_ARTIFACT, managed, MAX_JSON_BYTES) as archive:
            files = read_archive_reports(archive, MANAGED_DEBIAN_ARTIFACT, (REPORT_NAME,))
        if files[REPORT_NAME] != qualification_receipt_bytes(managed["receipt"]):
            raise ValueError("managed Debian archive receipt does not match the sealed inventory")

    if "rpm_smoke" in inventory:
        rpm = inventory["rpm_recovery"]
        with retained_archive(archive_root, RPM_ARTIFACT, rpm, MAX_JSON_BYTES) as archive:
            files = read_archive_reports(archive, RPM_ARTIFACT, (RPM_REPORT_NAME, *RPM_SMOKE_FILES))
        validate_rpm_smoke_files(files, rpm["receipt"], inventory["rpm_smoke"])

    smoke = {**inventory.get("gui_smoke", {}), **inventory.get("linux_smoke", {})}
    for name, record in smoke.items():
        with retained_archive(archive_root, name, record, record["size_in_bytes"]) as archive:
            check_smoke_archive(archive, name, record, inventory["build_run_id"], inventory["release_sha"])


def retained_archive(root: Path, name: str, record: dict[str, Any], limit: int) -> io.BytesIO:
    path = root / f"{name}.zip"
    if not path.exists() or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"missing or invalid retained candidate qualification archive: {path.name}")
    with path.open("rb") as source:
        raw = source.read(limit + 1)
    if (
        not 0 < len(raw) <= limit or len(raw) != record.get("size_in_bytes", len(raw))
        or f"sha256:{hashlib.sha256(raw).hexdigest()}" != record["archive_digest"]
    ):
        raise ValueError(f"{name} retained archive digest or size differs from the sealed inventory")
    return io.BytesIO(raw)


def require_smoked_installer_assets(
    records: list[dict[str, Any]], release_tag: str, smoke: dict[str, Any],
) -> None:
    by_name = {record["name"]: record["files"] for record in records}
    for name, receipt in smoke.items():
        target = name.removeprefix("release-").replace("-gui-smoke-", "-", 1).replace("-native-smoke-", "-", 1)
        platform, arch = target.split("-", 1)
        base = f"remote-ops-workspace-{release_tag}-{target}"
        if platform == "linux":
            deb_arch = {"x86_64": "amd64", "aarch64": "arm64"}[arch]
            expected_names = {f"remote-ops-workspace-{release_tag}-linux-{deb_arch}.deb", base + ".rpm", base + ".AppImage"}
        else:
            suffixes = ("-native.zip", "-setup.exe", ".msi") if platform == "windows" else (".dmg", ".pkg")
            expected_names = {base + suffix for suffix in suffixes}
        hashes = receipt.get("installer_sha256")
        if (
            not isinstance(hashes, dict) or hashes.keys() != expected_names
            or any(not isinstance(digest, str) or DIGEST_RE.fullmatch(f"sha256:{digest}") is None
                   for digest in hashes.values())
        ):
            raise ValueError(f"{name} receipt must bind the complete installer digest set")
        files = by_name.get(f"release-{platform}-native-{arch}", [])
        for asset, sha256 in hashes.items():
            if [row.get("sha256") for row in files if isinstance(row, dict) and row.get("path") == asset] != [sha256]:
                raise ValueError(f"{name} smoke receipt differs from the candidate installer {asset}")


def require_linux_installer(records: list[dict[str, Any]], name: str, sha256: str, label: str) -> None:
    matches = [
        file.get("sha256")
        for record in records if record["name"] == "release-linux-native-x86_64"
        for file in record["files"] if isinstance(file, dict) and file.get("path") == name
    ]
    if matches != [sha256]:
        raise ValueError(f"{label} receipt must bind the exact candidate {name.rsplit('.', 1)[1].upper()}")


def require_managed_deb(records: list[dict[str, Any]], release_tag: str, sha256: str) -> None:
    require_linux_installer(records, f"remote-ops-workspace-{release_tag}-linux-amd64.deb", sha256, "managed Debian")


def read_candidate_deb_metadata(package: Path) -> tuple[str, bool]:
    try:
        depends = subprocess.check_output(
            ["dpkg-deb", "--field", str(package), "Depends"], encoding="utf-8", timeout=30,
        ).strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("could not read the candidate Debian Depends field") from error
    return depends, bool(read_verified_debian_notices(package, target="linux-x86_64", verify_runtime=True))


def verify_candidate_deb_metadata(package: Path, receipt: dict[str, Any]) -> None:
    depends, bundled = read_candidate_deb_metadata(package)
    if depends != receipt["debian_depends"]:
        raise ValueError("managed Debian receipt Depends field differs from the candidate DEB")
    if bundled != receipt["candidate_has_server_bundle"]:
        raise ValueError("managed Debian receipt server bundle claim differs from the candidate DEB")


def require_release_rpm(records: list[dict[str, Any]], release_tag: str, sha256: str) -> None:
    name = rpm_qualification.rpm_name(release_tag.removeprefix("v"))
    require_linux_installer(records, name, sha256, "RPM recovery")


def validate_managed_release_qualification(
    inventory: dict[str, Any], *, repository: str, release_tag: str, release_sha: str, deb_sha256: str,
    deb_package: Path | None = None,
) -> list[dict[str, Any]]:
    if (type(inventory.get("schema_version")) is not int
            or not MANAGED_SCHEMA_VERSION <= inventory["schema_version"] <= SCHEMA_VERSION):
        raise ValueError("production Debian qualification requires the current sealed candidate inventory")
    run_id = inventory.get("build_run_id")
    if type(run_id) is not int or run_id < 1:
        raise ValueError("production Debian qualification requires a numeric candidate build run")
    records = validate_inventory(
        inventory, repository=repository, release_tag=release_tag, release_sha=release_sha,
        run_id=run_id, run_attempt=1,
    )
    require_managed_deb(records, release_tag, deb_sha256)
    if inventory["schema_version"] >= SERVER_BUNDLE_SCHEMA_VERSION:
        if deb_package is None:
            raise ValueError("production Debian qualification requires the exact package for server bundle verification")
        with deb_package.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != deb_sha256:
                raise ValueError("Debian package differs from the qualified release installer")
        verify_candidate_deb_metadata(deb_package, inventory["managed_debian_update"]["receipt"])
    return records


def validate_runtime_report(report: bytes, label: str) -> None:
    if not 0 < len(report) <= MAX_JSON_BYTES:
        raise ValueError(f"{label} pip inspect report exceeds the allowed size or is empty")
    value = json.loads(report)
    if (
        not isinstance(value, dict) or value.get("version") != "1"
        or not isinstance(value.get("installed"), list) or not value["installed"]
    ):
        raise ValueError(f"{label} must be a non-empty pip inspect v1 inventory")


def promote(
    client: GitHubClient,
    *,
    release_tag: str,
    release_sha: str,
    run_id: int,
    run_attempt: int,
    inventory_artifact_id: int,
    inventory_archive_digest: str,
    approved_inventory: Path,
    assets_root: Path,
    qualification_archives: Path | None = None,
) -> None:
    run = client.json(f"actions/runs/{run_id}")
    check_build_run(
        run,
        release_tag=release_tag,
        release_sha=release_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        require_success=True,
    )
    pointer = client.json(f"actions/artifacts/{inventory_artifact_id}")
    check_artifact_metadata(
        pointer,
        artifact_id=inventory_artifact_id,
        name=CANDIDATE_INVENTORY_ARTIFACT,
        digest=inventory_archive_digest,
        run_id=run_id,
        release_sha=release_sha,
    )
    pointer_size = positive_int(pointer.get("size_in_bytes"), "candidate inventory ZIP size")
    if pointer_size > MAX_JSON_BYTES:
        raise ValueError("candidate inventory ZIP exceeds the size limit")
    with tempfile.TemporaryDirectory(prefix="row-candidate-inventory-") as temporary:
        extracted = Path(temporary)
        pointer_zip = extracted / "candidate-inventory.zip"
        actual_digest = client.download(
            f"actions/artifacts/{inventory_artifact_id}/zip", pointer_zip, max_bytes=MAX_JSON_BYTES,
        )
        if actual_digest != inventory_archive_digest or pointer_zip.stat().st_size != pointer_size:
            raise ValueError(
                "candidate inventory raw ZIP digest or size does not match GitHub and the pinned input"
            )
        unpacked = extracted / "unpacked"
        inventory_name = "release-candidate-inventory.json"
        extract_archive(pointer_zip, unpacked, max_expanded_bytes=MAX_JSON_BYTES, only_name=inventory_name)
        staged_bytes = (unpacked / inventory_name).read_bytes()
    if not approved_inventory.is_file() or approved_inventory.is_symlink():
        raise ValueError("approved candidate inventory must be a regular non-symlink file")
    approved_bytes = approved_inventory.read_bytes()
    if staged_bytes != approved_bytes:
        raise ValueError(
            "approved candidate inventory bytes do not match the pinned staging artifact"
        )
    verify_candidate_attestation(
        approved_inventory,
        repository=normalize_repository_from_api(run),
        release_tag=release_tag,
        release_sha=release_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        inventory_sha256=hashlib.sha256(approved_bytes).hexdigest(),
        build_event=run["event"],
    )
    inventory = json.loads(approved_bytes)
    records = validate_inventory(
        inventory,
        repository=normalize_repository_from_api(run),
        release_tag=release_tag,
        release_sha=release_sha,
        run_id=run_id,
        run_attempt=run_attempt,
    )
    if qualification_archives is not None:
        resolved = qualification_archives.resolve()
        assets = assets_root.resolve()
        if os.path.lexists(qualification_archives) or resolved.is_relative_to(assets) or assets.is_relative_to(resolved):
            raise ValueError("qualification archive output must be an unused path separate from the release assets")
    directory = None if qualification_archives is None else qualification_archives.parent
    with tempfile.TemporaryDirectory(prefix="row-promotion-qualifications-", dir=directory) as temporary:
        retained = Path(temporary) / "archives"
        retained.mkdir()
        download_qualification_archives(client, inventory, run_id, release_sha, retained)
        materialize_sealed_records(
            client, records, assets_root, inventory=inventory, run_id=run_id, release_sha=release_sha,
        )
        if qualification_archives is not None:
            retained.rename(qualification_archives)


def download_qualification_archives(
    client: GitHubClient, inventory: dict[str, Any], run_id: int, release_sha: str, archive_root: Path,
) -> None:
    if "managed_debian_update" in inventory:
        verify_sealed_debian_update(
            client, inventory["managed_debian_update"], run_id, release_sha,
            archive_output=archive_root / f"{MANAGED_DEBIAN_ARTIFACT}.zip",
        )
    if "rpm_smoke" in inventory:
        verify_sealed_rpm_smoke(
            client, inventory, run_id, release_sha, archive_output=archive_root / f"{RPM_ARTIFACT}.zip",
        )
    smoke = {**inventory.get("gui_smoke", {}), **inventory.get("linux_smoke", {})}
    verify_sealed_smoke(client, smoke, run_id, release_sha, archive_root=archive_root)


def materialize_sealed_records(
    client: GitHubClient, records: list[dict[str, Any]], assets_root: Path, *,
    inventory: dict[str, Any], run_id: int, release_sha: str,
) -> None:
    live: dict[str, dict[str, Any]] = {}
    for record in records:
        artifact_id = record["id"]
        metadata = client.json(f"actions/artifacts/{artifact_id}")
        check_artifact_metadata(
            metadata,
            artifact_id=artifact_id,
            name=record["name"],
            digest=record["archive_digest"],
            run_id=run_id,
            release_sha=release_sha,
        )
        live[record["name"]] = metadata
    managed_deb = None
    if inventory["schema_version"] >= SERVER_BUNDLE_SCHEMA_VERSION:
        managed_deb = (inventory["release_tag"], inventory["managed_debian_update"]["receipt"])
    materialize_records(client, live, assets_root, expected_records=records, managed_deb=managed_deb)


def check_build_run(
    run: dict[str, Any],
    *,
    release_tag: str,
    release_sha: str,
    run_id: int,
    run_attempt: int,
    require_success: bool,
) -> None:
    expected = {
        "id": run_id,
        "run_attempt": run_attempt,
        "head_branch": release_tag,
        "head_sha": release_sha,
    }
    for key, value in expected.items():
        if run.get(key) != value:
            raise ValueError(f"candidate build run {key} must be {value!r}, got {run.get(key)!r}")
    if run.get("event") not in ("push", "workflow_dispatch"):
        raise ValueError("candidate build run event must be push or workflow_dispatch")
    if not workflow_path_matches(run.get("path"), BUILD_WORKFLOW, release_tag):
        raise ValueError(
            f"candidate build run path must identify {BUILD_WORKFLOW!r} at tag {release_tag!r}"
        )
    if run_attempt != 1:
        raise ValueError("candidate build run attempt must be exactly 1")
    if require_success and (run.get("status"), run.get("conclusion")) != (
        "completed",
        "success",
    ):
        raise ValueError("candidate build run must be completed successfully before promotion")
    normalize_repository_from_api(run)


def normalize_repository_from_api(run: dict[str, Any]) -> str:
    repository = run.get("repository")
    full_name = repository.get("full_name") if isinstance(repository, dict) else None
    return normalize_repository(full_name)


def unique_artifacts(raw_artifacts: list[Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    folded: dict[str, str] = {}
    for item in raw_artifacts:
        if not isinstance(item, dict):
            raise ValueError("GitHub run artifact entries must be objects")
        name = item.get("name")
        if not safe_name(name):
            raise ValueError(f"GitHub run artifact name is unsafe: {name!r}")
        assert isinstance(name, str)
        key = name.casefold()
        if key in folded:
            raise ValueError(f"duplicate/case-colliding run artifacts: {folded[key]!r}, {name!r}")
        folded[key] = name
        result[name] = item
    return result


def materialize_records(
    client: GitHubClient,
    artifacts: dict[str, dict[str, Any]],
    assets_root: Path,
    *,
    expected_records: list[dict[str, Any]] | None = None,
    managed_deb: tuple[str, dict[str, Any]] | None = None,
    release_rpm: tuple[str, str] | None = None,
    smoked_installers: tuple[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if assets_root.is_symlink() or (
        assets_root.exists() and (not assets_root.is_dir() or any(assets_root.iterdir()))
    ):
        raise ValueError("assets root must be absent or an empty regular directory")
    expected_by_name = (
        {record["name"]: record for record in expected_records}
        if expected_records is not None
        else None
    )
    if expected_by_name is not None and set(artifacts) != set(expected_by_name):
        raise ValueError("live candidate artifact names do not match approved inventory")

    assets_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".row-release-staging-", dir=assets_root.parent) as temporary:
        staged_root = Path(temporary) / "assets"
        staged_root.mkdir()
        records = materialize_candidate_files(client, artifacts, staged_root, expected_by_name)
        if managed_deb is not None:
            release_tag, receipt = managed_deb
            require_managed_deb(records, release_tag, receipt["candidate_sha256"])
            package = staged_root / f"remote-ops-workspace-{release_tag}-linux-amd64.deb"
            verify_candidate_deb_metadata(package, receipt)
        if release_rpm is not None:
            require_release_rpm(records, *release_rpm)
        if smoked_installers is not None:
            require_smoked_installer_assets(records, *smoked_installers)
        if assets_root.is_symlink():
            raise ValueError("assets root became a symlink during staging")
        if assets_root.exists():
            assets_root.rmdir()
        publish_candidate_directory(staged_root, assets_root)
    return records


def publish_candidate_directory(staged_root: Path, assets_root: Path) -> None:
    expected = staged_root.lstat()

    def publish() -> None:
        current = staged_root.lstat()
        if (
            not stat.S_ISDIR(current.st_mode)
            or getattr(current, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            or (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino)
        ):
            raise ValueError("verified candidate staging directory changed before publication")
        if assets_root.is_symlink() or assets_root.exists():
            raise ValueError("candidate assets root appeared before publication")
        staged_root.rename(assets_root)

    retry_evidence_operation(publish)


def materialize_candidate_files(
    client: GitHubClient,
    artifacts: dict[str, dict[str, Any]],
    staged_root: Path,
    expected_by_name: dict[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    global_files: dict[str, str] = {}
    for name in sorted(artifacts):
        item = artifacts[name]
        artifact_id = positive_int(item.get("id"), f"artifact {name} id")
        digest = normalize_digest(item.get("digest"), f"artifact {name} digest")
        archive_size = positive_int(item.get("size_in_bytes"), f"artifact {name} size")
        if item.get("expired") is not False:
            raise ValueError(f"artifact {name} must be unexpired")
        with tempfile.TemporaryDirectory(prefix="row-release-artifact-") as temporary:
            temporary_root = Path(temporary)
            archive = temporary_root / "artifact.zip"
            actual_digest = client.download(f"actions/artifacts/{artifact_id}/zip", archive)
            if actual_digest != digest:
                raise ValueError(
                    f"artifact {name} raw ZIP digest must be {digest}, got {actual_digest}"
                )
            if archive.stat().st_size != archive_size:
                raise ValueError(f"artifact {name} raw ZIP size must match GitHub metadata")
            extracted_root = temporary_root / "unpacked"
            files = extract_archive(archive, extracted_root)
            for file_record in files:
                relative = file_record["path"]
                folded = relative.casefold()
                if folded in global_files:
                    raise ValueError(
                        f"candidate artifacts collide on release file {relative!r}: "
                        f"{global_files[folded]!r}, {name!r}"
                    )
                global_files[folded] = name
                shutil.copyfile(extracted_root / relative, staged_root / relative)
        record = {
            "id": artifact_id,
            "name": name,
            "archive_digest": digest,
            "size_in_bytes": archive_size,
            "files": files,
        }
        if expected_by_name is not None and record != expected_by_name.get(name):
            raise ValueError(f"artifact {name} bytes/metadata do not match approved inventory")
        records.append(record)
    return records


def validate_inventory(
    value: Any,
    *,
    repository: str,
    release_tag: str,
    release_sha: str,
    run_id: int,
    run_attempt: int,
) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError("approved candidate inventory must be an object")
    schema = value.get("schema_version")
    if type(schema) is not int or not LEGACY_SCHEMA_VERSION <= schema <= SCHEMA_VERSION:
        raise ValueError("approved candidate inventory schema version is unsupported")
    expected = {
        "repository": repository,
        "release_tag": release_tag,
        "release_sha": release_sha,
        "source_ref": f"refs/tags/{release_tag}",
        "workflow": BUILD_WORKFLOW,
        "build_run_id": run_id,
        "build_run_attempt": run_attempt,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise ValueError(f"approved candidate inventory {key} must be {wanted!r}")
    raw_records = value.get("artifacts")
    if not isinstance(raw_records, list):
        raise ValueError("approved candidate inventory artifacts must be a list")
    names: set[str] = set()
    ids: set[int] = set()
    records: list[dict[str, Any]] = []
    for item in raw_records:
        if not isinstance(item, dict):
            raise ValueError("approved candidate inventory artifact entries must be objects")
        name = item.get("name")
        if not safe_name(name) or name in names:
            raise ValueError(f"approved candidate artifact name is unsafe or duplicated: {name!r}")
        assert isinstance(name, str)
        artifact_id = positive_int(item.get("id"), f"artifact {name} id")
        if artifact_id in ids:
            raise ValueError(f"approved candidate artifact id is duplicated: {artifact_id}")
        ids.add(artifact_id)
        names.add(name)
        normalize_digest(item.get("archive_digest"), f"artifact {name} archive digest")
        positive_int(item.get("size_in_bytes"), f"artifact {name} size")
        files = item.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError(f"approved candidate artifact {name} files must be non-empty")
        records.append(item)
    if names != set(EXPECTED_ARTIFACT_NAMES):
        raise ValueError("approved candidate inventory must contain the exact standard artifact names")
    reports = value.get("runtime_reports")
    if not isinstance(reports, dict) or reports.keys() != RUNTIME_REPORT_ARTIFACT_NAMES.keys():
        raise ValueError("approved candidate inventory must contain all native runtime reports")
    for target, report in reports.items():
        if (
            not isinstance(report, dict) or set(report) != {"artifact_id", "archive_digest", "sha256", "size_bytes"}
            or DIGEST_RE.fullmatch(f'sha256:{report["sha256"]}') is None
        ):
            raise ValueError(f"approved candidate runtime report for {target} is invalid")
        report_id = positive_int(report["artifact_id"], f"runtime report {target} artifact id")
        if report_id in ids:
            raise ValueError(f"runtime report {target} artifact id is duplicated")
        ids.add(report_id)
        normalize_digest(report["archive_digest"], f"runtime report {target} archive digest")
        if positive_int(report["size_bytes"], f"runtime report {target} size") > MAX_JSON_BYTES:
            raise ValueError(f"runtime report {target} exceeds the size limit")
    if schema >= MANAGED_SCHEMA_VERSION or "managed_debian_update" in value:
        managed = value.get("managed_debian_update")
        artifact_id = validate_managed_report(
            managed, release_tag, release_sha, run_id, run_attempt,
            require_server_bundle=schema >= SERVER_BUNDLE_SCHEMA_VERSION,
        )
        if artifact_id in ids:
            raise ValueError(f"managed Debian report artifact id is duplicated: {artifact_id}")
        ids.add(artifact_id)
        require_managed_deb(records, release_tag, managed["receipt"]["candidate_sha256"])
    if schema >= RPM_SCHEMA_VERSION or "rpm_recovery" in value or "rpm_smoke" in value:
        artifact_id, rpm_sha = validate_rpm_report(
            value.get("rpm_recovery"), repository, release_tag, release_sha, run_id, run_attempt,
            require_managed=schema >= MANAGED_RPM_SCHEMA_VERSION,
        )
        if artifact_id in ids:
            raise ValueError(f"RPM recovery report artifact id is duplicated: {artifact_id}")
        ids.add(artifact_id)
        require_release_rpm(records, release_tag, rpm_sha)
        if schema >= RPM_SMOKE_SCHEMA_VERSION or "rpm_smoke" in value:
            validate_rpm_smoke_metadata(value.get("rpm_smoke"), value["rpm_recovery"]["receipt"])
    if schema >= GUI_SMOKE_SCHEMA_VERSION or "gui_smoke" in value:
        validate_smoke_records(value.get("gui_smoke"), ids, GUI_SMOKE_ARTIFACT_NAMES, "desktop GUI")
    if schema >= GUI_INSTALLER_SCHEMA_VERSION:
        require_smoked_installer_assets(records, release_tag, value["gui_smoke"])
    if schema >= LINUX_INSTALLER_SCHEMA_VERSION or "linux_smoke" in value:
        validate_smoke_records(value.get("linux_smoke"), ids, LINUX_SMOKE_ARTIFACT_NAMES, "Linux native")
        require_smoked_installer_assets(records, release_tag, value["linux_smoke"])
    return sorted(records, key=lambda item: item["name"])


def check_artifact_metadata(
    item: dict[str, Any],
    *,
    artifact_id: int,
    name: str,
    digest: str,
    run_id: int,
    release_sha: str,
) -> None:
    expected = {"id": artifact_id, "name": name, "digest": digest, "expired": False}
    for key, value in expected.items():
        if item.get(key) != value:
            raise ValueError(f"artifact {name} live {key} must be {value!r}")
    workflow_run = item.get("workflow_run")
    if not isinstance(workflow_run, dict):
        raise ValueError(f"artifact {name} must expose workflow_run identity")
    if workflow_run.get("id") != run_id or workflow_run.get("head_sha") != release_sha:
        raise ValueError(f"artifact {name} is not bound to the approved build run and SHA")


def verify_candidate_attestation(
    inventory_path: Path,
    *,
    repository: str,
    release_tag: str,
    release_sha: str,
    run_id: int,
    run_attempt: int,
    inventory_sha256: str,
    build_event: str,
) -> None:
    command = [
        "gh",
        "attestation",
        "verify",
        str(inventory_path),
        "--repo",
        repository,
        "--signer-workflow",
        f"{repository}/{BUILD_WORKFLOW}",
        "--source-digest",
        release_sha,
        "--source-ref",
        f"refs/tags/{release_tag}",
        "--predicate-type",
        "https://slsa.dev/provenance/v1",
        "--deny-self-hosted-runners",
        "--format",
        "json",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("candidate inventory attestation verification could not run") from exc
    if completed.returncode != 0:
        detail = completed.stderr[:2000].decode("utf-8", errors="replace")
        raise RuntimeError(f"candidate inventory attestation verification failed: {detail}")
    if len(completed.stdout) > MAX_JSON_BYTES:
        raise RuntimeError("candidate inventory attestation result exceeds the JSON size limit")
    payload = json.loads(completed.stdout)
    check_candidate_attestation_payload(
        payload,
        repository=repository,
        release_tag=release_tag,
        release_sha=release_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        inventory_sha256=inventory_sha256,
        build_event=build_event,
    )


def check_candidate_attestation_payload(
    payload: Any,
    *,
    repository: str,
    release_tag: str,
    release_sha: str,
    run_id: int,
    run_attempt: int,
    inventory_sha256: str,
    build_event: str,
) -> None:
    if not isinstance(payload, list) or not payload:
        raise ValueError("candidate inventory attestation verification returned no results")
    expected_run = (
        f"https://github.com/{repository}/actions/runs/{run_id}/attempts/{run_attempt}"
    )
    for item in payload:
        verification = item.get("verificationResult") if isinstance(item, dict) else None
        if not isinstance(verification, dict):
            continue
        timestamps = verification.get("verifiedTimestamps")
        signature = verification.get("signature")
        certificate = signature.get("certificate") if isinstance(signature, dict) else None
        if not isinstance(timestamps, list) or not timestamps or not isinstance(certificate, dict):
            continue
        if certificate_value(certificate, "sourceRepositoryURI") != f"https://github.com/{repository}":
            continue
        if str(certificate_value(certificate, "sourceRepositoryDigest")).lower() != release_sha:
            continue
        if certificate_value(certificate, "sourceRepositoryRef") != f"refs/tags/{release_tag}":
            continue
        if certificate_value(certificate, "runnerEnvironment") != "github-hosted":
            continue
        if certificate_value(certificate, "buildTrigger", "githubWorkflowTrigger") != build_event:
            continue
        invocation = certificate_value(certificate, "runInvocationURI", "runnerInvocationURI")
        match = RUN_URI_RE.fullmatch(invocation) if isinstance(invocation, str) else None
        if (
            match is None
            or match.group(1).casefold() != repository.casefold()
            or invocation != expected_run
        ):
            continue
        statement = verification.get("statement")
        if not statement_has_digest(statement, inventory_sha256):
            continue
        return
    raise ValueError(
        "candidate inventory lacks a witnessed exact-tag attestation from the supplied build run attempt"
    )


def certificate_value(certificate: dict[str, Any], *names: str) -> Any:
    wanted = {name.casefold() for name in names}
    for key, value in certificate.items():
        if isinstance(key, str) and key.casefold() in wanted:
            return value
    return None


def statement_has_digest(statement: Any, digest: str) -> bool:
    if not isinstance(statement, dict):
        return False
    if statement.get("predicateType") != "https://slsa.dev/provenance/v1":
        return False
    subjects = statement.get("subject")
    return isinstance(subjects, list) and any(
        isinstance(subject, dict)
        and isinstance(subject.get("digest"), dict)
        and subject["digest"].get("sha256") == digest
        for subject in subjects
    )


def extract_archive(
    archive: Path, destination: Path, *,
    max_expanded_bytes: int = MAX_EXPANDED_BYTES,
    only_name: str | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    names: set[str] = set()
    expanded = 0
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if not members:
            raise ValueError("artifact ZIP must contain files")
        if len(members) > MAX_MEMBERS:
            raise ValueError(f"artifact ZIP exceeds {MAX_MEMBERS} members")
        if only_name is not None and [member.orig_filename for member in members] != [only_name]:
            raise ValueError(f"artifact ZIP must contain only {only_name}")
        for member in members:
            name = member.orig_filename
            if name != member.filename or not safe_name(name):
                raise ValueError(f"artifact ZIP must contain safe files at ZIP root: {name!r}")
            mode = (member.external_attr >> 16) & 0xFFFF
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG) or member.external_attr & 0x10:
                raise ValueError(f"artifact ZIP contains non-regular entry: {name!r}")
            if member.flag_bits & 1:
                raise ValueError(f"artifact ZIP contains encrypted entry: {name!r}")
            folded = name.casefold()
            if folded in names:
                raise ValueError(f"artifact ZIP contains duplicate/case-colliding path: {name!r}")
            names.add(folded)
            expanded += member.file_size
            if expanded > max_expanded_bytes:
                raise ValueError(f"artifact ZIP expands beyond {max_expanded_bytes} bytes")
        destination.mkdir(parents=True, exist_ok=True)
        for member in members:
            name = member.filename
            target = destination / name
            digest = hashlib.sha256()
            size = 0
            with bundle.open(member) as source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
                    output.write(chunk)
            if size != member.file_size:
                raise ValueError(f"artifact ZIP size changed while extracting {name!r}")
            records.append({"path": name, "size": size, "sha256": digest.hexdigest()})
    return sorted(records, key=lambda item: item["path"].casefold())


def origin(value: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(value)
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def normalize_repository(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("repository must be owner/name")
    result = value.strip().strip("/")
    if REPOSITORY_RE.fullmatch(result) is None:
        raise ValueError("repository must be owner/name")
    return result


def normalize_tag(value: Any) -> str:
    if not isinstance(value, str) or TAG_RE.fullmatch(value.strip()) is None:
        raise ValueError("release tag must look like vX.Y.Z")
    return value.strip()


def normalize_sha(value: Any) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value.strip().lower()) is None:
        raise ValueError("release SHA must be a full 40-character hexadecimal commit id")
    return value.strip().lower()


def normalize_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value.strip().lower()) is None:
        raise ValueError(f"{label} must be sha256:<64 lowercase hex characters>")
    return value.strip().lower()


def positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if result < 1 or str(result) != str(value).strip():
        raise ValueError(f"{label} must be a positive integer")
    return result


def safe_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value.strip() == value
        and not value.endswith(".")
        and UNSAFE_FILENAME_RE.search(value) is None
        and WINDOWS_DEVICE_NAME_RE.fullmatch(value.partition(".")[0].rstrip(" ")) is None
    )


def workflow_path_matches(value: Any, workflow: str, tag: str) -> bool:
    return isinstance(value, str) and value in {
        workflow,
        f"{workflow}@{tag}",
        f"{workflow}@refs/tags/{tag}",
    }


if __name__ == "__main__":
    raise SystemExit(main())
