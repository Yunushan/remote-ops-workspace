from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
from collections.abc import Callable, Sequence
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

GOAL_TARGETS = (
    "linux-i386",
    "linux-armhf",
    "windows-xp-native-x86",
    "windows-xp-native-x64",
)
TARGET_RUNNER_LABELS = {
    "linux-i386": frozenset({"self-hosted", "linux", "i386"}),
    "linux-armhf": frozenset({"self-hosted", "linux", "armhf"}),
    "windows-xp-native-x86": frozenset({"self-hosted", "xp-evidence"}),
    "windows-xp-native-x64": frozenset({"self-hosted", "xp-evidence"}),
}
REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9._-]+$"
)
ApiFetcher = Callable[[str], dict[str, Any]]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    targets = selected_targets(args.target, require_goal_targets=args.require_goal_targets)
    report, errors = check_platform_evidence_runner_readiness(
        repository=args.repository,
        targets=targets,
        require_idle=args.require_idle,
        fetcher=GitHubRunnerApiFetcher(repository=args.repository, timeout=args.timeout),
    )
    if args.json:
        print(json.dumps({**report, "errors": errors}, indent=2, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"platform evidence runner readiness: {error}", file=sys.stderr)
    else:
        mode = "idle" if args.require_idle else "online"
        print(
            "platform evidence runner readiness passed: "
            f"{args.repository}; targets={len(targets)}/{len(targets)}; mode={mode}"
        )
    return 1 if errors else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check that the required self-hosted evidence runner labels are online "
            "before dispatching protected platform evidence workflows."
        )
    )
    parser.add_argument("--repository", required=True, help="GitHub repository as owner/name")
    parser.add_argument(
        "--target",
        action="append",
        choices=GOAL_TARGETS,
        help="Protected target to inspect; repeat for more than one target",
    )
    parser.add_argument(
        "--require-goal-targets",
        action="store_true",
        help="Require runner availability for all four protected platform targets",
    )
    parser.add_argument(
        "--require-idle",
        action="store_true",
        help="Require a matching runner to be idle as well as online",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="GitHub API timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable report")
    args = parser.parse_args(argv)
    if not args.require_goal_targets and not args.target:
        parser.error("pass --require-goal-targets or at least one --target")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    return args


def selected_targets(raw_targets: Sequence[str] | None, *, require_goal_targets: bool) -> tuple[str, ...]:
    if require_goal_targets:
        return GOAL_TARGETS
    return tuple(dict.fromkeys(raw_targets or ()))


def check_platform_evidence_runner_readiness(
    *,
    repository: object,
    targets: Sequence[object],
    require_idle: bool,
    fetcher: ApiFetcher,
) -> tuple[dict[str, Any], list[str]]:
    report: dict[str, Any] = {
        "repository": repository,
        "targets": list(targets),
        "require_idle": require_idle,
        "runner_count": 0,
        "target_readiness": {},
        "ready": False,
    }
    errors = validate_inputs(repository=repository, targets=targets, require_idle=require_idle)
    if errors:
        return report, errors

    runners, fetch_errors = fetch_all_runners(fetcher)
    errors.extend(fetch_errors)
    report["runner_count"] = len(runners)
    if fetch_errors:
        return report, errors

    for target in tuple(str(target) for target in targets):
        required_labels = TARGET_RUNNER_LABELS[target]
        matching = [runner for runner in runners if required_labels <= runner_labels(runner)]
        online = [runner for runner in matching if runner.get("status") == "online"]
        idle = [runner for runner in online if runner.get("busy") is False]
        report["target_readiness"][target] = {
            "required_labels": sorted(required_labels),
            "matching_runners": len(matching),
            "online_runners": len(online),
            "idle_runners": len(idle),
            "ready": bool(idle if require_idle else online),
        }
        if not matching:
            errors.append(
                f"{target} requires a self-hosted runner with labels {sorted(required_labels)}; none found"
            )
        elif not online:
            errors.append(
                f"{target} has matching self-hosted runner labels {sorted(required_labels)} but none are online"
            )
        elif require_idle and not idle:
            errors.append(
                f"{target} has online self-hosted runner labels {sorted(required_labels)} but none are idle"
            )

    report["ready"] = not errors
    return report, errors


