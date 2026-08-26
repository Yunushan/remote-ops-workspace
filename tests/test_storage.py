import json
from pathlib import Path

import pytest

import remote_ops_workspace.storage as storage_module
from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore


def test_profile_store_roundtrip(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    profile = Profile(name="lab", protocol="ssh", host="192.0.2.10")
    store.add(profile)
    assert store.get("lab").host == "192.0.2.10"
    assert len(store.load()) == 1


def test_no_examples_purges_only_unchanged_seeded_profiles(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.init(with_examples=True)

    edited = store.get("example-ssh")
    edited.host = "10.3.25.200"
    store.add(edited, replace=True)
    store.add(Profile(name="real-ops", protocol="ssh", host="10.3.25.201"))

    store.init(with_examples=False)

    names = {profile.name for profile in store.load(resolve=False)}
    assert names == {"example-ssh", "real-ops"}
    assert store.get("example-ssh").host == "10.3.25.200"


def test_profile_store_applies_group_defaults(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.set_group_defaults(
        "prod",
        {"username": "admin", "options": {"proxy_jump": "bastion"}},
        replace=True,
    )
    store.add(Profile(name="edge", protocol="ssh", host="192.0.2.10", group="prod"))
    profile = store.get("edge")
    assert profile.username == "admin"
    assert profile.options["proxy_jump"] == "bastion"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("[]", "profile store root must be a JSON object"),
        ('{"profiles": {}}', "profiles must be a JSON array"),
        ('{"profiles": [1]}', "profile at index 0 must be a JSON object"),
    ],
)
def test_profile_store_rejects_malformed_document(
    tmp_path: Path, payload: str, message: str
) -> None:
    path = tmp_path / "profiles.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        ProfileStore(path).load()


def test_profile_import_rejects_malformed_profile_rows(tmp_path: Path) -> None:
    path = tmp_path / "import.json"
    path.write_text('{"profiles": ["not-an-object"]}', encoding="utf-8")

    with pytest.raises(ValueError, match="profile at index 0 must be a JSON object"):
        ProfileStore(tmp_path / "profiles.json").import_from(path)


def test_profile_import_is_atomic_when_late_profile_validation_fails(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.set_group_defaults("prod", {"username": "before"}, replace=True)
    store.add(Profile(name="existing", protocol="ssh", host="192.0.2.10"))
    before = store.path.read_bytes()
    source = tmp_path / "import.json"
    source.write_text(
        json.dumps(
            {
                "profiles": [
                    {"name": "would-have-been-added", "protocol": "ssh", "host": "192.0.2.11"},
                    {"name": "invalid-late-row", "protocol": "ssh"},
                ],
                "group_defaults": {"prod": {"username": "must-not-persist"}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="profile at index 1 is invalid"):
        store.import_from(source, replace=True)

    assert store.path.read_bytes() == before
    assert [profile.name for profile in store.load(resolve=False)] == ["existing"]
    assert store.group_defaults()["prod"]["username"] == "before"


def test_profile_import_collision_does_not_partially_add_earlier_rows(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.add(Profile(name="existing", protocol="ssh", host="192.0.2.10"))
    before = store.path.read_bytes()
    source = tmp_path / "import.json"
    source.write_text(
        json.dumps(
            {
                "profiles": [
                    {"name": "new", "protocol": "ssh", "host": "192.0.2.11"},
                    {"name": "existing", "protocol": "ssh", "host": "192.0.2.12"},
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="profile already exists: existing"):
        store.import_from(source)

    assert store.path.read_bytes() == before
    assert [profile.name for profile in store.load(resolve=False)] == ["existing"]


def test_profile_import_rejects_duplicate_normalized_names_atomically(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.add(Profile(name="existing", protocol="ssh", host="192.0.2.10"))
    before = store.path.read_bytes()
    source = tmp_path / "import.json"
    source.write_text(
        json.dumps(
            {
                "profiles": [
                    {"name": "edge", "protocol": "ssh", "host": "192.0.2.11"},
                    {"name": " edge ", "protocol": "ssh", "host": "192.0.2.12"},
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate normalized profile names"):
        store.import_from(source, replace=True)

    assert store.path.read_bytes() == before


def test_profile_import_commits_profiles_and_defaults_together(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.add(Profile(name="existing", protocol="ssh", host="192.0.2.10"))
    store.add(Profile(name="untouched", protocol="ssh", host="192.0.2.20"))
    source = tmp_path / "import.json"
    source.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "name": "existing",
                        "protocol": "ssh",
                        "host": "192.0.2.11",
                        "group": "prod",
                    },
                    {
                        "name": "new",
                        "protocol": "ssh",
                        "host": "192.0.2.12",
                        "group": "prod",
                    },
                ],
                "group_defaults": {"prod": {"username": "operator"}},
            }
        ),
        encoding="utf-8",
    )

    assert store.import_from(source, replace=True) == 2
    assert {profile.name for profile in store.load(resolve=False)} == {
        "existing",
        "new",
        "untouched",
    }
    assert store.get("existing").host == "192.0.2.11"
    assert store.get("existing").username == "operator"
    assert store.get("new").username == "operator"
    assert store.get("untouched").host == "192.0.2.20"


def test_profile_import_reports_invalid_json_without_touching_store(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.add(Profile(name="existing", protocol="ssh", host="192.0.2.10"))
    before = store.path.read_bytes()
    source = tmp_path / "invalid.json"
    source.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="profile import is not valid JSON"):
        store.import_from(source)

    assert store.path.read_bytes() == before


def test_profile_store_export_remove_and_missing_paths(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.init(with_examples=False)
    store.init(with_examples=False)
    store.init(with_examples=True)
    store.init(with_examples=True, purge_examples=False)
    store.add(Profile(name="edge", protocol="ssh", host="192.0.2.10"))

    with pytest.raises(ValueError, match="already exists"):
        store.add(Profile(name="edge", protocol="ssh", host="192.0.2.11"))
    with pytest.raises(KeyError):
        store.get("missing")
    with pytest.raises(KeyError):
        store.remove("missing")

    exported = tmp_path / "export.json"
    store.export_to(exported)
    assert json.loads(exported.read_text(encoding="utf-8"))["profiles"][0]["name"] == "edge"

    store.remove("edge")
    assert store.load() == []


def test_profile_import_rejects_nonobject_root(tmp_path: Path) -> None:
    source = tmp_path / "import.json"
    source.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="import root must be a JSON object"):
        ProfileStore(tmp_path / "profiles.json").import_from(source)


def test_profile_rows_reject_nonstring_keys_and_group_defaults_tolerate_nonmaps() -> None:
    with pytest.raises(ValueError, match="contains a non-string key"):
        storage_module._profile_rows([{1: "value"}], source="test")

    assert storage_module._apply_group_defaults(
        {"name": "edge", "options": "profile-options"},
        {"options": {"proxy_jump": "bastion"}},
    ) == {"name": "edge", "options": "profile-options"}


def test_profile_import_adds_new_rows_without_replacing_defaults(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    source = tmp_path / "import.json"
    source.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "name": "edge",
                        "protocol": "ssh",
                        "host": "192.0.2.10",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert store.import_from(source) == 1
    assert store.get("edge").host == "192.0.2.10"
