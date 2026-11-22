"""Validate the result of an isolated managed Debian update drill."""

from __future__ import annotations

import re
from signal import SIGTERM

REPORT_NAME = "managed-debian-update.json"
MANAGED_IMAGE = "python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f"
DEBIAN_TARGETS = {"linux-x86_64": ("amd64", "x86_64"), "linux-arm64": ("arm64", "aarch64")}
HASH = re.compile(r"[0-9a-f]{64}")
SCHEMA = "row.managed-debian-qualification.v6"
ROLLBACK_PLAN_SCHEMA = "row.managed-debian-qualification.v5"
UPGRADE_PLAN_SCHEMA = "row.managed-debian-qualification.v4"
INTERRUPTION_SCHEMA = "row.managed-debian-qualification.v3"
AUTOMATIC_SCHEMA = "row.managed-debian-qualification.v2"
PREVIOUS_SCHEMA = "row.managed-debian-qualification.v1"


def validate_receipt(
    receipt: object, *, previous_sha: str, candidate_sha: str,
    require_automatic: bool = False, require_current: bool = False, expected_target: str = "linux-x86_64",
) -> None:
    error = "managed-debian-receipt-binding-mismatch"
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") not in (
            SCHEMA, ROLLBACK_PLAN_SCHEMA, UPGRADE_PLAN_SCHEMA, INTERRUPTION_SCHEMA, AUTOMATIC_SCHEMA, PREVIOUS_SCHEMA,
        )
        or require_automatic and receipt.get("schema") == PREVIOUS_SCHEMA
        or require_current and receipt.get("schema") != SCHEMA
        or receipt.get("status") != "passed"
        or expected_target not in DEBIAN_TARGETS
        or receipt.get("target") != expected_target
        or receipt.get("production_acceptance") is not False
        or receipt.get("previous_sha256") != previous_sha or receipt.get("candidate_sha256") != candidate_sha
        or receipt.get("download_server_closed_before_apply") is not True
        or receipt.get("workspace_unchanged") is not True
        or type(receipt.get("candidate_has_server_bundle")) is not bool
    ):
        raise ValueError(error)
    expected_steps = {
        "previous": ("authenticated-staged", 0), "candidate": ("authenticated-staged", 0),
        "failing": ("authenticated-staged", 0), "interrupted": ("authenticated-staged", 0),
        "candidate-apply": ("applied", 0), "explicit-rollback": ("rolled-back", 0),
        "changed-launcher-rollback": ("refused", 1),
        "failing-apply": ("rolled-back", 1), "interrupted-apply": ("rolled-back", 1),
    }
    refusals = {"changed-launcher-rollback": "installed-launcher-digest-refused"}
    if receipt["candidate_has_server_bundle"]:
        expected_steps["changed-server-manifest-rollback"] = ("refused", 1)
        refusals["changed-server-manifest-rollback"] = "installed-runtime-payload-refused"
    automatic_actions = {}
    if receipt["schema"] != PREVIOUS_SCHEMA:
        expected_steps.update({
            "automatic-candidate": ("applied", 0), "automatic-failing": ("rolled-back", 1),
            "automatic-explicit-rollback": ("rolled-back", 0),
        })
        automatic_actions = {
            "candidate-apply": "update", "interrupted-apply": "update", "automatic-candidate": "update",
            "automatic-failing": "update", "automatic-explicit-rollback": "rollback",
        }
    if receipt["schema"] in (SCHEMA, ROLLBACK_PLAN_SCHEMA, UPGRADE_PLAN_SCHEMA, INTERRUPTION_SCHEMA):
        expected_steps.update({"rollback-interruption": ("rolling-back", -SIGTERM), "repeated-rollback": ("rolled-back", 0)})
        automatic_actions.update({
            "rollback-interruption": "rollback", "explicit-rollback": "rollback", "repeated-rollback": "rollback",
        })
    if receipt["schema"] in (SCHEMA, ROLLBACK_PLAN_SCHEMA, UPGRADE_PLAN_SCHEMA):
        expected_steps.update({"dependency-blocked": ("authenticated-staged", 0),
                               "dependency-blocked-apply": ("refused", 1)})
        refusals["dependency-blocked-apply"] = "debian-upgrade-plan-refused"
    if receipt["schema"] in (SCHEMA, ROLLBACK_PLAN_SCHEMA):
        expected_steps.update({"dependency-blocked-rollback": ("refused", 1),
                               "dependency-blocked-update-retry": ("applied", 0)})
        refusals["dependency-blocked-rollback"] = "debian-rollback-plan-refused"
        automatic_actions["dependency-blocked-rollback"] = "rollback"
    steps = receipt.get("receipts")
    if not isinstance(steps, dict) or steps.keys() != expected_steps.keys() or any(
        not isinstance(steps[name], dict)
        or (steps[name].get("phase"), steps[name].get("exit_code")) != expected
        for name, expected in expected_steps.items()
    ) or any(steps[name].get("refusal") != expected for name, expected in refusals.items()):
        raise ValueError(error)
    # Historical x86-64 reports predate the explicit dpkg and kernel fields.
    # A new ARM64 report must bind the host, signed staging target and dpkg transactions.
    if expected_target == "linux-arm64" or "debian_architecture" in receipt or "kernel_machine" in receipt:
        architecture, machine = DEBIAN_TARGETS[expected_target]
        if (receipt["schema"] != SCHEMA
                or (receipt.get("debian_architecture"), receipt.get("kernel_machine")) != (architecture, machine)):
            raise ValueError(error)
        for step in steps.values():
            if step["phase"] == "authenticated-staged" and step.get("selected_target") != expected_target:
                raise ValueError(error)
            if step["phase"] in ("applied", "rolled-back") and step.get("architecture") != architecture:
                raise ValueError(error)
    for name, action in automatic_actions.items():
        if steps[name].get("action") != action or steps[name].get("previous_sha256") != previous_sha:
            raise ValueError(error)
    if automatic_actions:
        if any(steps[name].get("candidate_sha256") != candidate_sha for name in (
            "automatic-candidate", "automatic-explicit-rollback", "candidate-apply",
        )):
            raise ValueError(error)
        fault_sha = steps["automatic-failing"].get("candidate_sha256")
        if not isinstance(fault_sha, str) or HASH.fullmatch(fault_sha) is None or fault_sha == candidate_sha or (
            fault_sha != steps["failing-apply"].get("candidate_sha256")
        ):
            raise ValueError(error)
    if receipt["schema"] in (SCHEMA, ROLLBACK_PLAN_SCHEMA, UPGRADE_PLAN_SCHEMA, INTERRUPTION_SCHEMA):
        applied = steps["candidate-apply"]
        launcher_sha = applied.get("previous_launcher_sha256")
        if not isinstance(launcher_sha, str) or HASH.fullmatch(launcher_sha) is None or any(
            steps[name].get("candidate_sha256") != candidate_sha
            or steps[name].get("previous_launcher_sha256") != launcher_sha
            for name in ("rollback-interruption", "explicit-rollback", "repeated-rollback")
        ) or steps["explicit-rollback"] != steps["repeated-rollback"]:
            raise ValueError(error)
    if receipt["schema"] in (SCHEMA, ROLLBACK_PLAN_SCHEMA, UPGRADE_PLAN_SCHEMA):
        blocked = steps["dependency-blocked-apply"]
        blocked_sha = blocked.get("candidate_sha256")
        if (blocked.get("action") != "apply"
                or blocked.get("previous_sha256") != previous_sha
                or not isinstance(blocked_sha, str) or HASH.fullmatch(blocked_sha) is None
                or blocked_sha in (previous_sha, candidate_sha)
                or blocked.get("previous_installation_unchanged") is not True
                or blocked.get("journal_created") is not False):
            raise ValueError(error)
    if receipt["schema"] in (SCHEMA, ROLLBACK_PLAN_SCHEMA):
        refused = steps["dependency-blocked-rollback"]
        if (refused.get("candidate_sha256") != candidate_sha
                or refused.get("candidate_installation_unchanged") is not True
                or refused.get("journal_unchanged") is not True
                or steps["dependency-blocked-update-retry"] != steps["candidate-apply"]):
            raise ValueError(error)
    if receipt["schema"] == SCHEMA:
        count = steps["rollback-interruption"].get("native_rollback_invocations")
        if type(count) is not int or count != 1:
            raise ValueError(error)
