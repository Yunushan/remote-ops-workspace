from __future__ import annotations

import gzip
import io
import json
import shutil
import struct
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from unittest.mock import Mock

import pytest

from scripts import moba_debian_server_payload as payload
from scripts import stage_debian_server_bundle as staging
from scripts.debian_server_notices import NOTICE_DIR, notice_path, read_verified_debian_notices

TARGET = "linux-x86_64"


def make_elf(contents: bytes) -> bytes:
    header = bytearray(64)
    header[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", header, 16, 3, 62, 1)
    struct.pack_into("<H", header, 52, 64)
    return bytes(header) + contents


@pytest.fixture
def approved_bundle(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    document = {
        "schema": payload.SCHEMA, "release_target": TARGET, "system": "linux",
        "services": [], "debian_notices": {},
    }
    for service in sorted(payload.EXTERNAL_SERVICES):
        relative = f"linux/{service}/bin/{service}d"
        executable = root / relative
        executable.parent.mkdir(parents=True)
        executable.write_bytes(make_elf(service.encode()))
        document["services"].append({
            "service": service,
            "runtime": {
                "source": "packaged", "bundled": True, "placeholder": False, "key": f"{service}d",
                "executable": relative, "sha256": payload.sha256_file(executable),
            },
        })
        notice = root / "notices" / f"{service}-daemon.copyright"
        notice.parent.mkdir(exist_ok=True)
        notice.write_bytes(f"distro notice for {service}\n".encode())
        document["debian_notices"][f"{service}-daemon"] = {
            "version": "1:2.4.0-1~deb13u1", "services": [service],
            "sha256": payload.sha256_file(notice), "size_bytes": notice.stat().st_size,
        }
    (root / payload.MANIFEST).write_text(json.dumps(document), encoding="utf-8")
    return root


@pytest.fixture
def staged_debian(tmp_path: Path, approved_bundle: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    package = tmp_path / "debian"
    launcher = package / payload.LAUNCHER
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(make_elf(b"the actual ROW launcher"))
    monkeypatch.setattr(payload, "debian_dependencies", lambda *_: ["libc6 (>= 2.38)", "libpam0g"])
    assert payload.stage_payload(approved_bundle, package, TARGET) == "libc6 (>= 2.38), libpam0g"
    return package


def make_tar(root: Path, *, substitute: str | None = None, link: Path | None = None) -> bytes:
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as archive:
        for path in sorted(root.rglob("*")):
            relative = PurePosixPath(path.relative_to(root).as_posix())
            info = tarfile.TarInfo("./" + relative.as_posix())
            if path == link:
                info.type, info.linkname = tarfile.SYMTYPE, "/tmp"
                archive.addfile(info)
            elif path.is_dir():
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                archive.addfile(info)
            else:
                content = path.read_bytes() + (b"changed" if relative.as_posix() == substitute else b"")
                info.mode = 0o644 if relative.is_relative_to(NOTICE_DIR) else 0o755
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
    return data.getvalue()


@pytest.fixture
def bundle_archive(tmp_path: Path, approved_bundle: Path) -> Path:
    archive = tmp_path / staging.ARCHIVE_NAME
    archive.write_bytes(gzip.compress(make_tar(approved_bundle)))
    return archive


def test_portable_bundle_stages_only_the_reviewed_bytes(
    approved_bundle: Path, bundle_archive: Path, tmp_path: Path,
) -> None:
    output = tmp_path / "staged"
    staging.stage_bundle(bundle_archive, payload.sha256_file(bundle_archive), TARGET, output)
    assert {
        file.relative_to(output): file.read_bytes() for file in output.rglob("*") if file.is_file()
    } == {
        file.relative_to(approved_bundle): file.read_bytes()
        for file in approved_bundle.rglob("*") if file.is_file()
    }
    with pytest.raises(ValueError, match="output already exists"):
        staging.stage_bundle(bundle_archive, payload.sha256_file(bundle_archive), TARGET, output)


@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        ("digest", "does not match the approved archive"),
        ("link", "must be a regular file"),
        ("extra", "outside the reviewed manifest"),
        ("notice", "differs from reviewed evidence"),
        ("architecture", "exact Linux target"),
    ],
)
def test_portable_bundle_rejects_unreviewed_content(
    approved_bundle: Path, bundle_archive: Path, tmp_path: Path, damage: str, reason: str,
) -> None:
    target = TARGET
    if damage == "link":
        linked = next((approved_bundle / "notices").iterdir())
        bundle_archive.write_bytes(gzip.compress(make_tar(approved_bundle, link=linked)))
    elif damage == "extra":
        (approved_bundle / "notices" / "extra.copyright").write_bytes(b"extra")
        bundle_archive.write_bytes(gzip.compress(make_tar(approved_bundle)))
    elif damage == "notice":
        notice = next((approved_bundle / "notices").iterdir())
        bundle_archive.write_bytes(gzip.compress(make_tar(approved_bundle, substitute=f"notices/{notice.name}")))
    elif damage == "architecture":
        target = "linux-arm64"
    digest = "0" * 64 if damage == "digest" else payload.sha256_file(bundle_archive)
    output = tmp_path / "stage"
    with pytest.raises(ValueError, match=reason):
        staging.stage_bundle(bundle_archive, digest, target, output)
    assert not output.exists()


@pytest.mark.parametrize("damage", [None, "expired", "digest", "entry"])
def test_actions_bundle_download_binds_zip_metadata_and_its_only_file(
    bundle_archive: Path, tmp_path: Path, damage: str | None,
) -> None:
    zipped = tmp_path / "source.zip"
    with zipfile.ZipFile(zipped, mode="w") as archive:
        archive.write(bundle_archive, "unexpected.tar.gz" if damage == "entry" else staging.ARCHIVE_NAME)
    digest = f"sha256:{payload.sha256_file(zipped)}"
    client = Mock(spec=staging.GitHubClient)
    client.json.return_value = {
        "id": 123, "expired": damage == "expired", "size_in_bytes": zipped.stat().st_size,
        "digest": "sha256:" + "0" * 64 if damage == "digest" else digest,
    }

    def download(endpoint: str, destination: Path, *, max_bytes: int) -> str:
        assert endpoint == "actions/artifacts/123/zip"
        assert max_bytes == zipped.stat().st_size
        shutil.copyfile(zipped, destination)
        return digest

    client.download.side_effect = download
    if damage is None:
        extracted = staging.download_bundle(client, 123, tmp_path)
        assert extracted.read_bytes() == bundle_archive.read_bytes()
    else:
        with pytest.raises(ValueError, match={
            "expired": "expired", "digest": "do not match GitHub", "entry": "contain only",
        }[damage]):
            staging.download_bundle(client, 123, tmp_path)
    client.json.assert_called_once_with("actions/artifacts/123")
    if damage == "expired":
        client.download.assert_not_called()


def test_debian_staging_includes_six_approved_daemons_and_both_row_runtime_roles(staged_debian: Path) -> None:
    document, digests = payload.server_payload(staged_debian / payload.PAYLOAD, TARGET)
    assert document["debian_depends"] == ["libc6 (>= 2.38)", "libpam0g"]
    assert {service["service"] for service in document["services"]} == payload.SERVICES
    launcher = payload.sha256_file(staged_debian / payload.LAUNCHER)
    assert digests["linux/http/bin/python"] == digests["linux/ftp/bin/pyftpdlib"] == launcher
    with tarfile.open(fileobj=io.BytesIO(make_tar(staged_debian))) as archive:
        payload.compare_payload_tar(archive, digests)


@pytest.mark.parametrize(
    ("relative", "detail"),
    [
        ("usr/bin/row", "must match the Debian ROW launcher"),
        ("usr/lib/remote-ops-workspace/servers/linux/tftp/bin/tftpd", "differs from reviewed evidence"),
    ],
)
def test_debian_audit_rejects_substituted_shipped_bytes(staged_debian: Path, relative: str, detail: str) -> None:
    _, digests = payload.server_payload(staged_debian / payload.PAYLOAD, TARGET)
    with tarfile.open(fileobj=io.BytesIO(make_tar(staged_debian, substitute=relative))) as archive:
        with pytest.raises(ValueError, match=detail):
            payload.compare_payload_tar(archive, digests)


def test_debian_audit_rejects_redirected_runtime_ancestors(staged_debian: Path) -> None:
    _, digests = payload.server_payload(staged_debian / payload.PAYLOAD, TARGET)
    linked = staged_debian / payload.PAYLOAD.parent
    with tarfile.open(fileobj=io.BytesIO(make_tar(staged_debian, link=linked))) as archive:
        with pytest.raises(ValueError, match="untrusted directory"):
            payload.compare_payload_tar(archive, digests)


def test_staging_refuses_wrong_architecture_and_tampered_daemons(approved_bundle: Path) -> None:
    with pytest.raises(ValueError, match="exact Linux target"):
        payload.server_payload(approved_bundle, "linux-arm64", payload.EXTERNAL_SERVICES)
    (approved_bundle / "linux/tftp/bin/tftpd").write_bytes(make_elf(b"wrong binary"))
    with pytest.raises(ValueError, match="differs from its manifest digest"):
        payload.server_payload(approved_bundle, TARGET, payload.EXTERNAL_SERVICES)


@pytest.fixture
def private_openssh_bundle(approved_bundle: Path) -> Path:
    manifest = approved_bundle / payload.MANIFEST
    record = json.loads(manifest.read_bytes())
    helpers = approved_bundle / payload.SERVER_OPENSSH_HELPER_DIR
    helpers.mkdir(parents=True)
    helper_reference = f"/{payload.PAYLOAD}/{payload.SERVER_OPENSSH_HELPER_DIR}/".encode()
    daemon = make_elf(helper_reference + b"sshd-session\0")
    for row in record["services"]:
        service = row["service"]
        if service in payload.OPENSSH_DAEMON_KEYS:
            runtime = row["runtime"]
            executable = f"linux/{service}/bin/sshd"
            installed = approved_bundle / executable
            installed.write_bytes(daemon)
            runtime.update(key=payload.OPENSSH_DAEMON_KEYS[service], executable=executable,
                           sha256=payload.sha256_file(installed))
    (helpers / "sshd-session").write_bytes(make_elf(helper_reference + b"sshd-auth\0"))
    (helpers / "sshd-auth").write_bytes(make_elf(b"package-owned auth"))
    record["openssh_helpers"] = {path.name: payload.sha256_file(path) for path in helpers.iterdir()}
    manifest.write_text(json.dumps(record), encoding="utf-8")
    return approved_bundle


def test_debian_stages_and_audits_both_private_openssh_helpers(
    private_openssh_bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "debian"
    launcher = package / payload.LAUNCHER
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(make_elf(b"launcher"))
    monkeypatch.setattr(payload, "debian_dependencies", lambda *_: ["libc6 (>= 2.38)", "libpam0g"])
    payload.stage_payload(private_openssh_bundle, package, TARGET)
    _, expected = payload.server_payload(package / payload.PAYLOAD, TARGET)
    helpers = {f"{payload.SERVER_OPENSSH_HELPER_DIR}/{name}" for name in ("sshd-session", "sshd-auth")}
    assert helpers <= expected.keys()
    with tarfile.open(fileobj=io.BytesIO(make_tar(package))) as archive:
        payload.compare_payload_tar(archive, expected)

    changed = (payload.PAYLOAD / payload.SERVER_OPENSSH_HELPER_DIR / "sshd-auth").as_posix()
    with tarfile.open(fileobj=io.BytesIO(make_tar(package, substitute=changed))) as archive:
        with pytest.raises(ValueError, match="differs from reviewed evidence"):
            payload.compare_payload_tar(archive, expected)
    (package / changed).unlink()
    with tarfile.open(fileobj=io.BytesIO(make_tar(package))) as archive:
        with pytest.raises(ValueError, match="missing the reviewed server payload members"):
            payload.compare_payload_tar(archive, expected)


@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        ("unrecorded", "helper files must be recorded"),
        ("differing-daemons", "SSH and SFTP must use the same OpenSSH daemon"),
        ("external-session", "sshd-session must reference the package-owned sshd-auth"),
        ("foreign-elf", "machine does not match"),
    ],
)
def test_debian_rejects_unbound_openssh_helpers(private_openssh_bundle: Path, damage: str, reason: str) -> None:
    root = private_openssh_bundle
    manifest = root / payload.MANIFEST
    record = json.loads(manifest.read_bytes())
    if damage == "unrecorded":
        del record["openssh_helpers"]
    elif damage == "differing-daemons":
        runtime = next(row["runtime"] for row in record["services"] if row["service"] == "sftp")
        path = root / runtime["executable"]
        path.write_bytes(path.read_bytes() + b"other build")
        runtime["sha256"] = payload.sha256_file(path)
    else:
        path = root / payload.SERVER_OPENSSH_HELPER_DIR / "sshd-session"
        changed = bytearray(path.read_bytes())
        if damage == "external-session":
            changed = bytearray(make_elf(b"/usr/lib/openssh/sshd-auth\0"))
        else:
            struct.pack_into("<H", changed, 18, 183)
        path.write_bytes(changed)
        record["openssh_helpers"][path.name] = payload.sha256_file(path)
    manifest.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(ValueError, match=reason):
        payload.server_payload(root, TARGET, payload.EXTERNAL_SERVICES)


