from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import shlex
import struct
import sys
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace.moba_servers import build_moba_server_config_plan
from scripts import check_moba_server_release_evidence as server_evidence
from scripts import check_release_mobaxterm_parity as release_parity
from scripts.check_mobaxterm_parity_evidence import (
    PROFESSIONAL_POLICY_SURFACES,
    SOURCE_BOUND_ARTICLES,
)
from scripts.write_release_notes import moba_counts


def test_mobaxterm_parity_evidence_empty_registry_is_valid_but_not_complete() -> None:
    checker = _load_checker()
    registry = {
        "schema_version": 2,
        "policy": _policy(),
        "accepted_evidence": [],
    }

    assert checker.check_mobaxterm_parity_evidence(registry=registry) == []
    errors = checker.check_mobaxterm_parity_evidence(registry=registry, require_complete=True)

    assert any("missing required MobaXterm parity articles" in error for error in errors)
    assert any("shared-authenticated-transport-terminal-grid" in error for error in errors)


def test_mobaxterm_parity_evidence_catalog_tracks_all_eight_articles() -> None:
    checker = _load_checker()

    assert set(checker.ARTICLE_SPECS) == {
        "embedded-server-suite",
        "embedded-x-server",
        "macro-recorder",
        "moba-text-editor-diff",
        "mobapt-unix-runtime",
        "professional-deployment",
        "shared-authenticated-transport-terminal-grid",
        "ssh-browser-26-4-smartcard",
    }
    transport = checker.ARTICLE_SPECS["shared-authenticated-transport-terminal-grid"]
    assert transport.evidence_type == "moba-shared-transport-terminal-grid-release"
    assert transport.required_checks == {
        "shared_authenticated_transport",
        "structured_connection_state",
        "real_terminal_grid",
        "alternate_screen_semantics",
        "cursor_color_mode_mouse_semantics",
        "real_connected_session",
        "release_asset_attachment",
    }


def test_mobaxterm_record_generator_registers_eighth_article_validator() -> None:
    generator = _load_generator()

    validator = generator.VALIDATORS["shared-authenticated-transport-terminal-grid"]

    assert validator.__name__ == "validate_moba_transport_terminal_evidence"


@pytest.mark.parametrize(("article", "validator_name", "flag", "missing_receipt"), [
    ("mobapt-unix-runtime", "validate_mobapt_release_cache_evidence", "offline_execution_receipts_verified",
     "must record verified offline execution receipts"),
    ("embedded-x-server", "validate_moba_x_server_release_asset_evidence", "live_forwarding_receipt_verified",
     "must record a verified live forwarding receipt"),
])
def test_registry_binds_native_debian_evidence_to_asset_and_source(article, validator_name, flag, missing_receipt) -> None:
    checker, generator = _load_checker(), _load_generator()
    assert generator.VALIDATORS[article].__name__ == validator_name
    record = _complete_record(checker.ARTICLE_SPECS[article])
    record["article_id"] = article
    name = "remote-ops-workspace-v1.0.2-linux-amd64.deb"
    record["artifact_sha256"] = record["release_asset_bytes"]["sha256"] = {name: "a" * 64}
    record["release_asset_urls"][0] = record["release_asset_urls"][0].replace("moba-professional-deployment.zip", name)
    record["release_target"] = "linux-x86_64"
    source = record["release_source"]
    summary = record["validation_summary"]["summary"] = {
        "release_target": record["release_target"], "repository": source["repository"],
        "release_tag": source["release_tag"], "workflow_run_url": source["workflow_run_url"],
        "run_attempt": source["run_attempt"], "source_head_sha": source["head_sha"],
        "tested_release_asset": {"name": name, "sha256": "a" * 64},
    }
    assert checker.check_record(record) == [f"{article} validation summary {missing_receipt}"]
    summary[flag] = True
    assert checker.check_record(record) == []
    summary["tested_release_asset"]["sha256"] = "b" * 64
    assert checker.check_record(record) == [f"{article} tested release asset must match the record artifact name and SHA-256"]
    summary["tested_release_asset"]["sha256"] = "a" * 64
    summary["run_attempt"] = 1
    assert checker.check_record(record) == [f"{article} release_source.run_attempt must match validation summary provenance"]


@pytest.fixture
def embedded_server_bundle(tmp_path):
    root = tmp_path / "reviewed" / "embedded-server-suite"
    root.mkdir(parents=True)
    repository = "example/remote-ops-workspace"
    tag = "v1.0.2"
    package = tmp_path / "candidate.deb"
    package.write_bytes(b"fixture release package")
    source = {
        "repository": repository, "release_tag": tag, "head_sha": "d" * 40,
        "workflow_run_url": f"https://github.com/{repository}/actions/runs/1234", "run_attempt": 2,
    }

    def attachment(name, data):
        if isinstance(data, dict):
            data = json.dumps(data).encode()
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"file": name, "sha256": hashlib.sha256(data).hexdigest()}

    marker = b"row-live-fixture-abc123\n"
    challenge = attachment("fixture.txt", marker)
    package_hash = hashlib.sha256(package.read_bytes()).hexdigest()
    manifest = {"schema": "row.moba-servers.runtime-bundle.v1", "release_target": "linux-x86_64", "system": "linux", "services": []}
    evidence = {
        "schema": "row.moba-servers.release-evidence.v1", "release_target": "linux-x86_64", "source": source,
        "release_asset": {"name": package.name, "sha256": package_hash}, "services": [],
    }
    clients = {"http": "curl", "ftp": "lftp", "tftp": "tftp", "ssh": "ssh", "sftp": "sftp", "telnet": "telnet", "vnc": "vncsnapshot", "nfs": "mount.nfs4"}
    keys = {"http": "python-http", "ftp": "pyftpdlib", "tftp": "tftpd", "ssh": "sshd", "sftp": "sshd-sftp", "telnet": "telnetd", "vnc": "x11vnc", "nfs": "nfsd"}
    for service, client in clients.items():
        runtime_file = attachment(f"runtimes/{service}/{keys[service]}", b"\x7fELF" + service.encode())
        relative = runtime_file["file"].removeprefix("runtimes/")
        runtime = {"key": keys[service], "bundled": True, "executable": relative, "sha256": runtime_file["sha256"]}
        manifest["services"].append({"service": service, "runtime": {**runtime, "source": "packaged", "placeholder": False}})
        policy = build_moba_server_config_plan(service, root=tmp_path).to_dict()
        argv = [client, "127.0.0.1", str(policy["port"])]
        data = b"fixture login: proof\r\nPassword: \r\n" + marker if service == "telnet" else marker
        if service == "vnc":
            data = _server_screenshot()
        capture = attachment(f"captures/{service}.data", data)
        receipt = {
            "schema": server_evidence.CLIENT_CAPTURE_SCHEMA, "service": service,
            "runtime_sha256": runtime_file["sha256"], "release_asset_sha256": package_hash,
            "source_head_sha": source["head_sha"], "workflow_run_url": source["workflow_run_url"],
            "run_attempt": source["run_attempt"], "endpoint": {"host": policy["host"], "port": policy["port"]},
            "argv": argv, "exit_code": 0, "capture": capture, "challenge": challenge,
        }
        if service == "nfs":
            receipt["mount_options"] = attachment("captures/nfs.options", b"server:/ nfs4 vers=4.2,proto=tcp,sec=krb5p\n")
            receipt["rejected_sys_mount"] = attachment("captures/nfs.denial", b"mount.nfs4: Operation not permitted\n")
        proof = attachment(f"receipts/{service}.json", receipt)
        evidence["services"].append({
            "service": service, "runtime": {**runtime, "executable": runtime_file["file"]}, "policy": policy,
            "client_test": {"status": "passed", "command": shlex.join(argv), "evidence_file": proof["file"], "evidence_sha256": proof["sha256"]},
        })
    evidence["runtime_manifest"] = attachment("runtimes/servers-runtime.json", manifest)
    attachment("evidence.json", evidence)
    return root, package, evidence, attachment


