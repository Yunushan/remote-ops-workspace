from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path
from urllib.error import HTTPError


def test_source_ref_accepts_all_goal_workflows_at_release_tag() -> None:
    checker = _load_checker()
    fetcher = FakeFetcher(_valid_responses())

    report, errors = checker.check_platform_evidence_source_ref(
        repository="example/remote-ops-workspace",
        release_tag="v1.0.3",
        targets=checker.GOAL_TARGETS,
        fetcher=fetcher,
    )

    assert errors == []
    assert report["ready"] is True
    assert report["source_head_sha"] == "a" * 40
    assert report["project_version"] == "1.0.3"
    assert report["workflow_files"] == [
        ".github/workflows/extended-platform-evidence.yml",
        ".github/workflows/xp-native-evidence.yml",
    ]
    assert fetcher.calls.count(
        "contents/.github/workflows/extended-platform-evidence.yml?ref=v1.0.3"
    ) == 1


def test_source_ref_rejects_workflow_missing_from_release_tag() -> None:
    checker = _load_checker()
    responses = _valid_responses()
    endpoint = "contents/.github/workflows/xp-native-evidence.yml?ref=v1.0.3"
    responses[endpoint] = HTTPError(endpoint, 404, "Not Found", None, None)

    report, errors = checker.check_platform_evidence_source_ref(
        repository="example/remote-ops-workspace",
        release_tag="v1.0.3",
        targets=checker.GOAL_TARGETS,
        fetcher=FakeFetcher(responses),
    )

    assert report["ready"] is False
    assert errors == [
        "v1.0.3 does not contain required workflow .github/workflows/xp-native-evidence.yml; "
        "create a new release tag from a commit containing the workflow before dispatch"
    ]


def test_source_ref_rejects_tagged_project_version_mismatch() -> None:
    checker = _load_checker()
    responses = _valid_responses()
    responses["contents/pyproject.toml?ref=v1.0.3"] = _file_payload(
        '[project]\nname = "remote-ops-workspace"\nversion = "1.0.2"\n',
        sha="b" * 40,
    )

    report, errors = checker.check_platform_evidence_source_ref(
        repository="example/remote-ops-workspace",
        release_tag="v1.0.3",
        targets=("linux-i386",),
        fetcher=FakeFetcher(responses),
    )

    assert report["project_version"] == "1.0.2"
    assert "v1.0.3 pyproject.toml version must be 1.0.3, got '1.0.2'" in errors


def test_source_ref_resolves_annotated_tag_to_commit() -> None:
    checker = _load_checker()
    responses = _valid_responses()
    responses["git/ref/tags/v1.0.3"] = {
        "object": {"type": "tag", "sha": "c" * 40}
    }
    responses[f"git/tags/{'c' * 40}"] = {
        "object": {"type": "commit", "sha": "d" * 40}
    }

    report, errors = checker.check_platform_evidence_source_ref(
        repository="example/remote-ops-workspace",
        release_tag="v1.0.3",
        targets=("linux-armhf",),
        fetcher=FakeFetcher(responses),
    )

    assert errors == []
    assert report["source_head_sha"] == "d" * 40


def test_source_ref_rejects_missing_target_dispatch_option() -> None:
    checker = _load_checker()
    responses = _valid_responses()
    responses["contents/.github/workflows/extended-platform-evidence.yml?ref=v1.0.3"] = (
        _file_payload(
            "on:\n  workflow_dispatch:\n    inputs:\n      target:\n        options:\n"
            "          - linux-i386\n",
            sha="e" * 40,
        )
    )

    _, errors = checker.check_platform_evidence_source_ref(
        repository="example/remote-ops-workspace",
        release_tag="v1.0.3",
        targets=("linux-i386", "linux-armhf"),
        fetcher=FakeFetcher(responses),
    )

    assert (
        "v1.0.3 workflow .github/workflows/extended-platform-evidence.yml "
        "does not expose target linux-armhf"
    ) in errors


def test_source_ref_rejects_invalid_inputs_without_fetching() -> None:
    checker = _load_checker()
    fetcher = FakeFetcher({})

    _, errors = checker.check_platform_evidence_source_ref(
        repository=" example/repo",
        release_tag="1.0.3",
        targets=("linux-i386", "linux-i386", False),
        fetcher=fetcher,
    )

    assert "repository must be a canonical GitHub owner/name slug, got ' example/repo'" in errors
    assert "release_tag must look like vX.Y.Z, got '1.0.3'" in errors
    assert "target must not be repeated: linux-i386" in errors
    assert "target must be a string, got False" in errors
    assert fetcher.calls == []


class FakeFetcher:
    def __init__(self, responses):
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, endpoint: str):
        self.calls.append(endpoint)
        response = self.responses[endpoint]
        if isinstance(response, Exception):
            raise response
        return response


def _valid_responses() -> dict[str, object]:
    linux_workflow = (
        "on:\n  workflow_dispatch:\n    inputs:\n      target:\n        options:\n"
        "          - linux-i386\n          - linux-armhf\n"
    )
    xp_workflow = (
        "on:\n  workflow_dispatch:\n    inputs:\n      target:\n        options:\n"
        "          - windows-xp-native-x86\n          - windows-xp-native-x64\n"
    )
    return {
        "git/ref/tags/v1.0.3": {"object": {"type": "commit", "sha": "a" * 40}},
        "contents/pyproject.toml?ref=v1.0.3": _file_payload(
            '[project]\nname = "remote-ops-workspace"\nversion = "1.0.3"\n',
            sha="b" * 40,
        ),
        "contents/.github/workflows/extended-platform-evidence.yml?ref=v1.0.3": (
            _file_payload(linux_workflow, sha="c" * 40)
        ),
        "contents/.github/workflows/xp-native-evidence.yml?ref=v1.0.3": _file_payload(
            xp_workflow,
            sha="d" * 40,
        ),
    }


def _file_payload(text: str, *, sha: str) -> dict[str, str]:
    encoded = base64.encodebytes(text.encode("utf-8")).decode("ascii")
    return {"type": "file", "sha": sha, "encoding": "base64", "content": encoded}


def _load_checker():
    path = Path("scripts/check_platform_evidence_source_ref.py")
    spec = importlib.util.spec_from_file_location("check_platform_evidence_source_ref", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
