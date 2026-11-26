from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import shlex
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace.moba_servers import build_moba_server_config_plan
from scripts import assemble_debian_server_evidence as assembly
from scripts import capture_debian_server_clients as client_capture
from scripts import check_candidate_mobaxterm_parity as candidate_parity
from scripts import check_moba_server_release_evidence as server_evidence
from scripts import check_release_mobaxterm_parity as release_parity
from scripts import finalize_mobaxterm_parity_release as batch_finalize
from scripts import release_candidate_inventory as candidate_inventory
from scripts.check_mobaxterm_parity_evidence import (
    PROFESSIONAL_POLICY_SURFACES,
    SOURCE_BOUND_ARTICLES,
)
from scripts.run_debian_server_lab import capture as capture_debian_lab
from scripts.write_release_notes import moba_counts


@pytest.mark.parametrize(("workflow", "target", "image", "work"), [
    ("mobapt-offline-evidence", "mobapt", "MOBAPT_IMAGE", "MOBAPT_WORK"),
    ("x11-forwarding-evidence", "x11", "X11_IMAGE", "X11_WORK"),
])
def test_debian_parity_capture_prepares_the_verified_asset_dependencies(
    workflow: str, target: str, image: str, work: str,
) -> None:
    source = Path(f".github/workflows/{workflow}.yml").read_text(encoding="utf-8")
    verified_asset = source.index("scripts/fetch_qualification_release_asset.py --kind debian-amd64")
    image_build = source.index(f"docker build --platform linux/amd64 --pull --target {target}")
    offline_capture = source.index("docker run --rm --pull never --platform linux/amd64 --network none")
    assert verified_asset < image_build < offline_capture
    assert f'sha256sum -- "${work}/release/$asset"' in source[verified_asset:image_build]
    assert '--build-arg "ROW_DEB_SHA256=${digest%% *}"' in source[image_build:offline_capture]
    assert f'--file docker/Dockerfile.debian-parity-evidence --tag "${image}" "${work}/release"' in (
        source[image_build:offline_capture]
    )
    assert f'"${image}" python /src/scripts/capture_moba' in source[offline_capture:]
    fixture = Path("docker/Dockerfile.debian-parity-evidence").read_text(encoding="utf-8")
    assert fixture.index("sha256sum --check --strict") < fixture.index("apt-get update")
    assert 'satisfy -- "$depends"' in fixture
    assert "FROM mobapt AS x11" in fixture
    if target == "mobapt":
        assert "apt-get download" not in source and "--bundle" not in source[offline_capture:]
    if target == "x11":
        assert "--installed-runtime" in source[offline_capture:]
        assert " xvfb " not in fixture.split("FROM mobapt AS x11", 1)[1]


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


@pytest.mark.parametrize("article", sorted(release_parity.ARTICLE_SPECS))
def test_release_parity_workflow_declares_each_reviewed_job(article: str) -> None:
    workflow = release_parity.EVIDENCE_WORKFLOWS[article]
    source = Path(workflow.path).read_text(encoding="utf-8")
    job_lines = source.split("\njobs:\n", 1)[1].splitlines()
    expected_names = [workflow.job, *(name for name, _labels in workflow.prerequisite_jobs)]
    for name in expected_names:
        assert job_lines.count(f"    name: {name}") == 1, f"{workflow.path} must declare exactly one job named {name!r}"


def test_mobaxterm_record_generator_registers_eighth_article_validator() -> None:
    generator = _load_generator()

    validator = generator.VALIDATORS["shared-authenticated-transport-terminal-grid"]

    assert validator.__name__ == "validate_moba_transport_terminal_evidence"


@pytest.mark.parametrize(("tag", "named", "valid"), [
    ("v1.0.27", None, True), ("v1.0.28", None, False), ("v1.0.28", True, False),
    ("v1.0.28", 0, False), ("v1.0.28", 1, False), ("v1.0.28", 2, True),
    ("v1.1.0", None, False), ("v2.0.0", None, False), ("v1.0.27", 1, False),
    ("1.0.27", None, False), ("v0", None, False),
])
def test_macro_summary_binds_named_workspace_playback_to_release(tag, named, valid):
    checker = _load_checker()
    details = {"verified_macro_replays": 2, "replay_sessions": 2, "release_target": "linux-x86_64"}
    if named is not None:
        details["verified_named_macro_replays"] = named
    errors = checker.check_validation_summary(
        "macro-recorder", {"passed": True, "errors": [], "summary": details},
        release_target="linux-x86_64", release_tag=tag,
    )
    assert errors == ([] if valid else [
        "macro-recorder validation summary must verify named workspace playback for every replay"
    ])


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
    expected = [f"{article} validation summary {missing_receipt}"]
    if article == "mobapt-unix-runtime":
        expected.append(f"{article} validation summary must record the verified Debian package-owned cache")
    elif article == "embedded-x-server":
        expected.append(f"{article} validation summary must record the package-owned and unprivileged runtime")
    assert checker.check_record(record) == expected
    summary[flag] = True
    if article == "mobapt-unix-runtime":
        assert checker.check_record(record) == expected[1:]
        summary["installed_cache_verified"] = True
    elif article == "embedded-x-server":
        summary["installed_runtime_verified"] = True
        assert checker.check_record(record) == expected[1:]
        summary["unprivileged_runtime_verified"] = True
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
    package = tmp_path / "remote-ops-workspace-v1.0.2-linux-amd64.deb"
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
        header = bytearray(64)
        header[:7] = b"\x7fELF\x02\x01\x01"
        struct.pack_into("<HHI", header, 16, 3, 62, 1)
        struct.pack_into("<H", header, 52, len(header))
        name = {"http": "python", "sftp": "sshd"}.get(service, keys[service])
        runtime_file = attachment(f"runtimes/linux/{service}/bin/{name}", bytes(header) + service.encode())
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


