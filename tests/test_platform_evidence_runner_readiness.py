from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from urllib.error import HTTPError


def test_security_extra_includes_system_trust_store_adapter() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'security = ["cryptography>=42", "truststore>=0.10"]' in pyproject


def test_runner_api_fetcher_uses_authenticated_gh_when_no_ci_token(monkeypatch) -> None:
    checker = _load_checker()
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(checker.shutil, "which", lambda name: "C:/Program Files/GitHub CLI/gh.exe" if name == "gh" else None)

    fetcher = checker.runner_api_fetcher(repository="example/remote-ops-workspace", timeout=20.0)

    assert isinstance(fetcher, checker.GitHubCliRunnerApiFetcher)


def test_runner_readiness_accepts_all_goal_targets_with_idle_runners() -> None:
    checker = _load_checker()
    report, errors = checker.check_platform_evidence_runner_readiness(
        repository="example/remote-ops-workspace",
        targets=checker.GOAL_TARGETS,
        require_idle=True,
        fetcher=FakeFetcher(
            {
                "actions/runners?per_page=100&page=1": _runner_page(
                    _runner("online", False, "self-hosted", "linux", "i386"),
                    _runner("online", False, "self-hosted", "linux", "armhf"),
                    _runner("online", False, "self-hosted", "xp-evidence"),
                )
            }
        ),
    )

    assert errors == []
    assert report["ready"] is True
    assert report["target_readiness"]["linux-i386"]["idle_runners"] == 1
    assert report["target_readiness"]["windows-xp-native-x64"]["idle_runners"] == 1


def test_runner_readiness_rejects_missing_or_offline_target_runners() -> None:
    checker = _load_checker()
    report, errors = checker.check_platform_evidence_runner_readiness(
        repository="example/remote-ops-workspace",
        targets=("linux-i386", "linux-armhf"),
        require_idle=False,
        fetcher=FakeFetcher(
            {
                "actions/runners?per_page=100&page=1": _runner_page(
                    _runner("offline", False, "self-hosted", "linux", "i386"),
                )
            }
        ),
    )

    assert report["ready"] is False
    assert "linux-i386 has matching self-hosted runner labels ['i386', 'linux', 'self-hosted'] but none are online" in errors
    assert "linux-armhf requires a self-hosted runner with labels ['armhf', 'linux', 'self-hosted']; none found" in errors


def test_runner_readiness_require_idle_rejects_busy_runner() -> None:
    checker = _load_checker()
    _, errors = checker.check_platform_evidence_runner_readiness(
        repository="example/remote-ops-workspace",
        targets=("windows-xp-native-x86",),
        require_idle=True,
        fetcher=FakeFetcher(
            {
                "actions/runners?per_page=100&page=1": _runner_page(
                    _runner("online", True, "self-hosted", "xp-evidence"),
                )
            }
        ),
    )

    assert errors == [
        "windows-xp-native-x86 has online self-hosted runner labels ['self-hosted', 'xp-evidence'] but none are idle"
    ]


def test_runner_readiness_fetches_all_pages_without_exposing_runner_names() -> None:
    checker = _load_checker()
    fetcher = FakeFetcher(
        {
            "actions/runners?per_page=100&page=1": {
                "total_count": 2,
                "runners": [_runner("online", False, "self-hosted", "linux", "i386")],
            },
            "actions/runners?per_page=100&page=2": {
                "total_count": 2,
                "runners": [_runner("online", False, "self-hosted", "linux", "armhf")],
            },
        }
    )
    report, errors = checker.check_platform_evidence_runner_readiness(
        repository="example/remote-ops-workspace",
        targets=("linux-i386", "linux-armhf"),
        require_idle=False,
        fetcher=fetcher,
    )

    assert errors == []
    assert report["runner_count"] == 2
    assert fetcher.calls == [
        "actions/runners?per_page=100&page=1",
        "actions/runners?per_page=100&page=2",
    ]
    assert "runner_name" not in repr(report)


def test_runner_readiness_rejects_incomplete_or_inconsistent_pagination() -> None:
    checker = _load_checker()
    incomplete_report, incomplete_errors = checker.check_platform_evidence_runner_readiness(
        repository="example/remote-ops-workspace",
        targets=("linux-i386",),
        require_idle=False,
        fetcher=FakeFetcher(
            {
                "actions/runners?per_page=100&page=1": {
                    "total_count": 2,
                    "runners": [_runner("online", False, "self-hosted", "linux", "i386")],
                },
                "actions/runners?per_page=100&page=2": {"total_count": 2, "runners": []},
            }
        ),
    )
    _, inconsistent_errors = checker.check_platform_evidence_runner_readiness(
        repository="example/remote-ops-workspace",
        targets=("linux-i386",),
        require_idle=False,
        fetcher=FakeFetcher(
            {
                "actions/runners?per_page=100&page=1": {
                    "total_count": 2,
                    "runners": [_runner("online", False, "self-hosted", "linux", "i386")],
                },
                "actions/runners?per_page=100&page=2": {"total_count": 3, "runners": []},
            }
        ),
    )

    assert incomplete_report["ready"] is False
    assert incomplete_errors == [
        "GitHub runner inventory response actions/runners?per_page=100&page=2 ended before total_count runners were returned"
    ]
    assert inconsistent_errors == [
        "GitHub runner inventory response actions/runners?per_page=100&page=2 changed total_count from 2 to 3"
    ]


def test_runner_readiness_rejects_invalid_inputs_without_fetching() -> None:
    checker = _load_checker()
    fetcher = FakeFetcher({})
    _, errors = checker.check_platform_evidence_runner_readiness(
        repository=" example/repo",
        targets=("linux-i386", "linux-i386", False),
        require_idle="yes",
        fetcher=fetcher,
    )

    assert "repository must be a canonical GitHub owner/name slug, got ' example/repo'" in errors
    assert "require_idle must be a boolean, got 'yes'" in errors
    assert "target must not be repeated: linux-i386" in errors
    assert "target must be a string, got False" in errors
    assert fetcher.calls == []


def test_runner_readiness_reports_permission_problem() -> None:
    checker = _load_checker()
    _, errors = checker.check_platform_evidence_runner_readiness(
        repository="example/remote-ops-workspace",
        targets=("linux-i386",),
        require_idle=False,
        fetcher=FakeFetcher(
            {"actions/runners?per_page=100&page=1": HTTPError("url", 403, "Forbidden", None, None)}
        ),
    )

    assert errors == [
        "cannot read GitHub runner inventory at actions/runners?per_page=100&page=1: 403; "
        "set GH_TOKEN or GITHUB_TOKEN with repository administration read access"
    ]


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


def _runner_page(*runners: dict[str, object]) -> dict[str, object]:
    return {"total_count": len(runners), "runners": list(runners)}


def _runner(status: str, busy: bool, *labels: str) -> dict[str, object]:
    return {
        "name": "private-runner-name-must-not-appear",
        "status": status,
        "busy": busy,
        "labels": [{"name": label} for label in labels],
    }


def _load_checker():
    path = Path("scripts/check_platform_evidence_runner_readiness.py")
    spec = importlib.util.spec_from_file_location("platform_evidence_runner_readiness", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
