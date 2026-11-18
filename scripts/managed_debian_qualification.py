"""Validate the result of an isolated managed Debian update drill."""

from __future__ import annotations

import re

REPORT_NAME = "managed-debian-update.json"
MANAGED_IMAGE = "python:3.14.7-slim-trixie@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d"
HASH = re.compile(r"[0-9a-f]{64}")


def validate_receipt(receipt: object, *, previous_sha: str, candidate_sha: str) -> None:
    error = "managed-debian-receipt-binding-mismatch"
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != "row.managed-debian-qualification.v1"
        or receipt.get("status") != "passed"
        or receipt.get("target") != "linux-x86_64"
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
    steps = receipt.get("receipts")
    if not isinstance(steps, dict) or steps.keys() != expected_steps.keys() or any(
        not isinstance(steps[name], dict)
        or (steps[name].get("phase"), steps[name].get("exit_code")) != expected
        for name, expected in expected_steps.items()
    ) or any(steps[name].get("refusal") != expected for name, expected in refusals.items()):
        raise ValueError(error)