@pytest.mark.parametrize(("change", "reason"), [
    (None, None),
    ("iperf", None),
    ("package", "capture index must bind the supplied Debian asset"),
    ("receipt", "must bind a successful protocol client"),
    ("attempt", "capture index must bind the current Actions workflow attempt"),
    ("hidden-path", "capture attachment must use a canonical relative path"),
    ("missing", "requires each of the eight services"),
    ("package-contents", "Debian package differs from the deployed runtime"),
])
def test_assemble_debian_server_review_inputs(embedded_server_bundle, tmp_path, monkeypatch, change, reason):
    captures, package, evidence, attachment = embedded_server_bundle
    installed = tmp_path / "installed"
    runtime_root = installed / assembly.PAYLOAD
    shutil.copytree(captures / "runtimes", runtime_root)
    if change == "iperf":
        manifest_path = runtime_root / assembly.MANIFEST
        manifest = json.loads(manifest_path.read_bytes())
        relative = "linux/iperf/bin/iperf"
        daemon = runtime_root / relative
        daemon.parent.mkdir(parents=True)
        launcher = runtime_root / "linux/http/bin/python"
        daemon.write_bytes(launcher.read_bytes() + b"iperf")
        manifest["services"].append({"service": "iperf", "runtime": {
            "source": "packaged", "bundled": True, "placeholder": False, "key": "iperf2",
            "executable": relative, "sha256": hashlib.sha256(daemon.read_bytes()).hexdigest(),
        }})
        manifest["debian_notices"] = {}
        for component, services in (("server-suite", ["tftp", "ssh", "sftp", "telnet", "vnc", "nfs"]), ("iperf", ["iperf"])):
            path = installed / assembly.notice_path(component)
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = component.encode()
            path.write_bytes(raw)
            manifest["debian_notices"][component] = {
                "version": "1:2.3-1", "services": services, "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    authoring_index = {key: evidence[key] for key in ("source", "release_asset")}
    source = evidence["source"]
    for key, value in {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": f"refs/tags/{source['release_tag']}",
        "GITHUB_REPOSITORY": source["repository"],
        "GITHUB_SHA": source["head_sha"],
        "GITHUB_RUN_ID": source["workflow_run_url"].rsplit("/", 1)[-1],
        "GITHUB_RUN_ATTEMPT": str(source["run_attempt"] + (change == "attempt")),
    }.items():
        monkeypatch.setenv(key, value)
    authoring_index["services"] = [
        {
            "service": row["service"], "policy": row["policy"],
            "receipt": {"file": row["client_test"]["evidence_file"], "sha256": row["client_test"]["evidence_sha256"]},
        }
        for row in evidence["services"]
    ]
    if change == "package":
        package.write_bytes(b"wrong package")
    elif change == "missing":
        authoring_index["services"].pop()
    elif change == "hidden-path":
        row = authoring_index["services"][0]
        row["receipt"] = attachment(".captures/http.json", (captures / row["receipt"]["file"]).read_bytes())
    elif change == "receipt":
        row = authoring_index["services"][0]
        name = row["receipt"]["file"]
        receipt = json.loads((captures / name).read_bytes())
        receipt["run_attempt"] += 1
        row["receipt"] = attachment(name, receipt)
    attachment(assembly.CAPTURES_INDEX, authoring_index)
    audited = []

    def verify_debian_file(actual_package, candidate, target):
        assert actual_package == package and target == evidence["release_target"]
        assert (candidate / evidence["runtime_manifest"]["file"]).read_bytes() == (runtime_root / assembly.MANIFEST).read_bytes()
        audited.append(target)
        if change == "package-contents":
            raise ValueError(reason)

    monkeypatch.setattr(assembly, "verify_packaged_debian_server_evidence", verify_debian_file)
    output = tmp_path / "review-output"
    if reason:
        with pytest.raises(ValueError, match=reason):
            assembly.assemble(package, evidence["release_target"], installed, captures, output)
        assert not output.exists()
        assert bool(audited) == (change == "package-contents")
        return

    evidence_path = assembly.assemble(package, evidence["release_target"], installed, captures, output)
    result = server_evidence.validate_live_server_release_evidence(evidence_path)
    assert result.passed and result.summary["live_client_proof_count"] == 8
    if change == "iperf":
        assert (output / assembly.RUNTIME_DIR / relative).read_bytes() == daemon.read_bytes()
        assert (output / assembly.RUNTIME_DIR / "notices/iperf.copyright").read_bytes() == b"iperf"
    assert audited == [evidence["release_target"]]
    assert not (output / assembly.CAPTURES_INDEX).exists()


@pytest.mark.parametrize("change", [None, "attempt", "package", "client-failed"])
def test_server_recorder_binds_nfs_fragment_to_the_receipts_attempt(embedded_server_bundle, tmp_path, change):
    fixture, package, evidence, _ = embedded_server_bundle
    nfs = next(row for row in evidence["services"] if row["service"] == "nfs")
    source = tmp_path / "source.json"
    source.write_text(json.dumps(evidence["source"]), encoding="utf-8")
    fragment = tmp_path / "fragment"
    fragment.mkdir()
    recorder = client_capture.Recorder(fragment, tmp_path, package, source)
    recorder.runtime = {"nfs": nfs["runtime"]}
    receipt = json.loads((fixture / nfs["client_test"]["evidence_file"]).read_bytes())
    files = {key: (fixture / receipt[key]["file"]).read_bytes()
             for key in ("capture", "challenge", "mount_options", "rejected_sys_mount")}
    actual = subprocess.CompletedProcess(receipt["argv"], int(change == "client-failed"))
    if change == "client-failed":
        with pytest.raises(ValueError, match="must bind a successful protocol client"):
            recorder.record("nfs", nfs["policy"], actual, **files)
        assert not recorder.observations
        return
    recorder.record("nfs", nfs["policy"], actual, **files)
    recorder.finish()

    combined = tmp_path / "combined"
    combined.mkdir()
    if change == "attempt":
        source.write_text(json.dumps({**evidence["source"], "run_attempt": 3}), encoding="utf-8")
    if change == "package":
        package.write_bytes(b"different package")
    receiver = client_capture.Recorder(combined, tmp_path, package, source)
    receiver.runtime = recorder.runtime
    if change:
        with pytest.raises(ValueError, match="must bind this release asset and source attempt"):
            receiver.include_nfs(fragment)
        assert not list(combined.iterdir())
    else:
        receiver.include_nfs(fragment)
        receiver.finish()
        assert receiver.observations == recorder.observations
        assert {entry.name: entry.read_bytes() for entry in combined.iterdir()} == {
            entry.name: entry.read_bytes() for entry in fragment.iterdir()
        }


@pytest.mark.parametrize(("change", "error"), [
    ("package-digest", "does not match the supplied SHA-256"),
    ("missing-actions", "requires source and release_asset objects"),
])
def test_debian_lab_rejects_unverified_inputs_before_starting_docker(embedded_server_bundle, tmp_path, monkeypatch,
                                                            change, error):
    _, package, evidence, _ = embedded_server_bundle
    digest = "0" * 64 if change == "package-digest" else evidence["release_asset"]["sha256"]
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr("scripts.run_debian_server_lab.docker", lambda *_args: pytest.fail("unexpected Docker call"))
    output = tmp_path / "capture"
    with pytest.raises(ValueError, match=error):
        capture_debian_lab("fixture-image", package, digest, output)
    assert not output.exists()


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


def test_server_review_binds_declared_openssh_helper_attachments(embedded_server_bundle):
    root, _, evidence, attachment = embedded_server_bundle
    manifest_file = evidence["runtime_manifest"]["file"]
    manifest = json.loads((root / manifest_file).read_bytes())
    helpers = [
        attachment(f"runtimes/linux/openssh/libexec/{name}", name.encode())
        for name in ("sshd-session", "sshd-auth")
    ]
    manifest["openssh_helpers"] = {Path(row["file"]).name: row["sha256"] for row in helpers}
    evidence["runtime_manifest"] = attachment(manifest_file, manifest)
    evidence_file = root / "evidence.json"
    attachment("evidence.json", evidence)

    assert server_evidence.validate_live_server_release_evidence(evidence_file).passed
    (root / helpers[0]["file"]).write_bytes(b"replacement")
    result = server_evidence.validate_live_server_release_evidence(evidence_file)
    assert not result.passed and any("OpenSSH helper failed its integrity check" in error for error in result.errors)


def test_server_review_rejects_missing_debian_notice_attachment(embedded_server_bundle):
    root, _, evidence, attachment = embedded_server_bundle
    manifest_file = evidence["runtime_manifest"]["file"]
    manifest = json.loads((root / manifest_file).read_bytes())
    raw = b"Debian archive copyright fixture\n"
    notice = attachment("runtimes/notices/server-suite.copyright", raw)
    manifest["debian_notices"] = {"server-suite": {
        "version": "1:2.3-1", "services": ["tftp", "ssh", "sftp", "telnet", "vnc", "nfs"],
        "sha256": notice["sha256"], "size_bytes": len(raw),
    }}
    evidence["runtime_manifest"] = attachment(manifest_file, manifest)
    evidence_file = root / "evidence.json"
    attachment("evidence.json", evidence)
    assert server_evidence.validate_live_server_release_evidence(evidence_file).passed

    (root / notice["file"]).unlink()
    result = server_evidence.validate_live_server_release_evidence(evidence_file)
    assert not result.passed and any("Debian server notice" in error for error in result.errors)


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
        if article in {"mobapt-unix-runtime", "embedded-x-server", "embedded-server-suite"}:
            record["release_target"] = "linux-x86_64"
            record["release_asset_urls"] = [f"https://github.com/{repository}/releases/download/{tag}/{debian_asset.name}"]
            record["artifact_sha256"] = record["release_asset_bytes"]["sha256"] = {debian_asset.name: debian_digest}
        if article == "embedded-x-server":
            record["release_source"]["workflow_run_url"] = f"https://github.com/{repository}/actions/runs/1235"
        if article == "embedded-server-suite":
            record["release_source"]["workflow_run_url"] = f"https://github.com/{repository}/actions/runs/1239"
        if article == "professional-deployment":
            record["release_target"] = "windows-x64"
            record["release_source"]["workflow_run_url"] = f"https://github.com/{repository}/actions/runs/1240"
            record["release_asset_urls"] = [f"https://github.com/{repository}/releases/download/{tag}/{wheel.name}"]
            record["artifact_sha256"] = record["release_asset_bytes"]["sha256"] = {wheel.name: wheel_digest}
        if article == "moba-text-editor-diff":
            record["release_target"] = "linux-x86_64"
            record["release_source"]["workflow_run_url"] = f"https://github.com/{repository}/actions/runs/1236"
            record["release_asset_urls"] = [f"https://github.com/{repository}/releases/download/{tag}/{wheel.name}"]
            record["artifact_sha256"] = record["release_asset_bytes"]["sha256"] = {wheel.name: wheel_digest}
        if article == "macro-recorder":
            record["release_target"] = "linux-x86_64"
            record["release_source"]["workflow_run_url"] = f"https://github.com/{repository}/actions/runs/1237"
            record["release_asset_urls"] = [f"https://github.com/{repository}/releases/download/{tag}/{wheel.name}"]
            record["artifact_sha256"] = record["release_asset_bytes"]["sha256"] = {wheel.name: wheel_digest}
        if article == "ssh-browser-26-4-smartcard":
            record["release_target"] = "linux-x86_64"
            record["release_source"]["workflow_run_url"] = f"https://github.com/{repository}/actions/runs/1241"
            record["release_asset_urls"] = [f"https://github.com/{repository}/releases/download/{tag}/{wheel.name}"]
            record["artifact_sha256"] = record["release_asset_bytes"]["sha256"] = {wheel.name: wheel_digest}
        if article == "shared-authenticated-transport-terminal-grid":
            record["release_target"] = "linux-x86_64"
            record["release_source"]["workflow_run_url"] = f"https://github.com/{repository}/actions/runs/1238"
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
                installed_cache_verified=True,
                tested_release_asset={"name": debian_asset.name, "sha256": debian_digest},
            )
        if article == "embedded-x-server":
            record["validation_summary"]["summary"].update(
                live_forwarding_receipt_verified=True,
                installed_runtime_verified=True,
                unprivileged_runtime_verified=True,
                tested_release_asset={"name": debian_asset.name, "sha256": debian_digest},
            )
        if article == "embedded-server-suite":
            record["validation_summary"]["summary"].update(
                live_client_proof_count=8, tested_release_asset={"name": debian_asset.name, "sha256": debian_digest},
            )
        if article == "shared-authenticated-transport-terminal-grid":
            record["validation_summary"]["summary"].update(
                verified_capture_count=12, verified_ssh_channel_count=3, verified_screen_proof_count=3,
                tested_release_asset={"name": wheel.name, "sha256": wheel_digest},
            )
        if article == "macro-recorder":
            record["validation_summary"]["summary"].update(
                verified_macro_replays=1, replay_sessions=1, tested_release_asset={"name": wheel.name, "sha256": wheel_digest},
            )
        if article == "moba-text-editor-diff":
            record["validation_summary"]["summary"].update(
                verified_remote_edit=True, tested_release_asset={"name": wheel.name, "sha256": wheel_digest},
            )
        if article == "ssh-browser-26-4-smartcard":
            record["validation_summary"]["summary"].update(
                verified_hardware_smartcard=True, verified_multiplexed_sftp=True,
                openssh_key_fingerprint="SHA256:" + "a" * 43,
                tested_release_asset={"name": wheel.name, "sha256": wheel_digest},
            )
        if article == "professional-deployment":
            record["validation_summary"]["summary"].update(
                verified_windows_installers={"org-setup.exe": "a" * 64, "org.msi": "b" * 64},
                verified_policy_surfaces=list(PROFESSIONAL_POLICY_SURFACES), verified_machine_policy_sha256="e" * 64,
                tested_release_asset={"name": wheel.name, "sha256": wheel_digest},
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
    macro_run = "actions/runs/1237/attempts/2"
    macro_jobs = f"{macro_run}/jobs?per_page=20&page=1"
    transport_run = "actions/runs/1238/attempts/2"
    transport_jobs = f"{transport_run}/jobs?per_page=20&page=1"
    server_run = "actions/runs/1239/attempts/2"
    server_jobs = f"{server_run}/jobs?per_page=20&page=1"
    professional_run = "actions/runs/1240/attempts/2"
    professional_jobs = f"{professional_run}/jobs?per_page=20&page=1"
    smartcard_run = "actions/runs/1241/attempts/2"
    smartcard_jobs = f"{smartcard_run}/jobs?per_page=20&page=1"
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
            "actor": {"login": "release-operator", "id": 20},
            "triggering_actor": {"login": "qualification-operator", "id": 21},
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
            "user": {"login": "release-reviewer", "id": 22},
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
    responses[macro_run] = {**responses[run], "id": 1237, "path": release_parity.MACRO_WORKFLOW}
    responses[macro_jobs] = {
        "total_count": 1, "jobs": [{**responses[jobs]["jobs"][0], "name": release_parity.MACRO_JOB, "run_id": 1237}],
    }
    responses[transport_run] = {**responses[run], "id": 1238, "path": release_parity.TRANSPORT_WORKFLOW}
    responses[transport_jobs] = {
        "total_count": 1, "jobs": [{
            **responses[jobs]["jobs"][0], "name": release_parity.TRANSPORT_JOB, "run_id": 1238,
            "labels": ["self-hosted", "Linux", "X64", "transport-evidence"],
        }],
    }
    responses[server_run] = {**responses[run], "id": 1239, "path": release_parity.SERVER_WORKFLOW}
    responses[server_jobs] = {
        "total_count": 1, "jobs": [{
            **responses[jobs]["jobs"][0], "name": release_parity.SERVER_JOB, "run_id": 1239,
            "labels": ["ubuntu-24.04"],
        }],
    }
    responses[professional_run] = {**responses[run], "id": 1240, "path": release_parity.PROFESSIONAL_WORKFLOW}
    responses[professional_jobs] = {
        "total_count": 3, "jobs": [
            {**responses[jobs]["jobs"][0], "id": index, "run_id": 1240, "name": name, "labels": [runner]}
            for index, (name, runner) in enumerate([
                (release_parity.PROFESSIONAL_BUILD_JOB, "windows-latest"),
                (release_parity.PROFESSIONAL_POLICY_JOB, "ubuntu-24.04"),
                (release_parity.PROFESSIONAL_JOB, "windows-latest"),
            ], 1)
        ],
    }
    responses[smartcard_run] = {**responses[run], "id": 1241, "path": release_parity.SMARTCARD_WORKFLOW}
    responses[smartcard_jobs] = {
        "total_count": 1,
        "jobs": [{
            **responses[jobs]["jobs"][0], "name": release_parity.SMARTCARD_JOB, "run_id": 1241,
            "labels": ["self-hosted", "Linux", "X64", "smartcard-evidence"],
        }],
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
    server_payload_calls = []
    monkeypatch.setattr(
        release_parity, "verify_packaged_debian_server_evidence",
        lambda *values: server_payload_calls.append(values),
    )
    mobapt_payload_calls = []
    monkeypatch.setattr(
        release_parity, "verify_packaged_mobapt_review",
        lambda package, tag, digest, *, capture_root: mobapt_payload_calls.append((package, tag, digest, capture_root)),
    )
    x11_payload_calls = []

    def verify_x11_payload(package, root, target, *, expected_xvfb_sha256):
        x11_payload_calls.append((package, root, target, expected_xvfb_sha256))

    monkeypatch.setattr(release_parity, "verify_packaged_debian_x11_evidence", verify_x11_payload)
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
        args=args, wheel=wheel, records=records, responses=responses,
        on_main=on_main, run=run, jobs=jobs, x11_run=x11_run, x11_jobs=x11_jobs,
        editor_run=editor_run, editor_jobs=editor_jobs,
        macro_run=macro_run, macro_jobs=macro_jobs,
        transport_run=transport_run, transport_jobs=transport_jobs,
        server_run=server_run, server_jobs=server_jobs,
        professional_run=professional_run, professional_jobs=professional_jobs,
        smartcard_run=smartcard_run, smartcard_jobs=smartcard_jobs,
        hosted_archives=hosted_archives,
        review=review, validator_calls=validator_calls,
        delivery_calls=delivery_calls,
        server_payload_calls=server_payload_calls, x11_payload_calls=x11_payload_calls,
        mobapt_payload_calls=mobapt_payload_calls,
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


@pytest.fixture
def reviewed_parity_inputs(reviewed_release):
    root = reviewed_release.args["evidence_root"]
    (root / "candidates").mkdir()
    index_path = root / "candidate-reviews.json"
    index = {row["article_id"]: row["acceptance_review"] for row in reviewed_release.records}
    index_path.write_text(json.dumps(index), encoding="utf-8")
    for name, archive in reviewed_release.hosted_archives.items():
        (root / "candidates" / f"{name}.json").write_text(json.dumps(archive.candidate), encoding="utf-8")
    return reviewed_release


def make_staged_parity_archives(assets_dir: Path, tag: str, fault: str) -> list[dict]:
    groups = candidate_inventory.expected_candidate_archive_files(tag)
    staged_assets = {path.name for path in assets_dir.iterdir()}
    payloads, checksums = {}, {}
    for owner, files in groups.items():
        manifest, = (name for name in files if name.endswith("-manifest.json"))
        checksum, = (name for name in files if name.endswith("-SHA256SUMS.txt"))
        payload = {}
        for name in sorted(files - {manifest, checksum}):
            payload[name] = (assets_dir / name).read_bytes() if name in staged_assets else name.encode()
        rows = [
            {"file": name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in payload.items()
        ]
        payload[manifest] = json.dumps({"artifacts": rows} if owner == "release-source-python" else rows).encode()
        payload[checksum] = "".join(
            f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in payload.items()
        ).encode()
        payloads[owner], checksums[owner] = payload, checksum
    source, linux = "release-source-python", "release-linux-native-x86_64"
    if fault == "current-swapped-checksums":
        first, second = payloads[source], payloads[linux]
        left, right = checksums[source], checksums[linux]
        first[left], second[right] = second[right], first[left]

    records = []
    for owner, payload in payloads.items():
        files = []
        for name, data in payload.items():
            files.append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            if (
                groups[owner] & staged_assets and name.endswith(("-manifest.json", "-SHA256SUMS.txt"))
                and not (fault == "current-missing-index" and name == checksums[source])
            ):
                (assets_dir / name).write_bytes(data)
        records.append({"name": owner, "files": files})
    return records


@pytest.mark.parametrize(("fault", "detail"), [
    ("none", ""),
    ("current-valid-indexes", ""),
    ("current-frozen-xvfb", ""),
    ("current-missing-xvfb", "missing the frozen Xvfb archive and its rollback qualification"),
    ("current-missing-mobapt", "missing the frozen MobApt review and its rollback qualification"),
    ("current-swapped-checksums", "foreign, repeated or mismatched checksum"),
    ("current-missing-index", "missing sealed archive indexes"),
    ("missing-review", "must index all eight"),
    ("foreign-review", "review_url repository must match"),
    ("wrong-source", "candidate must match the exact release repository, tag, and source SHA"),
    ("already-accepted", "preflight requires the original workflow candidate"),
    ("different-sealed-inventory", "reviewed SHA-256 differs from the sealed inventory"),
    ("changed-staged-download", "SHA-256 differs from the staged candidate asset"),
    ("different-workflow", "its dedicated workflow dispatched at the release tag"),
    ("wrong-review-body", "does not explicitly accept this exact article evidence"),
    ("modified-capture", "reviewed article evidence SHA-256 differs"),
    ("colliding-inventory-filenames", "duplicate or case-colliding asset"),
    ("retain-workflow-artifacts", ""),
    ("corrupt-workflow-download", "workflow artifact ZIP digest differs from GitHub"),
    ("concurrent-retained-archive", "workflow artifact ZIP size differs from GitHub"),
])
def test_parity_preflight_uses_staged_bytes_original_archives_and_live_reviews(
    reviewed_parity_inputs, monkeypatch, capsys, fault, detail,
):
    reviewed_release = reviewed_parity_inputs
    args = reviewed_release.args
    root = args["evidence_root"]
    article = "ssh-browser-26-4-smartcard"
    index_path = root / "candidate-reviews.json"
    index = json.loads(index_path.read_bytes())
    if fault == "missing-review":
        index.pop(article)
    if fault == "foreign-review":
        index[article]["review_url"] = index[article]["review_url"].replace("example/", "foreign/")
    index_path.write_text(json.dumps(index), encoding="utf-8")
    if fault in ("wrong-source", "already-accepted"):
        path = root / "candidates" / f"{article}.json"
        candidate = json.loads(path.read_bytes())
        if fault == "wrong-source":
            candidate["validation_summary"]["summary"]["source_head_sha"] = "a" * 40
        else:
            candidate["release_asset_bytes"] = {"verified": True}
        path.write_text(json.dumps(candidate), encoding="utf-8")
    files = [
        {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in args["assets_dir"].iterdir()
    ]
    if fault == "different-sealed-inventory":
        next(row for row in files if row["path"] == reviewed_release.wheel.name)["sha256"] = "e" * 64
    if fault == "colliding-inventory-filenames":
        files.append({"path": files[0]["path"].upper(), "sha256": files[0]["sha256"]})
    if fault == "changed-staged-download":
        reviewed_release.wheel.write_bytes(b"changed staged wheel bytes")
    if fault == "different-workflow":
        reviewed_release.responses[reviewed_release.smartcard_run]["path"] = ".github/workflows/ci.yml"
    if fault == "wrong-review-body":
        reviewed_release.responses[reviewed_release.review]["body"] = "Reviewed another candidate."
    if fault == "modified-capture":
        (root / article / "evidence.json").write_bytes(b"modified capture")

    retain = fault in {"retain-workflow-artifacts", "corrupt-workflow-download", "concurrent-retained-archive"}
    downloaded = {}
    archives = {}
    concurrent_bytes = b"other writer's bytes"
    if retain:
        for archive in reviewed_release.hosted_archives.values():
            if fault == "retain-workflow-artifacts" or archive is reviewed_release.hosted_archives[article]:
                archives[archive.metadata["id"]] = (archive, archive.path.read_bytes())
                archive.path.unlink()
        if fault == "retain-workflow-artifacts":
            (root / "workflow-artifacts").rmdir()

        def download_archive(repository, artifact_id, destination, size):
            archive, data = archives[artifact_id]
            assert repository == args["repository"] and size == len(data)
            assert not archive.path.exists()
            downloaded[artifact_id] = data
            if fault == "concurrent-retained-archive":
                archive.path.write_bytes(concurrent_bytes)
            destination.write_bytes(bytes([data[0] ^ 1]) + data[1:] if fault == "corrupt-workflow-download" else data)

        monkeypatch.setattr(release_parity, "download_workflow_archive", download_archive)

    seen = []
    monkeypatch.setenv("GH_TOKEN", "fixture-token")
    monkeypatch.setattr(candidate_parity, "GitHubClient", lambda *_args, **_kwargs: "fixture-client")
    monkeypatch.setattr(release_parity, "load_registry", lambda *_args: pytest.fail("preflight used an accepted registry"))

    def read_attested(client, repository, directory, tag, sha, pointer):
        assert (client, repository, tag, sha) == ("fixture-client", args["repository"], args["tag"], args["release_sha"])
        assert directory.is_dir() and pointer.run_id == 31 and pointer.artifact_id == 32
        assert pointer.archive_digest == "sha256:" + "7" * 64
        seen.append(pointer)
        if fault in {"current-frozen-xvfb", "current-missing-xvfb", "current-missing-mobapt"}:
            inventory = {"schema_version": candidate_parity.MIN_XVFB_INVENTORY_SCHEMA}
            if fault != "current-missing-xvfb":
                inventory["debian_xvfb_sha256"] = "f" * 64
            if fault != "current-missing-mobapt":
                inventory["debian_mobapt_review_sha256"] = "e" * 64
            return make_staged_parity_archives(args["assets_dir"], tag, fault), inventory
        if fault.startswith("current-"):
            return make_staged_parity_archives(args["assets_dir"], tag, fault), {
                "schema_version": candidate_inventory.ARCHIVE_FILE_SCOPE_SCHEMA_VERSION,
            }
        return [{"files": files}], {"schema_version": candidate_inventory.LEGACY_SCHEMA_VERSION}

    monkeypatch.setattr(candidate_parity, "read_attested_inventory", read_attested)
    before = {path: path.read_bytes() for path in root.rglob("*.json")}
    status = candidate_parity.main([
        "--repository", args["repository"], "--tag", args["tag"], "--sha", args["release_sha"],
        "--candidate-inventory", "31 32 sha256:" + "7" * 64,
        "--assets-dir", str(args["assets_dir"]), "--evidence-root", str(root),
        "--professional-update-origin", args["professional_update_origins"][0],
        *(["--retain-workflow-artifacts"] if retain else []),
    ])
    output = capsys.readouterr()
    assert {path: path.read_bytes() for path in root.rglob("*.json")} == before
    if detail:
        assert status == 1 and detail in output.err and not output.out
        assert not reviewed_release.delivery_calls
        if fault.startswith("current-"):
            assert not reviewed_release.validator_calls
    else:
        assert status == 0 and "8/8 reviewed candidates verified" in output.out and not output.err
        assert len(seen) == 1 and set(reviewed_release.validator_calls) == set(release_parity.ARTICLE_SPECS)
        assert len(reviewed_release.delivery_calls) == 1 and reviewed_release.delivery_calls[0][1]["published"] is True
    if not detail:
        assert len(reviewed_release.x11_payload_calls) == 1
        assert reviewed_release.x11_payload_calls[0][-1] == ("f" * 64 if fault == "current-frozen-xvfb" else None)
        assert len(reviewed_release.mobapt_payload_calls) == 1
        assert reviewed_release.mobapt_payload_calls[0][2] == ("e" * 64 if fault == "current-frozen-xvfb" else None)
    if retain:
        assert downloaded == {artifact_id: data for artifact_id, (_, data) in archives.items()}
        assert not list((root / "workflow-artifacts").glob(".row-parity-artifact-*"))
    if fault == "corrupt-workflow-download":
        assert not reviewed_release.hosted_archives[article].path.exists()
    if fault == "concurrent-retained-archive":
        assert reviewed_release.hosted_archives[article].path.read_bytes() == concurrent_bytes
    if fault == "retain-workflow-artifacts":
        for archive, data in archives.values():
            assert archive.path.read_bytes() == data
            archive.metadata["expired"] = True
        monkeypatch.setattr(release_parity, "download_workflow_archive", lambda *_args: pytest.fail("unnecessary download"))
        audit_args = {name: value for name, value in args.items() if name != "registry_commit"}
        assert release_parity.audit_reviewed_records(reviewed_release.records, **audit_args) == []


@pytest.mark.parametrize(("fault", "detail"), [
    ("none", ""),
    ("provenance-failure", "immutable release provenance did not pass"),
    ("stale-review", "does not explicitly accept this exact article evidence"),
    ("changed-after-provenance", "SHA-256 differs from the downloaded release asset"),
    ("conflicting-review-hashes", "reviewed candidates disagree on the published SHA-256"),
    ("delivery-failure", "fixture delivery rejected"),
    ("output-inside-input", "--out must be a new file outside"),
    ("existing-output", "--out must be a new file outside"),
    ("concurrent-output", "already exists"),
])
def test_batch_finalization_writes_all_reviewed_records_only_after_live_checks(
    reviewed_parity_inputs, tmp_path, monkeypatch, capsys, fault, detail,
):
    reviewed = reviewed_parity_inputs
    args = reviewed.args
    root = args["evidence_root"]
    output = tmp_path / "acceptance" / "registry.json"
    if fault == "existing-output":
        output.parent.mkdir()
        output.write_bytes(b"other registry")
    if fault == "output-inside-input":
        output = args["assets_dir"] / "registry.json"
    if fault == "stale-review":
        reviewed.responses[reviewed.review]["body"] = "Reviewed different bytes."
    if fault == "conflicting-review-hashes":
        file = root / "candidates" / "ssh-browser-26-4-smartcard.json"
        candidate = json.loads(file.read_bytes())
        name = reviewed.wheel.name
        candidate["artifact_sha256"][name] = "9" * 64
        candidate["validation_summary"]["summary"]["tested_release_asset"]["sha256"] = "9" * 64
        file.write_text(json.dumps(candidate), encoding="utf-8")
    if fault == "delivery-failure":
        def reject_delivery(*_args, **_kwargs):
            raise ValueError("fixture delivery rejected")
        monkeypatch.setattr(release_parity, "verify_hosted_professional_update", reject_delivery)
    if fault == "concurrent-output":
        publisher, operation = (Path, "rename") if batch_finalize.os.name == "nt" else (batch_finalize.os, "link")
        publish = getattr(publisher, operation)

        def race(staged, target):
            assert target == output
            output.write_bytes(b"other registry")
            try:
                publish(staged, target)
            except FileExistsError as exc:
                raise FileExistsError("registry already exists") from exc

        monkeypatch.setattr(publisher, operation, race)

    checks = []

    def check_release(argv, *, reviewed_asset_hashes):
        assert not output.exists()
        assert argv == ["--assets-dir", str(args["assets_dir"]), "--repository", args["repository"],
                        "--tag", args["tag"], "--sha", args["release_sha"]]
        expected = {name: digest for row in reviewed.records for name, digest in row["artifact_sha256"].items()}
        assert reviewed_asset_hashes == expected
        checks.append(reviewed_asset_hashes)
        if fault == "changed-after-provenance":
            reviewed.wheel.write_bytes(b"substituted after release provenance")
        return int(fault == "provenance-failure")

    monkeypatch.setattr(batch_finalize, "verify_release_provenance", check_release)
    before = {path: path.read_bytes() for path in root.rglob("*.json")}
    result = batch_finalize.main([
        "--repository", args["repository"], "--tag", args["tag"], "--sha", args["release_sha"],
        "--assets-dir", str(args["assets_dir"]), "--evidence-root", str(root), "--out", str(output),
        "--professional-update-origin", args["professional_update_origins"][0],
    ])
    log = capsys.readouterr()
    assert {path: path.read_bytes() for path in root.rglob("*.json")} == before
    if detail:
        assert result == 1 and detail in log.err
        if fault in ("existing-output", "concurrent-output"):
            assert output.read_bytes() == b"other registry"
        else:
            assert not output.exists()
    else:
        assert result == 0 and "8/8 reviewed records written" in log.out and not log.err, log.err
        assert len(checks) == 1 and len(reviewed.delivery_calls) == 1
        registry = json.loads(output.read_bytes())
        checker = _load_checker()
        assert checker.check_mobaxterm_parity_evidence(registry=registry, require_complete=True) == []
        assert registry["accepted_evidence"] == sorted(reviewed.records, key=lambda row: row["article_id"])


@pytest.mark.parametrize(("failure", "expected"), [
    ("generic-workflow", "its dedicated workflow dispatched at the release tag"),
    ("missing-build", "Build the signed Professional installers) evidence attempt must contain"),
    ("wrong-policy-runner", "Capture the live Professional policy surfaces) evidence job did not report"),
])
def test_professional_certification_requires_the_exact_native_workflow_jobs(reviewed_release, failure, expected):
    attempt = reviewed_release.responses[reviewed_release.professional_run]
    jobs = reviewed_release.responses[reviewed_release.professional_jobs]["jobs"]
    if failure == "generic-workflow":
        attempt["path"] = ".github/workflows/ci.yml"
    if failure == "missing-build":
        jobs[0]["conclusion"] = "failure"
    if failure == "wrong-policy-runner":
        jobs[1]["labels"] = ["ubuntu-22.04"]
    errors = release_parity.audit_release(**reviewed_release.args)
    assert len(errors) == 1 and errors[0].startswith("professional-deployment ") and expected in errors[0]
    assert reviewed_release.delivery_calls == []


def test_linux_server_certification_requires_the_reviewed_payload_in_the_release_debian_package(
    reviewed_release, monkeypatch,
) -> None:
    assert release_parity.audit_release(**reviewed_release.args) == []
    package, root, target = reviewed_release.server_payload_calls[0]
    assert package.name == "remote-ops-workspace-v1.0.2-linux-amd64.deb"
    assert root.name == "embedded-server-suite"
    assert target == "linux-x86_64"

    def reject_unshipped_runtime(*_args):
        raise ValueError("reviewed daemon differs from published Debian payload")

    monkeypatch.setattr(release_parity, "verify_packaged_debian_server_evidence", reject_unshipped_runtime)
    assert release_parity.audit_release(**reviewed_release.args) == [
        "embedded-server-suite reviewed daemon differs from published Debian payload"
    ]


def test_x11_certification_refuses_a_different_runtime_in_the_published_package(reviewed_release, monkeypatch):
    def reject_payload(*args, **requirements):
        package, root, target = args
        assert package.name == "remote-ops-workspace-v1.0.2-linux-amd64.deb"
        assert root.name == "embedded-x-server" and target == "linux-x86_64"
        assert requirements == {"expected_xvfb_sha256": None}
        raise ValueError("reviewed X11 runtime differs from the Debian package payload")

    monkeypatch.setattr(release_parity, "verify_packaged_debian_x11_evidence", reject_payload)
    assert release_parity.audit_release(**reviewed_release.args) == [
        "embedded-x-server reviewed X11 runtime differs from the Debian package payload"
    ]


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


def test_mobapt_certification_refuses_bytes_not_shipped_in_the_published_package(reviewed_release, monkeypatch):
    def reject_payload(package, tag, digest, *, capture_root):
        assert package.name == "remote-ops-workspace-v1.0.2-linux-amd64.deb" and tag == "v1.0.2"
        assert digest is None and capture_root.name == "mobapt-unix-runtime"
        raise ValueError("reviewed MobApt cache differs from the Debian package payload")

    monkeypatch.setattr(release_parity, "verify_packaged_mobapt_review", reject_payload)
    assert release_parity.audit_release(**reviewed_release.args) == [
        "mobapt-unix-runtime reviewed MobApt cache differs from the Debian package payload"
    ]


def test_mobapt_certification_requires_the_successful_qualification_job(reviewed_release) -> None:
    reviewed_release.responses[reviewed_release.jobs]["jobs"][0]["name"] = "An unrelated successful job"

    assert release_parity.audit_release(**reviewed_release.args) == [
        "mobapt-unix-runtime MobApt evidence attempt must contain one successful qualification job"
    ]


@pytest.mark.parametrize(("failure", "message"), [
    ("generic-workflow", "its dedicated workflow dispatched at the release tag"),
    ("wrong-runner", "did not report the approved native runner labels"),
    ("changed-archive", "ZIP digest differs from GitHub"),
])
def test_smartcard_certification_binds_the_hardware_lab_and_archive(reviewed_release, failure, message):
    article = "ssh-browser-26-4-smartcard"
    if failure == "generic-workflow":
        reviewed_release.responses[reviewed_release.smartcard_run]["path"] = ".github/workflows/ci.yml"
    elif failure == "wrong-runner":
        reviewed_release.responses[reviewed_release.smartcard_jobs]["jobs"][0]["labels"].remove("smartcard-evidence")
    else:
        reviewed_release.hosted_archives[article].metadata["digest"] = "sha256:" + "9" * 64
    errors = release_parity.audit_release(**reviewed_release.args)
    assert len(errors) == 1 and errors[0].startswith(f"{article} ") and message in errors[0]


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


def test_debian_server_certification_binds_the_hosted_lab_attempt_and_archive(reviewed_release) -> None:
    article = "embedded-server-suite"
    attempt = reviewed_release.responses[reviewed_release.server_run]
    job = reviewed_release.responses[reviewed_release.server_jobs]["jobs"][0]
    attempt["path"] = release_parity.X11_WORKFLOW
    assert release_parity.audit_release(**reviewed_release.args) == [
        f"{article} Embedded servers evidence must come from its dedicated workflow dispatched at the release tag"
    ]
    attempt["path"] = release_parity.SERVER_WORKFLOW
    job["labels"] = ["self-hosted", "Linux", "X64", "server-evidence"]
    assert release_parity.audit_release(**reviewed_release.args) == [
        f"{article} Embedded servers evidence job did not report the approved native runner labels"
    ]
    job["labels"] = ["ubuntu-24.04"]
    archive = reviewed_release.hosted_archives[article]
    archive.metadata["expired"] = True
    archive.path.unlink()
    assert release_parity.audit_release(**reviewed_release.args) == [
        f"{article} GitHub workflow artifact expired; retain its original ZIP at "
        "workflow-artifacts/embedded-server-evidence-1239-2.zip"
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


def test_macro_certification_requires_its_dedicated_workflow(reviewed_release) -> None:
    reviewed_release.responses[reviewed_release.macro_run]["path"] = release_parity.EDITOR_WORKFLOW
    assert release_parity.audit_release(**reviewed_release.args) == [
        "macro-recorder Macro replay evidence must come from its dedicated workflow dispatched at the release tag"
    ]


def test_transport_certification_requires_the_dedicated_tag_attempt(reviewed_release) -> None:
    reviewed_release.responses[reviewed_release.transport_run]["path"] = release_parity.MACRO_WORKFLOW
    assert release_parity.audit_release(**reviewed_release.args) == [
        "shared-authenticated-transport-terminal-grid Terminal grid evidence must come "
        "from its dedicated workflow dispatched at the release tag"
    ]


def test_transport_certification_requires_the_native_runner_labels(reviewed_release) -> None:
    job = reviewed_release.responses[reviewed_release.transport_jobs]["jobs"][0]
    job["labels"] = ["ubuntu-24.04", "transport-evidence"]
    assert release_parity.audit_release(**reviewed_release.args) == [
        "shared-authenticated-transport-terminal-grid Terminal grid evidence job did not "
        "report the approved native runner labels"
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
    assert not archive.path.exists()


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
    reviewed_release.wheel.write_bytes(b"changed download")

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


@pytest.mark.parametrize("actor_field", ["actor", "triggering_actor"])
def test_certification_requires_a_reviewer_independent_of_each_evidence_attempt(
    reviewed_release, actor_field,
) -> None:
    run = reviewed_release.responses[reviewed_release.run]
    reviewer = reviewed_release.responses[reviewed_release.review]["user"]
    run[actor_field] = {"login": "prior-reviewer-login", "id": reviewer["id"]}

    errors = release_parity.audit_release(**reviewed_release.args)

    assert errors == [
        "mobapt-unix-runtime GitHub reviewer must be independent of the workflow dispatcher and rerun initiator"
    ]
    assert reviewed_release.delivery_calls == []


@pytest.mark.parametrize(("response", "field", "value", "expected"), [
    ("run", "actor", None, "must identify its actor account"),
    ("run", "triggering_actor", {"id": True}, "must identify its triggering_actor account"),
    ("review", "user", {"login": "release-reviewer"}, "review identity differs"),
])
def test_certification_requires_account_ids_to_establish_independent_review(
    reviewed_release, response, field, value, expected,
) -> None:
    reviewed_release.responses[getattr(reviewed_release, response)][field] = value

    errors = release_parity.audit_release(**reviewed_release.args)

    assert len(errors) == (1 if response == "run" else len(reviewed_release.records))
    assert all(expected in error for error in errors)
    assert reviewed_release.delivery_calls == []


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("completed_at", "2026-08-23T12:35:00Z", "review predates completion"),
    ("completed_at", None, "missing a valid completion timestamp"),
    ("run_attempt", 1, "job does not match the completed evidence attempt"),
])
def test_certification_binds_review_time_to_completed_attempt_jobs(
    reviewed_release, field, value, expected,
) -> None:
    for jobs in (reviewed_release.jobs, reviewed_release.x11_jobs, reviewed_release.editor_jobs,
                 reviewed_release.macro_jobs, reviewed_release.transport_jobs, reviewed_release.server_jobs,
                 reviewed_release.professional_jobs, reviewed_release.smartcard_jobs):
        reviewed_release.responses[jobs]["jobs"][0][field] = value

    errors = release_parity.audit_release(**reviewed_release.args)

    assert len(errors) == len(reviewed_release.records)
    assert all(expected in error for error in errors)


@pytest.mark.parametrize(("field", "wrong_value", "expected_error"), [
    (None, None, None),
    ("repository", "other/remote-ops-workspace", "repository"),
    ("head_sha", "a" * 40, "head_sha"),
    ("tag_source_head_sha", "a" * 40, "tag_source_head_sha"),
    ("workflow_run_url", "https://github.com/example/remote-ops-workspace/actions/runs/777", "workflow_run_url"),
    ("run_attempt", 3, "run_attempt"),
])
def test_finalizer_prints_review_line_only_for_exact_capture(
    reviewed_release, tmp_path, capsys, field, wrong_value, expected_error,
) -> None:
    record = reviewed_release.records[0]
    candidate = {key: value for key, value in record.items()
                 if key not in {"release_source", "acceptance_review", "release_asset_bytes"}}
    candidate["status"] = "candidate"
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    source = dict(record["release_source"])
    if field:
        source[field] = wrong_value

    result = _load_finalizer().main([
        "--candidate-record", str(candidate_path), "--repository", source["repository"],
        "--source-head-sha", source["head_sha"], "--tag-source-head-sha", source["tag_source_head_sha"],
        "--workflow-run-url", source["workflow_run_url"], "--run-attempt", str(source["run_attempt"]),
        "--print-review-line",
    ])
    output = capsys.readouterr()
    if expected_error:
        assert result == 1
        assert output.out == ""
        assert expected_error in output.err
    else:
        assert result == 0
        assert output.out == release_parity.review_acceptance_line(record) + "\n"
        assert output.err == ""


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
