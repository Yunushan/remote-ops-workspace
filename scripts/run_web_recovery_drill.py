from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPOSE_FILE = ROOT / "docker" / "compose.yaml"
DEFAULT_OUTPUT = ROOT / "artifacts" / "recovery" / "web-recovery-evidence.json"
SCHEMA = "remote-ops-web-recovery-evidence/v1"
MARKER_SCHEMA = "remote-ops-web-recovery-marker/v1"
MARKER_PATH = "recovery-drill/revision.json"
SENTINEL_PATH = "recovery-drill/post-backup-sentinel"
SERVICE_NAME = "remote-ops-web"
COMPOSE_VOLUME = "remote-ops-data"
EXPECTED_USER = "10001:10001"
EXPECTED_MEMORY_LIMIT = 256 * 1024 * 1024
SHA_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
PROJECT_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,40}")
WORKFLOW_URL_RE = re.compile(r"https://github\.com/([^/]+/[^/]+)/actions/runs/[1-9][0-9]*")


class DrillError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def run_text(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"+ {shlex.join(command)}", flush=True)
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        detail = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        raise DrillError(f"command failed with exit {result.returncode}: {detail[:2000]}")
    return result


def run_to_file(command: list[str], output: Path) -> None:
    print(f"+ {shlex.join(command)} > {output.name}", flush=True)
    with output.open("wb") as handle:
        result = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise DrillError(f"backup command failed with exit {result.returncode}: {detail[:2000]}")


def run_from_file(command: list[str], source: Path) -> None:
    print(f"+ {shlex.join(command)} < {source.name}", flush=True)
    with source.open("rb") as handle:
        result = subprocess.run(
            command,
            stdin=handle,
            capture_output=True,
            check=False,
        )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise DrillError(f"restore command failed with exit {result.returncode}: {detail[:2000]}")


def compose_command(compose_file: Path, project_name: str, *args: str) -> list[str]:
    return ["docker", "compose", "-p", project_name, "-f", str(compose_file), *args]


def wait_for_health(url: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error = "health endpoint was not attempted"
    opener = build_opener(ProxyHandler({}))
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=3) as response:  # noqa: S310 - fixed loopback URL is validated
                body = response.read()
                if response.status == 200 and body:
                    return {
                        "status_code": response.status,
                        "body_sha256": sha256_bytes(body),
                        "body_size_bytes": len(body),
                    }
                last_error = f"status={response.status} body_size={len(body)}"
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        time.sleep(1)
    raise DrillError(f"health endpoint {url!r} was not ready within {timeout_seconds}s: {last_error}")


def inspect_hardening(container_id: str, volume_name: str) -> dict[str, Any]:
    result = run_text(["docker", "inspect", container_id])
    rows = json.loads(result.stdout)
    if not isinstance(rows, list) or len(rows) != 1:
        raise DrillError("docker inspect did not return exactly one container")
    row = rows[0]
    if not isinstance(row, dict):
        raise DrillError("docker inspect container record is not an object")
    config = mapping(row.get("Config"))
    host = mapping(row.get("HostConfig"))
    raw_mounts = row.get("Mounts")
    mounts = [mapping(item) for item in raw_mounts] if isinstance(raw_mounts, list) else []
    data_mount: dict[str, Any] = next(
        (item for item in mounts if item.get("Destination") == "/data"), {}
    )
    checks = {
        "non_root_user": config.get("User") == EXPECTED_USER,
        "read_only_rootfs": host.get("ReadonlyRootfs") is True,
        "pids_limit": host.get("PidsLimit") == 128,
        "memory_limit_bytes": host.get("Memory") == EXPECTED_MEMORY_LIMIT,
        "all_capabilities_dropped": set(host.get("CapDrop") or []) == {"ALL"},
        "no_new_privileges": "no-new-privileges:true" in (host.get("SecurityOpt") or []),
        "bounded_local_logs": host.get("LogConfig", {}).get("Type") == "local",
        "restart_policy": host.get("RestartPolicy", {}).get("Name") == "unless-stopped",
        "named_data_volume": (
            data_mount.get("Type") == "volume"
            and data_mount.get("Name") == volume_name
            and data_mount.get("RW") is True
        ),
    }
    return {"verified": all(checks.values()), **checks}


def find_compose_volume(project_name: str) -> str:
    result = run_text(
        [
            "docker",
            "volume",
            "ls",
            "--filter",
            f"label=com.docker.compose.project={project_name}",
            "--filter",
            f"label=com.docker.compose.volume={COMPOSE_VOLUME}",
            "--format",
            "{{.Name}}",
        ]
    )
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(names) != 1:
        raise DrillError(f"expected exactly one Compose data volume, found {names}")
    return names[0]


