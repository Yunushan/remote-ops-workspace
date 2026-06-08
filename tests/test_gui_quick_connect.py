from remote_ops_workspace.gui import parse_quick_connect_profile, quick_connect_candidates
from remote_ops_workspace.gui_designs import gui_design_moba_quick_connect_suggestion_chrome
from remote_ops_workspace.models import Profile


def test_quick_connect_ranks_exact_saved_profile_before_direct_target() -> None:
    profiles = [
        Profile(name="edge-prod", protocol="ssh", host="edge.example", username="operator"),
        Profile(name="files-prod", protocol="sftp", host="files.example", username="operator"),
    ]

    candidates = quick_connect_candidates("edge-prod", profiles)

    assert candidates[0].kind == "profile"
    assert candidates[0].profile_name == "edge-prod"


def test_mobaxterm_preview_query_returns_saved_profile_and_direct_candidate() -> None:
    chrome = gui_design_moba_quick_connect_suggestion_chrome()
    profiles = [
        Profile(
            name="edge-prod",
            protocol="ssh",
            host="edge-prod.example.invalid",
            port=22,
            username="operator",
            group="prod",
            tags=["ssh", "demo"],
        ),
        Profile(name="files-prod", protocol="sftp", host="files.example.invalid", port=22, group="files"),
    ]

    candidates = quick_connect_candidates(chrome.preview_query, profiles, limit=chrome.max_visible_rows)

    assert [candidate.kind for candidate in candidates[:2]] == list(chrome.expected_kinds)
    assert candidates[0].profile_name == "edge-prod"
    assert candidates[1].label.startswith("DIRECT SSH")
    assert chrome.preview_query in candidates[0].detail


def test_quick_connect_parses_explicit_ssh_target() -> None:
    candidate = parse_quick_connect_profile("ssh operator@example.com:2222")

    assert candidate is not None
    assert candidate.kind == "direct"
    assert candidate.profile is not None
    assert candidate.profile.protocol == "ssh"
    assert candidate.profile.host == "example.com"
    assert candidate.profile.port == 2222
    assert candidate.profile.username == "operator"


def test_quick_connect_parses_url_target() -> None:
    candidate = parse_quick_connect_profile("https://admin.example.com")

    assert candidate is not None
    assert candidate.profile is not None
    assert candidate.profile.protocol == "https"
    assert candidate.profile.url == "https://admin.example.com"


def test_quick_connect_parses_ssh_uri_target() -> None:
    candidate = parse_quick_connect_profile("ssh://operator@example.com:2222")

    assert candidate is not None
    assert candidate.profile is not None
    assert candidate.profile.protocol == "ssh"
    assert candidate.profile.host == "example.com"
    assert candidate.profile.port == 2222
    assert candidate.profile.username == "operator"


def test_quick_connect_defaults_host_like_target_to_ssh() -> None:
    candidate = parse_quick_connect_profile("192.0.2.10")

    assert candidate is not None
    assert candidate.profile is not None
    assert candidate.profile.protocol == "ssh"
    assert candidate.profile.host == "192.0.2.10"
    assert candidate.profile.port == 22


def test_quick_connect_ignores_plain_words_without_saved_match() -> None:
    assert parse_quick_connect_profile("edge") is None
