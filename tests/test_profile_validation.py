from __future__ import annotations

import pytest

from remote_ops_workspace import profile_validation
from remote_ops_workspace.gui_editors import profile_from_editor_data
from remote_ops_workspace.models import Profile, Tunnel
from remote_ops_workspace.profile_validation import (
    PROFILE_ONLY_SECURITY_OPTIONS,
    ProfileValidationError,
    normalize_group_defaults,
    normalize_group_defaults_map,
    normalize_group_name,
    normalize_tunnel,
    prepare_profile,
    validate_profile,
)
from remote_ops_workspace.storage import ProfileStore


def test_prepare_profile_normalizes_shared_profile_shape() -> None:
    profile = prepare_profile(
        Profile(
            name=" edge ",
            protocol="SSH",
            host="192.0.2.10",
            tags=[" prod ", "prod", ""],
            options={" keepalive_interval ": " 30 "},
            tunnels=[Tunnel(mode="DYNAMIC", local_port=1080)],
        )
    )

    assert profile.name == "edge"
    assert profile.protocol == "ssh"
    assert profile.tags == ["prod"]
    assert profile.options == {"keepalive_interval": "30"}
    assert profile.tunnels[0].mode == "dynamic"


def test_prepare_profile_rejects_missing_required_targets() -> None:
    try:
        prepare_profile(Profile(name="edge", protocol="ssh"))
    except ProfileValidationError as exc:
        assert "ssh profile requires host" in str(exc)
    else:
        raise AssertionError("ssh profile without host should be rejected")

    try:
        prepare_profile(Profile(name="raw", protocol="raw", host="192.0.2.10"))
    except ProfileValidationError as exc:
        assert "raw profile requires explicit port" in str(exc)
    else:
        raise AssertionError("raw profile without explicit port should be rejected")


def test_prepare_profile_rejects_unsafe_url_and_option_key() -> None:
    try:
        prepare_profile(Profile(name="web", protocol="https", url="https://admin:secret@example.com"))
    except ValueError as exc:
        assert "embedded password" in str(exc)
    else:
        raise AssertionError("embedded URL passwords should be rejected")

    try:
        prepare_profile(Profile(name="edge", protocol="ssh", host="192.0.2.10", options={"bad key": "value"}))
    except ProfileValidationError as exc:
        assert "option key" in str(exc)
    else:
        raise AssertionError("option keys with whitespace should be rejected")