def write_running_service_file(compose: list[str], path: str, content: bytes) -> None:
    encoded = base64.b64encode(content).decode("ascii")
    code = (
        "import base64, pathlib, sys; "
        "p=pathlib.Path('/data')/sys.argv[1]; "
        "p.parent.mkdir(parents=True, exist_ok=True); "
        "p.write_bytes(base64.b64decode(sys.argv[2]))"
    )
    run_text([*compose, "exec", "-T", SERVICE_NAME, "python", "-c", code, path, encoded])


def write_volume_file(image_id: str, volume_name: str, path: str, content: bytes) -> None:
    encoded = base64.b64encode(content).decode("ascii")
    code = (
        "import base64, pathlib, sys; "
        "p=pathlib.Path('/data')/sys.argv[1]; "
        "p.parent.mkdir(parents=True, exist_ok=True); "
        "p.write_bytes(base64.b64decode(sys.argv[2]))"
    )
    run_text(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            EXPECTED_USER,
            "--volume",
            f"{volume_name}:/data",
            image_id,
            "python",
            "-c",
            code,
            path,
            encoded,
        ]
    )


def read_restored_state(image_id: str, volume_name: str) -> dict[str, Any]:
    code = (
        "import base64, json, pathlib; "
        f"marker=pathlib.Path('/data/{MARKER_PATH}'); "
        f"sentinel=pathlib.Path('/data/{SENTINEL_PATH}'); "
        "print(json.dumps({'marker_b64':base64.b64encode(marker.read_bytes()).decode('ascii'),"
        "'sentinel_exists':sentinel.exists()}))"
    )
    result = run_text(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            EXPECTED_USER,
            "--volume",
            f"{volume_name}:/data:ro",
            image_id,
            "python",
            "-c",
            code,
        ]
    )
    value = json.loads(result.stdout)
    value["marker"] = base64.b64decode(value.pop("marker_b64"))
    return value


def archive_marker_bytes(archive_path: Path) -> bytes:
    marker: bytes | None = None
    seen_names: set[str] = set()
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            name = member.name
            while name.startswith("./"):
                name = name[2:]
            path = PurePosixPath(name)
            if not name or path.is_absolute() or ".." in path.parts:
                raise DrillError(f"backup archive has unsafe member path: {member.name!r}")
            if name in seen_names:
                raise DrillError(f"backup archive has duplicate member path: {member.name!r}")
            seen_names.add(name)
            if not (member.isfile() or member.isdir()):
                raise DrillError(f"backup archive has unsupported member type: {member.name!r}")
            if name == MARKER_PATH:
                if not member.isfile():
                    raise DrillError("backup revision marker is not a regular file")
                handle = archive.extractfile(member)
                if handle is None:
                    raise DrillError("backup revision marker could not be read")
                marker = handle.read()
    if marker is None:
        raise DrillError("backup archive is missing the revision marker")
    return marker


def validate_identity(repository: str, source_sha: str, workflow_run_url: str, run_attempt: int) -> list[str]:
    errors: list[str] = []
    if not REPOSITORY_RE.fullmatch(repository):
        errors.append("repository must be in owner/name form")
    if not SHA_RE.fullmatch(source_sha):
        errors.append("source_sha must be a lowercase 40-character Git SHA")
    match = WORKFLOW_URL_RE.fullmatch(workflow_run_url)
    if match is None or match.group(1) != repository:
        errors.append("workflow_run_url must be a numeric GitHub Actions run URL for repository")
    if run_attempt < 1:
        errors.append("run_attempt must be positive")
    return errors


