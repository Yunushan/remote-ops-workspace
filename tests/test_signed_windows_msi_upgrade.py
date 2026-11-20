from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from scripts import check_signed_windows_msi_upgrade as review
from scripts.inspect_windows_msi import (
    EXPECTED_PREDECESSOR,
    EXPECTED_PREDECESSOR_CONDITION,
    ROLLBACK_ACTIONS,
    STOCK_CLI_COMPONENT,
    STOCK_UPGRADE,
)

WORKFLOW_COMMIT = "b" * 40
PREVIOUS = review.PackageReference("v1.0.27", "c" * 40, "d" * 64)
CANDIDATE = review.PackageReference("v1.0.28", "e" * 40, "f" * 64)
RUN = review.RunInvocation(review.REPOSITORY, 12340, 2)
PROVENANCE = sys.modules[review.verify_workflow_attestation.__module__]


def package(reference, launcher, code) -> dict:
    return {
        "release_tag": reference.tag, "release_sha": reference.source_commit, "sha256": reference.msi_sha256,
        "name_on_release": f"remote-ops-workspace-{reference.tag}-windows-x64.msi",
        "source": {"kind": "immutable-release"}, "size_bytes": 58000000, "launcher_payload_sha256": launcher,
        "name": "Remote Ops Workspace", "manufacturer": "Remote Ops Workspace Contributors",
        "upgrade_code": STOCK_UPGRADE, "row_component_code": STOCK_CLI_COMPONENT,
        "architecture": "x64", "version": reference.tag[1:], "all_users": "1", "per_user": "",
        "package_code": "{513386E8-345B-4813-8BA3-115A443D" + code + "}",
        "product_code": "{740B55D4-4EA0-4C75-A8B4-B7C2FD70" + code + "}",
    }


@pytest.fixture
def completed_receipt() -> dict:
    old = package(PREVIOUS, "1" * 64, "005A")
    new = package(CANDIDATE, "2" * 64, "006A")
    old["gui_launcher_payload_sha256"] = "a" * 64
    new["gui_launcher_payload_sha256"] = "b" * 64
    new.update({
        "upgrade_sequence": dict(zip(ROLLBACK_ACTIONS, (1400, 1500, 1501, 1600, 4000, 6600), strict=True)),
        "disable_rollback": "",
        "major_upgrade": {"launch_conditions": [EXPECTED_PREDECESSOR_CONDITION],
                          "secure_properties": [EXPECTED_PREDECESSOR], "authored_expected_predecessor": False},
    })
    staging = {"feed": "disposable-loopback-https", "initial_command": "update", "initial_stages_absent": True,
               "https_requests": ["/previous/manifest.json", f"/previous/{old['name_on_release']}",
                                  "/candidate/manifest.json", f"/candidate/{new['name_on_release']}"],
               "feed_closed_before_retry": True}
    observations = {"target": "windows-x64", "authenticode_and_timestamp_checked": True}
    for role, item, token in (("previous", old, "a"), ("candidate", new, "b")):
        staging[role] = {"phase": "authenticated-staged", "version": item["version"],
                         "selected_target": "windows-x64", "selected_files": [item["name_on_release"]],
                         "artifact_total_bytes": item["size_bytes"], "whole_declared_asset_set_verified": True,
                         "authenticity_checked": True, "windows_dacl_metadata_verified": True,
                         "install_permitted": False, "manifest_sha256": token * 64,
                         "trust_policy_sha256": token * 64, "transaction_id": token * 64}
        observations[f"{role}_stage"] = dict(staging[role])
        observations[f"{role}_msi"] = {**item, "asset": item["name_on_release"]}
    return {
        "schema": review.SCHEMA, "status": "passed", "phase": "complete", "target": "windows-x64",
        "source_commit": WORKFLOW_COMMIT, "run_id": str(RUN.run_id), "run_attempt": str(RUN.attempt),
        "input_read_only_sharing_held": True, "previous": old, "candidate": new,
        "rollback_disabled_upgrade": {"exit_code": 1603, "launch_condition_refused_upgrade": True,
                                      "previous_preserved": True, "candidate_absent": True, "workspace_preserved": True},
        "cancellation": {"exit_code": 1602, "removal_started": True, "previous_launcher_absent_at_cancel": True,
                         "installer_error_before_cancel": False},
        "candidate_absent_after_cancel": True, "original_workspace_preserved_after_cancel": True,
        "previous_installed": review.registration(old), "previous_restored": review.registration(old),
        "previous_reinstalled": review.registration(old), "candidate_installed": review.registration(new),
        "previous_absent_after_retry": True, "stock_products_absent_after_uninstall": True,
        "managed_staging": staging,
        "managed_preflight": {**observations, "phase": "msi-preflight-passed", "previous_launcher_sha256": "1" * 64},
        "managed_apply": {**observations, "phase": "msi-applied", "installer_exit_code": 0,
                          "previous_launcher_sha256": "1" * 64, "installed_launcher_sha256": "2" * 64},
        "managed_retry": {**observations, "phase": "msi-already-applied", "installed_launcher_sha256": "2" * 64},
        "workspace_recovery": {"encrypted_backup_sha256": "3" * 64, "pre_upgrade_inventory": {"sha256": "4" * 64},
                               "upgraded_inventory": {"sha256": "5" * 64}, "restored_matches_pre_upgrade": True,
                               "upgraded_workspace_unchanged": True, "predecessor_decrypted_restored_vault": True},
    }