def _server_screenshot(*, solid=False):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    left = bytes([10, 20, 30])
    right = left if solid else bytes([40, 50, 60])
    row = b"\0" + left * 32 + right * 32
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * 64))
        + chunk(b"IEND", b"")
    )


def test_server_candidate_and_release_audit_validate_the_same_client_evidence(embedded_server_bundle):
    root, package, evidence, _ = embedded_server_bundle
    source = evidence["source"]
    arguments = SimpleNamespace(
        article_id="embedded-server-suite", release_tag=source["release_tag"], release_target="linux-x86_64",
        evidence=root / "evidence.json", assets_dir=root,
        release_asset_url=[f"https://github.com/{source['repository']}/releases/download/{source['release_tag']}/{package.name}"],
        artifact=[f"{package.name}={package}"],
    )
    generator = _load_generator()
    errors, candidate = generator.build_evidence_record(arguments)
    assert errors == []
    assert candidate["validation_summary"]["summary"]["live_client_proof_count"] == 8
    release_parity.verify_article_evidence(candidate, root.parent)

    finalizer = _load_finalizer()
    errors, accepted = finalizer.finalize_candidate(
        candidate, repository=source["repository"], source_head_sha=source["head_sha"],
        tag_source_head_sha=source["head_sha"], workflow_run_url=source["workflow_run_url"],
        run_attempt=source["run_attempt"], reviewer="reviewer",
        review_url=f"https://github.com/{source['repository']}/pull/1#pullrequestreview-2",
        reviewed_at="2026-08-23T12:34:56Z", published_assets={package.name: package},
    )
    assert errors == [] and accepted["status"] == "accepted"

    arguments.release_tag = "v1.0.3"
    errors, _ = generator.build_evidence_record(arguments)
    assert any("--release-tag" in error for error in errors)
    arguments.release_tag = source["release_tag"]
    package.write_bytes(b"different release package")
    errors, _ = generator.build_evidence_record(arguments)
    assert any("tested release asset must match" in error for error in errors)


@pytest.mark.parametrize(
    ("service", "change", "expected_error"),
    [
        ("http", "plain", "client receipt"),
        ("http", "tampered-data", "differs from the server challenge"),
        ("ftp", "workflow-attempt", "must bind a successful protocol client"),
        ("ssh", "daemon", "native executable header"),
        ("telnet", "no-auth", "show the login prompts"),
        ("vnc", "bad-image", "VNC client screenshot must be a valid PNG"),
        ("vnc", "blank-image", "must show a visible framebuffer"),
        ("nfs", "weak-mount", "Kerberos-privacy mount"),
    ],
)
def test_server_release_validator_rejects_incomplete_client_evidence(embedded_server_bundle, service, change, expected_error):
    root, _, evidence, attachment = embedded_server_bundle
    entry = next(row for row in evidence["services"] if row["service"] == service)
    client = entry["client_test"]
    receipt = json.loads((root / client["evidence_file"]).read_bytes())
    if change == "plain":
        receipt = b"client passed"
    elif change == "tampered-data":
        receipt["capture"] = attachment("captures/altered.data", b"different result")
    elif change == "workflow-attempt":
        receipt["run_attempt"] += 1
    elif change == "daemon":
        manifest = json.loads((root / evidence["runtime_manifest"]["file"]).read_bytes())
        runtime = next(row["runtime"] for row in manifest["services"] if row["service"] == service)
        altered = attachment(entry["runtime"]["executable"], b"text placeholder")
        runtime["sha256"] = entry["runtime"]["sha256"] = receipt["runtime_sha256"] = altered["sha256"]
        evidence["runtime_manifest"] = attachment(evidence["runtime_manifest"]["file"], manifest)
    elif change == "no-auth":
        receipt["capture"] = attachment("captures/unauthenticated.data", b"row-live-fixture-abc123\n")
    elif change == "bad-image":
        receipt["capture"] = attachment("captures/bad.png", b"\x89PNG\r\n\x1a\n\0\0\0\0IHDR")
    elif change == "blank-image":
        receipt["capture"] = attachment("captures/blank.png", _server_screenshot(solid=True))
    elif change == "weak-mount":
        receipt["mount_options"] = attachment("captures/nfs.options", b"server:/ nfs4 vers=4.2,proto=tcp,sec=sys\n")
    client["evidence_sha256"] = attachment(client["evidence_file"], receipt)["sha256"]
    attachment("evidence.json", evidence)
    result = server_evidence.validate_live_server_release_evidence(root / "evidence.json", assets_dir=root)
    assert not result.passed and any(expected_error in error for error in result.errors)


def test_mobaxterm_parity_evidence_accepts_complete_article_record() -> None:
    checker = _load_checker()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    record = _complete_record(spec)
    registry = {
        "schema_version": 2,
        "policy": _policy(),
        "accepted_evidence": [record],
    }

    assert checker.check_mobaxterm_parity_evidence(registry=registry) == []


