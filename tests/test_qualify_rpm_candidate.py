from copy import deepcopy

import pytest

from scripts import qualify_rpm_candidate as candidate
from scripts.qualify_rpm_recovery import sha256

SOURCE = "a" * 40
VERSION = "1.0.28"
RUN_ID = "192"
ATTEMPT = "2"


@pytest.fixture
def inputs(tmp_path):
    rpm = tmp_path / f"native-dist/linux/{candidate.rpm_name(VERSION)}"
    rpm.parent.mkdir(parents=True)
    rpm.write_bytes(b"candidate-rpm-fixture")
    proof = {
        "target": "linux-x86_64",
        "source": {"head": SOURCE},
        "run_id": RUN_ID,
        "run_attempt": ATTEMPT,
        "source_unchanged": True,
        "native_build_outcome": "success",
        "native_smoke_outcome": "success",
        "native_executable_byte_binding": {"status": "bound"},
        "assets": [
            {
                "path": rpm.relative_to(tmp_path).as_posix(),
                "size": rpm.stat().st_size,
                "sha256": sha256(rpm),
            }
        ],
    }
    return rpm, proof


def test_candidate_requires_exact_native_smoke_package(tmp_path, inputs):
    rpm, proof = inputs
    digest = sha256(rpm)
    assert candidate.candidate_input(tmp_path, proof, VERSION, SOURCE, RUN_ID, ATTEMPT) == (
        rpm,
        digest,
    )
    rpm.write_bytes(b"different-rpm-fixture")
    with pytest.raises(candidate.QualificationError, match="RPM bytes differ"):
        candidate.candidate_input(tmp_path, proof, VERSION, SOURCE, RUN_ID, ATTEMPT)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("source", {"head": "b" * 40}),
        ("run_id", "191"),
        ("run_attempt", "1"),
        ("native_smoke_outcome", "failure"),
        ("native_executable_byte_binding", {"status": "not-bound"}),
    ],
)
def test_run_refuses_incompatible_native_proof(tmp_path, inputs, field, replacement):
    _, proof = inputs
    proof[field] = replacement
    with pytest.raises(candidate.QualificationError, match="candidate source, run, and smoke"):
        candidate.candidate_input(tmp_path, proof, VERSION, SOURCE, RUN_ID, ATTEMPT)


def test_result_requires_both_expected_package_hashes_and_complete_recovery():
    candidate_digest = "d" * 64
    record = {
        "schema": "remote-ops-workspace/rpm-recovery/v1",
        "backup_created_with": "verified-candidate-launcher-before-upgrade",
        "backup_sha256": "a" * 64,
        "previous": {
            "version": candidate.PREVIOUS_VERSION,
            "package_sha256": candidate.PREVIOUS_SHA256,
            "architecture": "x86_64",
            "launcher_sha256": "b" * 64,
        },
        "candidate": {
            "version": VERSION,
            "package_sha256": candidate_digest,
            "architecture": "x86_64",
            "launcher_sha256": "c" * 64,
        },
        **dict.fromkeys(candidate.CHECKS, True),
    }
    candidate.verify_receipt(record, VERSION, candidate_digest)
    wrong = deepcopy(record)
    wrong["previous"]["package_sha256"] = candidate_digest
    with pytest.raises(candidate.QualificationError, match="different package"):
        candidate.verify_receipt(wrong, VERSION, candidate_digest)
    record["restored_profiles_and_vault_read_by_previous_launcher"] = False
    with pytest.raises(candidate.QualificationError, match="Incomplete"):
        candidate.verify_receipt(record, VERSION, candidate_digest)
