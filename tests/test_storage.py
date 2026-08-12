from pathlib import Path

import pytest

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