def test_release_notes_count_only_valid_parity_articles_for_the_release() -> None:
    checker = _load_checker()
    record = _complete_record(checker.ARTICLE_SPECS["professional-deployment"])
    root = Path(__file__).resolve().parents[1]
    repository = record["release_source"]["repository"]
    tag = record["release_tag"]
    assert moba_counts(root, {"accepted_evidence": [record, dict(record)]}, tag=tag, repository=repository) == (1, 8)
    assert moba_counts(root, {"accepted_evidence": [record]}, tag="v1.0.3", repository=repository) == (0, 8)
    assert moba_counts(root, {"accepted_evidence": [record]}, tag=tag, repository="other/project") == (0, 8)
    incomplete = dict(record)
    del incomplete["acceptance_review"]
    assert moba_counts(root, {"accepted_evidence": [incomplete]}, tag=tag, repository=repository) == (0, 8)


def test_mobaxterm_parity_evidence_rejects_incomplete_article_record() -> None:
    checker = _load_checker()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    record = {
        "article_id": "professional-deployment",
        "status": "accepted",
        "evidence_type": spec.evidence_type,
        "release_tag": "v1.0.2",
        "release_target": "windows-x64",
        "validation_command": spec.validation_command,
        "evidence_file_sha256": "a" * 64,
        "evidence_assets_sha256": {"moba-professional-deployment.json": "b" * 64},
        "release_asset_urls": [
            "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/moba-professional-deployment.zip"
        ],
        "artifact_sha256": {"moba-professional-deployment.zip": "not-a-sha"},
        "checks": ["branded_windows_exe"],
        "validation_summary": {"passed": False, "errors": ["failed"], "summary": {}},
    }
    registry = {
        "schema_version": 2,
        "policy": _policy(),
        "accepted_evidence": [record, dict(record)],
    }

    errors = checker.check_mobaxterm_parity_evidence(registry=registry)

    assert "professional-deployment validation_summary.passed must be true" in errors
    assert any("missing required checks" in error for error in errors)
    assert any("artifact_sha256" in error for error in errors)
    assert "accepted_evidence article_id must be unique: professional-deployment" in errors


def test_mobaxterm_parity_evidence_rejects_missing_acceptance_provenance() -> None:
    checker = _load_checker()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    record = _complete_record(spec)
    record.pop("release_source")
    record.pop("acceptance_review")
    record.pop("release_asset_bytes")

    errors = checker.check_record(record)

    assert "professional-deployment release_source must be an object" in errors


def test_mobaxterm_parity_evidence_rejects_provenance_drift() -> None:
    checker = _load_checker()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    record = _complete_record(spec)
    record["release_source"]["repository"] = "other/remote-ops-workspace"
    record["release_source"]["tag_source_head_sha"] = "e" * 40
    record["release_source"]["run_attempt"] = True
    record["acceptance_review"]["review_url"] = (
        "https://github.com/review-drift/remote-ops-workspace/pull/42#pullrequestreview-99"
    )
    record["release_asset_bytes"]["sha256"] = {
        "moba-professional-deployment.zip": "d" * 64
    }

    errors = checker.check_record(record)

    assert any("release asset repository must exactly match" in error for error in errors)
    assert any("tag_source_head_sha must match" in error for error in errors)
    assert any("run_attempt must be a positive integer" in error for error in errors)
    assert any("review_url repository must match" in error for error in errors)
    assert any("release_asset_bytes.sha256 must exactly match" in error for error in errors)


def test_mobaxterm_generator_emits_candidate_and_has_no_registry_append(tmp_path: Path, monkeypatch) -> None:
    generator = _load_generator()
    evidence = tmp_path / "evidence.json"
    artifact = tmp_path / "bundle.zip"
    evidence.write_text("{}\n", encoding="utf-8")
    artifact.write_bytes(b"published bytes\n")

    class PassingValidation:
        passed = True
        errors: list[str] = []

        @staticmethod
        def to_dict() -> dict[str, object]:
            return {"passed": True, "errors": [], "summary": {
                "release_target": "windows-x64", "release_tag": "v1.0.2",
                "repository": "example/remote-ops-workspace", "source_head_sha": "d" * 40,
                "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/1234",
                "run_attempt": 2, "tested_release_asset": {"name": artifact.name, "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()},
                "verified_windows_installers": {"org-setup.exe": "a" * 64, "org.msi": "b" * 64},
                "verified_policy_surfaces": list(PROFESSIONAL_POLICY_SURFACES), "verified_machine_policy_sha256": "e" * 64,
            }}

    monkeypatch.setitem(generator.VALIDATORS, "professional-deployment", lambda *_args, **_kwargs: PassingValidation())
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            article_id="professional-deployment",
            release_tag="v1.0.2",
            release_target="windows-x64",
            evidence=evidence,
            assets_dir=tmp_path,
            release_asset_url=[
                "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/bundle.zip"
            ],
            artifact=[f"bundle.zip={artifact}"],
        )
    )

    assert errors == []
    assert record["status"] == "candidate"
    assert "release_source" not in record
    assert "acceptance_review" not in record
    with pytest.raises(SystemExit):
        generator.parse_args(
            [
                "--article-id",
                "professional-deployment",
                "--release-tag",
                "v1.0.2",
                "--release-target",
                "windows-x64",
                "--evidence",
                str(evidence),
                "--append-registry",
            ]
        )


@pytest.mark.parametrize("explicit_assets_dir", [False, True])
def test_mobaxterm_generator_keeps_candidate_outside_reviewed_evidence(
    explicit_assets_dir: bool, tmp_path: Path, capsys
) -> None:
    generator = _load_generator()
    evidence_root = tmp_path / "reviewed"
    evidence_root.mkdir()
    evidence = evidence_root / "evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    output = evidence_root / "records" / "candidate.json"
    args = [
        "--article-id", "professional-deployment", "--release-tag", "v1.0.2",
        "--release-target", "windows-x64", "--evidence", str(evidence), "--out", str(output),
    ]
    if explicit_assets_dir:
        args.extend(["--assets-dir", str(evidence_root)])

    assert generator.main(args) == 1
    assert "--out must be outside the reviewed evidence directory" in capsys.readouterr().err
    assert list(evidence_root.iterdir()) == [evidence]