def coordinates(path: Path) -> list[str]:
    return ["--receipt", str(path), "--workflow-sha", WORKFLOW_COMMIT,
            "--previous", PREVIOUS.tag, PREVIOUS.source_commit, PREVIOUS.msi_sha256,
            "--candidate", CANDIDATE.tag, CANDIDATE.source_commit, CANDIDATE.msi_sha256]


@pytest.mark.parametrize(("keys", "value", "refusal"), [
    (("status",), "failed", "expected a completed"),
    (("source_commit",), "9" * 40, "expected a completed"),
    (("candidate", "sha256"), "0" * 64, "candidate MSI does not match"),
    (("candidate", "gui_launcher_payload_sha256"), None, "missing the Windows x64 GUI launcher payload binding"),
    (("previous", "release_sha"), "0" * 40, "previous MSI does not match"),
    (("managed_staging", "initial_command"), "apply", "one-command download"),
    (("managed_staging", "initial_stages_absent"), False, "one-command download"),
    (("managed_staging", "https_requests"), ["/previous/manifest.json"], "one-command download"),
    (("managed_staging", "feed_closed_before_retry"), False, "one-command download"),
    (("managed_staging", "candidate", "windows_dacl_metadata_verified"), False, "authenticated private staging"),
    (("managed_preflight", "candidate_msi", "sha256"), "0" * 64, "used different candidate inputs"),
    (("rollback_disabled_upgrade", "workspace_preserved"), False, "rollback-disabled refusal"),
    (("cancellation", "previous_launcher_absent_at_cancel"), False, "cancellation after predecessor removal"),
    (("managed_retry", "installer_exit_code"), 0, "no-op retry was not demonstrated"),
    (("previous_reinstalled", "package_code"), "different package", "registration differs"),
    (("previous_reinstalled", "gui_launcher_sha256"), "0" * 64, "registration differs"),
    (("managed_retry", "candidate_msi", "gui_launcher_payload_sha256"), "0" * 64, "used different candidate inputs"),
    (("workspace_recovery", "predecessor_decrypted_restored_vault"), False, "workspace recovery"),
])
def test_refuses_incomplete_or_mismatched_claims_before_network(
    completed_receipt, keys, value, refusal, tmp_path, monkeypatch, capsys,
):
    field = completed_receipt
    for key in keys[:-1]:
        field = field[key]
    field[keys[-1]] = value
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(completed_receipt), encoding="utf-8")
    monkeypatch.setattr(PROVENANCE, "run_gh_json", lambda *a, **k: pytest.fail("invalid receipt reached GitHub"))
    assert review.main(coordinates(path)) == 1
    assert refusal in capsys.readouterr().err


def test_old_receipt_cannot_claim_automatic_download(completed_receipt, tmp_path, monkeypatch, capsys):
    completed_receipt["schema"] = review.MANUALLY_STAGED_SCHEMA
    for key in ("initial_command", "initial_stages_absent", "https_requests", "feed_closed_before_retry"):
        del completed_receipt["managed_staging"][key]
    assert review.check_receipt(completed_receipt, WORKFLOW_COMMIT, PREVIOUS, CANDIDATE) == RUN
    path = tmp_path / "legacy-receipt.json"
    path.write_text(json.dumps(completed_receipt), encoding="utf-8")
    monkeypatch.setattr(PROVENANCE, "run_gh_json", lambda *a, **k: pytest.fail("legacy receipt reached GitHub"))
    assert review.main([*coordinates(path), "--require-automatic-update"]) == 1
    assert "requires an automatic update receipt" in capsys.readouterr().err


def test_legacy_automatic_receipt_keeps_its_original_launcher_contract(completed_receipt):
    completed_receipt["schema"] = review.AUTOMATIC_UPDATE_SCHEMA
    for role in ("previous", "candidate"):
        del completed_receipt[role]["gui_launcher_payload_sha256"]
        for phase in ("managed_preflight", "managed_apply", "managed_retry"):
            completed_receipt[phase][f"{role}_msi"].pop("gui_launcher_payload_sha256", None)
    for field in ("previous_installed", "previous_restored", "previous_reinstalled", "candidate_installed"):
        del completed_receipt[field]["gui_launcher_sha256"]
    assert review.check_receipt(completed_receipt, WORKFLOW_COMMIT, PREVIOUS, CANDIDATE,
                                require_automatic_update=True) == RUN


