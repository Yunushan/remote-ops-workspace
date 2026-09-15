from __future__ import annotations

import io
import sys
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import release_candidate_inventory as candidate  # noqa: E402


def redirect_error(url: str, location: str) -> urllib.error.HTTPError:
    headers = Message()
    headers["Location"] = location
    return urllib.error.HTTPError(url, 302, "Found", headers, io.BytesIO(b""))


def test_artifact_download_strips_auth_and_rejects_second_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[object] = []

    class Opener:
        def open(self, request: object, timeout: int) -> object:
            del timeout
            requests.append(request)
            if len(requests) == 1:
                raise redirect_error(
                    "https://api.github.com/repos/acme/project/actions/artifacts/7/zip",
                    "https://objects.githubusercontent.com/candidate.zip",
                )
            raise redirect_error(
                "https://objects.githubusercontent.com/candidate.zip",
                "http://attacker.invalid/candidate.zip",
            )

    opener = Opener()
    monkeypatch.setattr(candidate.urllib.request, "build_opener", lambda *_: opener)
    client = candidate.GitHubClient("acme/project", "top-secret")

    with pytest.raises(RuntimeError, match="unexpected second redirect"):
        client._open("actions/artifacts/7/zip", allow_redirect=True)

    assert len(requests) == 2
    first_headers = dict(requests[0].header_items())  # type: ignore[attr-defined]
    second_headers = dict(requests[1].header_items())  # type: ignore[attr-defined]
    assert first_headers["Authorization"] == "Bearer top-secret"
    assert "Authorization" not in second_headers


@pytest.mark.parametrize(
    "value",
    [
        ".github/workflows/release.yml",
        ".github/workflows/release.yml@v1.2.3",
        ".github/workflows/release.yml@refs/tags/v1.2.3",
    ],
)
def test_workflow_path_accepts_only_exact_tag_suffixes(value: str) -> None:
    assert candidate.workflow_path_matches(value, candidate.BUILD_WORKFLOW, "v1.2.3")


@pytest.mark.parametrize(
    "value",
    [
        ".github/workflows/release.yml@main",
        ".github/workflows/release.yml.evil@refs/tags/v1.2.3",
        "prefix/.github/workflows/release.yml@v1.2.3",
        ".github/workflows/release.yml@refs/tags/v1.2.30",
    ],
)
def test_workflow_path_rejects_branch_and_spoof_suffixes(value: str) -> None:
    assert not candidate.workflow_path_matches(value, candidate.BUILD_WORKFLOW, "v1.2.3")