def test_mobaxterm_finalizer_binds_reviewed_published_bytes(tmp_path: Path) -> None:
    checker = _load_checker()
    finalizer = _load_finalizer()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    published = tmp_path / "moba-professional-deployment.zip"
    published.write_bytes(b"published release bytes\n")
    digest = hashlib.sha256(published.read_bytes()).hexdigest()
    candidate = _complete_record(spec)
    candidate["status"] = "candidate"
    candidate["artifact_sha256"] = {published.name: digest}
    candidate["validation_summary"]["summary"]["tested_release_asset"]["sha256"] = digest
    candidate.pop("release_source")
    candidate.pop("acceptance_review")
    candidate.pop("release_asset_bytes")

    errors, accepted = finalizer.finalize_candidate(
        candidate,
        repository="example/remote-ops-workspace",
        source_head_sha="d" * 40,
        tag_source_head_sha="d" * 40,
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/1234",
        run_attempt=2,
        reviewer="release-reviewer",
        review_url=(
            "https://github.com/example/remote-ops-workspace/pull/42#pullrequestreview-99"
        ),
        reviewed_at="2026-08-23T12:34:56Z",
        published_assets={published.name: published},
    )

    assert errors == []
    assert accepted["status"] == "accepted"
    assert accepted["release_asset_bytes"]["sha256"] == {published.name: digest}
    assert checker.check_record(accepted) == []


def test_mobaxterm_finalizer_rejects_tampered_published_bytes(tmp_path: Path) -> None:
    checker = _load_checker()
    finalizer = _load_finalizer()
    spec = checker.ARTICLE_SPECS["professional-deployment"]
    published = tmp_path / "moba-professional-deployment.zip"
    published.write_bytes(b"tampered\n")
    candidate = _complete_record(spec)
    candidate["status"] = "candidate"
    candidate.pop("release_source")
    candidate.pop("acceptance_review")
    candidate.pop("release_asset_bytes")

    errors, accepted = finalizer.finalize_candidate(
        candidate,
        repository="example/remote-ops-workspace",
        source_head_sha="d" * 40,
        tag_source_head_sha="d" * 40,
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/1234",
        run_attempt=2,
        reviewer="release-reviewer",
        review_url=(
            "https://github.com/example/remote-ops-workspace/pull/42#pullrequestreview-99"
        ),
        reviewed_at="2026-08-23T12:34:56Z",
        published_assets={published.name: published},
    )

    assert accepted == {}
    assert any("published release asset bytes" in error for error in errors)



