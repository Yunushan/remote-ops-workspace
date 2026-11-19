"""Exercise authenticated RPM upgrades and rollback in an offline Fedora container."""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from remote_ops_workspace.state_lock import exclusive_file_lock  # noqa: E402
from scripts import managed_rpm_qualification as contract  # noqa: E402
from scripts.managed_rpm_update import (  # noqa: E402
    JOURNAL,
    LAUNCHER,
    PREVIOUS,
    SYSTEM_LOCK,
    SYSTEM_LOCK_ROOT,
)
from scripts.qualify_managed_debian_update import https_feed, stage_policy  # noqa: E402
from scripts.qualify_rpm_recovery import (  # noqa: E402
    ENV,
    PACKAGE,
    RPM,
    checked,
    read_package,
    seed,
    sha256,
    state_digests,
    validate_container,
    verify_installed,
    verify_workspace,
)

INTERRUPT = """
import os
import sys
sys.path[:0] = [sys.argv[1], sys.argv[1] + '/src']
from scripts import managed_rpm_update as controller
real_write = controller.journal_write
boundary = sys.argv[2]
def write(path, state, phase):
    if phase == boundary:
        os._exit(88)
    next_state = real_write(path, state, phase)
    if 'after-' + phase == boundary:
        os._exit(88)
    return next_state
controller.journal_write = write
raise SystemExit(controller.main(sys.argv[3:]))
"""


