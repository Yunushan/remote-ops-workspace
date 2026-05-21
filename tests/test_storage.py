from pathlib import Path

from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore


def test_profile_store_roundtrip(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    profile = Profile(name="lab", protocol="ssh", host="192.0.2.10")
    store.add(profile)
    assert store.get("lab").host == "192.0.2.10"
    assert len(store.load()) == 1


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