@pytest.fixture
def reviewed_release(tmp_path, monkeypatch):
    release_sha = "d" * 40
    registry_commit = "e" * 40
    main_tip = "f" * 40
    repository = "example/remote-ops-workspace"
    tag = "v1.0.2"
    name = "remote-ops-workspace-v1.0.2-windows-x64.msi"
    assets_dir = tmp_path / "published"
    evidence_root = tmp_path / "reviewed"
    assets_dir.mkdir()
    evidence_root.mkdir()
    (evidence_root / "workflow-artifacts").mkdir()
    asset = assets_dir / name
    asset.write_bytes(b"published release asset bytes")
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    debian_asset = assets_dir / f"remote-ops-workspace-{tag}-linux-amd64.deb"
    debian_asset.write_bytes(b"published Debian installer")
    debian_digest = hashlib.sha256(debian_asset.read_bytes()).hexdigest()
    wheel = assets_dir / f"remote_ops_workspace-{tag[1:]}-py3-none-any.whl"
    wheel.write_bytes(b"published wheel")
    wheel_digest = hashlib.sha256(wheel.read_bytes()).hexdigest()

    records = []
    for article, spec in release_parity.ARTICLE_SPECS.items():
        record = _complete_record(spec)
        record["article_id"] = article
        record["release_asset_urls"] = [
            f"https://github.com/{repository}/releases/download/{tag}/{name}"
        ]
        record["artifact_sha256"] = {name: digest}
        record["release_asset_bytes"]["sha256"] = {name: digest}
        if article in {"mobapt-unix-runtime", "embedded-x-server"}:
            record["release_target"] = "linux-x86_64"
            record["release_asset_urls"] = [f"https://github.com/{repository}/releases/download/{tag}/{debian_asset.name}"]
            record["artifact_sha256"] = record["release_asset_bytes"]["sha256"] = {debian_asset.name: debian_digest}
        if article == "embedded-x-server":
            record["release_source"]["workflow_run_url"] = f"https://github.com/{repository}/actions/runs/1235"
        if article == "moba-text-editor-diff":
            record["release_target"] = "linux-x86_64"
            record["release_source"]["workflow_run_url"] = f"https://github.com/{repository}/actions/runs/1236"
            record["release_asset_urls"] = [f"https://github.com/{repository}/releases/download/{tag}/{wheel.name}"]
            record["artifact_sha256"] = record["release_asset_bytes"]["sha256"] = {wheel.name: wheel_digest}
        if article in SOURCE_BOUND_ARTICLES:
            record["validation_summary"]["summary"] = {
                "repository": repository,
                "release_tag": tag,
                "release_target": record["release_target"],
                "source_head_sha": release_sha,
                "workflow_run_url": record["release_source"]["workflow_run_url"],
                "run_attempt": 2,
            }
        if article == "mobapt-unix-runtime":
            record["validation_summary"]["summary"].update(
                offline_execution_receipts_verified=True,
                tested_release_asset={"name": debian_asset.name, "sha256": debian_digest},
            )
        if article == "embedded-x-server":
            record["validation_summary"]["summary"].update(
                live_forwarding_receipt_verified=True,
                tested_release_asset={"name": debian_asset.name, "sha256": debian_digest},
            )
        if article == "embedded-server-suite":
            record["validation_summary"]["summary"].update(
                live_client_proof_count=8, tested_release_asset={"name": name, "sha256": digest},
            )
        if article == "macro-recorder":
            record["validation_summary"]["summary"].update(
                verified_macro_replays=1, replay_sessions=1, tested_release_asset={"name": name, "sha256": digest},
            )
        if article == "moba-text-editor-diff":
            record["validation_summary"]["summary"].update(
                verified_remote_edit=True, tested_release_asset={"name": wheel.name, "sha256": wheel_digest},
            )
        if article == "ssh-browser-26-4-smartcard":
            record["validation_summary"]["summary"].update(
                verified_hardware_smartcard=True, verified_multiplexed_sftp=True,
                openssh_key_fingerprint="SHA256:" + "a" * 43, tested_release_asset={"name": name, "sha256": digest},
            )
        if article == "professional-deployment":
            record["validation_summary"]["summary"].update(
                verified_windows_installers={"org-setup.exe": "a" * 64, "org.msi": "b" * 64},
                verified_policy_surfaces=list(PROFESSIONAL_POLICY_SURFACES), verified_machine_policy_sha256="e" * 64,
                tested_release_asset={"name": name, "sha256": digest},
            )
        article_root = evidence_root / article
        article_root.mkdir()
        evidence = article_root / "evidence.json"
        evidence.write_bytes(b'{"fixture":true}')
        evidence_digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
        record["evidence_file_sha256"] = evidence_digest
        record["evidence_assets_sha256"] = {"evidence.json": evidence_digest}
        records.append(record)
    registry = {"schema_version": 2, "policy": _policy(), "accepted_evidence": records}

    on_main = f"compare/{registry_commit}...{main_tip}?per_page=1"
    run = "actions/runs/1234/attempts/2"
    jobs = f"{run}/jobs?per_page=20&page=1"
    x11_run = "actions/runs/1235/attempts/2"
    x11_jobs = f"{x11_run}/jobs?per_page=20&page=1"
    editor_run = "actions/runs/1236/attempts/2"
    editor_jobs = f"{editor_run}/jobs?per_page=20&page=1"
    review = "pulls/42/reviews/99"
    responses = {
        "branches/main": {"name": "main", "protected": True, "commit": {"sha": main_tip}},
        run: {
            "id": 1234,
            "run_attempt": 2,
            "head_sha": release_sha,
            "head_branch": tag,
            "event": "workflow_dispatch",
            "path": f"{release_parity.MOBAPT_WORKFLOW}@refs/tags/{tag}",
            "status": "completed",
            "conclusion": "success",
            "repository": {"full_name": repository},
            "head_repository": {"full_name": repository},
        },
        jobs: {
            "total_count": 2,
            "jobs": [
                {"id": 1, "name": release_parity.MOBAPT_JOB, "run_id": 1234, "run_attempt": 2, "head_sha": release_sha,
                 "status": "completed", "conclusion": "success",
                 "started_at": "2026-08-23T12:20:00Z", "completed_at": "2026-08-23T12:30:00Z"},
                {"id": 2, "run_id": 1234, "run_attempt": 2, "head_sha": release_sha,
                 "status": "completed", "conclusion": "skipped", "completed_at": None},
            ],
        },
        review: {
            "id": 99,
            "state": "APPROVED",
            "html_url": records[0]["acceptance_review"]["review_url"],
            "submitted_at": "2026-08-23T12:34:56Z",
            "body": "\n".join(release_parity.review_acceptance_line(record) for record in records),
            "user": {"login": "release-reviewer"},
        },
    }
    responses[x11_run] = {**responses[run], "id": 1235, "path": release_parity.X11_WORKFLOW}
    responses[x11_jobs] = {
        "total_count": 1, "jobs": [{**responses[jobs]["jobs"][0], "name": release_parity.X11_JOB, "run_id": 1235}],
    }
    responses[editor_run] = {**responses[run], "id": 1236, "path": release_parity.EDITOR_WORKFLOW}
    responses[editor_jobs] = {
        "total_count": 1, "jobs": [{**responses[jobs]["jobs"][0], "name": release_parity.EDITOR_JOB, "run_id": 1236}],
    }
    hosted_archives = {}
    for record in records:
        article = record["article_id"]
        if article not in release_parity.EVIDENCE_WORKFLOWS:
            continue
        run_id = int(record["release_source"]["workflow_run_url"].rsplit("/", 1)[1])
        prefix = release_parity.EVIDENCE_WORKFLOWS[article].artifact_prefix
        artifact_name = f"{prefix}-{run_id}-2"
        archive = evidence_root / "workflow-artifacts" / f"{artifact_name}.zip"
        candidate = {key: value for key, value in record.items()
                     if key not in {"release_source", "acceptance_review", "release_asset_bytes"}}
        candidate["status"] = "candidate"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as payload:
            payload.writestr("candidate.json", json.dumps(candidate))
            payload.writestr(f"{article}/", b"")
            for relative in record["evidence_assets_sha256"]:
                payload.write(evidence_root / article / relative, f"{article}/{relative}")
        metadata = {
            "id": run_id + 5000, "name": artifact_name,
            "created_at": "2026-08-23T12:29:59Z", "expired": False,
            "size_in_bytes": archive.stat().st_size,
            "digest": "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest(),
            "workflow_run": {"id": run_id, "head_sha": release_sha},
        }
        listing = {"total_count": 1, "artifacts": [metadata]}
        responses[f"actions/runs/{run_id}/artifacts?name={artifact_name}&per_page=100"] = listing
        hosted_archives[article] = SimpleNamespace(
            path=archive, metadata=metadata, candidate=candidate, listing=listing,
        )
    for ancestor, descendant in ((release_sha, registry_commit), (registry_commit, main_tip)):
        responses[f"compare/{ancestor}...{descendant}?per_page=1"] = {
            "status": "ahead",
            "behind_by": 0,
            "base_commit": {"sha": ancestor},
            "merge_base_commit": {"sha": ancestor},
        }

    def github_object(expected_repository, resource):
        assert expected_repository == repository
        if resource == f"contents/{release_parity.REGISTRY}?ref={registry_commit}":
            payload = json.dumps(registry).encode("utf-8")
            return {
                "type": "file",
                "path": release_parity.REGISTRY,
                "encoding": "base64",
                "content": base64.b64encode(payload).decode("ascii"),
                "size": len(payload),
            }
        return responses[resource]

    monkeypatch.setattr(release_parity, "github_object", github_object)
    validator_calls = []

    def validate(evidence, *, assets_dir):
        article = assets_dir.name
        assert evidence == assets_dir / "evidence.json"
        validator_calls.append(article)
        summary = next(row["validation_summary"]["summary"] for row in records if row["article_id"] == article)
        return SimpleNamespace(to_dict=lambda: {"passed": True, "summary": summary})

    monkeypatch.setattr(release_parity, "VALIDATORS", dict.fromkeys(release_parity.ARTICLE_SPECS, validate))
    delivery_calls = []

    def verify_delivery(evidence, **requirements):
        assert set(validator_calls) == set(release_parity.ARTICLE_SPECS)
        delivery_calls.append((evidence, requirements))

    monkeypatch.setattr(release_parity, "verify_hosted_professional_update", verify_delivery)
    args = {
        "repository": repository,
        "tag": tag,
        "release_sha": release_sha,
        "registry_commit": registry_commit,
        "assets_dir": assets_dir,
        "evidence_root": evidence_root,
        "professional_update_origins": ["https://updates.example.com"],
    }
    return SimpleNamespace(
        args=args, asset=asset, records=records, responses=responses,
        on_main=on_main, run=run, jobs=jobs, x11_run=x11_run, x11_jobs=x11_jobs,
        editor_run=editor_run, editor_jobs=editor_jobs,
        hosted_archives=hosted_archives,
        review=review, validator_calls=validator_calls,
        delivery_calls=delivery_calls,
    )


