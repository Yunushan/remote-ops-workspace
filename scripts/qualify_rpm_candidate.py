"""Run offline native and managed RPM recovery drills against a byte-bound CI candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import managed_rpm_qualification as managed
from scripts.qualify_rpm_recovery import ARCH, PACKAGE, SHA256, VERSION, sha256

TARGET = "linux-x86_64"
SCHEMA = "row.rpm-candidate-qualification.v2"
NATIVE_ONLY_SCHEMA = "row.rpm-candidate-qualification.v1"
REPORT_NAME = "rpm-recovery.json"
PROOF = Path("build/candidate-proof") / TARGET / "finish.json"
SMOKE_BINDING = Path("build/native-smoke") / TARGET / "candidate-runtime-byte-binding.json"
DRILL = Path("scripts/qualify_rpm_recovery.py")
IMAGE = "quay.io/fedora/fedora-toolbox@sha256:0612cc841f649cda34bafbc3138a9a8eec2bc06fad6f6ad576d1a900f0b3c7da"
PREVIOUS_VERSION = "1.0.27"
PREVIOUS_SIZE = 32_092_015
PREVIOUS_SHA256 = "928e93ed2679fe01ce127e1393cf245df854bb6579c1356ed97cd9a5a3a1daf6"
PREVIOUS_ASSET = 597789828
PREVIOUS_URL = (
    f"https://github.com/Yunushan/remote-ops-workspace/releases/download/v{PREVIOUS_VERSION}/"
    f"{PACKAGE}-v{PREVIOUS_VERSION}-linux-{ARCH}.rpm"
)
CHECKS = (
    "upgrade_preserved_profiles_and_vault",
    "downgrade_refused_without_oldpackage",
    "explicit_downgrade_restored_previous_launcher",
    "restored_profiles_and_vault_read_by_previous_launcher",
    "upgraded_workspace_preserved",
)
MANAGED_ENTRYPOINT = """
mkdir /tmp/source
tar -xf /input/source.tar -C /tmp/source
python3 -I -m venv /tmp/managed-rpm
/tmp/managed-rpm/bin/python -I -m pip --isolated install --no-index --find-links=/wheels \
  --only-binary=:all: --require-hashes --no-deps --requirement /input/crypto.txt >&2
exec /tmp/managed-rpm/bin/python -I -B /tmp/source/scripts/qualify_managed_rpm_update.py \
  --crypto-requirements /input/crypto.txt "$@"
