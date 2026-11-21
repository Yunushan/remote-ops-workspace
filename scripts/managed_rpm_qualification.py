"""Input and receipt contracts for the managed RPM qualification."""

from __future__ import annotations

import re
from pathlib import Path

from scripts.qualify_rpm_recovery import PACKAGE, SHA256

SCHEMA = "row.managed-rpm-qualification.v4"
ROLLBACK_PLAN_SCHEMA = "row.managed-rpm-qualification.v3"
PREVIOUS_SCHEMA = "row.managed-rpm-qualification.v2"
LEGACY_SCHEMA = "row.managed-rpm-qualification.v1"
CONTROLLER = Path("scripts/managed_rpm_update.py")
LOCK = Path("requirements-locks/source-linux-x86_64.txt")
FEED = "loopback-https-test-signer"
UPGRADE_BLOCKER = "row-qualification-upgrade-blocker"
ROLLBACK_BLOCKER = "row-qualification-rollback-blocker"
LEGACY_CHECKS = (
    "untrusted_tls_refused_before_install",
    "signed_loopback_upgrade_preserved_workspace",
    "offline_update_retry_verified_exact_candidate",
    "tampered_rollback_package_refused",
    "same_version_changed_launcher_refused",
    "interrupted_native_rollback_completed_offline",
    "interrupted_native_upgrade_recovered_predecessor_offline",
    "interrupted_predecessor_repaired_by_native_reinstall",
    "concurrent_controllers_applied_only_one_transaction",
)
PREVIOUS_CHECKS = (*LEGACY_CHECKS, "dependency_conflict_refused_and_same_transaction_retried_offline")
CHECKS = (*PREVIOUS_CHECKS, "rollback_conflict_preserved_applied_state_and_retried_offline")
CHECKS_BY_SCHEMA = {
    SCHEMA: CHECKS, ROLLBACK_PLAN_SCHEMA: CHECKS, PREVIOUS_SCHEMA: PREVIOUS_CHECKS, LEGACY_SCHEMA: LEGACY_CHECKS,
}


def locked_crypto_requirements(root: Path) -> bytes:
    text = (root / LOCK).read_text(encoding="utf-8")
    names = ("cffi", "cryptography", "pycparser")
    requirements = []
    for name in names:
        matches = re.findall(rf"(?m)^{name}==[^\n]+(?:\n[ ]+--hash=sha256:[^\n]+)+", text)
        if len(matches) != 1:
            raise ValueError(f"Managed RPM qualification requires one hash-locked {name} requirement")
        requirements.append(matches[0])
    return ("\n".join(requirements) + "\n").encode("ascii")


def verify_receipt(receipt: object, native: dict, *, controller_sha256: str | None = None,
                   requirements_sha256: str | None = None, require_current: bool = False) -> None:
    if (
        not isinstance(receipt, dict)
        or not isinstance(receipt.get("schema"), str) or receipt["schema"] not in CHECKS_BY_SCHEMA
        or receipt.get("feed") != FEED
        or any(not isinstance(receipt.get(key), str) or not SHA256.fullmatch(receipt[key])
               for key in ("controller_sha256", "crypto_requirements_sha256"))
        or (controller_sha256 is not None and receipt["controller_sha256"] != controller_sha256)
        or (requirements_sha256 is not None and receipt["crypto_requirements_sha256"] != requirements_sha256)
    ):
        raise ValueError("Managed RPM receipt is missing its controller, feed, or dependency binding")
    if require_current and receipt["schema"] != SCHEMA:
        raise ValueError("Managed RPM receipt must verify upgrade and rollback dependency-conflict recovery and installer retries")
    requests = []
    for role in ("previous", "candidate"):
        package = native[role]
        if receipt.get(role) != package:
            raise ValueError("Managed RPM receipt refers to a different package or launcher")
        requests.extend((f"/{role}/manifest.json",
                         f"/{role}/{PACKAGE}-v{package['version']}-linux-{package['architecture']}.rpm"))
    if receipt.get("requests") != requests:
        raise ValueError("Managed RPM receipt is missing the ordered HTTPS downloads")
    checks = receipt.get("checks")
    expected = CHECKS_BY_SCHEMA[receipt["schema"]]
    if not isinstance(checks, dict) or set(checks) != set(expected) or any(checks[key] is not True for key in expected):
        raise ValueError("Managed RPM receipt is missing passing upgrade and rollback checks")
    if receipt["schema"] == SCHEMA:
        count = receipt.get("interrupted_rollback_native_invocations")
        if type(count) is not int or count != 1:
            raise ValueError("Interrupted RPM rollback must record exactly one native installer invocation including retries")