def test_certification_accepts_post_release_registry_and_exact_assets(reviewed_release) -> None:
    assert release_parity.audit_release(**reviewed_release.args) == []
    assert set(reviewed_release.validator_calls) == set(release_parity.ARTICLE_SPECS)
    article = next(row for row in reviewed_release.records if row["article_id"] == "professional-deployment")
    directory = reviewed_release.args["evidence_root"] / "professional-deployment"
    assert reviewed_release.delivery_calls == [(directory / "evidence.json", {
        "assets_dir": directory, "published": True, "origins": ["https://updates.example.com"],
        "evidence_sha256": article["evidence_file_sha256"],
        "verified_installers": article["validation_summary"]["summary"]["verified_windows_installers"],
    })]


def test_hosted_delivery_failure_blocks_certification(reviewed_release, monkeypatch) -> None:
    def stale_delivery(*_args, **_kwargs):
        raise ValueError("signed manifest HTTPS delivery SHA-256 differs from the reviewed bytes")

    monkeypatch.setattr(release_parity, "verify_hosted_professional_update", stale_delivery)
    assert release_parity.audit_release(**reviewed_release.args) == [
        "professional-deployment signed manifest HTTPS delivery SHA-256 differs from the reviewed bytes"
    ]


@pytest.mark.parametrize(("field", "value"), [
    ("event", "push"),
    ("head_branch", "main"),
    ("path", ".github/workflows/ci.yml"),
])
def test_mobapt_certification_refuses_successful_attempt_from_the_wrong_workflow(reviewed_release, field, value) -> None:
    reviewed_release.responses[reviewed_release.run][field] = value

    assert release_parity.audit_release(**reviewed_release.args) == [
        "mobapt-unix-runtime MobApt evidence must come from its dedicated workflow dispatched at the release tag"
    ]


def test_mobapt_certification_requires_the_successful_qualification_job(reviewed_release) -> None:
    reviewed_release.responses[reviewed_release.jobs]["jobs"][0]["name"] = "An unrelated successful job"

    assert release_parity.audit_release(**reviewed_release.args) == [
        "mobapt-unix-runtime MobApt evidence attempt must contain one successful qualification job"
    ]


def test_x11_certification_refuses_the_wrong_workflow_or_job(reviewed_release) -> None:
    run = reviewed_release.responses[reviewed_release.x11_run]
    run["path"] = release_parity.MOBAPT_WORKFLOW
    assert release_parity.audit_release(**reviewed_release.args) == [
        "embedded-x-server X11 evidence must come from its dedicated workflow dispatched at the release tag"
    ]
    run["path"] = release_parity.X11_WORKFLOW
    reviewed_release.responses[reviewed_release.x11_jobs]["jobs"][0]["name"] = release_parity.MOBAPT_JOB
    assert release_parity.audit_release(**reviewed_release.args) == [
        "embedded-x-server X11 evidence attempt must contain one successful qualification job"
    ]


def test_editor_certification_refuses_the_wrong_workflow_or_job(reviewed_release) -> None:
    run = reviewed_release.responses[reviewed_release.editor_run]
    run["path"] = release_parity.X11_WORKFLOW
    assert release_parity.audit_release(**reviewed_release.args) == [
        "moba-text-editor-diff Connected editor evidence must come from its dedicated workflow dispatched at the release tag"
    ]
    run["path"] = release_parity.EDITOR_WORKFLOW
    reviewed_release.responses[reviewed_release.editor_jobs]["jobs"][0]["name"] = release_parity.X11_JOB
    assert release_parity.audit_release(**reviewed_release.args) == [
        "moba-text-editor-diff Connected editor evidence attempt must contain one successful qualification job"
    ]


def test_editor_certification_requires_the_published_wheel(reviewed_release) -> None:
    editor = next(row for row in reviewed_release.records if row["article_id"] == "moba-text-editor-diff")
    debian = next(row for row in reviewed_release.records if row["article_id"] == "mobapt-unix-runtime")
    for field in ("release_asset_urls", "artifact_sha256", "release_asset_bytes"):
        editor[field] = debian[field]
    editor["validation_summary"]["summary"]["tested_release_asset"] = (
        debian["validation_summary"]["summary"]["tested_release_asset"]
    )
    assert release_parity.audit_release(**reviewed_release.args) == [
        "moba-text-editor-diff must verify the published wheel on Linux x86_64"
    ]


@pytest.mark.parametrize(("field", "value"), [
    ("created_at", "2026-08-23T12:19:59Z"),
    ("created_at", "2026-08-23T12:30:01Z"),
    ("name", "connected-editor-evidence-1236-1"),
    ("workflow_run", {"id": 1237, "head_sha": "d" * 40}),
])
def test_certification_binds_the_uploaded_archive_to_its_attempt(reviewed_release, field, value) -> None:
    archive = reviewed_release.hosted_archives["moba-text-editor-diff"]
    archive.metadata[field] = value
    assert release_parity.audit_release(**reviewed_release.args) == [
        "moba-text-editor-diff GitHub workflow artifact connected-editor-evidence-1236-2 "
        "does not match the exact evidence attempt"
    ]


def test_certification_rejects_an_ambiguous_hosted_archive(reviewed_release) -> None:
    archive = reviewed_release.hosted_archives["moba-text-editor-diff"]
    archive.listing["total_count"] = 2
    archive.listing["artifacts"].append({**archive.metadata, "id": 7000})
    assert release_parity.audit_release(**reviewed_release.args) == [
        "moba-text-editor-diff GitHub must report one workflow artifact named connected-editor-evidence-1236-2"
    ]


