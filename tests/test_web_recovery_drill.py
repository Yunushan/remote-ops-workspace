from __future__ import annotations

import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

REPOSITORY = "Yunushan/remote-ops-workspace"
SOURCE_SHA = "a" * 40
WORKFLOW_URL = f"https://github.com/{REPOSITORY}/actions/runs/12345"
RUN_ATTEMPT = 2
DIGEST = "b" * 64


def test_recovery_evidence_contract_accepts_complete_proof() -> None:
    drill = _load_drill()

    assert _validate(drill, _valid_evidence(drill)) == []


@pytest.mark.parametrize(
    ("path", "value", "expected_error"),
    [
        (("status",), "failed", "evidence status must be 'passed'"),
        (("backup", "payload_uploaded"), True, "backup.payload_uploaded must be False"),
        (("recovery", "original_volume_removed"), False, "original_volume_removed must be true"),
        (("recovery", "post_backup_sentinel_absent"), False, "post_backup_sentinel_absent must be true"),
        (("health", "after_restore", "status_code"), 503, "after_restore.status_code must be 200"),
        (("hardening", "after_restore", "verified"), False, "after_restore.verified must be true"),
        (("cleanup", "completed"), False, "cleanup.completed must be true"),
    ],
)
def test_recovery_evidence_contract_rejects_missing_proof(
    path: tuple[str, ...], value: object, expected_error: str
) -> None:
    drill = _load_drill()
    evidence = _valid_evidence(drill)
    target = evidence
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    errors = _validate(drill, evidence)

    assert any(expected_error in error for error in errors)


def test_recovery_evidence_contract_requires_each_hardening_check() -> None:
    drill = _load_drill()
    evidence = _valid_evidence(drill)
    evidence["hardening"]["after_restore"]["no_new_privileges"] = False

    errors = _validate(drill, evidence)

    assert any("after_restore.no_new_privileges must be true" in error for error in errors)


def test_recovery_evidence_contract_binds_repository_source_and_run() -> None:
    drill = _load_drill()
    evidence = _valid_evidence(drill)
    evidence["repository"] = "attacker/other"
    evidence["source_sha"] = "c" * 40
    evidence["workflow_run_url"] = "https://github.com/attacker/other/actions/runs/999"
    evidence["workflow_run_attempt"] = 9

    errors = _validate(drill, evidence)

    assert any("evidence repository" in error for error in errors)
    assert any("evidence source_sha" in error for error in errors)
    assert any("evidence workflow_run_url" in error for error in errors)
    assert any("evidence workflow_run_attempt" in error for error in errors)


def test_recovery_evidence_contract_recomputes_marker_digest() -> None:
    drill = _load_drill()
    evidence = _valid_evidence(drill)
    evidence["marker"]["workflow_run_attempt"] = 7
    evidence["revision_sha256"] = drill.sha256_bytes(
        drill.canonical_json_bytes(evidence["marker"])
    )

    errors = _validate(drill, evidence)

    assert any("evidence marker must bind" in error for error in errors)
    assert any("revision_sha256 must match the canonical marker" in error for error in errors)


def test_backup_archive_validation_returns_bound_revision_marker(tmp_path: Path) -> None:
    drill = _load_drill()
    marker = b'{"revision":"proof"}\n'
    archive = tmp_path / "backup.tar.gz"
    _write_archive(archive, [(drill.MARKER_PATH, marker, None)])

    assert drill.archive_marker_bytes(archive) == marker


def test_backup_archive_validation_rejects_duplicate_marker(tmp_path: Path) -> None:
    drill = _load_drill()
    archive = tmp_path / "duplicate.tar.gz"
    _write_archive(
        archive,
        [(drill.MARKER_PATH, b"first", None), (drill.MARKER_PATH, b"second", None)],
    )

    with pytest.raises(drill.DrillError, match="duplicate member path"):
        drill.archive_marker_bytes(archive)


@pytest.mark.parametrize(
    ("name", "linkname"),
    [
        ("../escape", None),
        ("/absolute", None),
        ("recovery-drill/link", "../../escape"),
    ],
)
def test_backup_archive_validation_rejects_unsafe_members(
    tmp_path: Path, name: str, linkname: str | None
) -> None:
    drill = _load_drill()
    archive = tmp_path / "unsafe.tar.gz"
    members = [(drill.MARKER_PATH, b"marker", None), (name, b"bad", linkname)]
    _write_archive(archive, members)

    with pytest.raises(drill.DrillError, match="unsafe member path|unsupported member type"):
        drill.archive_marker_bytes(archive)


