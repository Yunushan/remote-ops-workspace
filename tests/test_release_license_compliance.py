from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

UTC = timezone.utc


def _load_checker():
    path = Path("scripts/check_release_license_compliance.py")
    spec = importlib.util.spec_from_file_location("check_release_license_compliance", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load release license compliance checker")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_release_license_compliance"] = module
    spec.loader.exec_module(module)
    return module


def _write_record(root: Path, relative: str, content: bytes, **extra: object) -> dict:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "file": relative,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        **extra,
    }


def _license_record(root: Path, name: str) -> dict:
    return _write_record(
        root,
        f"licenses/{name}.txt",
        f"license for {name}\n".encode(),
        path=f"docs/third-party/{name}.txt",
    )


def _component(root: Path, name: str, version: str, origin: str) -> dict:
    return {
        "name": name,
        "version": version,
        "origin": origin,
        "scope": "bundled",
        "license_expression": "LicenseRef-reviewed",
        "license_files": [_license_record(root, name.lower().replace("-", "_"))],
    }


def _positive_fixture(tmp_path: Path, checker) -> list[str]:
    assets = tmp_path / "assets"
    evidence_root = tmp_path / "evidence"
    assets.mkdir()
    evidence_root.mkdir()
    tag = "v1.2.3"
    sha = "a" * 40
    repository = "example/project"
    manifest_name = f"remote-ops-workspace-{tag}-windows-x86-native-manifest.json"
    artifact_name = f"remote-ops-workspace-{tag}-windows-x86-native.zip"
    artifact = assets / artifact_name
    artifact.write_bytes(b"native bytes")
    manifest = [
        {
            "file": f"native-dist/windows/{artifact_name}",
            "size_bytes": artifact.stat().st_size,
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }
    ]
    manifest_path = assets / manifest_name
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    toolchain = {
        "python": {"version": "3.14.7"},
        "python_packages": [{"name": "pyinstaller", "version": "6.22.2"}],
    }
    toolchain_path = tmp_path / "toolchain.json"
    toolchain_path.write_text(json.dumps(toolchain), encoding="utf-8")
    matrix = {
        "default_github_release": {
            "native_jobs": [
                {
                    "platform_target_ids": ["windows-x86"],
                    "arches": ["x86"],
                    "asset_patterns": [
                        "remote-ops-workspace-v1.2.3-windows-<x86>-native-manifest.json"
                    ],
                },
            ]
        }
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    lock_content = f"pyinstaller==6.22.2 --hash=sha256:{'1' * 64}\n".encode()
    tracked_lock = tmp_path / "locks" / "windows-x86.txt"
    tracked_lock.parent.mkdir()
    tracked_lock.write_bytes(lock_content)
    verifier_lock_content = f"cryptography==50.0.1 --hash=sha256:{'2' * 64}\n".encode()
    verifier_lock = tmp_path / "locks" / "verifier.txt"
    verifier_lock.write_bytes(verifier_lock_content)
    workflow_path = tmp_path / "release.yml"
    workflow_path.write_text(
        """jobs:
  windows-native:
    strategy:
      matrix:
        include:
          - arch: x86
            lock: locks/windows-x86.txt
    steps:
      - run: python -m pip install --require-hashes --requirement locks/windows-x86.txt
      - run: python -m pip install --no-deps ".[package]"
  publish:
    steps:
      - run: python -m pip install --require-hashes --requirement locks/verifier.txt
      - run: python scripts/check_release_license_compliance.py --assets-dir release-assets --repository example/project --tag v1.2.3 --sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa --policy configs/policy.json --policy-root . --evidence approval.json --signature approval.sig.json --evidence-root evidence --candidate-inventory evidence/release-candidate-inventory.json --protected-platform-registry evidence/platform/platform_verified_evidence.json --tag-governance-attestation evidence/tag-governance-attestation.json --tag-governance-signature evidence/tag-governance-attestation.sig.json
      - uses: softprops/action-gh-release@pinned
""",
        encoding="utf-8",
    )
    policy = {
        "schema_version": 1,
        "policy_status": "approved",
        "closed_world_inventory_approved": True,
        "trusted_ed25519_keys": [
            {
                "key_id": "legal-review-test",
                "public_key": base64.b64encode(public_key).decode(),
            }
        ],
        "tag_governance_attestation": {
            "state": "enforced",
            "max_validity_seconds": 300,
            "trusted_ed25519_keys": [
                {
                    "key_id": "governance-review-test",
                    "public_key": base64.b64encode(public_key).decode(),
                }
            ],
        },
        "required_profiles": {
            "minimal-cli": ["CPython", "remote-ops-workspace", "PyInstaller"],
            "secure-cli": ["CPython"],
            "gui-secure": ["CPython"],
        },
        "production_targets": ["windows-x86"],
        "build_lock_enforcement": {
            "state": "enforced",
            "fully_hashed": True,
            "platform_locks": {"windows-x86": "locks/windows-x86.txt"},
        },
        "verifier_bootstrap": {
            "state": "enforced",
            "fully_hashed": True,
            "lock_file": "locks/verifier.txt",
        },
    }
    policy_path = tmp_path / "configs" / "policy.json"
    policy_path.parent.mkdir()
    policy_bytes = json.dumps(policy, sort_keys=True).encode()
    policy_path.write_bytes(policy_bytes)

    lock = _write_record(
        evidence_root,
        "locks/windows-x86.txt",
        lock_content,
        format="pip-requirements",
        fully_hashed=True,
        source_file="locks/windows-x86.txt",
    )
    inspect_payload = {
        "version": "1",
        "installed": [
            {"metadata": {"name": "PyInstaller", "version": "6.22.2"}},
            {"metadata": {"name": "remote-ops-workspace", "version": "1.2.3"}},
        ],
    }
    realized = _write_record(
        evidence_root,
        "inventory/pip-inspect.json",
        json.dumps(inspect_payload).encode(),
        reference="python -m pip inspect --local",
        format="pip-inspect-v1",
    )
    components = [
        _component(evidence_root, "CPython", "3.14.7", "python-runtime"),
        _component(
            evidence_root,
            "remote-ops-workspace",
            "1.2.3",
            "python-distribution",
        ),
        _component(
            evidence_root,
            "PyInstaller",
            "6.22.2",
            "python-distribution",
        ),
    ]
    all_licenses = [
        license_file
        for component in components
        for license_file in component["license_files"]
    ]
    inventory = {
        "schema_version": 1,
        "profile": "minimal-cli",
        "closed_world_complete": True,
        "artifact_contents_scanned": True,
        "all_installed_distributions_recorded": True,
        "classification_complete": True,
        "resolver_lock": lock,
        "realized_environment": realized,
        "components": components,
        "artifact_license_files": {artifact_name: all_licenses},
    }
    protected_registry = _write_record(
        evidence_root,
        "platform/platform_verified_evidence.json",
        b'{"accepted_evidence":[]}',
        reference="signed protected platform registry",
    )
    candidate_inventory = _write_record(
        evidence_root,
        "release-candidate-inventory.json",
        b'{"schema_version":1}\n',
        reference="attested exact-tag candidate inventory",
    )
    evidence = {
        "schema_version": 1,
        "decision": "approved",
        "repository": repository,
        "release_tag": tag,
        "release_sha": sha,
        "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
        "reviewed_at": "2026-09-13T00:00:00Z",
        "expires_at": "2027-09-13T00:00:00Z",
        "protected_platform_registry": protected_registry,
        "candidate_inventory": candidate_inventory,
        "native_manifests": {
            manifest_name: {
                "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "inventory_sha256": hashlib.sha256(checker.canonical_json(inventory)).hexdigest(),
                "inventory": inventory,
            }
        },
    }
    evidence_path = evidence_root / "approval.json"
    evidence_bytes = json.dumps(evidence, sort_keys=True).encode()
    evidence_path.write_bytes(evidence_bytes)
    signature = {
        "schema_version": 1,
        "algorithm": "ed25519",
        "key_id": "legal-review-test",
        "signature": base64.b64encode(private_key.sign(evidence_bytes)).decode(),
    }
    signature_path = evidence_root / "approval.sig.json"
    signature_path.write_text(json.dumps(signature), encoding="utf-8")

    current = datetime.now(UTC)
    observed = current - timedelta(seconds=30)
    expires = current + timedelta(seconds=60)
    governance = {
        "schema_version": 1,
        "decision": "approved",
        "source": "github-rulesets-api",
        "repository": repository,
        "release_tag": tag,
        "release_sha": sha,
        "tag_update_blocked": True,
        "tag_deletion_blocked": True,
        "bypass_actors": [],
        "ruleset_ids": [42],
        "auditor": {"kind": "github-app", "identity": "fixture-auditor"},
        "observed_at": observed.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "expires_at": expires.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    governance_path = evidence_root / "tag-governance-attestation.json"
    governance_bytes = json.dumps(governance, sort_keys=True).encode()
    governance_path.write_bytes(governance_bytes)
    governance_signature = {
        "schema_version": 1,
        "algorithm": "ed25519",
        "key_id": "governance-review-test",
        "signature": base64.b64encode(private_key.sign(governance_bytes)).decode(),
    }
    governance_signature_path = evidence_root / "tag-governance-attestation.sig.json"
    governance_signature_path.write_text(json.dumps(governance_signature), encoding="utf-8")

    checker.TOOLCHAIN_PATH = toolchain_path
    checker.MATRIX_PATH = matrix_path
    checker.WORKFLOW_PATH = workflow_path
    checker.PROMOTION_WORKFLOW_PATH = workflow_path
    return [
        "--assets-dir",
        str(assets),
        "--repository",
        repository,
        "--tag",
        tag,
        "--sha",
        sha,
        "--policy",
        str(policy_path),
        "--policy-root",
        str(tmp_path),
        "--evidence",
        str(evidence_path),
        "--signature",
        str(signature_path),
        "--evidence-root",
        str(evidence_root),
        "--protected-platform-registry",
        str(evidence_root / "platform" / "platform_verified_evidence.json"),
        "--candidate-inventory",
        str(evidence_root / "release-candidate-inventory.json"),
        "--tag-governance-attestation",
        str(governance_path),
        "--tag-governance-signature",
        str(governance_signature_path),
    ]


def test_current_compliance_policy_is_deliberately_fail_closed() -> None:
    checker = _load_checker()
    policy = json.loads(Path("configs/release_compliance_policy.json").read_text())
    toolchain = json.loads(Path("configs/release_toolchain.json").read_text())

    errors = checker.check_policy(policy, toolchain)

    assert any("not independently approved" in error for error in errors)
    assert any("no approved closed-world inventory" in error for error in errors)
    assert any("no trusted Ed25519 approver key" in error for error in errors)


def test_complete_signed_release_compliance_fixture_passes(tmp_path: Path) -> None:
    checker = _load_checker()

    assert checker.main(_positive_fixture(tmp_path, checker)) == 0


def test_signed_evidence_still_rejects_local_artifact_drift(tmp_path: Path) -> None:
    checker = _load_checker()
    args = _positive_fixture(tmp_path, checker)
    artifact = next((tmp_path / "assets").glob("*.zip"))
    artifact.write_bytes(b"tampered after review")

    assert checker.main(args) == 1


def test_component_version_matching_is_case_and_separator_normalized() -> None:
    checker = _load_checker()
    versions = checker.required_versions(
        {
            "python": {"version": "3.14.7"},
            "python_packages": [{"name": "pyinstaller", "version": "6.22.2"}],
        },
        "v1.2.3",
    )

    assert versions[checker.normalize_component_name("PyInstaller")] == "6.22.2"


def test_open_source_qt_channel_requires_source_and_relink_records(tmp_path: Path) -> None:
    checker = _load_checker()
    record = _write_record(
        tmp_path,
        "review/record.json",
        b"reviewed",
        reference="review-ticket",
    )
    channel = {
        "channel": "open-source",
        "pyqt_terms": record,
        "qt_terms": record,
        "qt_component_inventory": record,
    }

    errors = checker.check_qt_channel(channel, prefix="fixture", evidence_root=tmp_path)

    assert any("application_license_review" in error for error in errors)
    assert any("corresponding_source" in error for error in errors)
    assert any("relink_mechanism" in error for error in errors)


def test_review_approval_must_be_current() -> None:
    checker = _load_checker()
    evidence = {
        "reviewed_at": "2025-01-01T00:00:00Z",
        "expires_at": "2025-02-01T00:00:00Z",
    }

    assert checker.check_review_window(
        evidence,
        now=datetime(2026, 9, 14, tzinfo=UTC),
    ) == ["compliance evidence approval has expired"]


def test_release_workflow_withholds_production_but_retains_prerelease_preview() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    promotion = Path(".github/workflows/release-promotion.yml").read_text(encoding="utf-8")
    preview = Path(".github/workflows/unsigned-preview.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" not in workflow
    assert "softprops/action-gh-release" not in workflow
    assert "seal-release-candidate:" in workflow
    assert "check_release_license_compliance.py" in promotion
    assert "--tag-governance-attestation" in promotion
    assert "prerelease: false" in promotion
    assert "PREVIEW_TAG: unsigned-preview-${{ github.run_id }}" in preview
    assert "prerelease: true" in preview


def test_dummy_lock_install_cannot_hide_mutable_extras_resolution() -> None:
    checker = _load_checker()
    block = '''
    steps:
      - run: echo "python -m pip install --require-hashes -r locks/windows-x64.txt"
      - run: python -m pip install --require-hashes -r locks/windows-x64.txt
      - run: python -m pip install ".[desktop,security,package]"
'''

    errors = checker.check_native_job_lock_usage(
        block,
        "windows-native",
        "windows-x64",
        "locks/windows-x64.txt",
    )

    assert any("dependency-resolving pip install outside" in error for error in errors)
    assert any("project/extras install must use --no-deps" in error for error in errors)


def test_echoed_publish_audit_is_not_executable_workflow_evidence() -> None:
    checker = _load_checker()
    block = '''
    steps:
      - run: echo "python scripts/check_release_license_compliance.py --assets-dir release-assets --evidence e --signature s --evidence-root r"
'''

    commands = checker.executable_run_commands(block)

    assert commands == []


def test_echo_before_upload_cannot_hide_real_audit_after_upload(tmp_path: Path) -> None:
    checker = _load_checker()
    verifier = tmp_path / "verifier.txt"
    verifier.write_text(
        f"cryptography==50.0.1 --hash=sha256:{'1' * 64}\n",
        encoding="utf-8",
    )
    workflow = '''jobs:
  publish:
    steps:
      - run: echo "python scripts/check_release_license_compliance.py --assets-dir release-assets --repository r --tag t --sha s --policy p --policy-root pr --evidence e --signature sig --evidence-root er"
      - uses: softprops/action-gh-release@pinned
      - run: python scripts/check_release_license_compliance.py --assets-dir release-assets --repository r --tag t --sha s --policy p --policy-root pr --evidence e --signature sig --evidence-root er --candidate-inventory ci --protected-platform-registry registry --tag-governance-attestation governance --tag-governance-signature governance.sig
'''
    policy = {
        "schema_version": 1,
        "policy_status": "approved",
        "closed_world_inventory_approved": True,
        "trusted_ed25519_keys": [
            {"key_id": "k", "public_key": base64.b64encode(b"k" * 32).decode()}
        ],
        "tag_governance_attestation": {
            "state": "enforced",
            "max_validity_seconds": 300,
            "trusted_ed25519_keys": [
                {"key_id": "g", "public_key": base64.b64encode(b"g" * 32).decode()}
            ],
        },
        "required_profiles": {
            "minimal-cli": ["CPython"],
            "secure-cli": ["CPython"],
            "gui-secure": ["CPython"],
        },
        "production_targets": [],
        "build_lock_enforcement": {
            "state": "enforced",
            "fully_hashed": True,
            "platform_locks": {},
        },
        "verifier_bootstrap": {
            "state": "enforced",
            "fully_hashed": True,
            "lock_file": "verifier.txt",
        },
    }

    errors = checker.check_policy(
        policy,
        {"python": {"version": "3.14.7"}},
        policy_root=tmp_path,
        workflow=workflow,
        promotion_workflow=workflow,
    )

    assert "release workflow license compliance audit must run before release upload" in errors


def test_nested_reparse_point_cannot_escape_compliance_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_checker()
    nested = tmp_path / "nested"
    nested.mkdir()
    target = nested / "license.txt"
    target.write_text("license", encoding="utf-8")
    real_detector = checker.path_is_reparse
    monkeypatch.setattr(
        checker,
        "path_is_reparse",
        lambda path: path == nested or real_detector(path),
    )

    path, error = checker.secure_regular_file(
        tmp_path,
        "nested/license.txt",
        "fixture",
    )

    assert path is None
    assert error == (
        "fixture must not traverse a symlink or reparse point: nested/license.txt"
    )


def test_release_workflow_runs_exact_artifact_audit_before_draft_creation() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/release-promotion.yml").read_text(encoding="utf-8")
    publish = checker.workflow_job_block(workflow, "promote-production-release")

    assert "--assets-dir release-assets" in publish
    assert "--repository \"$GITHUB_REPOSITORY\"" in publish
    assert "--tag \"$RELEASE_TAG\"" in publish
    assert "--sha \"$RELEASE_SHA\"" in publish
    assert publish.index("check_release_license_compliance.py") < publish.index(
        "gh api --method POST"
    )