@pytest.mark.parametrize(("mutation", "detail"), [
    ("archive-digest", "workflow artifact ZIP digest differs from GitHub"),
    ("candidate", "workflow artifact candidate differs from the reviewed record"),
    ("member", "workflow artifact bytes differ from the reviewed evidence: moba-text-editor-diff/evidence.json"),
    ("extra", "workflow artifact ZIP has an unexpected file: 'moba-text-editor-diff/unreviewed.txt'"),
])
def test_certification_rejects_substituted_archive_contents(reviewed_release, mutation, detail) -> None:
    article = "moba-text-editor-diff"
    archive = reviewed_release.hosted_archives[article]
    if mutation == "archive-digest":
        archive.metadata["digest"] = "sha256:" + "a" * 64
    else:
        candidate = {**archive.candidate, "release_target": "linux-arm64"} if mutation == "candidate" else archive.candidate
        reviewed = reviewed_release.args["evidence_root"] / article / "evidence.json"
        with zipfile.ZipFile(archive.path, "w") as payload:
            payload.writestr("candidate.json", json.dumps(candidate))
            payload.writestr(f"{article}/evidence.json", b"substituted" if mutation == "member" else reviewed.read_bytes())
            if mutation == "extra":
                payload.writestr(f"{article}/unreviewed.txt", b"extra")
        archive.metadata.update(
            size_in_bytes=archive.path.stat().st_size,
            digest="sha256:" + hashlib.sha256(archive.path.read_bytes()).hexdigest(),
        )
    assert release_parity.audit_release(**reviewed_release.args) == [f"{article} {detail}"]


def test_certification_can_reuse_an_expired_artifacts_original_zip(reviewed_release, monkeypatch) -> None:
    archive = reviewed_release.hosted_archives["embedded-x-server"]
    archive.metadata["expired"] = True
    monkeypatch.setattr(release_parity, "download_workflow_archive", lambda *_args: pytest.fail("unnecessary download"))
    assert release_parity.audit_release(**reviewed_release.args) == []
    archive.path.unlink()
    assert release_parity.audit_release(**reviewed_release.args) == [
        "embedded-x-server GitHub workflow artifact expired; retain its original ZIP at "
        "workflow-artifacts/x11-forwarding-evidence-1235-2.zip"
    ]


def test_certification_downloads_only_the_exact_artifact_when_needed(reviewed_release, monkeypatch) -> None:
    archive = reviewed_release.hosted_archives["mobapt-unix-runtime"]
    data = archive.path.read_bytes()
    archive.path.unlink()
    requested = []

    def download(repository, artifact_id, destination, size):
        requested.append((repository, artifact_id, size))
        destination.write_bytes(data)

    monkeypatch.setattr(release_parity, "download_workflow_archive", download)
    assert release_parity.audit_release(**reviewed_release.args) == []
    assert requested == [(reviewed_release.args["repository"], archive.metadata["id"], len(data))]


@pytest.mark.parametrize("observed_target", ["linux-arm64", None])
def test_parity_evidence_for_each_article_must_bind_its_tested_target(reviewed_release, observed_target) -> None:
    checker = _load_checker()
    for record in reviewed_release.records:
        article = record["article_id"]
        record["validation_summary"]["summary"]["release_target"] = observed_target
        candidate = dict(record, status="candidate")
        error = f"{article} validation summary release_target must match record release_target"
        assert error in checker.check_candidate_record(candidate)
        assert error in checker.check_record(record)


def test_certification_rejects_registry_commit_outside_main(reviewed_release) -> None:
    reviewed_release.responses[reviewed_release.on_main]["status"] = "diverged"

    with pytest.raises(ValueError, match="did not establish .* as an ancestor"):
        release_parity.audit_release(**reviewed_release.args)


def test_certification_rejects_other_release_and_changed_download(reviewed_release) -> None:
    stale = next(row for row in reviewed_release.records if row["article_id"] == "professional-deployment")
    stale["release_tag"] = "v1.0.1"
    stale["release_source"]["release_tag"] = "v1.0.1"
    stale["validation_summary"]["summary"]["release_tag"] = "v1.0.1"
    stale["release_asset_urls"][0] = stale["release_asset_urls"][0].replace("/download/v1.0.2/", "/download/v1.0.1/")
    assert _load_checker().check_record(stale) == []
    reviewed_release.asset.write_bytes(b"changed download")

    errors = release_parity.audit_release(**reviewed_release.args)

    assert any("professional-deployment accepted record must bind the exact release" in error for error in errors)
    assert any("SHA-256 differs from the downloaded release asset" in error for error in errors)
    assert reviewed_release.delivery_calls == []


@pytest.mark.parametrize(
    ("key", "field", "value", "expected_error"),
    [
        ("run", "run_attempt", 3, "does not match successful release evidence"),
        ("review", "state", "DISMISSED", "review is not approved"),
    ],
)
def test_certification_checks_live_attempt_and_review(
    reviewed_release, key, field, value, expected_error,
) -> None:
    reviewed_release.responses[getattr(reviewed_release, key)][field] = value

    errors = release_parity.audit_release(**reviewed_release.args)

    assert any(expected_error in error for error in errors)


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("completed_at", "2026-08-23T12:35:00Z", "review predates completion"),
    ("completed_at", None, "missing a valid completion timestamp"),
    ("run_attempt", 1, "job does not match the completed evidence attempt"),
])
def test_certification_binds_review_time_to_completed_attempt_jobs(
    reviewed_release, field, value, expected,
) -> None:
    for jobs in (reviewed_release.jobs, reviewed_release.x11_jobs, reviewed_release.editor_jobs):
        reviewed_release.responses[jobs]["jobs"][0][field] = value

    errors = release_parity.audit_release(**reviewed_release.args)

    assert len(errors) == len(reviewed_release.records)
    assert all(expected in error for error in errors)


def test_finalizer_prints_the_same_review_line_before_acceptance(reviewed_release, tmp_path, capsys) -> None:
    record = reviewed_release.records[0]
    candidate = {key: value for key, value in record.items()
                 if key not in {"release_source", "acceptance_review", "release_asset_bytes"}}
    candidate["status"] = "candidate"
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    source = record["release_source"]

    assert _load_finalizer().main([
        "--candidate-record", str(candidate_path), "--repository", source["repository"],
        "--source-head-sha", source["head_sha"], "--tag-source-head-sha", source["tag_source_head_sha"],
        "--workflow-run-url", source["workflow_run_url"], "--run-attempt", str(source["run_attempt"]),
        "--print-review-line",
    ]) == 0
    assert capsys.readouterr().out.strip() == release_parity.review_acceptance_line(record)


