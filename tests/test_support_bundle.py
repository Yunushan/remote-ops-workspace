import json
import zipfile
from datetime import datetime

import pytest

from remote_ops_workspace import launcher
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
                        "options": {"proxy_jump": "bastion.customer.example", "api_token": "secret-token"},
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
                        "options": {"proxy_jump": "bastion.customer.example", "password": "secret"},
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
    assert summary["profiles"][0]["sensitive_option_key_count"] == 1
    assert summary["group_defaults"]["groups"][0]["option_keys"] == ["proxy_jump"]
    assert summary["group_defaults"]["groups"][0]["sensitive_option_key_count"] == 1
    assert summary["profiles"][0]["tunnel_modes"] == ["dynamic"]
    assert "router.customer.example" not in serialized
    assert "customer-router" not in serialized
    assert "admin" not in serialized
    assert "bastion.customer.example" not in serialized
    assert "prod/router-password" not in serialized
    assert "api_token" not in serialized
    assert "secret-token" not in serialized
    assert "password" not in serialized


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


def test_support_bundle_excludes_unreviewed_labels_and_keeps_builtin_diagnostics(monkeypatch, tmp_path) -> None:
    private = "fixture-customer.example"
    (tmp_path / "profiles.json").write_text(json.dumps({
        "version": private,
        "group_defaults": {private: {"options": {private: "fixture"}}},
        "profiles": [
            {"protocol": f"plugin-{private}", "options": {"proxy_jump": private, private: "fixture"},
             "url": "fixture-customer:opaque", "tunnels": [{"mode": private}, {"mode": "dynamic"}]},
            {"protocol": "ssh", "url": f"https://[{private}"},
        ],
    }), encoding="utf-8")
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    monkeypatch.setenv("ROW_ENABLE_PLUGINS", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(launcher, "load_plugin_registry", lambda: pytest.fail("support bundle loaded plugins"))

    assert support_bundle.main() == 0

    bundle, = tmp_path.glob("support-bundle-*.zip")
    with zipfile.ZipFile(bundle) as archive:
        report, summary = (
            json.loads(archive.read(name)) for name in ("doctor.json", "profiles.summary.json")
        )
    assert private not in json.dumps((report, summary))
    assert "fixture-customer" not in json.dumps(summary)
    assert "ssh" in report["executables"]
    assert summary["version"] is None
    assert summary["protocol_counts"] == {"<other>": 1, "ssh": 1}
    assert summary["profiles"][0]["option_keys"] == ["proxy_jump"]
    assert summary["profiles"][0]["unrecognized_option_key_count"] == 1
    assert summary["profiles"][0]["url_scheme"] == "<other>"
    assert summary["profiles"][0]["tunnel_modes"] == ["<other>", "dynamic"]
    assert summary["profiles"][1]["url_scheme"] == "https"
    assert summary["group_defaults"]["groups"][0]["unrecognized_option_key_count"] == 1


@pytest.mark.parametrize("profile_store", [None, "{broken-fixture", '["invalid-fixture"]'])
def test_support_bundle_keeps_doctor_available_without_a_readable_profile_store(
    monkeypatch, tmp_path, profile_store,
) -> None:
    if profile_store is not None:
        (tmp_path / "profiles.json").write_text(profile_store, encoding="utf-8")
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    assert support_bundle.main() == 0

    bundle, = tmp_path.glob("support-bundle-*.zip")
    with zipfile.ZipFile(bundle) as archive:
        assert "doctor.json" in archive.namelist()
        if profile_store is not None:
            assert json.loads(archive.read("profiles.summary.json")) == {
                "status": "unavailable", "raw_profiles_included": False,
            }
        else:
            assert archive.namelist() == ["doctor.json"]


def test_support_bundle_retries_use_distinct_files(monkeypatch, tmp_path, capsys) -> None:
    class FixedClock:
        @staticmethod
        def now(tz):
            return datetime(2026, 1, 1, tzinfo=tz)

    monkeypatch.setattr(support_bundle, "datetime", FixedClock)
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert support_bundle.main() == 0
    assert support_bundle.main() == 0

    paths = sorted(tmp_path.glob("support-bundle-20260101-000000-*.zip"))
    assert len(paths) == 2
    assert set(capsys.readouterr().out.splitlines()) == {str(path) for path in paths}
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            assert archive.namelist() == ["doctor.json"]


def test_support_bundle_removes_a_failed_archive(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    def fail_write(*_args, **_kwargs):
        raise OSError("fixture write failed")

    monkeypatch.setattr(zipfile.ZipFile, "writestr", fail_write)
    with pytest.raises(OSError, match="fixture write failed"):
        support_bundle.main()
    assert list(tmp_path.glob("support-bundle-*.zip")) == []