@pytest.mark.parametrize("defect", [
    "valid", "wrong-ref", "self-hosted", "wrong-signer-source", "wrong-attempt",
    "unwitnessed", "wrong-receipt-bytes", "failed-attempt", "different-workflow", "fork",
])
def test_requires_exact_receipt_attestation_and_successful_exact_attempt(
    completed_receipt, defect, tmp_path, monkeypatch, capsys,
):
    receipt = tmp_path / "receipt.json"
    raw = json.dumps(completed_receipt).encode()
    receipt.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    expected_flags = [
        "--repo", review.REPOSITORY, "--signer-workflow", f"{review.REPOSITORY}/{review.WORKFLOW}",
        "--source-digest", WORKFLOW_COMMIT, "--source-ref", "refs/heads/main", "--predicate-type",
        PROVENANCE.PREDICATE_TYPE, "--deny-self-hosted-runners", "--limit", "100", "--format", "json",
    ]
    certificate = {"sourceRepositoryURI": f"https://github.com/{review.REPOSITORY}",
                   "sourceRepositoryDigest": WORKFLOW_COMMIT, "sourceRepositoryRef": "refs/heads/main",
                   "runnerEnvironment": "github-hosted", "buildTrigger": "workflow_dispatch", "runInvocationURI": RUN.url}
    for token, name, value in (
        ("wrong-ref", "sourceRepositoryRef", "refs/heads/other"),
        ("self-hosted", "runnerEnvironment", "self-hosted"),
        ("wrong-signer-source", "sourceRepositoryDigest", "7" * 40),
        ("wrong-attempt", "runInvocationURI", RUN.url.rsplit("/", 1)[0] + "/1"),
    ):
        if defect == token:
            certificate[name] = value
    attempts = []

    def attestation(args, label, timeout):
        path = Path(args[2])
        assert args[:2] == ["attestation", "verify"] and args[3:] == expected_flags
        assert path.name == review.RECEIPT.name and path != receipt and timeout == 120
        assert path.read_bytes() == raw
        # Changes to the caller's path during the network check cannot
        # authenticate a different set of bytes from the one reviewed.
        receipt.write_bytes(b"new bytes")
        return [{"verificationResult": {
            "signature": {"certificate": certificate},
            "verifiedTimestamps": [] if defect == "unwitnessed" else [{"type": "transparency-log"}],
            "statement": {"predicateType": PROVENANCE.PREDICATE_TYPE, "subject": [{
                "name": review.RECEIPT.name,
                "digest": {"sha256": "9" * 64 if defect == "wrong-receipt-bytes" else digest},
            }]},
        }}]

    def run_attempt(args, label, timeout):
        assert args == ["api", "--method", "GET", f"repos/{review.REPOSITORY}/actions/runs/12340/attempts/2"]
        assert timeout == 60
        attempts.append(args)
        return {
            "id": RUN.run_id, "run_attempt": RUN.attempt, "head_sha": WORKFLOW_COMMIT,
            "head_branch": "main", "event": "workflow_dispatch", "status": "completed",
            "conclusion": "failure" if defect == "failed-attempt" else "success",
            "path": ".github/workflows/release.yml" if defect == "different-workflow" else f"{review.WORKFLOW}@main",
            "repository": {"full_name": review.REPOSITORY},
            "head_repository": {"full_name": "example/fork" if defect == "fork" else review.REPOSITORY},
        }

    monkeypatch.setattr(PROVENANCE, "run_gh_json", attestation)
    monkeypatch.setattr(review, "run_gh_json", run_attempt)
    status = review.main(coordinates(receipt))
    output = capsys.readouterr()
    if defect == "valid":
        assert status == 0 and RUN.url in output.out and digest in output.out
    else:
        assert status == 1 and not output.out
    passed_attestation = defect in {"valid", "failed-attempt", "different-workflow", "fork"}
    assert len(attempts) == int(passed_attestation)
    if defect != "valid":
        reason = "not a successful canonical" if passed_attestation else "lacks a witnessed GitHub-hosted attestation"
        assert reason in output.err


def test_workflow_isolates_attestation_permissions_and_checks_exact_attempt() -> None:
    source = (review.ROOT / review.WORKFLOW).read_text(encoding="utf-8")
    windows, issuer = source.split("  attest-signed-windows-upgrade:\n")
    assert "id-token:" not in windows and "attestations: write" not in windows and "actions/attest@" not in windows
    assert "steps.upload-receipt.outputs.artifact-id" in windows and "steps.receipt-hash.outputs.sha256" in windows
    assert "needs.signed-windows-upgrade.result == 'success'" in issuer
    assert "artifact-ids: ${{ needs.signed-windows-upgrade.outputs.receipt-artifact-id }}" in issuer
    assert issuer.index("hashlib.sha256(raw).hexdigest()") < issuer.index("actions/attest@")
    assert f'"schema": "{review.SCHEMA}"' in issuer
    assert '"run_attempt": os.environ["GITHUB_RUN_ATTEMPT"]' in issuer
    assert '"source_commit": os.environ["GITHUB_SHA"]' in issuer