def validate_evidence(
    evidence: dict[str, Any],
    *,
    expected_repository: str,
    expected_source_sha: str,
    expected_workflow_run_url: str,
    expected_run_attempt: int,
    expected_project_name: str = "row-web-recovery",
    expected_compose_file: str = "docker/compose.yaml",
) -> list[str]:
    errors = validate_identity(
        expected_repository,
        expected_source_sha,
        expected_workflow_run_url,
        expected_run_attempt,
    )
    if not PROJECT_RE.fullmatch(expected_project_name):
        errors.append("expected_project_name must use lowercase Docker Compose-safe characters")
    compose_path = PurePosixPath(expected_compose_file)
    if compose_path.is_absolute() or ".." in compose_path.parts or "\\" in expected_compose_file:
        errors.append("expected_compose_file must be a sanitized relative POSIX path")
    expected = {
        "schema": SCHEMA,
        "status": "passed",
        "repository": expected_repository,
        "source_sha": expected_source_sha,
        "workflow_run_url": expected_workflow_run_url,
        "workflow_run_attempt": expected_run_attempt,
        "project_name": expected_project_name,
        "compose_file": expected_compose_file,
        "revision": expected_source_sha,
    }
    for key, value in expected.items():
        if evidence.get(key) != value:
            errors.append(f"evidence {key} must be {value!r}")
    for key in ("started_at_utc", "completed_at_utc"):
        raw = evidence.get(key)
        if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", raw):
            errors.append(f"evidence {key} must be an RFC 3339 UTC second timestamp")
    started = evidence.get("started_at_utc")
    completed = evidence.get("completed_at_utc")
    if isinstance(started, str) and isinstance(completed, str) and completed < started:
        errors.append("evidence completed_at_utc must not precede started_at_utc")
    for key in ("compose_sha256", "revision_sha256"):
        if not DIGEST_RE.fullmatch(str(evidence.get(key, ""))):
            errors.append(f"evidence {key} must be a lowercase SHA-256 digest")
    expected_marker = {
        "schema": MARKER_SCHEMA,
        "repository": expected_repository,
        "revision": expected_source_sha,
        "source_sha": expected_source_sha,
        "workflow_run_url": expected_workflow_run_url,
        "workflow_run_attempt": expected_run_attempt,
        "created_at_utc": evidence.get("started_at_utc"),
    }
    if evidence.get("marker") != expected_marker:
        errors.append("evidence marker must bind the repository, source, run, attempt and start time")
    if evidence.get("revision_sha256") != sha256_bytes(canonical_json_bytes(expected_marker)):
        errors.append("evidence revision_sha256 must match the canonical marker")
    image_id = evidence.get("image_id")
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        errors.append("evidence image_id must be an immutable Docker image ID")
    backup = mapping(evidence.get("backup"))
    if not DIGEST_RE.fullmatch(str(backup.get("sha256", ""))):
        errors.append("evidence backup.sha256 must be a lowercase SHA-256 digest")
    if not isinstance(backup.get("size_bytes"), int) or backup.get("size_bytes", 0) <= 0:
        errors.append("evidence backup.size_bytes must be positive")
    for key in ("archive_validated", "marker_bound", "payload_uploaded"):
        expected_value = key != "payload_uploaded"
        if backup.get(key) is not expected_value:
            errors.append(f"evidence backup.{key} must be {expected_value}")
    recovery = mapping(evidence.get("recovery"))
    for key in (
        "original_volume_removed",
        "fresh_volume_created",
        "restored_revision_verified",
        "post_backup_sentinel_absent",
    ):
        if recovery.get(key) is not True:
            errors.append(f"evidence recovery.{key} must be true")
    health = mapping(evidence.get("health"))
    for phase in ("before_backup", "after_restore"):
        row = mapping(health.get(phase))
        if row.get("status_code") != 200:
            errors.append(f"evidence health.{phase}.status_code must be 200")
        if not DIGEST_RE.fullmatch(str(row.get("body_sha256", ""))):
            errors.append(f"evidence health.{phase}.body_sha256 must be a SHA-256 digest")
        if not isinstance(row.get("body_size_bytes"), int) or row.get("body_size_bytes", 0) <= 0:
            errors.append(f"evidence health.{phase}.body_size_bytes must be positive")
    hardening = mapping(evidence.get("hardening"))
    hardening_checks = (
        "non_root_user",
        "read_only_rootfs",
        "pids_limit",
        "memory_limit_bytes",
        "all_capabilities_dropped",
        "no_new_privileges",
        "bounded_local_logs",
        "restart_policy",
        "named_data_volume",
    )
    for phase in ("before_backup", "after_restore"):
        row = mapping(hardening.get(phase))
        if row.get("verified") is not True:
            errors.append(f"evidence hardening.{phase}.verified must be true")
        for key in hardening_checks:
            if row.get(key) is not True:
                errors.append(f"evidence hardening.{phase}.{key} must be true")
    before_health = mapping(health.get("before_backup"))
    after_health = mapping(health.get("after_restore"))
    if before_health.get("body_sha256") != after_health.get("body_sha256"):
        errors.append("evidence health response digest must match before backup and after restore")
    if evidence.get("volume_name") != f"{expected_project_name}_{COMPOSE_VOLUME}":
        errors.append("evidence volume_name must match the isolated Compose project volume")
    cleanup = mapping(evidence.get("cleanup"))
    if cleanup.get("completed") is not True:
        errors.append("evidence cleanup.completed must be true")
    if evidence.get("failure") is not None:
        errors.append("passed evidence failure must be null")
    return errors


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def cleanup_project(compose: list[str]) -> bool:
    result = run_text([*compose, "down", "--volumes", "--remove-orphans"], check=False)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
    return result.returncode == 0