"""


class QualificationError(ValueError):
    """A failed input or receipt check with a public diagnostic."""


def rpm_name(version: str) -> str:
    return f"{PACKAGE}-v{version}-linux-{ARCH}.rpm"


def rpm_proof_asset(proof: dict, version: str, commit: str, run_id: str, attempt: str) -> dict:
    if (
        proof.get("target") != TARGET
        or proof["source"].get("head") != commit
        or str(proof.get("run_id")) != run_id
        or str(proof.get("run_attempt")) != attempt
        or proof.get("source_unchanged") is not True
        or proof.get("native_build_outcome") != "success"
        or proof.get("native_smoke_outcome") != "success"
        or proof["native_executable_byte_binding"].get("status") != "bound"
    ):
        raise QualificationError(
            "Native proof must bind the candidate source, run, and smoke outcome"
        )
    relative = f"native-dist/linux/{rpm_name(version)}"
    matches = [item for item in proof["assets"] if item.get("path") == relative]
    if len(matches) != 1:
        raise QualificationError("Native proof must list one x86-64 candidate RPM")
    asset = matches[0]
    if (
        type(asset.get("size")) is not int
        or asset["size"] <= 0
        or not isinstance(asset.get("sha256"), str)
        or not SHA256.fullmatch(asset["sha256"])
    ):
        raise QualificationError("Native proof has an invalid RPM digest or size")
    return asset


def candidate_input(
    root: Path, proof: dict, version: str, commit: str, run_id: str, attempt: str
) -> tuple[Path, str]:
    asset = rpm_proof_asset(proof, version, commit, run_id, attempt)
    path = root / asset["path"]
    digest = asset["sha256"]
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_size != asset["size"]
        or sha256(path) != digest
    ):
        raise QualificationError("Candidate RPM bytes differ from the native proof")
    return path, digest


def verify_receipt(receipt: dict, version: str, candidate_sha256: str) -> None:
    if (
        receipt.get("schema") != "remote-ops-workspace/rpm-recovery/v1"
        or receipt.get("backup_created_with") != "verified-candidate-launcher-before-upgrade"
        or not SHA256.fullmatch(receipt["backup_sha256"])
        or any(receipt.get(key) is not True for key in CHECKS)
    ):
        raise QualificationError("Incomplete RPM recovery receipt")
    for role, expected_version, digest in (
        ("previous", PREVIOUS_VERSION, PREVIOUS_SHA256),
        ("candidate", version, candidate_sha256),
    ):
        package = receipt[role]
        if (package.get("version"), package.get("package_sha256"), package.get("architecture")) != (
            expected_version,
            digest,
            ARCH,
        ) or not SHA256.fullmatch(package["launcher_sha256"]):
            raise QualificationError("RPM recovery receipt refers to a different package")


def build_dependency_blocker(directory: Path, name: str, version: str) -> Path:
    if name not in (managed.UPGRADE_BLOCKER, managed.ROLLBACK_BLOCKER) or not VERSION.fullmatch(version):
        raise QualificationError("The dependency fixture requires a known name and exact version")
    directory.mkdir()
    spec = directory / "blocker.spec"
    spec.write_text(
        f"Name: {name}\n"
        "Version: 1\nRelease: 1\nSummary: RPM qualification dependency fixture\n"
        "License: 0BSD\nBuildArch: noarch\n"
        f"Requires: {PACKAGE} = {version}\n"
        "\n%description\nHolds the selected version in a disposable qualification container.\n"
        "\n%files\n",
        encoding="ascii",
    )
    subprocess.run(
        ["rpmbuild", "--define", f"_topdir {directory}", "-bb", str(spec)],
        check=True, stdout=sys.stderr, timeout=60,
    )
    return directory / "RPMS" / "noarch" / f"{name}-1-1.noarch.rpm"


def managed_drill(root: Path, temporary: Path, commit: str, previous: Path, candidate: Path,
                  digest: str, wheelhouse: Path | None, *, version: str) -> dict:
    requirements = temporary / "crypto.txt"
    requirements.write_bytes(managed.locked_crypto_requirements(root))
    if wheelhouse is None:
        wheelhouse = temporary / "wheels"
        wheelhouse.mkdir()
        subprocess.run(
            [sys.executable, "-I", "-m", "pip", "--isolated", "download", "--disable-pip-version-check",
             "--index-url", "https://pypi.org/simple", "--only-binary=:all:", "--require-hashes", "--no-deps",
             "--dest", str(wheelhouse), "--requirement", str(requirements)],
            check=True, stdout=sys.stderr, timeout=180,
        )
    else:
        wheelhouse = wheelhouse.resolve(strict=True)
        if not wheelhouse.is_dir():
            raise QualificationError("The offline wheelhouse must be a directory")
    source = temporary / "source.tar"
    subprocess.run(["git", "archive", "--format=tar", f"--output={source}", commit], cwd=root, check=True, timeout=60)
    blocker = build_dependency_blocker(temporary / "dependency-blocker", managed.UPGRADE_BLOCKER, PREVIOUS_VERSION)
    rollback_blocker = build_dependency_blocker(
        temporary / "rollback-blocker", managed.ROLLBACK_BLOCKER, version,
    )
    result = subprocess.run(
        ["docker", "run", "--rm", "--platform", "linux/amd64", "--network", "none",
         "--security-opt", "no-new-privileges",
         "--mount", f"type=bind,source={source},target=/input/source.tar,readonly",
         "--mount", f"type=bind,source={requirements},target=/input/crypto.txt,readonly",
         "--mount", f"type=bind,source={wheelhouse},target=/wheels,readonly",
         "--mount", f"type=bind,source={previous},target=/previous/{previous.name},readonly",
         "--mount", f"type=bind,source={candidate},target=/candidate/{candidate.name},readonly",
         "--mount", f"type=bind,source={blocker},target=/input/dependency-blocker.rpm,readonly",
         "--mount", f"type=bind,source={rollback_blocker},target=/input/rollback-blocker.rpm,readonly",
         "--entrypoint", "/bin/sh", IMAGE, "-ec", MANAGED_ENTRYPOINT, "row-managed-rpm",
         "--previous-rpm", f"/previous/{previous.name}", "--previous-sha256", PREVIOUS_SHA256,
         "--candidate-rpm", f"/candidate/{candidate.name}", "--candidate-sha256", digest,
         "--dependency-blocker", "/input/dependency-blocker.rpm", "--rollback-blocker", "/input/rollback-blocker.rpm"],
        check=True, stdout=subprocess.PIPE, timeout=600,
    )
    return json.loads(result.stdout)


def qualify(root: Path, tag: str, commit: str, run_id: str, attempt: str, *, wheelhouse: Path | None = None) -> dict:
    version = tag.removeprefix("v")
    if (
        tag != f"v{version}"
        or not VERSION.fullmatch(version)
        or not re.fullmatch(r"[0-9a-f]{40}", commit)
        or not all(re.fullmatch(r"[1-9][0-9]*", value) for value in (run_id, attempt))
    ):
        raise QualificationError(
            "Exact candidate tag, source SHA, run ID, and attempt are required"
        )
    if (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=30
        ).strip()
        != commit
        or subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--"], cwd=root, timeout=60, check=False
        ).returncode
    ):
        raise QualificationError("Checkout differs from the requested source commit")
    proof_bytes = (root / PROOF).read_bytes()
    proof = json.loads(proof_bytes)
    candidate, digest = candidate_input(root, proof, version, commit, run_id, attempt)
    filename = rpm_name(PREVIOUS_VERSION)
    with TemporaryDirectory(prefix="row-rpm-candidate-") as directory:
        temporary = Path(directory)
        previous = temporary / filename
        subprocess.run(
            [
                "curl",
                "--disable",
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--proto",
                "=https",
                "--proto-redir",
                "=https",
                "--max-time",
                "120",
                "--max-filesize",
                str(PREVIOUS_SIZE),
                "--output",
                str(previous),
                PREVIOUS_URL,
            ],
            check=True,
            timeout=135,
        )
        if previous.stat().st_size != PREVIOUS_SIZE or sha256(previous) != PREVIOUS_SHA256:
            raise QualificationError("Previous release RPM differs from the pinned input")
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--platform",
                "linux/amd64",
                "--network",
                "none",
                "--security-opt",
                "no-new-privileges",
                "--mount",
                f"type=bind,source={root / DRILL},target=/drill.py,readonly",
                "--mount",
                f"type=bind,source={previous},target=/previous/{filename},readonly",
                "--mount",
                f"type=bind,source={candidate},target=/candidate/{candidate.name},readonly",
                IMAGE,
                "python3",
                "-I",
                "/drill.py",
                "--previous-rpm",
                f"/previous/{filename}",
                "--previous-sha256",
                PREVIOUS_SHA256,
                "--candidate-rpm",
                f"/candidate/{candidate.name}",
                "--candidate-sha256",
                digest,
            ],
            check=True,
            stdout=subprocess.PIPE,
            timeout=420,
        )
        receipt = json.loads(result.stdout)
        verify_receipt(receipt, version, digest)
        managed_receipt = managed_drill(root, temporary, commit, previous, candidate, digest, wheelhouse, version=version)
        managed.verify_receipt(
            managed_receipt, receipt, controller_sha256=sha256(root / managed.CONTROLLER),
            requirements_sha256=hashlib.sha256(managed.locked_crypto_requirements(root)).hexdigest(),
            require_current=True,
        )
    if (root / PROOF).read_bytes() != proof_bytes or sha256(candidate) != digest:
        raise QualificationError("Native proof or candidate RPM changed during qualification")
    return {
        "schema": SCHEMA,
        "target": TARGET,
        "source_commit": commit,
        "run_id": int(run_id),
        "run_attempt": int(attempt),
        "workflow_ref": proof.get("workflow_ref"),
        "candidate_native_proof_sha256": hashlib.sha256(proof_bytes).hexdigest(),
        "previous_release_asset_id": PREVIOUS_ASSET,
        "previous_release_url": PREVIOUS_URL,
        "container_image": IMAGE,
        "receipt": receipt,
        "managed_update": managed_receipt,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-tag", required=True)
    parser.add_argument("--candidate-source-sha", required=True)
    parser.add_argument("--wheelhouse", type=Path, help="reuse cached wheels verified against the source lock")
    args = parser.parse_args()
    try:
        report = qualify(
            Path.cwd(),
            args.candidate_tag,
            args.candidate_source_sha,
            os.environ["GITHUB_RUN_ID"],
            os.environ["GITHUB_RUN_ATTEMPT"],
            wheelhouse=args.wheelhouse,
        )
    except QualificationError as exc:
        print(exc, file=sys.stderr)
        return 1
    except (KeyError, OSError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"RPM candidate qualification failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