def test_debian_archive_audit_checks_the_control_dependency_field(
    staged_debian: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "remote-ops-workspace-v1.0.28-linux-amd64.deb"
    manifest = staged_debian / payload.PAYLOAD / payload.MANIFEST
    contents = make_tar(staged_debian)
    monkeypatch.setattr(payload.subprocess, "run", lambda *_, stdout, **__: stdout.write(contents))
    monkeypatch.setattr(payload.subprocess, "check_output", lambda *_args, **_kwargs: "libc6 (>= 2.38),\n libpam0g\n")
    payload.verify_debian_payload(package, manifest, TARGET)

    monkeypatch.setattr(payload.subprocess, "check_output", lambda *_args, **_kwargs: "libc6 (>= 2.38)\n")
    with pytest.raises(ValueError, match="Depends differs from the reviewed server runtime dependencies"):
        payload.verify_debian_payload(package, manifest, TARGET)


def test_staging_refuses_changed_notice_attachments(approved_bundle: Path, tmp_path: Path) -> None:
    target = tmp_path / "unstaged"
    (approved_bundle / "notices/nfs-daemon.copyright").write_bytes(b"changed")
    with pytest.raises(ValueError, match="notice attachment differs from reviewed evidence"):
        payload.stage_payload(approved_bundle, target, TARGET)
    assert not target.exists()


@pytest.mark.parametrize(("change", "error"), [
    ("omitted", "missing services"),
    ("extra-service", "unique and external"),
    ("bad-name", "invalid Debian server notice record"),
])
def test_staging_requires_a_notice_for_each_external_service(
    approved_bundle: Path, tmp_path: Path, change: str, error: str,
) -> None:
    manifest = approved_bundle / payload.MANIFEST
    document = json.loads(manifest.read_bytes())
    records = document["debian_notices"]
    if change == "omitted":
        del records["nfs-daemon"]
    elif change == "extra-service":
        records["nfs-daemon"]["services"].append("http")
    else:
        records["../nfs-daemon"] = records.pop("nfs-daemon")
    manifest.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        payload.stage_payload(approved_bundle, tmp_path / "unstaged", TARGET)


def test_redistribution_reads_exact_installed_notice_bytes(
    staged_debian: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "remote-ops-workspace-v1.0.28-linux-amd64.deb"
    manifest = staged_debian / payload.PAYLOAD / payload.MANIFEST
    contents = make_tar(staged_debian)
    monkeypatch.setattr(payload.subprocess, "run", lambda *_, stdout, **__: stdout.write(contents))
    assert read_verified_debian_notices(archive, target=TARGET) == json.loads(manifest.read_bytes())["debian_notices"]

    path = staged_debian / notice_path("nfs-daemon")
    old = path.read_bytes()
    path.write_bytes(b"B" + old[1:])
    contents = make_tar(staged_debian)
    with pytest.raises(ValueError, match="notice differs from reviewed evidence"):
        read_verified_debian_notices(archive, target=TARGET)

    path.unlink()
    contents = make_tar(staged_debian)
    with pytest.raises(ValueError, match="missing reviewed server notices"):
        read_verified_debian_notices(archive, target=TARGET)


def test_legacy_archive_without_an_embedded_server_bundle_requires_no_daemon_notices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = tmp_path / "plain"
    launcher = stage / payload.LAUNCHER
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(b"fixture")
    contents = make_tar(stage)
    monkeypatch.setattr(payload.subprocess, "run", lambda *_, stdout, **__: stdout.write(contents))
    assert read_verified_debian_notices(tmp_path / "plain.deb", target=TARGET) == {}