def run_drill(args: argparse.Namespace) -> int:
    compose_file = Path(args.compose_file).resolve()
    output = Path(args.output).resolve()
    compose = compose_command(compose_file, args.project_name)
    started = utc_now()
    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "failed",
        "repository": args.repository,
        "source_sha": args.source_sha,
        "workflow_run_url": args.workflow_run_url,
        "workflow_run_attempt": args.run_attempt,
        "started_at_utc": started,
        "completed_at_utc": started,
        "project_name": args.project_name,
        "compose_file": evidence_compose_path(compose_file),
        "compose_sha256": "",
        "image_id": "",
        "volume_name": "",
        "revision": args.source_sha,
        "revision_sha256": "",
        "marker": {},
        "backup": {},
        "recovery": {},
        "health": {},
        "hardening": {},
        "cleanup": {"completed": False},
        "failure": None,
    }
    exit_code = 1
    try:
        identity_errors = validate_identity(
            args.repository, args.source_sha, args.workflow_run_url, args.run_attempt
        )
        if identity_errors:
            raise DrillError("; ".join(identity_errors))
        if not PROJECT_RE.fullmatch(args.project_name):
            raise DrillError("project_name must use lowercase Docker Compose-safe characters")
        if not compose_file.is_file():
            raise DrillError(f"Compose file does not exist: {compose_file}")
        if args.health_url != "http://127.0.0.1:8765/healthz":
            raise DrillError("health_url must use the checked-in loopback health endpoint")
        evidence["compose_sha256"] = sha256_file(compose_file)
        cleanup_project(compose)
        run_text([*compose, "up", "--detach", "--build"])
        health_before = wait_for_health(args.health_url, args.health_timeout_seconds)
        container_id = run_text([*compose, "ps", "-q", SERVICE_NAME]).stdout.strip()
        if not container_id:
            raise DrillError("Compose did not return the Web/PWA container ID")
        image_id = run_text(["docker", "inspect", "--format", "{{.Image}}", container_id]).stdout.strip()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            raise DrillError(f"container image ID is not immutable: {image_id!r}")
        volume_name = find_compose_volume(args.project_name)
        evidence["image_id"] = image_id
        evidence["volume_name"] = volume_name
        evidence["health"]["before_backup"] = health_before
        evidence["hardening"]["before_backup"] = inspect_hardening(container_id, volume_name)
        if not evidence["hardening"]["before_backup"]["verified"]:
            raise DrillError("pre-backup container hardening verification failed")

        marker_value = {
            "schema": MARKER_SCHEMA,
            "repository": args.repository,
            "revision": args.source_sha,
            "source_sha": args.source_sha,
            "workflow_run_url": args.workflow_run_url,
            "workflow_run_attempt": args.run_attempt,
            "created_at_utc": started,
        }
        marker = canonical_json_bytes(marker_value)
        evidence["marker"] = marker_value
        evidence["revision_sha256"] = sha256_bytes(marker)
        write_running_service_file(compose, MARKER_PATH, marker)
        run_text([*compose, "stop", SERVICE_NAME])

        with tempfile.TemporaryDirectory(prefix="row-web-recovery-") as raw_temp:
            backup_path = Path(raw_temp) / "remote-ops-data.tar.gz"
            run_to_file(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--user",
                    "0:0",
                    "--volume",
                    f"{volume_name}:/data:ro",
                    image_id,
                    "tar",
                    "--numeric-owner",
                    "-C",
                    "/data",
                    "-czf",
                    "-",
                    ".",
                ],
                backup_path,
            )
            archived_marker = archive_marker_bytes(backup_path)
            if archived_marker != marker:
                raise DrillError("backup archive revision marker does not match the source marker")
            evidence["backup"] = {
                "sha256": sha256_file(backup_path),
                "size_bytes": backup_path.stat().st_size,
                "archive_validated": True,
                "marker_bound": True,
                "payload_uploaded": False,
            }
            write_volume_file(image_id, volume_name, SENTINEL_PATH, b"must-not-survive-restore\n")

            if not cleanup_project(compose):
                raise DrillError("failed to remove the original Compose project and volume")
            removed_result = run_text(["docker", "volume", "inspect", volume_name], check=False)
            if removed_result.returncode == 0:
                raise DrillError("original data volume still exists after destructive cleanup")
            removed_detail = f"{removed_result.stdout}\n{removed_result.stderr}".lower()
            if "no such volume" not in removed_detail:
                raise DrillError("could not prove original volume removal: " + removed_detail.strip()[:1000])
            evidence["recovery"]["original_volume_removed"] = True

            run_text(
                [
                    "docker",
                    "volume",
                    "create",
                    "--label",
                    f"com.docker.compose.project={args.project_name}",
                    "--label",
                    f"com.docker.compose.volume={COMPOSE_VOLUME}",
                    volume_name,
                ]
            )
            volume_row = json.loads(run_text(["docker", "volume", "inspect", volume_name]).stdout)[0]
            labels = volume_row.get("Labels") or {}
            if labels.get("com.docker.compose.project") != args.project_name or labels.get(
                "com.docker.compose.volume"
            ) != COMPOSE_VOLUME:
                raise DrillError("fresh volume is missing the expected Compose ownership labels")
            evidence["recovery"]["fresh_volume_created"] = True
            run_from_file(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--user",
                    "0:0",
                    "--interactive",
                    "--volume",
                    f"{volume_name}:/data",
                    image_id,
                    "tar",
                    "--numeric-owner",
                    "-C",
                    "/data",
                    "-xzf",
                    "-",
                ],
                backup_path,
            )
            run_text(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--user",
                    "0:0",
                    "--volume",
                    f"{volume_name}:/data",
                    image_id,
                    "chown",
                    "-R",
                    EXPECTED_USER,
                    "/data",
                ]
            )

        restored = read_restored_state(image_id, volume_name)
        if restored["marker"] != marker:
            raise DrillError("restored revision marker does not match the backup revision")
        if restored["sentinel_exists"]:
            raise DrillError("post-backup sentinel survived, so fresh-volume restore was not proved")
        evidence["recovery"]["restored_revision_verified"] = True
        evidence["recovery"]["post_backup_sentinel_absent"] = True

        run_text([*compose, "up", "--detach"])
        health_after = wait_for_health(args.health_url, args.health_timeout_seconds)
        restored_container_id = run_text([*compose, "ps", "-q", SERVICE_NAME]).stdout.strip()
        evidence["health"]["after_restore"] = health_after
        evidence["hardening"]["after_restore"] = inspect_hardening(restored_container_id, volume_name)
        if not evidence["hardening"]["after_restore"]["verified"]:
            raise DrillError("post-restore container hardening verification failed")
        if not cleanup_project(compose):
            raise DrillError("post-drill Compose cleanup failed")
        evidence["cleanup"]["completed"] = True
        evidence["status"] = "passed"
        exit_code = 0
    except Exception as exc:  # evidence must survive every operational failure
        evidence["failure"] = {"type": type(exc).__name__, "message": str(exc)[:2000]}
        evidence["cleanup"]["completed"] = cleanup_project(compose)
        print(f"web recovery drill failed: {exc}", file=sys.stderr)
    finally:
        evidence["completed_at_utc"] = utc_now()
        write_evidence(output, evidence)

    if exit_code == 0:
        errors = validate_evidence(
            evidence,
            expected_repository=args.repository,
            expected_source_sha=args.source_sha,
            expected_workflow_run_url=args.workflow_run_url,
            expected_run_attempt=args.run_attempt,
            expected_project_name=args.project_name,
            expected_compose_file=evidence_compose_path(compose_file),
        )
        if errors:
            evidence["status"] = "failed"
            evidence["failure"] = {"type": "EvidenceValidationError", "message": "; ".join(errors)}
            write_evidence(output, evidence)
            print("web recovery evidence validation failed: " + "; ".join(errors), file=sys.stderr)
            return 1
        print(f"Web/PWA recovery drill passed; evidence: {output}")
    return exit_code


def evidence_compose_path(compose_file: Path) -> str:
    try:
        return compose_file.relative_to(ROOT).as_posix()
    except ValueError:
        return compose_file.name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Destructively exercise and record Web/PWA Compose volume backup and restore."
    )
    parser.add_argument("--compose-file", default=str(DEFAULT_COMPOSE_FILE))
    parser.add_argument("--project-name", default="row-web-recovery")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-run-url", required=True)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--health-url", default="http://127.0.0.1:8765/healthz")
    parser.add_argument("--health-timeout-seconds", type=int, default=60)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.health_timeout_seconds < 1 or args.health_timeout_seconds > 300:
        raise SystemExit("--health-timeout-seconds must be between 1 and 300")
    return run_drill(args)


if __name__ == "__main__":
    raise SystemExit(main())