def test_recovery_evidence_checker_reads_and_validates_report(tmp_path: Path) -> None:
    drill = _load_drill()
    checker = _load_checker()
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(_valid_evidence(drill)), encoding="utf-8")

    assert checker.check_evidence(
        path,
        repository=REPOSITORY,
        source_sha=SOURCE_SHA,
        workflow_run_url=WORKFLOW_URL,
        run_attempt=RUN_ATTEMPT,
    ) == []


def test_recovery_evidence_checker_rejects_non_object_json(tmp_path: Path) -> None:
    checker = _load_checker()
    path = tmp_path / "evidence.json"
    path.write_text("[]", encoding="utf-8")

    errors = checker.check_evidence(
        path,
        repository=REPOSITORY,
        source_sha=SOURCE_SHA,
        workflow_run_url=WORKFLOW_URL,
        run_attempt=RUN_ATTEMPT,
    )

    assert errors == ["evidence root must be a JSON object"]


def _valid_evidence(drill):
    health = {"status_code": 200, "body_sha256": DIGEST, "body_size_bytes": 2}
    marker = {
        "schema": drill.MARKER_SCHEMA,
        "repository": REPOSITORY,
        "revision": SOURCE_SHA,
        "source_sha": SOURCE_SHA,
        "workflow_run_url": WORKFLOW_URL,
        "workflow_run_attempt": RUN_ATTEMPT,
        "created_at_utc": "2026-07-30T10:00:00Z",
    }
    return {
        "schema": drill.SCHEMA,
        "status": "passed",
        "repository": REPOSITORY,
        "source_sha": SOURCE_SHA,
        "workflow_run_url": WORKFLOW_URL,
        "workflow_run_attempt": RUN_ATTEMPT,
        "started_at_utc": "2026-07-30T10:00:00Z",
        "completed_at_utc": "2026-07-30T10:01:00Z",
        "project_name": "row-web-recovery",
        "compose_file": "docker/compose.yaml",
        "compose_sha256": DIGEST,
        "image_id": f"sha256:{DIGEST}",
        "volume_name": "row-web-recovery_remote-ops-data",
        "revision": SOURCE_SHA,
        "revision_sha256": drill.sha256_bytes(drill.canonical_json_bytes(marker)),
        "marker": marker,
        "backup": {
            "sha256": DIGEST,
            "size_bytes": 100,
            "archive_validated": True,
            "marker_bound": True,
            "payload_uploaded": False,
        },
        "recovery": {
            "original_volume_removed": True,
            "fresh_volume_created": True,
            "restored_revision_verified": True,
            "post_backup_sentinel_absent": True,
        },
        "health": {"before_backup": dict(health), "after_restore": dict(health)},
        "hardening": {
            "before_backup": _hardening(),
            "after_restore": _hardening(),
        },
        "cleanup": {"completed": True},
        "failure": None,
    }


def _validate(drill, evidence):
    return drill.validate_evidence(
        evidence,
        expected_repository=REPOSITORY,
        expected_source_sha=SOURCE_SHA,
        expected_workflow_run_url=WORKFLOW_URL,
        expected_run_attempt=RUN_ATTEMPT,
    )


def _hardening() -> dict[str, bool]:
    return {
        "verified": True,
        "non_root_user": True,
        "read_only_rootfs": True,
        "pids_limit": True,
        "memory_limit_bytes": True,
        "all_capabilities_dropped": True,
        "no_new_privileges": True,
        "bounded_local_logs": True,
        "restart_policy": True,
        "named_data_volume": True,
    }


def _write_archive(path: Path, members: list[tuple[str, bytes, str | None]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, content, linkname in members:
            info = tarfile.TarInfo(name)
            if linkname is not None:
                info.type = tarfile.SYMTYPE
                info.linkname = linkname
                info.size = 0
                archive.addfile(info)
            else:
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))


def _load_drill():
    return _load_module("run_web_recovery_drill", Path("scripts/run_web_recovery_drill.py"))


def _load_checker():
    _load_drill()
    return _load_module("check_web_recovery_evidence", Path("scripts/check_web_recovery_evidence.py"))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
