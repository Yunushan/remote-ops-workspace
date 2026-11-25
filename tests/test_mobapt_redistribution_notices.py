from __future__ import annotations

import hashlib
import io
import json
import tarfile

import pytest

from scripts import check_release_license_compliance as compliance
from scripts.debian_server_notices import (
    MOBAPT_ASSEMBLY,
    MOBAPT_CACHE_DIR,
    MOBAPT_NOTICE_DIR,
    MOBAPT_REVIEW,
    observe_mobapt_notices,
)

TAG = "v1.0.28"


def package_payload(*, change: str = "") -> io.BytesIO:
    assembly = b"assembly"
    notice = b"Debian license notice"
    path = MOBAPT_NOTICE_DIR / "bash/copyright"
    data = {
        MOBAPT_CACHE_DIR / MOBAPT_ASSEMBLY: assembly,
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
