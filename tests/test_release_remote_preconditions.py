from __future__ import annotations

import pytest

from scripts import check_release_remote_preconditions as preconditions

API_ROOT = "https://api.github.com"
REPOSITORY = "owner/repo"
REPOSITORY_URL = f"{API_ROOT}/repos/{REPOSITORY}"
RELEASES_PATH = "/repositories/123/releases"
FIRST_PAGE = f"{REPOSITORY_URL}/releases?per_page=100"
SECOND_PAGE = f"{API_ROOT}{RELEASES_PATH}?per_page=100&page=2"


@pytest.mark.parametrize("collision", [False, True])
def test_namespace_checks_numeric_pages_and_accepts_terminal_link(monkeypatch, collision) -> None:
    previous_page = f"{API_ROOT}{RELEASES_PATH}?per_page=100&page=1"
    responses = {
        REPOSITORY_URL: ({"id": 123, "full_name": "Owner/Repo"}, {}),
        FIRST_PAGE: ([], {"Link": f'<{SECOND_PAGE}>; rel="next", <{SECOND_PAGE}>; rel="last"'}),
        SECOND_PAGE: (
            [{"tag_name": "v1.2.3" if collision else "v1.2.2", "draft": True}],
            {"Link": f'<{previous_page}>; rel="prev", <{previous_page}>; rel="first"'},
        ),
    }
    visited = []

    def get_json(url, token, *, api_version):
        assert token == "fixture"
        assert api_version == "2022-11-28"
        visited.append(url)
        return responses[url]

    monkeypatch.setattr(preconditions, "get_json", get_json)
    if collision:
        with pytest.raises(RuntimeError, match="already uses tag/name"):
            preconditions.require_unused_namespace(API_ROOT, REPOSITORY, "v1.2.3", "fixture")
    else:
        preconditions.require_unused_namespace(API_ROOT, REPOSITORY, "v1.2.3", "fixture")
    assert visited == list(responses)


@pytest.mark.parametrize(
    "next_url",
    [
        SECOND_PAGE.replace("api.github.com", "elsewhere.example"),
        SECOND_PAGE.replace("/123/", "/999/"),
        SECOND_PAGE.replace("page=2", "page=3"),
        SECOND_PAGE.replace("per_page=100", "per_page=1"),
    ],
)
def test_next_release_page_must_stay_in_the_exact_repository_and_sequence(next_url) -> None:
    with pytest.raises(RuntimeError, match="expected HTTPS endpoint or page"):
        preconditions.next_page_url(
            f'<{next_url}>; rel="next"',
            current=FIRST_PAGE,
            allowed_paths={"/repos/owner/repo/releases", RELEASES_PATH},
            expected_page=2,
        )
