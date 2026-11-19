"""Verify an attested signed Windows MSI upgrade receipt for two exact packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src"), str(ROOT)]

from check_release_provenance import (  # noqa: E402
    RunInvocation,
    normalize_sha,
    normalize_tag,
    run_gh_json,
    verified_run_invocations,
    verify_workflow_attestation,
)
from inspect_windows_msi import (  # noqa: E402
    require,
    validate_managed_upgrade,
    validate_package,
    validate_upgrade_rollback,
)
from qualify_windows_msi_upgrade import (  # noqa: E402
    INSTALL_FAILURE,
    INSTALL_USER_EXIT,
    RECEIPT,
    REPOSITORY,
    SCHEMA,
    SOURCE_REF,
    WORKFLOW,
)
from windows_msi_stage_fixture import require_same_inputs  # noqa: E402

MAX_RECEIPT_BYTES = 1024 * 1024
RUN_NUMBER = re.compile(r"[1-9][0-9]{0,18}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
LAUNCHER = "Program Files/Remote Ops Workspace/bin/row.exe"
TARGET = "windows-x64"
MANUALLY_STAGED_SCHEMA = "row.signed-windows-msi-upgrade.v4"


@dataclass(frozen=True)
class PackageReference:
    tag: str
    source_commit: str
    msi_sha256: str

    @classmethod
    def parse(cls, values: list[str]) -> PackageReference:
        digest = values[2].lower()
        require(has_digest(digest), "expected a 64-character MSI SHA-256 digest")
        return cls(normalize_tag(values[0]), normalize_sha(values[1]), digest)


def object_field(parent: dict, name: str) -> dict:
    value = parent.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"receipt {name} must be an object")
    return value


def run_number(value: object) -> int:
    if not isinstance(value, str) or RUN_NUMBER.fullmatch(value) is None:
        raise ValueError("receipt run identifiers must be positive decimal strings")
    return int(value)


def has_digest(value: object) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def package(parent: dict, role: str, ref: PackageReference) -> dict:
    record = object_field(parent, role)
    require((record.get("release_tag"), record.get("release_sha"), record.get("sha256"))
            == (ref.tag, ref.source_commit, ref.msi_sha256), f"{role} MSI does not match the selected release bytes")
    validate_package(record, "x64", ref.tag[1:])
    require(record.get("name_on_release") == f"remote-ops-workspace-{ref.tag}-{TARGET}.msi"
            and has_digest(record.get("launcher_payload_sha256"))
            and type(record.get("size_bytes")) is int and record["size_bytes"] > 0
            and object_field(record, "source").get("kind") in ("immutable-release", "sealed-candidate"),
            f"{role} MSI has incomplete stock package identity")
    return record


def check_staging(report: dict, previous: dict, candidate: dict) -> dict:
    stage = object_field(report, "managed_staging")
    require(stage.get("feed") == "disposable-loopback-https", "receipt is missing managed HTTPS staging")
    if report["schema"] == SCHEMA:
        requests = [
            f"/{role}/{name}"
            for role, msi in (("previous", previous), ("candidate", candidate))
            for name in ("manifest.json", msi["name_on_release"])
        ]
        require(stage.get("initial_command") == "update"
                and stage.get("initial_stages_absent") is True
                and stage.get("https_requests") == requests
                and stage.get("feed_closed_before_retry") is True,
                "receipt is missing the one-command download and offline retry observations")
    for role, msi in (("previous", previous), ("candidate", candidate)):
        result = object_field(stage, role)
        require((result.get("phase"), result.get("version"), result.get("selected_target"),
                 result.get("selected_files"), result.get("artifact_total_bytes"))
                == ("authenticated-staged", msi["version"], TARGET, [msi["name_on_release"]], msi["size_bytes"])
                and all(result.get(key) is True for key in
                        ("whole_declared_asset_set_verified", "authenticity_checked", "windows_dacl_metadata_verified"))
                and result.get("install_permitted") is False
                and all(has_digest(result.get(key)) for key in
                        ("manifest_sha256", "trust_policy_sha256", "transaction_id")),
                f"receipt is missing authenticated private staging for the {role} MSI")
    require(stage["previous"]["transaction_id"] != stage["candidate"]["transaction_id"],
            "previous and candidate MSI stages share a transaction")
    return stage


def registration(msi: dict) -> dict:
    return {"state": "installed", "package_code": msi["package_code"], "version": msi["version"],
            "row_path": LAUNCHER, "launcher_sha256": msi["launcher_payload_sha256"]}


def check_recovery(report: dict, previous: dict, candidate: dict) -> None:
    refusal = object_field(report, "rollback_disabled_upgrade")
    require(refusal.get("exit_code") == INSTALL_FAILURE and all(
        refusal.get(key) is True for key in
        ("launch_condition_refused_upgrade", "previous_preserved", "candidate_absent", "workspace_preserved")
    ), "rollback-disabled refusal was not demonstrated")
    canceled = object_field(report, "cancellation")
    require(canceled.get("exit_code") == INSTALL_USER_EXIT
            and canceled.get("removal_started") is True
            and canceled.get("previous_launcher_absent_at_cancel") is True
            and canceled.get("installer_error_before_cancel") is False
            and report.get("candidate_absent_after_cancel") is True
            and report.get("original_workspace_preserved_after_cancel") is True,
            "the drill did not prove cancellation after predecessor removal")
    require(all(report.get(field) == registration(previous) for field in
                ("previous_installed", "previous_restored", "previous_reinstalled"))
            and report.get("candidate_installed") == registration(candidate)
            and report.get("previous_absent_after_retry") is True
            and report.get("stock_products_absent_after_uninstall") is True,
            "installed or restored registration differs from the verified package")
    recovered = object_field(report, "workspace_recovery")
    before, after = (object_field(recovered, field) for field in ("pre_upgrade_inventory", "upgraded_inventory"))
    require(has_digest(recovered.get("encrypted_backup_sha256"))
            and all(has_digest(row.get("sha256")) for row in (before, after)) and before["sha256"] != after["sha256"]
            and all(recovered.get(key) is True for key in
                    ("restored_matches_pre_upgrade", "upgraded_workspace_unchanged", "predecessor_decrypted_restored_vault")),
            "encrypted workspace recovery evidence is incomplete")


def check_receipt(report: dict, workflow_sha: str, previous_ref: PackageReference,
                  candidate_ref: PackageReference, *, require_automatic_update: bool = False) -> RunInvocation:
    versions = [tuple(map(int, ref.tag[1:].split("."))) for ref in (previous_ref, candidate_ref)]
    require(versions[0] < versions[1] and previous_ref.source_commit != candidate_ref.source_commit
            and previous_ref.msi_sha256 != candidate_ref.msi_sha256,
            "select two ordered versions from distinct commits with distinct MSI digests")
    require(report.get("schema") in (SCHEMA, MANUALLY_STAGED_SCHEMA)
            and (report.get("status"), report.get("phase"), report.get("target"), report.get("source_commit"))
            == ("passed", "complete", TARGET, workflow_sha)
            and report.get("input_read_only_sharing_held") is True,
            "expected a completed signed Windows x64 receipt from the selected workflow commit")
    require(not require_automatic_update or report["schema"] == SCHEMA,
            "one-command update verification requires an automatic update receipt")
    previous = package(report, "previous", previous_ref)
    candidate = package(report, "candidate", candidate_ref)
    require(all(previous[key] != candidate[key] for key in ("product_code", "package_code", "launcher_payload_sha256")),
            "previous and candidate MSI identities must be distinct")
    validate_upgrade_rollback(candidate.get("upgrade_sequence"), candidate.get("disable_rollback"))
    validate_managed_upgrade(candidate.get("major_upgrade"))

    stages = check_staging(report, previous, candidate)
    preflight, apply, retry = (object_field(report, name) for name in ("managed_preflight", "managed_apply", "managed_retry"))
    for result in (preflight, apply, retry):
        require_same_inputs(result, stages, previous, candidate)
    previous_launcher = previous["launcher_payload_sha256"]
    candidate_launcher = candidate["launcher_payload_sha256"]
    require((preflight.get("phase"), preflight.get("previous_launcher_sha256"))
            == ("msi-preflight-passed", previous_launcher)
            and type(apply.get("installer_exit_code")) is int
            and (apply.get("phase"), apply["installer_exit_code"], apply.get("previous_launcher_sha256"),
                 apply.get("installed_launcher_sha256")) == ("msi-applied", 0, previous_launcher, candidate_launcher)
            and (retry.get("phase"), retry.get("installed_launcher_sha256")) == ("msi-already-applied", candidate_launcher)
            and "installer_exit_code" not in retry, "managed preflight, apply, or no-op retry was not demonstrated")
    check_recovery(report, previous, candidate)
    return RunInvocation(REPOSITORY, run_number(report.get("run_id")), run_number(report.get("run_attempt")))


def require_successful_attempt(invocation: RunInvocation, workflow_sha: str) -> None:
    run = run_gh_json(
        ["api", "--method", "GET", f"repos/{REPOSITORY}/actions/runs/{invocation.run_id}/attempts/{invocation.attempt}"],
        "Windows MSI qualification workflow attempt", 60,
    )
    branch = SOURCE_REF.removeprefix("refs/heads/")
    expected = {"id": invocation.run_id, "run_attempt": invocation.attempt, "head_sha": workflow_sha,
                "head_branch": branch, "event": "workflow_dispatch", "status": "completed", "conclusion": "success"}
    require(isinstance(run, dict) and all(run.get(key) == value for key, value in expected.items())
            and run.get("path") in (WORKFLOW, f"{WORKFLOW}@{branch}", f"{WORKFLOW}@{SOURCE_REF}")
            and all(object_field(run, key).get("full_name") == REPOSITORY for key in ("repository", "head_repository")),
            "the attesting invocation is not a successful canonical Windows MSI qualification attempt")


def verify_receipt(path: Path, workflow_sha: str, previous: PackageReference,
                   candidate: PackageReference, *, require_automatic_update: bool = False) -> tuple[RunInvocation, str]:
    with path.open("rb") as stream:
        raw = stream.read(MAX_RECEIPT_BYTES + 1)
    require(0 < len(raw) <= MAX_RECEIPT_BYTES, "receipt exceeds the JSON byte limit or is empty")
    report = json.loads(raw)
    require(isinstance(report, dict), "receipt must be a JSON object")
    invocation = check_receipt(
        report, workflow_sha, previous, candidate, require_automatic_update=require_automatic_update,
    )
    digest = hashlib.sha256(raw).hexdigest()
    # Give the verifier exactly the bytes parsed above, even if the input file
    # is subsequently replaced. The attestation is looked up by this digest.
    with TemporaryDirectory(prefix="row-msi-upgrade-review-") as directory:
        frozen = Path(directory) / RECEIPT.name
        frozen.write_bytes(raw)
        proof = verify_workflow_attestation(
            frozen, repository=REPOSITORY, sha=workflow_sha, workflow=WORKFLOW, source_ref=SOURCE_REF,
        )
    invocations, errors = verified_run_invocations(
        proof, asset_name=RECEIPT.name, asset_sha256=digest, repository=REPOSITORY, sha=workflow_sha, source_ref=SOURCE_REF,
    )
    require(not errors and invocation in invocations,
            "receipt lacks a witnessed GitHub-hosted attestation for its exact bytes and workflow attempt")
    require_successful_attempt(invocation, workflow_sha)
    return invocation, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--workflow-sha", required=True, help="reviewed main-branch commit of the workflow")
    parser.add_argument("--require-automatic-update", action="store_true",
                        help="require the one-command download from empty stages and the offline retry")
    for name in ("previous", "candidate"):
        parser.add_argument(f"--{name}", nargs=3, required=True, metavar=("TAG", "COMMIT", "MSI_SHA256"))
    args = parser.parse_args(argv)
    try:
        invocation, digest = verify_receipt(
            args.receipt, normalize_sha(args.workflow_sha),
            PackageReference.parse(args.previous), PackageReference.parse(args.candidate),
            require_automatic_update=args.require_automatic_update,
        )
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        print(f"Windows MSI upgrade receipt: {exc}", file=sys.stderr)
        return 1
    print(f"Verified signed Windows MSI upgrade receipt {digest} from {invocation.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