def require(condition, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def controller(args: list[str], *, ca: Path | None = None, exits: tuple[int, ...] = (0,),
               interrupt: str | None = None) -> dict:
    environment = {**ENV, "HOME": "/root"}
    if ca is not None:
        environment["SSL_CERT_FILE"] = str(ca)
    command = [sys.executable, "-I", "-B"]
    if interrupt is None:
        command += [str(ROOT / contract.CONTROLLER)]
    else:
        command += ["-c", INTERRUPT, str(ROOT), interrupt]
    result = subprocess.run([*command, *args], env=environment, capture_output=True, text=True, timeout=240, check=False)
    if interrupt is not None:
        require(result.returncode == 88, f"Managed RPM controller did not reach interruption boundary {interrupt}")
        return {}
    state = json.loads(result.stdout)
    require(result.returncode in exits and isinstance(state, dict),
            f"Managed RPM {args[0]} returned an unexpected result (exit {result.returncode}, {state})")
    return state


def private_transaction(root: Path, name: str, workspace: Path) -> tuple[Path, list[str]]:
    path = root / name
    path.mkdir(mode=0o700)
    return path, ["--workspace", str(workspace), "--transaction", str(path)]


def exercise(args: argparse.Namespace, root: Path) -> dict:
    old = read_package(args.previous_rpm, args.previous_sha256)
    new = read_package(args.candidate_rpm, args.candidate_sha256)
    require(tuple(map(int, old.version.split("."))) < tuple(map(int, new.version.split("."))),
            "The predecessor RPM must be older than the candidate")
    checked("Install predecessor", RPM, "--upgrade", args.previous_rpm)
    verify_installed(old)
    workspace = root / "workspace"
    environment = {**ENV, "HOME": str(root), "ROW_HOME": str(workspace), "ROW_VAULT_PASSWORD": secrets.token_urlsafe(32)}
    checked("Initialize vault", LAUNCHER, "vault", "init", env=environment)
    secret = secrets.token_urlsafe(32)
    seed(environment, "managed-original", secret)
    verify_workspace(root, environment, {"managed-original": secret})
    before = state_digests(workspace)

    payloads, requested = {}, []
    signer = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    transaction, flags = private_transaction(root, "transaction", workspace)
    journal = transaction / JOURNAL
    with https_feed(root, payloads, now, requests=requested) as (origin, ca):
        old_policy, old_stage = stage_policy(root, "previous", args.previous_rpm, old.version, old.version,
                                             origin=origin, now=now, signer=signer, payloads=payloads)
        new_policy, new_stage = stage_policy(root, "candidate", args.candidate_rpm, new.version, old.version,
                                             origin=origin, now=now, signer=signer, payloads=payloads)
        update_flags = ["--version", new.version, "--policy", str(new_policy), "--stage", str(new_stage),
                        "--previous-policy", str(old_policy), "--previous-stage", str(old_stage)]
        update = ["update", *update_flags, *flags]
        refusal = controller(update, exits=(1,))
        require(refusal == {"phase": "refused", "refusal": "https-transport-refused"}
                and not journal.exists() and not requested, "The controller did not refuse the untrusted HTTPS feed")
        verify_installed(old)
        applied = controller(update, ca=ca)
        require(applied["phase"] == "applied" and applied["previous"]["sha256"] == old.package_sha256
                and applied["candidate"]["sha256"] == new.package_sha256 and requested == list(payloads),
                "Managed upgrade did not bind both expected downloads")
        verify_installed(new)
        require(state_digests(workspace) == before, "Managed upgrade changed saved workspace data")

    require(controller(update) == applied, "Offline retry did not recognize the exact candidate")
    restore = ["rollback", *flags]
    retained = transaction / PREVIOUS
    with retained.open("r+b") as stream:
        first = stream.read(1)
        stream.seek(0)
        stream.write(bytes([first[0] ^ 1]))
    require(controller(restore, exits=(1,))["refusal"] == "installer-digest-mismatch",
            "Rollback did not reject a changed retained installer")
    verify_installed(new)
    retained.write_bytes(args.previous_rpm.read_bytes())

    original_launcher = LAUNCHER.read_bytes()
    try:
        with LAUNCHER.open("ab") as stream:
            stream.write(b"invalid")
        require(controller(restore, exits=(1,))["refusal"] == "installed-launcher-digest-refused",
                "Rollback did not reject a changed candidate launcher")
    finally:
        LAUNCHER.write_bytes(original_launcher)
        checked("Restore candidate package metadata", RPM, "--restore", PACKAGE)
    verify_installed(new)

    controller(restore, interrupt="rolled-back")
    verify_installed(old)
    require(json.loads(journal.read_bytes())["phase"] == "rolling-back", "Rollback journal did not retain pending state")
    restored = controller(restore)
    completed_journal = journal.read_bytes()
    require(restored["phase"] == "rolled-back" and controller(restore) == restored
            and journal.read_bytes() == completed_journal, "Interrupted rollback did not finish offline and stay complete")

    interrupted, interrupted_flags = private_transaction(root, "interrupted-update", workspace)
    interrupted_update = ["update", *update_flags, *interrupted_flags]
    controller(interrupted_update, interrupt="applied")
    verify_installed(new)
    require(json.loads((interrupted / JOURNAL).read_bytes())["phase"] == "applying"
            and controller(interrupted_update, exits=(1,))["phase"] == "rolled-back",
            "Interrupted upgrade did not recover the predecessor offline")
    verify_installed(old)

    _, repair_flags = private_transaction(root, "repair-predecessor", workspace)
    controller(["update", *update_flags, *repair_flags], interrupt="after-applying")
    verify_installed(old)
    with LAUNCHER.open("ab") as stream:
        stream.write(b"partial-write-fixture")
    require(sha256(LAUNCHER) != old.launcher_sha256 and controller(["rollback", *repair_flags])["phase"] == "rolled-back",
            "Recovery did not repair the interrupted predecessor")
    verify_installed(old)

    contenders = [private_transaction(root, f"contender-{index}", workspace) for index in (1, 2)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        with exclusive_file_lock(SYSTEM_LOCK_ROOT / SYSTEM_LOCK):
            futures = [executor.submit(controller, ["update", *update_flags, *options], exits=(0, 1))
                       for _, options in contenders]
            finished, _ = wait(futures, timeout=0.7)
            require(not finished and all(not (path / JOURNAL).exists() for path, _ in contenders),
                    "A controller bypassed the shared system lease")
        outcomes = [future.result(timeout=240) for future in futures]
    require(sorted(result["phase"] for result in outcomes) == ["applied", "refused"],
            "Parallel managed updates did not produce exactly one upgrade")
    winner = next(index for index, outcome in enumerate(outcomes) if outcome["phase"] == "applied")
    require(outcomes[1 - winner]["refusal"] == "update-version-not-newer", "The second update refused for another reason")
    verify_installed(new)
    require(controller(["rollback", *contenders[winner][1]])["phase"] == "rolled-back",
            "The winning transaction did not roll back")
    verify_installed(old)
    verify_workspace(root, environment, {"managed-original": secret})
    require(state_digests(workspace) == before and sha256(args.previous_rpm) == old.package_sha256
            and sha256(args.candidate_rpm) == new.package_sha256, "Qualification changed saved workspace data or RPM inputs")

    return {
        "schema": contract.SCHEMA,
        "feed": contract.FEED,
        "controller_sha256": sha256(ROOT / contract.CONTROLLER),
        "crypto_requirements_sha256": sha256(args.crypto_requirements),
        "previous": asdict(old),
        "candidate": asdict(new),
        "requests": requested,
        "checks": dict.fromkeys(contract.CHECKS, True),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ("previous", "candidate"):
        parser.add_argument(f"--{role}-rpm", type=Path, required=True)
        parser.add_argument(f"--{role}-sha256", required=True)
    parser.add_argument("--crypto-requirements", type=Path, required=True)
    args = parser.parse_args()
    validate_container()
    require(args.crypto_requirements.read_bytes() == contract.locked_crypto_requirements(ROOT),
            "The managed RPM drill did not consume the committed dependency requirements")
    with TemporaryDirectory(prefix="row-managed-rpm-", dir="/var/lib") as directory:
        report = exercise(args, Path(directory))
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