def test_certification_rejects_review_body_that_only_accepts_another_article(reviewed_release) -> None:
    review = reviewed_release.responses[reviewed_release.review]
    other = reviewed_release.records[-1]
    review["body"] = release_parity.review_acceptance_line(other)

    errors = release_parity.audit_release(**reviewed_release.args)

    assert len(errors) == len(reviewed_release.records) - 1
    assert all("does not explicitly accept this exact article evidence" in error for error in errors)


def test_certification_rejects_changed_evidence_after_approval(reviewed_release) -> None:
    reviewed_release.records[0]["evidence_file_sha256"] = "2" * 64

    errors = release_parity.audit_release(**reviewed_release.args)

    assert len(errors) == 1
    assert "does not explicitly accept this exact article evidence" in errors[0]


def test_certification_rejects_unrelated_comment_with_matching_author(reviewed_release) -> None:
    review = reviewed_release.responses[reviewed_release.review]
    comment_url = "https://github.com/example/remote-ops-workspace/issues/42#issuecomment-99"
    reviewed_release.responses["issues/comments/99"] = {
        "id": 99, "html_url": comment_url, "created_at": review["submitted_at"],
        "user": review["user"], "body": "Thanks for putting this together.",
    }
    for record in reviewed_release.records:
        record["acceptance_review"]["review_url"] = comment_url

    errors = release_parity.audit_release(**reviewed_release.args)

    assert len(errors) == len(reviewed_release.records)
    assert all("does not explicitly accept this exact article evidence" in error for error in errors)


@pytest.mark.parametrize(("edit", "expected"), [
    ("changed", "SHA-256 differs"),
    ("missing", "files are missing"),
    ("extra", "unexpected file"),
])
def test_certification_checks_exact_reviewed_evidence_files(reviewed_release, edit, expected) -> None:
    article = reviewed_release.records[0]["article_id"]
    root = reviewed_release.args["evidence_root"] / article
    evidence = root / "evidence.json"
    if edit == "changed":
        evidence.write_bytes(b"changed evidence")
    elif edit == "missing":
        evidence.unlink()
    else:
        (root / "unexpected.txt").write_text("unreviewed", encoding="utf-8")

    errors = release_parity.audit_release(**reviewed_release.args)

    assert len(errors) == 1
    assert expected in errors[0]
    assert article not in reviewed_release.validator_calls


def test_certification_refuses_evidence_when_the_article_validator_fails(reviewed_release, monkeypatch) -> None:
    article = reviewed_release.records[0]["article_id"]
    monkeypatch.setitem(release_parity.VALIDATORS, article,
                        lambda *_args, **_kwargs: SimpleNamespace(to_dict=lambda: {"passed": False}))
    errors = release_parity.audit_release(**reviewed_release.args)
    assert len(errors) == 1
    assert "article validator did not pass" in errors[0]


def _load_checker():
    path = Path("scripts/check_mobaxterm_parity_evidence.py")
    spec = importlib.util.spec_from_file_location("check_mobaxterm_parity_evidence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_generator():
    path = Path("scripts/make_mobaxterm_parity_evidence_record.py")
    spec = importlib.util.spec_from_file_location("make_mobaxterm_parity_evidence_record", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_finalizer():
    path = Path("scripts/finalize_mobaxterm_parity_evidence_record.py")
    spec = importlib.util.spec_from_file_location("finalize_mobaxterm_parity_evidence_record", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _complete_record(spec):
    return {
        "article_id": "professional-deployment",
        "status": "accepted",
        "evidence_type": spec.evidence_type,
        "release_tag": "v1.0.2",
        "release_target": "windows-x64",
        "validation_command": spec.validation_command,
        "evidence_file_sha256": "a" * 64,
        "evidence_assets_sha256": {"moba-professional-deployment.json": "b" * 64},
        "release_asset_urls": [
            "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
            "moba-professional-deployment.zip"
        ],
        "artifact_sha256": {"moba-professional-deployment.zip": "c" * 64},
        "checks": sorted(spec.required_checks),
        "validation_summary": {
            "passed": True,
            "errors": [],
            "summary": {
                "release_target": "windows-x64", "brand_name": "Corp Ops", "release_tag": "v1.0.2",
                "repository": "example/remote-ops-workspace", "source_head_sha": "d" * 40,
                "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/1234",
                "run_attempt": 2,
                "tested_release_asset": {"name": "moba-professional-deployment.zip", "sha256": "c" * 64},
                "verified_windows_installers": {"org-setup.exe": "a" * 64, "org.msi": "b" * 64},
                "verified_policy_surfaces": list(PROFESSIONAL_POLICY_SURFACES), "verified_machine_policy_sha256": "e" * 64,
            },
        },
        "release_source": {
            "repository": "example/remote-ops-workspace",
            "release_tag": "v1.0.2",
            "head_sha": "d" * 40,
            "tag_source_head_sha": "d" * 40,
            "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/1234",
            "run_attempt": 2,
        },
        "acceptance_review": {
            "reviewer": "release-reviewer",
            "review_url": (
                "https://github.com/example/remote-ops-workspace/pull/42#pullrequestreview-99"
            ),
            "reviewed_at": "2026-08-23T12:34:56Z",
        },
        "release_asset_bytes": {
            "verified": True,
            "verified_by": "release-reviewer",
            "verified_at": "2026-08-23T12:34:56Z",
            "sha256": {"moba-professional-deployment.zip": "c" * 64},
        },
    }


def _policy() -> str:
    return (
        "Only accepted evidence records in this file can close strict MobaXterm 26.4 Home/Professional parity "
        "articles. Accepted records must include one unique article_id, status accepted, a vX.Y.Z release_tag, "
        "a release_target, the exact validation command for that article, SHA-256 digests for the validated "
        "evidence JSON and evidence assets, release asset URLs under the same GitHub release tag, per-artifact "
        "SHA-256 digests, required article checks, and a validation summary proving the article evidence passed. "
        "Acceptance additionally requires the exact GitHub repository, source head SHA and tag source head SHA, "
        "the exact source workflow run URL and positive run attempt, reviewer provenance, and hashes of the "
        "published release bytes matching the accepted per-artifact SHA-256 values. Candidate generation cannot "
        "append or accept its own output; a separate reviewed finalization step is mandatory. "
        "Empty means the generated feature-family score remains separate from true product-depth parity."
    )
