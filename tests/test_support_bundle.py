import json
import zipfile

from scripts import support_bundle


def test_profile_summary_excludes_raw_profile_identifiers(tmp_path) -> None:
    profiles = tmp_path / "profiles.json"
    profiles.write_text(
        json.dumps(
            {
                "version": 1,
                "group_defaults": {
                    "customer-prod": {
                        "username": "root",
                        "credential_ref": "prod/router-password",
                        "options": {"proxy_jump": "bastion.customer.example"},
                    }
                },
                "profiles": [
                    {
                        "name": "customer-router",
                        "protocol": "ssh",
                        "host": "router.customer.example",
                        "port": 2222,
                        "username": "admin",
                        "group": "customer-prod",
                        "tags": ["customer", "edge"],
                        "description": "Production edge router",
                        "identity_file": "/home/admin/.ssh/id_customer",
                        "credential_ref": "prod/router-password",
                        "options": {"proxy_jump": "bastion.customer.example"},
                        "tunnels": [{"mode": "dynamic", "local_port": 1080}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = support_bundle._profile_summary(profiles)
    serialized = json.dumps(summary)

    assert summary["raw_profiles_included"] is False
    assert summary["profile_count"] == 1
    assert summary["protocol_counts"] == {"ssh": 1}
    assert summary["profiles"][0]["option_keys"] == ["proxy_jump"]
    assert summary["profiles"][0]["tunnel_modes"] == ["dynamic"]
    assert "router.customer.example" not in serialized
    assert "customer-router" not in serialized
    assert "admin" not in serialized
    assert "bastion.customer.example" not in serialized
    assert "prod/router-password" not in serialized


def test_support_bundle_writes_sanitized_profiles_summary(monkeypatch, tmp_path) -> None:
    row_home = tmp_path / "row-home"
    row_home.mkdir()
    (row_home / "profiles.json").write_text(
        json.dumps({"version": 1, "profiles": [{"name": "edge", "protocol": "ssh", "host": "10.0.0.5"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("ROW_HOME", str(row_home))
    monkeypatch.chdir(tmp_path)

    assert support_bundle.main() == 0

    bundle = next(tmp_path.glob("support-bundle-*.zip"))
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        doctor = json.loads(archive.read("doctor.json").decode("utf-8"))
        summary_text = archive.read("profiles.summary.json").decode("utf-8")

    assert "profiles.redaction-required.json" not in names
    assert "profiles.summary.json" in names
    assert doctor["data_dir"] == "<redacted-data-dir>"
    assert doctor["raw_profiles_included"] is False
    assert "10.0.0.5" not in summary_text
    assert "edge" not in summary_text