def validate_inputs(*, repository: object, targets: Sequence[object], require_idle: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(repository, str):
        errors.append(f"repository must be a string, got {repository!r}")
    elif repository != repository.strip() or REPOSITORY_RE.fullmatch(repository) is None:
        errors.append(f"repository must be a canonical GitHub owner/name slug, got {repository!r}")
    if not isinstance(require_idle, bool):
        errors.append(f"require_idle must be a boolean, got {require_idle!r}")
    if not targets:
        errors.append("at least one protected target is required")
    seen: set[str] = set()
    for target in targets:
        if not isinstance(target, str):
            errors.append(f"target must be a string, got {target!r}")
            continue
        if target not in TARGET_RUNNER_LABELS:
            errors.append(f"target must be one of {list(GOAL_TARGETS)}, got {target!r}")
        if target in seen:
            errors.append(f"target must not be repeated: {target}")
        seen.add(target)
    return errors


def fetch_all_runners(fetcher: ApiFetcher) -> tuple[list[dict[str, Any]], list[str]]:
    runners: list[dict[str, Any]] = []
    page = 1
    expected_total: int | None = None
    while True:
        endpoint = f"actions/runners?per_page=100&page={page}"
        try:
            payload = fetcher(endpoint)
        except Exception as exc:
            return [], [fetch_failure(endpoint, exc)]
        page_runners = payload.get("runners")
        total_count = payload.get("total_count")
        if not isinstance(total_count, int) or isinstance(total_count, bool) or total_count < 0:
            return [], [f"GitHub runner inventory response {endpoint} has invalid total_count"]
        if not isinstance(page_runners, list) or any(not isinstance(item, dict) for item in page_runners):
            return [], [f"GitHub runner inventory response {endpoint} has invalid runners list"]
        if expected_total is None:
            expected_total = total_count
        elif total_count != expected_total:
            return [], [
                f"GitHub runner inventory response {endpoint} changed total_count "
                f"from {expected_total} to {total_count}"
            ]
        runners.extend(page_runners)
        if len(runners) > total_count:
            return [], [
                f"GitHub runner inventory response {endpoint} returned more runners than total_count"
            ]
        if len(runners) == total_count:
            return runners, []
        if not page_runners:
            return [], [
                f"GitHub runner inventory response {endpoint} ended before total_count runners were returned"
            ]
        page += 1
        if page > 100:
            return [], ["GitHub runner inventory pagination exceeded 100 pages"]


def runner_labels(runner: dict[str, Any]) -> frozenset[str]:
    labels = runner.get("labels")
    if not isinstance(labels, list):
        return frozenset()
    return frozenset(
        item["name"]
        for item in labels
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    )


def fetch_failure(endpoint: str, exc: Exception) -> str:
    if isinstance(exc, HTTPError) and exc.code in {401, 403, 404}:
        return (
            f"cannot read GitHub runner inventory at {endpoint}: {exc.code}; "
            "set GH_TOKEN or GITHUB_TOKEN with repository administration read access"
        )
    return f"failed to fetch GitHub runner inventory endpoint {endpoint}: {exc}"


class GitHubRunnerApiFetcher:
    def __init__(self, *, repository: str, timeout: float) -> None:
        self.repository = repository
        self.timeout = timeout
        self.ssl_context = verified_ssl_context()

    def __call__(self, endpoint: str) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repository}/{endpoint}"
        request = Request(url, headers=github_api_headers())
        with urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"GitHub API response must be an object: {endpoint}")
        return payload


def verified_ssl_context() -> ssl.SSLContext:
    try:
        import truststore
    except ImportError:
        pass
    else:
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def github_api_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "remote-ops-workspace-platform-evidence-runner-readiness",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


if __name__ == "__main__":
    raise SystemExit(main())
