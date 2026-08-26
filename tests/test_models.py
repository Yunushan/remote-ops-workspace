import pytest

from remote_ops_workspace.models import Profile, Tunnel


def test_tunnel_from_dict_roundtrips_optional_values() -> None:
    tunnel = Tunnel.from_dict(
        {
            "mode": "remote",
            "local_host": "0.0.0.0",
            "local_port": "8080",
            "remote_host": "example.invalid",
            "remote_port": "80",
        }
    )

    assert tunnel.to_dict() == {
        "mode": "remote",
        "local_host": "0.0.0.0",
        "local_port": 8080,
        "remote_host": "example.invalid",
        "remote_port": 80,
    }


def test_profile_from_dict_discards_nonmapping_options() -> None:
    profile = Profile.from_dict(
        {
            "name": "edge",
            "protocol": "SSH",
            "options": ["not", "a", "mapping"],
        }
    )

    assert profile.protocol == "ssh"
    assert profile.options == {}


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (Profile(name="web", protocol="https", url="https://example.invalid"), "https://example.invalid"),
        (Profile(name="serial", protocol="serial", path="COM3"), "COM3"),
        (Profile(name="ssh", protocol="ssh", host="example.invalid", port=2222), "example.invalid:2222"),
        (Profile(name="host", protocol="ssh", host="example.invalid"), "example.invalid"),
        (Profile(name="command", protocol="custom", command="uptime"), "uptime"),
        (Profile(name="local", protocol="custom"), "local"),
    ],
)
def test_profile_display_target_uses_most_specific_destination(profile: Profile, expected: str) -> None:
    assert profile.display_target == expected