def test_profile_store_validates_before_persisting(tmp_path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")

    try:
        store.add(Profile(name="bad", protocol="ssh"))
    except ProfileValidationError:
        pass
    else:
        raise AssertionError("store should reject invalid profiles before persisting")

    assert not store.path.exists()


def test_profile_store_normalizes_saved_profiles(tmp_path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.add(Profile(name="edge", protocol="SSH", host="192.0.2.10", tags=["prod", "prod"]))

    profile = store.get("edge")

    assert profile.protocol == "ssh"
    assert profile.tags == ["prod"]


def test_group_defaults_reject_every_profile_only_security_option() -> None:
    for option_name in PROFILE_ONLY_SECURITY_OPTIONS:
        try:
            normalize_group_defaults({"options": {option_name: "true"}})
        except ProfileValidationError as exc:
            assert "group default options" in str(exc)
            assert option_name in str(exc)
        else:
            raise AssertionError(f"group defaults must reject profile-only option {option_name}")


def test_profile_store_rejects_persisted_insecure_group_default(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text(
        """{
  "version": 1,
  "profiles": [{"name": "legacy", "protocol": "telnet", "host": "192.0.2.10", "group": "legacy"}],
  "group_defaults": {"legacy": {"options": {"allow_insecure_cleartext": "true"}}}
}""",
        encoding="utf-8",
    )
    store = ProfileStore(path)

    try:
        store.load()
    except ProfileValidationError as exc:
        assert "allow_insecure_cleartext" in str(exc)
    else:
        raise AssertionError("persisted group defaults must not bypass the per-profile security boundary")


def test_profile_editor_uses_shared_profile_validation() -> None:
    try:
        profile_from_editor_data({"name": "edge", "protocol": "ssh", "host": ""})
    except ProfileValidationError as exc:
        assert "ssh profile requires host" in str(exc)
    else:
        raise AssertionError("GUI editor data should use shared profile validation")


def test_validate_profile_rejects_non_normalized_protocol() -> None:
    with pytest.raises(ProfileValidationError, match="must be normalized"):
        validate_profile(Profile(name="edge", protocol="SSH", host="192.0.2.10"))

    validate_profile(Profile(name="edge", protocol="ssh"), require_target=False)


def test_validate_profile_defends_against_unsupported_normalizer_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(profile_validation, "_profile_protocol", lambda *_args, **_kwargs: "unsupported")

    with pytest.raises(ProfileValidationError, match="unsupported profile protocol"):
        validate_profile(Profile(name="edge", protocol="unsupported"), require_target=False)


def test_normalize_tunnel_supports_forwarding_modes_and_rejects_unknown_mode() -> None:
    for mode in ("local", "remote"):
        tunnel = normalize_tunnel(
            Tunnel(
                mode=mode.upper(),
                local_host="127.0.0.1",
                local_port=8080,
                remote_host="192.0.2.20",
                remote_port=80,
            )
        )
        assert tunnel.mode == mode
        assert tunnel.remote_port == 80

    with pytest.raises(ProfileValidationError, match="unsupported tunnel mode"):
        normalize_tunnel(Tunnel(mode="sideways", local_port=8080))


def test_group_default_normalizers_cover_empty_complete_and_invalid_values() -> None:
    assert normalize_group_name(None) == "default"
    assert normalize_group_defaults(None) == {}
    assert normalize_group_defaults({"options": {}}) == {}
    assert normalize_group_defaults(
        {
            "username": "admin",
            "identity_file": "~/.ssh/id_ed25519",
            "credential_ref": "vault://prod",
            "options": {"proxy_jump": "bastion"},
        }
    ) == {
        "username": "admin",
        "identity_file": "~/.ssh/id_ed25519",
        "credential_ref": "vault://prod",
        "options": {"proxy_jump": "bastion"},
    }
    assert normalize_group_defaults_map(None) == {}
    assert normalize_group_defaults_map("") == {}
    assert normalize_group_defaults_map({" prod ": {"username": "admin"}}) == {
        "prod": {"username": "admin"}
    }

    with pytest.raises(ProfileValidationError, match="group defaults must be an object"):
        normalize_group_defaults([])  # type: ignore[arg-type]
    with pytest.raises(ProfileValidationError, match="group default options must be an object"):
        normalize_group_defaults({"options": ["proxy_jump"]})
    with pytest.raises(ProfileValidationError, match="group_defaults must be an object"):
        normalize_group_defaults_map([])


@pytest.mark.parametrize(
    "protocol, expected",
    [
        ("bad protocol", "must not contain whitespace"),
        ("-ssh", "must not start"),
        ("unknown", "unsupported profile protocol"),
    ],
)
def test_prepare_profile_rejects_invalid_protocol_tokens(protocol: str, expected: str) -> None:
    with pytest.raises(ProfileValidationError, match=expected):
        prepare_profile(Profile(name="edge", protocol=protocol), require_target=False)


@pytest.mark.parametrize(
    "profile, expected",
    [
        (Profile(name="web", protocol="https"), "requires url or host"),
        (Profile(name="serial", protocol="serial"), "requires path or option device"),
        (Profile(name="custom", protocol="custom"), "requires command"),
        (Profile(name="ica", protocol="ica"), "requires path, url, or host"),
        (Profile(name="x2go", protocol="x2go"), "requires host or option session"),
    ],
)
def test_prepare_profile_rejects_each_missing_target(profile: Profile, expected: str) -> None:
    with pytest.raises(ProfileValidationError, match=expected):
        prepare_profile(profile)


def test_prepare_profile_preserves_non_web_url_and_rejects_dash_option() -> None:
    profile = prepare_profile(
        Profile(name="script", protocol="custom", command="echo ok", url="internal-target"),
    )
    assert profile.url == "internal-target"

    with pytest.raises(ProfileValidationError, match="option key must not start"):
        prepare_profile(
            Profile(name="edge", protocol="ssh", host="192.0.2.10", options={"-unsafe": "true"})
        )
