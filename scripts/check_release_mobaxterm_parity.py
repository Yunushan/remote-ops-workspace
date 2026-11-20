"""Verify reviewed MobaXterm parity evidence for one published release."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any, BinaryIO

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
for location in (ROOT, SCRIPTS):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from check_mobaxterm_parity_evidence import (  # noqa: E402
    ARTICLE_SPECS,
    GITHUB_REVIEW_RE,
    GITHUB_WORKFLOW_RUN_RE,
    check_mobaxterm_parity_evidence,
    review_acceptance_line,
    valid_utc_timestamp,
)
from check_python315_ci_evidence import JOBS_PAGE_SIZE, collect_paginated_attempt_jobs  # noqa: E402
from check_release_license_compliance import path_is_reparse, secure_regular_file  # noqa: E402
from check_release_provenance import (  # noqa: E402
    local_release_assets,
    normalize_repository,
    normalize_sha,
    normalize_tag,
    run_gh_json,
    sha256_file,
    workflow_path_matches,
)

from scripts.check_moba_professional_deployment_evidence import (  # noqa: E402
    verify_hosted_professional_update,
)
from scripts.check_moba_server_release_evidence import (  # noqa: E402
    verify_packaged_debian_server_evidence,
)
from scripts.make_mobaxterm_parity_evidence_record import VALIDATORS  # noqa: E402
from scripts.release_candidate_inventory import (  # noqa: E402
    DIGEST_RE,
    MAX_ARCHIVE_BYTES,
    MAX_EXPANDED_BYTES,
    MAX_JSON_BYTES,
    MAX_MEMBERS,
    GitHubClient,
    safe_name,
)

REGISTRY = "configs/mobaxterm_parity_evidence.json"
MOBAPT_WORKFLOW = ".github/workflows/mobapt-offline-evidence.yml"
MOBAPT_JOB = "Qualify published Debian package"
X11_WORKFLOW = ".github/workflows/x11-forwarding-evidence.yml"
X11_JOB = "Qualify packaged X11 forwarding"
SERVER_WORKFLOW = ".github/workflows/embedded-server-evidence.yml"
SERVER_JOB = "Qualify the published Debian package's embedded servers"
EDITOR_WORKFLOW = ".github/workflows/connected-editor-evidence.yml"
EDITOR_JOB = "Qualify the published wheel's connected editor"
MACRO_WORKFLOW = ".github/workflows/macro-replay-evidence.yml"
MACRO_JOB = "Qualify the published wheel's timed macro replay"
SMARTCARD_WORKFLOW = ".github/workflows/smartcard-browser-evidence.yml"
SMARTCARD_JOB = "Qualify physical smart-card SSH and SFTP"
TRANSPORT_WORKFLOW = ".github/workflows/transport-terminal-evidence.yml"
TRANSPORT_JOB = "Qualify native terminal-grid and shared SSH"
PROFESSIONAL_WORKFLOW = ".github/workflows/professional-deployment-evidence.yml"
PROFESSIONAL_BUILD_JOB = "Build the signed Professional installers"
PROFESSIONAL_POLICY_JOB = "Capture the live Professional policy surfaces"
PROFESSIONAL_JOB = "Qualify the branded Professional deployment"


@dataclass(frozen=True)
class EvidenceWorkflow:
    label: str
    path: str
    job: str
    artifact_prefix: str
    runner_labels: frozenset[str] = frozenset()
    prerequisite_jobs: tuple[tuple[str, frozenset[str]], ...] = ()


@dataclass(frozen=True)
class EvidenceAttempt:
    completed_at: str
    archive_window: tuple[str, str] | None
    actor_ids: frozenset[int]


EVIDENCE_WORKFLOWS = {
    "mobapt-unix-runtime": EvidenceWorkflow("MobApt", MOBAPT_WORKFLOW, MOBAPT_JOB, "mobapt-offline-evidence"),
    "embedded-x-server": EvidenceWorkflow("X11", X11_WORKFLOW, X11_JOB, "x11-forwarding-evidence"),
    "embedded-server-suite": EvidenceWorkflow(
        "Embedded servers", SERVER_WORKFLOW, SERVER_JOB, "embedded-server-evidence",
        frozenset({"ubuntu-24.04"}),
    ),
    "moba-text-editor-diff": EvidenceWorkflow(
        "Connected editor", EDITOR_WORKFLOW, EDITOR_JOB, "connected-editor-evidence",
    ),
    "macro-recorder": EvidenceWorkflow("Macro replay", MACRO_WORKFLOW, MACRO_JOB, "macro-replay-evidence"),
    "ssh-browser-26-4-smartcard": EvidenceWorkflow(
        "Smart card", SMARTCARD_WORKFLOW, SMARTCARD_JOB, "smartcard-browser-evidence",
        frozenset({"self-hosted", "linux", "x64", "smartcard-evidence"}),
    ),
    "professional-deployment": EvidenceWorkflow(
        "Professional deployment", PROFESSIONAL_WORKFLOW, PROFESSIONAL_JOB, "professional-deployment-evidence",
        frozenset({"windows-latest"}), (
            (PROFESSIONAL_BUILD_JOB, frozenset({"windows-latest"})),
            (PROFESSIONAL_POLICY_JOB, frozenset({"ubuntu-24.04"})),
        ),
    ),
    "shared-authenticated-transport-terminal-grid": EvidenceWorkflow(
        "Terminal grid", TRANSPORT_WORKFLOW, TRANSPORT_JOB, "transport-terminal-evidence",
        frozenset({"self-hosted", "linux", "x64", "transport-evidence"}),
    ),
}


def github_object(repository: str, resource: str) -> dict[str, Any]:
    value = run_gh_json(
        ["api", "--hostname", "github.com", f"repos/{repository}/{resource}"],
        resource,
        timeout=30,
    )
    if not isinstance(value, dict):
        raise ValueError(f"GitHub {resource} must return a JSON object")
    return value


def require_ancestor(repository: str, ancestor: str, descendant: str) -> None:
    if ancestor == descendant:
        return
    comparison = github_object(repository, f"compare/{ancestor}...{descendant}?per_page=1")
    base = comparison.get("base_commit")
    common = comparison.get("merge_base_commit")
    if (
        comparison.get("status") != "ahead"
        or type(comparison.get("behind_by")) is not int
        or comparison["behind_by"] != 0
        or not isinstance(base, dict)
        or base.get("sha") != ancestor
        or not isinstance(common, dict)
        or common.get("sha") != ancestor
    ):
        raise ValueError(f"GitHub did not establish {ancestor} as an ancestor of {descendant}")


def load_registry(repository: str, release_sha: str, registry_commit: str) -> dict[str, Any]:
    branch = github_object(repository, "branches/main")
    commit = branch.get("commit")
    if branch.get("name") != "main" or branch.get("protected") is not True or not isinstance(commit, dict):
        raise ValueError("GitHub must report a protected main branch")
    tip = commit.get("sha")
    if not isinstance(tip, str) or normalize_sha(tip) != tip:
        raise ValueError("GitHub main branch must resolve to a canonical commit SHA")
    if registry_commit == release_sha:
        raise ValueError("parity registry commit must follow the release source commit")
    require_ancestor(repository, release_sha, registry_commit)
    require_ancestor(repository, registry_commit, tip)

    file = github_object(repository, f"contents/{REGISTRY}?ref={registry_commit}")
    encoded = file.get("content")
    if (
        file.get("type") != "file"
        or file.get("path") != REGISTRY
        or file.get("encoding") != "base64"
        or not isinstance(encoded, str)
    ):
        raise ValueError("GitHub must return the parity registry file at the pinned commit")
    try:
        payload = base64.b64decode("".join(encoded.splitlines()), validate=True)
    except ValueError as exc:
        raise ValueError("GitHub parity registry has invalid base64 content") from exc
    if type(file.get("size")) is not int or len(payload) != file["size"]:
        raise ValueError("GitHub parity registry content length differs from its metadata")
    registry = json.loads(payload)
    if not isinstance(registry, dict):
        raise ValueError("GitHub parity registry must contain a JSON object")
    return registry


def successful_evidence_job(
    jobs: list[dict[str, Any]], name: str, runner_labels: frozenset[str], workflow_label: str,
) -> dict[str, Any]:
    matches = [job for job in jobs if job.get("name") == name and job.get("conclusion") == "success"]
    if len(matches) != 1:
        raise ValueError(f"{workflow_label} evidence attempt must contain one successful qualification job")
    job = matches[0]
    if runner_labels:
        labels = job.get("labels")
        if (
            not isinstance(labels, list) or not all(isinstance(label, str) for label in labels)
            or not runner_labels.issubset(label.casefold() for label in labels)
        ):
            raise ValueError(f"{workflow_label} evidence job did not report the approved native runner labels")
    return job


def verify_workflow_run(
    repository: str, source: dict[str, Any], *, evidence_workflow: EvidenceWorkflow | None = None,
) -> EvidenceAttempt:
    match = GITHUB_WORKFLOW_RUN_RE.fullmatch(source["workflow_run_url"])
    assert match is not None  # The registry validator checked the URL.
    run_id = int(match.group(2))
    attempt = source["run_attempt"]
    endpoint = f"actions/runs/{run_id}/attempts/{attempt}"
    run = github_object(repository, endpoint)
    expected = {
        "id": run_id,
        "run_attempt": attempt,
        "head_sha": source["head_sha"],
        "status": "completed",
        "conclusion": "success",
    }
    if (
        type(run.get("id")) is not int
        or type(run.get("run_attempt")) is not int
        or any(run.get(key) != value for key, value in expected.items())
    ):
        raise ValueError("GitHub workflow attempt does not match successful release evidence")
    for key in ("repository", "head_repository"):
        owner = run.get(key)
        if not isinstance(owner, dict) or owner.get("full_name") != repository:
            raise ValueError(f"GitHub workflow attempt {key} differs from the release repository")
    actor_ids = set()
    for key in ("actor", "triggering_actor"):
        actor = run.get(key)
        account_id = actor.get("id") if isinstance(actor, dict) else None
        if type(account_id) is not int or account_id < 1:
            raise ValueError(f"GitHub workflow attempt must identify its {key} account")
        actor_ids.add(account_id)
    if evidence_workflow is not None and (
        run.get("event") != "workflow_dispatch" or run.get("head_branch") != source["release_tag"]
        or not workflow_path_matches(run.get("path"), evidence_workflow.path, source["release_tag"])
    ):
        raise ValueError(f"{evidence_workflow.label} evidence must come from its dedicated workflow dispatched at the release tag")

    jobs = collect_paginated_attempt_jobs(
        lambda page: github_object(repository, f"{endpoint}/jobs?per_page={JOBS_PAGE_SIZE}&page={page}")
    )["jobs"]
    timestamps = []
    for job in jobs:
        if (
            job.get("status") != "completed" or job.get("head_sha") != source["head_sha"]
            or type(job.get("run_id")) is not int or job["run_id"] != run_id
            or type(job.get("run_attempt")) is not int or job["run_attempt"] != attempt
        ):
            raise ValueError("GitHub workflow job does not match the completed evidence attempt")
        if job.get("conclusion") == "skipped" and job.get("completed_at") is None:
            continue
        completed_at = job.get("completed_at")
        if not valid_utc_timestamp(completed_at):
            raise ValueError("GitHub evidence job is missing a valid completion timestamp")
        timestamps.append(completed_at)
    if not timestamps or not any(job.get("conclusion") == "success" for job in jobs):
        raise ValueError("GitHub evidence attempt has no successful jobs with completion timestamps")
    archive_window = None
    if evidence_workflow is not None:
        qualification = successful_evidence_job(jobs, evidence_workflow.job, evidence_workflow.runner_labels, evidence_workflow.label)
        for name, labels in evidence_workflow.prerequisite_jobs:
            successful_evidence_job(jobs, name, labels, f"{evidence_workflow.label} ({name})")
        started = qualification.get("started_at")
        completed = qualification["completed_at"]
        if not valid_utc_timestamp(started) or started > completed:
            raise ValueError("GitHub qualification job has an invalid start timestamp")
        archive_window = started, completed
    return EvidenceAttempt(max(timestamps), archive_window, frozenset(actor_ids))


def verify_review(repository: str, review: dict[str, Any]) -> tuple[int, set[str]]:
    url = review["review_url"]
    match = GITHUB_REVIEW_RE.fullmatch(url)
    assert match is not None  # The registry validator checked the URL.
    if "#pullrequestreview-" in url:
        identifier = int(match.group(3))
        result = github_object(repository, f"pulls/{match.group(2)}/reviews/{identifier}")
        if result.get("state") != "APPROVED":
            raise ValueError("GitHub pull request review is not approved")
        timestamp = result.get("submitted_at")
    else:
        identifier = int(match.group(3) or match.group(5))
        result = github_object(repository, f"issues/comments/{identifier}")
        timestamp = result.get("created_at")

    author = result.get("user")
    author_id = author.get("id") if isinstance(author, dict) else None
    if (
        type(result.get("id")) is not int
        or result["id"] != identifier
        or result.get("html_url") != url
        or timestamp != review["reviewed_at"]
        or not isinstance(author, dict)
        or author.get("login") != review["reviewer"]
        or type(author_id) is not int
        or author_id < 1
    ):
        raise ValueError("GitHub review identity differs from the accepted evidence record")
    body = result.get("body")
    if not isinstance(body, str):
        raise ValueError("GitHub review has no explicit parity acceptance")
    return author_id, set(body.splitlines())


def verify_article_evidence(record: dict[str, Any], evidence_root: Path) -> None:
    article = record["article_id"]
    root = evidence_root / article
    if path_is_reparse(root) or not root.is_dir():
        raise ValueError("reviewed article evidence directory must exist without a reparse point")

    # Use a closed file set so a validator cannot accidentally consume an
    # unreviewed adjacent file. All paths remain below the article directory.
    expected = record["evidence_assets_sha256"]
    evidence = "evidence.json"
    if expected.get(evidence) != record["evidence_file_sha256"]:
        raise ValueError("reviewed article evidence.json digest differs from its evidence inventory")
    remaining = set(expected)
    for directory, subdirs, files in os.walk(root, followlinks=False):
        current = Path(directory)
        if any(path_is_reparse(current / name) for name in subdirs):
            raise ValueError("reviewed article evidence contains a linked directory")
        for name in files:
            relative = (current / name).relative_to(root).as_posix()
            if relative not in remaining:
                raise ValueError(f"reviewed article evidence contains an unexpected file: {relative}")
            path, error = secure_regular_file(root, relative, "reviewed article evidence")
            if error is not None or path is None:
                raise ValueError(error or "reviewed article evidence file is unavailable")
            if sha256_file(path) != expected[relative]:
                raise ValueError(f"reviewed article evidence SHA-256 differs: {relative}")
            remaining.remove(relative)
    if remaining:
        raise ValueError(f"reviewed article evidence files are missing: {sorted(remaining)}")

    verified = VALIDATORS[article](root / evidence, assets_dir=root).to_dict()
    if verified.get("passed") is not True:
        raise ValueError("the article validator did not pass on the reviewed evidence")
    if verified.get("summary") != record["validation_summary"]["summary"]:
        raise ValueError("article validator results differ from the reviewed summary")


def download_workflow_archive(repository: str, artifact_id: int, path: Path, size: int) -> None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        try:
            login = subprocess.run(
                ["gh", "auth", "token", "--hostname", "github.com"],
                capture_output=True, check=True, timeout=15, text=True,
            )
        except (OSError, subprocess.SubprocessError):
            raise ValueError("GitHub Actions archive download requires GitHub CLI authentication") from None
        token = login.stdout.strip()
    if not token:
        raise ValueError("GitHub Actions archive download requires GitHub CLI authentication")
    client = GitHubClient(repository, token, api_url="https://api.github.com")
    client.download(f"actions/artifacts/{artifact_id}/zip", path, max_bytes=size)


def stream_sha256(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def verify_archive_contents(path: Path, record: dict[str, Any], size: int, digest: str) -> None:
    article = record["article_id"]
    expected = {f"{article}/{name}": checksum for name, checksum in record["evidence_assets_sha256"].items()}
    expected_directories = {
        parent.as_posix() + "/" for name in expected
        for parent in PurePosixPath(name).parents if parent.as_posix() != "."
    }
    candidate_fields = (
        "article_id", "evidence_type", "release_tag", "release_target", "validation_command",
        "evidence_file_sha256", "evidence_assets_sha256", "release_asset_urls", "artifact_sha256",
        "checks", "validation_summary",
    )
    candidate = {field: record[field] for field in candidate_fields}
    candidate["status"] = "candidate"
    try:
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size != size:
                raise ValueError("workflow artifact ZIP size differs from GitHub")
            if "sha256:" + stream_sha256(stream) != digest:
                raise ValueError("workflow artifact ZIP digest differs from GitHub")
            stream.seek(0)
            with zipfile.ZipFile(stream) as archive:
                members = archive.infolist()
                if len(members) > MAX_MEMBERS or sum(member.file_size for member in members) > MAX_EXPANDED_BYTES:
                    raise ValueError("workflow artifact ZIP exceeds the expansion limits")
                seen: set[str] = set()
                for member in members:
                    name = member.filename
                    mode = stat.S_IFMT(member.external_attr >> 16)
                    if (
                        name != member.orig_filename or name.casefold() in seen or member.flag_bits & 1
                        or not all(safe_name(part) for part in name.rstrip("/").split("/"))
                    ):
                        raise ValueError(f"workflow artifact ZIP has an unsafe or duplicate entry: {name!r}")
                    seen.add(name.casefold())
                    if member.is_dir():
                        if name not in expected_directories or mode not in (0, stat.S_IFDIR) or member.file_size:
                            raise ValueError(f"workflow artifact ZIP has an unexpected directory: {name!r}")
                    elif mode not in (0, stat.S_IFREG) or member.external_attr & 0x10:
                        raise ValueError(f"workflow artifact ZIP has a non-regular file: {name!r}")
                    elif name == "candidate.json":
                        if member.file_size > MAX_JSON_BYTES or json.loads(archive.read(member)) != candidate:
                            raise ValueError("workflow artifact candidate differs from the reviewed record")
                    elif name not in expected:
                        raise ValueError(f"workflow artifact ZIP has an unexpected file: {name!r}")
                    else:
                        with archive.open(member) as item:
                            if stream_sha256(item) != expected.pop(name):
                                raise ValueError(f"workflow artifact bytes differ from the reviewed evidence: {name}")
                if expected or "candidate.json" not in seen:
                    raise ValueError("workflow artifact ZIP is missing the candidate or reviewed evidence")
            after = os.fstat(stream.fileno())
            if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (
                before.st_size, before.st_mtime_ns, before.st_ctime_ns,
            ):
                raise ValueError("workflow artifact ZIP changed during verification")
    except zipfile.BadZipFile as exc:
        raise ValueError("workflow artifact is not a valid ZIP archive") from exc


def verify_hosted_evidence(
    repository: str, record: dict[str, Any], evidence_root: Path,
    workflow: EvidenceWorkflow, archive_window: tuple[str, str],
    *, retain_archive: bool = False,
) -> None:
    source = record["release_source"]
    match = GITHUB_WORKFLOW_RUN_RE.fullmatch(source["workflow_run_url"])
    assert match is not None
    run_id = int(match.group(2))
    name = f"{workflow.artifact_prefix}-{run_id}-{source['run_attempt']}"
    listing = github_object(repository, f"actions/runs/{run_id}/artifacts?name={name}&per_page=100")
    artifacts = listing.get("artifacts")
    if (type(listing.get("total_count")) is not int or listing["total_count"] != 1
            or not isinstance(artifacts, list) or len(artifacts) != 1 or not isinstance(artifacts[0], dict)):
        raise ValueError(f"GitHub must report one workflow artifact named {name}")
    artifact = artifacts[0]
    artifact_id, size, digest = (artifact.get(field) for field in ("id", "size_in_bytes", "digest"))
    run = artifact.get("workflow_run")
    created = artifact.get("created_at")
    if (
        artifact.get("name") != name or type(artifact_id) is not int or artifact_id < 1
        or type(size) is not int or not 0 < size <= MAX_ARCHIVE_BYTES
        or not isinstance(digest, str) or DIGEST_RE.fullmatch(digest) is None
        or type(artifact.get("expired")) is not bool
        or not isinstance(run, dict) or type(run.get("id")) is not int or run["id"] != run_id
        or run.get("head_sha") != source["head_sha"]
        or not valid_utc_timestamp(created) or not archive_window[0] <= created <= archive_window[1]
    ):
        raise ValueError(f"GitHub workflow artifact {name} does not match the exact evidence attempt")

    relative = f"workflow-artifacts/{name}.zip"
    retained = evidence_root / relative
    if not os.path.lexists(retained):
        if artifact["expired"]:
            raise ValueError(f"GitHub workflow artifact expired; retain its original ZIP at {relative}")
        archive_dir = retained.parent if retain_archive else None
        if archive_dir is not None:
            if path_is_reparse(archive_dir):
                raise ValueError("workflow-artifacts must be a real directory")
            archive_dir.mkdir(exist_ok=True)
            if path_is_reparse(archive_dir):
                raise ValueError("workflow-artifacts must be a real directory")
        with TemporaryDirectory(prefix=".row-parity-artifact-", dir=archive_dir) as scratch:
            archive = Path(scratch) / "artifact.zip"
            download_workflow_archive(repository, artifact_id, archive, size)
            verify_archive_contents(archive, record, size, digest)
            if not retain_archive:
                return
            try:
                # Both operations install verified bytes without replacing a concurrent writer's file.
                if os.name == "nt":
                    archive.rename(retained)
                else:
                    os.link(archive, retained)
                return
            except FileExistsError:
                pass
    archived, error = secure_regular_file(evidence_root, relative, "retained workflow artifact")
    if archived is None or error:
        raise ValueError(error)
    verify_archive_contents(archived, record, size, digest)


def audit_release(
    *,
    repository: str,
    tag: str,
    release_sha: str,
    registry_commit: str,
    assets_dir: Path,
    evidence_root: Path,
    professional_update_origins: list[str],
) -> list[str]:
    registry = load_registry(repository, release_sha, registry_commit)
    errors = check_mobaxterm_parity_evidence(registry=registry, require_complete=True)
    if errors:
        return errors
    return audit_reviewed_records(
        registry["accepted_evidence"], repository=repository, tag=tag, release_sha=release_sha,
        assets_dir=assets_dir, evidence_root=evidence_root, professional_update_origins=professional_update_origins,
    )


def audit_reviewed_records(
    records: list[dict[str, Any]],
    *,
    repository: str,
    tag: str,
    release_sha: str,
    assets_dir: Path,
    evidence_root: Path,
    professional_update_origins: list[str],
    sealed_assets: dict[str, str] | None = None,
    retain_workflow_artifacts: bool = False,
) -> list[str]:
    evidence_root = evidence_root.absolute()
    if not evidence_root.is_dir() or any(path_is_reparse(path) for path in (*evidence_root.parents, evidence_root)):
        return ["reviewed parity evidence root must be a real directory without linked parents"]
    assets, errors = local_release_assets(assets_dir)
    if errors:
        return errors

    digests: dict[str, str] = {}
    checked_runs: dict[tuple[str, int, EvidenceWorkflow | None], EvidenceAttempt] = {}
    checked_reviews: dict[tuple[str, str, str], tuple[int, set[str]]] = {}
    asset_kind = "published wheel" if sealed_assets is None else "sealed candidate wheel"
    asset_scope = "downloaded release asset" if sealed_assets is None else "staged candidate asset"
    for record in records:
        article = record["article_id"]
        source = record["release_source"]
        if record["release_tag"] != tag or source["repository"] != repository or source["head_sha"] != release_sha:
            errors.append(f"{article} accepted record must bind the exact release repository, tag, and source SHA")
            continue
        if article in {"moba-text-editor-diff", "macro-recorder", "ssh-browser-26-4-smartcard",
                       "shared-authenticated-transport-terminal-grid"}:
            tested = record["validation_summary"]["summary"]["tested_release_asset"]
            wheel = f"remote_ops_workspace-{tag[1:]}-py3-none-any.whl"
            if tested["name"] != wheel or record["release_target"] != "linux-x86_64":
                errors.append(f"{article} must verify the {asset_kind} on Linux x86_64")
                continue
        if article == "professional-deployment":
            asset = record["validation_summary"]["summary"]["tested_release_asset"]
            if asset["name"] != f"remote_ops_workspace-{tag[1:]}-py3-none-any.whl" or record["release_target"] != "windows-x64":
                errors.append(f"{article} must bind the {asset_kind} and the branded Windows x64 deployment")
                continue

        before_assets = len(errors)
        for name, expected in record["artifact_sha256"].items():
            if sealed_assets is not None and sealed_assets.get(name) != expected:
                errors.append(f"{article} reviewed SHA-256 differs from the sealed inventory: {name}")
                continue
            path = assets.get(name)
            if path is None:
                errors.append(f"{article} references a missing release asset: {name}")
                continue
            if name not in digests:
                digests[name] = sha256_file(path)
            if digests[name] != expected:
                errors.append(f"{article} SHA-256 differs from the {asset_scope}: {name}")
        if sealed_assets is not None and len(errors) != before_assets:
            continue

        evidence_workflow = EVIDENCE_WORKFLOWS.get(article)
        if article == "embedded-server-suite" and record["release_target"] != "linux-x86_64":
            evidence_workflow = None
        run_key = (source["workflow_run_url"], source["run_attempt"], evidence_workflow)
        review = record["acceptance_review"]
        review_key = (review["review_url"], review["reviewer"], review["reviewed_at"])
        try:
            if run_key not in checked_runs:
                checked_runs[run_key] = verify_workflow_run(repository, source, evidence_workflow=evidence_workflow)
            attempt = checked_runs[run_key]
            if review["reviewed_at"] < attempt.completed_at:
                raise ValueError("GitHub review predates completion of the evidence workflow attempt")
            if review_key not in checked_reviews:
                checked_reviews[review_key] = verify_review(repository, review)
            reviewer_id, acceptance_lines = checked_reviews[review_key]
            if reviewer_id in attempt.actor_ids:
                raise ValueError("GitHub reviewer must be independent of the workflow dispatcher and rerun initiator")
            if review_acceptance_line(record) not in acceptance_lines:
                raise ValueError("GitHub review does not explicitly accept this exact article evidence")
            verify_article_evidence(record, evidence_root)
            if article == "embedded-server-suite" and record["release_target"].startswith("linux-"):
                name = record["validation_summary"]["summary"]["tested_release_asset"]["name"]
                package = assets.get(name)
                if package is not None and digests.get(name) == record["artifact_sha256"][name]:
                    verify_packaged_debian_server_evidence(package, evidence_root / article, record["release_target"])
            if evidence_workflow is not None:
                assert attempt.archive_window is not None
                verify_hosted_evidence(
                    repository, record, evidence_root, evidence_workflow, attempt.archive_window,
                    retain_archive=retain_workflow_artifacts,
                )
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(f"{article} {exc}")
    if not errors:
        professional = next(row for row in records if row["article_id"] == "professional-deployment")
        root = evidence_root / "professional-deployment"
        try:
            verify_hosted_professional_update(
                root / "evidence.json", assets_dir=root, evidence_sha256=professional["evidence_file_sha256"],
                verified_installers=professional["validation_summary"]["summary"]["verified_windows_installers"],
                origins=professional_update_origins, published=True,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(f"professional-deployment {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--registry-commit", required=True, help="reviewed parity registry commit merged to main")
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--professional-update-origin", action="append", help="independently approved HTTPS origin for the organization update channel")
    args = parser.parse_args(argv)
    try:
        repository = normalize_repository(args.repository)
        if any(part in {".", ".."} for part in repository.split("/")):
            raise ValueError("repository must name a GitHub owner and repository")
        errors = audit_release(
            repository=repository,
            tag=normalize_tag(args.tag),
            release_sha=normalize_sha(args.sha),
            registry_commit=normalize_sha(args.registry_commit),
            assets_dir=args.assets_dir,
            evidence_root=args.evidence_root,
            professional_update_origins=(
                args.professional_update_origin
                or os.environ.get("RELEASE_PROFESSIONAL_UPDATE_ORIGINS", "").split()
            ),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        for error in errors:
            print(f"release MobaXterm parity: {error}", file=sys.stderr)
        return 1
    print(f"release MobaXterm parity: {len(ARTICLE_SPECS)}/{len(ARTICLE_SPECS)} articles verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
