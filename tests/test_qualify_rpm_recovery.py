from pathlib import Path

import pytest

from scripts import qualify_rpm_recovery as qualification

PACKAGE_SHA = "a" * 64
LAUNCHER_SHA = "b" * 64
HEADER = "remote-ops-workspace\t0\t1.0.27\t1.fc44\tx86_64\t8"
FILE = f"/usr/bin/row\t{LAUNCHER_SHA}"


def test_parse_identity_binds_launcher_to_header_and_artifact():
    assert qualification.parse_identity(
        f"{HEADER}\n/usr/share/doc/example\t{'c' * 64}\n{FILE}\n",
        PACKAGE_SHA,
    ) == qualification.RPMIdentity("1.0.27", "1.fc44", "x86_64", PACKAGE_SHA, LAUNCHER_SHA)


@pytest.mark.parametrize(
    "header",
    [
        HEADER.replace("x86_64", "aarch64"),
        HEADER.replace("\t0\t", "\t1\t"),
        HEADER.replace("\t8", "\t1"),
        HEADER.replace("1.0.27", "1.0.28-preview"),
        HEADER.replace("remote-ops-workspace", "some-other-package"),
    ],
)
def test_parse_identity_rejects_wrong_runtime_coordinates(header):
    with pytest.raises(ValueError, match="Unexpected RPM header"):
        qualification.parse_identity(f"{header}\n{FILE}\n", PACKAGE_SHA)


@pytest.mark.parametrize("files", ["", FILE + "\n" + FILE, "/usr/bin/row\tnot-a-sha256"])
def test_parse_identity_rejects_missing_ambiguous_or_invalid_launcher_digest(files):
    with pytest.raises(ValueError, match="Missing or ambiguous"):
        qualification.parse_identity(f"{HEADER}\n{files}\n", PACKAGE_SHA)


def test_package_digest_mismatch_is_rejected_before_rpm(tmp_path: Path, monkeypatch):
    path = tmp_path / "remote-ops-workspace-v1.0.27-linux-x86_64.rpm"
    path.write_bytes(b"not the expected RPM")

    def unexpected_query(*_args, **_kwargs):
        pytest.fail("RPM should never receive bytes that fail the SHA-256 check")

    monkeypatch.setattr(qualification, "checked", unexpected_query)
    with pytest.raises(ValueError, match="expected SHA-256"):
        qualification.read_package(path, PACKAGE_SHA)
