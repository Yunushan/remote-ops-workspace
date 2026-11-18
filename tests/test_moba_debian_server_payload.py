from __future__ import annotations

import io
import json
import struct
import tarfile
from pathlib import Path, PurePosixPath

import pytest

from scripts import moba_debian_server_payload as payload

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
    document = {"schema": payload.SCHEMA, "release_target": TARGET, "system": "linux", "services": []}
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
    (root / payload.MANIFEST).write_text(json.dumps(document), encoding="utf-8")
    return root


@pytest.fixture
def staged_debian(tmp_path: Path, approved_bundle: Path) -> Path:
    package = tmp_path / "debian"
    launcher = package / payload.LAUNCHER
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(make_elf(b"the actual ROW launcher"))
    payload.stage_payload(approved_bundle, package, TARGET)
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
                info.mode, info.size = 0o755, len(content)
                archive.addfile(info, io.BytesIO(content))
    return data.getvalue()


def test_debian_staging_includes_six_approved_daemons_and_both_row_runtime_roles(staged_debian: Path) -> None:
    document, digests = payload.server_payload(staged_debian / payload.PAYLOAD, TARGET)
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
