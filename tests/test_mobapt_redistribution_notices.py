from __future__ import annotations

import hashlib
import io
import json
import tarfile

import pytest

from scripts import check_release_license_compliance as compliance
from scripts import release_candidate_inventory as inventory
from scripts import stage_debian_mobapt_cache as mobapt
from scripts.debian_server_notices import (
    MOBAPT_ASSEMBLY,
    MOBAPT_CACHE_DIR,
    MOBAPT_NOTICE_DIR,
    MOBAPT_REVIEW,
    observe_mobapt_notices,
)

TAG = "v1.0.28"


def package_payload(*, change: str = "") -> io.BytesIO:
    binary, cached = b"reviewed Bash binary", b"reviewed tree archive"
    rows = [{
        "name": "tree", "version": "2.2.1-1", "archive": "packages/tree.deb",
        "sha256": hashlib.sha256(cached).hexdigest(), "source": "supplied", "synthetic": False,
    }]
    manifest = json.dumps({
        "packages": rows, "runtime": {"binaries": [{
            "path": "bin/bash", "sha256": hashlib.sha256(binary).hexdigest(),
            "source": "supplied", "shim": False,
        }]},
    }).encode()
    index = json.dumps({"schema": "row.mobapt.package-index.v1", "packages": rows,
                        "runtime": {"release_target": "linux-x86_64"}}).encode()
    assembly = json.dumps({
        "release_target": "linux-x86_64",
        "runtime": {"manifest": "mobapt-runtime.json", "manifest_sha256": hashlib.sha256(manifest).hexdigest()},
        "package_cache": {"index": "packages/index.json", "index_sha256": hashlib.sha256(index).hexdigest(),
                          "packages": rows},
    }).encode()
    notice = b"Debian license notice"
    path = MOBAPT_NOTICE_DIR / "bash/copyright"
    data = {
        MOBAPT_CACHE_DIR / MOBAPT_ASSEMBLY: assembly,
        MOBAPT_CACHE_DIR / "mobapt-runtime.json": manifest,
        MOBAPT_CACHE_DIR / "packages/index.json": index,
        MOBAPT_CACHE_DIR / "bin/bash": binary if change != "changed-binary" else b"changed binary",
        MOBAPT_CACHE_DIR / "packages/tree.deb": cached if change != "changed-archive" else b"changed archive",
        MOBAPT_NOTICE_DIR / MOBAPT_REVIEW: json.dumps({
            "release_tag": "v1.0.27" if change == "wrong-tag" else TAG,
            "assembly_sha256": hashlib.sha256(assembly).hexdigest(),
            "debian_inputs": {"bash": {"version": "5.2.37-2+b5"}},
            "notices": {"bash.copyright": hashlib.sha256(notice).hexdigest()},
        }).encode(),
        path: b"changed notice" if change == "changed" else notice,
    }
    if change == "missing-notice":
        del data[path]
    if change == "missing-review":
        del data[MOBAPT_NOTICE_DIR / MOBAPT_REVIEW]
        del data[path]
    if change == "wrong-assembly":
        data[MOBAPT_CACHE_DIR / MOBAPT_ASSEMBLY] = b"another assembly"
    if change == "missing-index":
        del data[MOBAPT_CACHE_DIR / "packages/index.json"]
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        for name, raw in data.items():
            entry = tarfile.TarInfo("./" + name.as_posix())
            entry.size = len(raw)
            if change == "linked" and name == path:
                entry.type = tarfile.SYMTYPE
                entry.linkname = "/tmp/fixture"
                archive.addfile(entry)
            else:
                archive.addfile(entry, io.BytesIO(raw))
                if change == "duplicate" and name == path:
                    archive.addfile(entry, io.BytesIO(raw))
    payload.seek(0)
    return payload


@pytest.mark.parametrize(
    ("change", "error"),
    [("missing-review", "requires one packaged file"), ("missing-notice", "requires one packaged file"),
     ("changed", "notice differs"), ("wrong-tag", "assembly binding"), ("wrong-assembly", "assembly binding"),
     ("linked", "invalid Debian MobApt file"), ("duplicate", "requires one packaged file")],
)
def test_packaged_mobapt_notices_fail_closed(change, error):
    with tarfile.open(fileobj=package_payload(change=change), mode="r:") as archive:
        with pytest.raises(ValueError, match=error):
            observe_mobapt_notices(archive, TAG)


def test_mobapt_notice_is_required_for_the_deb_only():
    with tarfile.open(fileobj=package_payload(), mode="r:") as archive:
        notices = observe_mobapt_notices(archive, TAG)
    notice = notices["bash"]
    assert notice.data == b"Debian license notice"
    assert notice.record["version"] == "5.2.37-2+b5"
    asset = "remote-ops-workspace-v1.0.28-linux-amd64.deb"
    rpm = "remote-ops-workspace-v1.0.28-linux-x86_64.rpm"
    errors = []
    assert not compliance.check_debian_notice_inventory({asset: {"bash": notice.record}}, {}, "review", errors)
    assert len(errors) == 1 and "requires the exact bundled Debian component and notice for bash" in errors[0]
    errors.clear()
    components = {"bash": {
        "scope": "bundled", "origin": "native-component", "version": notice.record["version"],
        "license_files": [{
            "path": notice.record["path"], "size_bytes": notice.record["size_bytes"],
            "sha256": notice.record["sha256"], "file": "notices/bash.copyright",
        }],
    }}
    scoped = compliance.check_debian_notice_inventory({asset: {"bash": notice.record}}, components, "review", errors)
    assert not errors
    required = compliance.required_artifact_license_records(components, {asset, rpm}, scoped, "review", errors)
    assert not errors and len(required[asset]) == 1 and required[rpm] == set()


@pytest.mark.parametrize(
    ("change", "error"),
    [("", ""), ("changed", "notice differs"), ("missing-notice", "requires one packaged file"),
     ("changed-binary", "bundled runtime executable differs"), ("changed-archive", "offline package archive differs"),
     ("missing-index", "expected one regular packaged MobApt member")],
)
def test_candidate_mobapt_sealing_checks_the_reviewed_payload(tmp_path, monkeypatch, change, error):
    package = tmp_path / "remote-ops-workspace-v1.0.28-linux-amd64.deb"
    package.write_bytes(b"fixture Debian package")
    payload = package_payload(change=change)
    with tarfile.open(fileobj=payload, mode="r:") as archive:
        member = archive.extractfile("./" + (MOBAPT_NOTICE_DIR / MOBAPT_REVIEW).as_posix())
        trusted_review = hashlib.sha256(member.read()).hexdigest()

    def dpkg(command, *, stdout, stderr, check, timeout):
        assert command == ["dpkg-deb", "--fsys-tarfile", str(package)]
        assert check and timeout > 0
        stdout.write(payload.getvalue())

    monkeypatch.setattr(mobapt.subprocess, "run", dpkg)
    receipt = {"candidate_has_mobapt_cache": True}
    if error:
        with pytest.raises(ValueError, match=error):
            inventory.verify_candidate_mobapt(package, receipt, TAG, trusted_review)
    else:
        inventory.verify_candidate_mobapt(package, receipt, TAG, trusted_review)
