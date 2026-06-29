from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


def test_remote_release_audit_reports_missing_goal_evidence() -> None:
    checker = _load_checker()
    registry = _empty_registry()
    promotion = checker.read_json(checker.PROMOTION_PATH)
    release = _release_with_assets([])

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow={
            ".github/workflows/extended-platform-evidence.yml": {"workflow_runs": []},
            ".github/workflows/xp-native-evidence.yml": {"workflow_runs": []},
        },
        release_tag="v1.0.2",
        required_targets=checker.PROTECTED_GOAL_TARGETS,
        require_source_runs=True,
    )

    assert any(
        "missing required accepted evidence targets for release_tag v1.0.2" in error
        and "linux-i386" in error
        for error in errors
    )
    assert any(
        "linux-i386 remote release v1.0.2 missing protected evidence assets" in error
        and "remote-ops-workspace-v1.0.2-linux-i386.deb" in error
        and "platform-verified-evidence-linux-i386-final.json" in error
        for error in errors
    )
    assert (
        "windows-xp-native-x64 accepted evidence record missing; cannot verify release source run"
        in errors
    )


def test_remote_release_audit_accepts_bound_linux_record(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=_workflow_runs_for(record),
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert errors == []


def test_remote_release_audit_accepts_exact_source_run_metadata(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert errors == []


def test_remote_release_audit_requires_exact_source_run_when_no_workflow_list(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    source_runs = _source_runs_for(record)
    source_runs["https://github.com/example/remote-ops-workspace/actions/runs/99999"] = (
        source_runs.pop("https://github.com/example/remote-ops-workspace/actions/runs/12345")
    )

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=source_runs,
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 exact source workflow run metadata missing for "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    ) in errors


def test_remote_release_audit_rejects_unexpected_protected_assets(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    release["assets"].extend(
        [
            {"name": "platform-verified-evidence-linux-i386.json"},
            {"name": "extended-linux-evidence-bundle-linux-armhf-v1.0.1.zip"},
            {"name": "remote-ops-workspace-v1.0.1-windows-xp-x64-native.zip"},
            {"name": "release-notes-v1.0.2.txt"},
        ]
    )

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=_workflow_runs_for(record),
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 remote release v1.0.2 contains protected platform assets "
        "not expected for this audited evidence scope: "
        "['platform-verified-evidence-linux-i386.json']"
    ) in errors
    assert (
        "linux-armhf remote release v1.0.2 contains protected platform assets "
        "not expected for this audited evidence scope: "
        "['extended-linux-evidence-bundle-linux-armhf-v1.0.1.zip']"
    ) in errors
    assert (
        "windows-xp-native-x64 remote release v1.0.2 contains protected platform assets "
        "not expected for this audited evidence scope: "
        "['remote-ops-workspace-v1.0.1-windows-xp-x64-native.zip']"
    ) in errors
    assert not any("release-notes-v1.0.2.txt" in error for error in errors)


def test_remote_release_audit_rejects_failed_source_run(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    workflow_runs = _workflow_runs_for(record)
    workflow = str(record["release_asset_source"]["workflow"])
    workflow_runs[workflow]["workflow_runs"][0]["conclusion"] = "failure"

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=workflow_runs,
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert "linux-i386 source workflow run conclusion must be success, got 'failure'" in errors


def test_remote_release_audit_rejects_published_asset_metadata_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    deb_asset = _release_asset(release, "remote-ops-workspace-v1.0.2-linux-i386.deb")
    deb_asset["state"] = "starter"
    deb_asset["digest"] = f"sha256:{'b' * 64}"
    deb_asset["browser_download_url"] = (
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/wrong.deb"
    )
    bundle_asset = _release_asset(
        release,
        "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip",
    )
    bundle_asset["size"] = 1
    final_record_asset = _release_asset(release, "platform-verified-evidence-linux-i386-final.json")
    final_record_asset["digest"] = f"sha256:{'c' * 64}"
    final_record_asset["size"] = 2

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=_workflow_runs_for(record),
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 remote release asset remote-ops-workspace-v1.0.2-linux-i386.deb "
        "state must be uploaded, got 'starter'"
    ) in errors
    assert (
        "linux-i386 remote release asset remote-ops-workspace-v1.0.2-linux-i386.deb "
        "digest must be "
        f"sha256:{'a' * 64}, got 'sha256:{'b' * 64}'"
    ) in errors
    assert any(
        "linux-i386 remote release asset remote-ops-workspace-v1.0.2-linux-i386.deb "
        "browser_download_url must be "
        in error
        and "wrong.deb" in error
        for error in errors
    )
    assert (
        "linux-i386 remote release asset extended-linux-evidence-bundle-linux-i386-v1.0.2.zip "
        "size must be 456, got 1"
    ) in errors
    assert any(
        "linux-i386 remote release asset platform-verified-evidence-linux-i386-final.json "
        "digest must be "
        in error
        and f"got 'sha256:{'c' * 64}'" in error
        for error in errors
    )
    assert any(
        "linux-i386 remote release asset platform-verified-evidence-linux-i386-final.json "
        "size must be "
        in error
        and "got 2" in error
        for error in errors
    )


def test_remote_release_audit_requires_exact_source_run_metadata(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    workflow_runs = _workflow_runs_for(record)
    workflow = str(record["release_asset_source"]["workflow"])
    run = workflow_runs[workflow]["workflow_runs"][0]
    run["html_url"] = "https://github.com/example/remote-ops-workspace/actions/runs/99999"
    run.pop("run_attempt")
    run.pop("path")

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=workflow_runs,
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow run html_url must match accepted record "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345, "
        "got 'https://github.com/example/remote-ops-workspace/actions/runs/99999'"
    ) in errors
    assert "linux-i386 source workflow run run_attempt must match accepted record 1, got None" in errors
    assert (
        "linux-i386 source workflow run path must be "
        "'.github/workflows/extended-platform-evidence.yml', got None"
    ) in errors


def test_remote_release_audit_requires_source_run_repository_binding(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    source_runs = _source_runs_for(record)
    run = next(iter(source_runs.values()))
    run["repository"]["full_name"] = "other/remote-ops-workspace"
    run["head_repository"]["full_name"] = "example/forked-remote-ops-workspace"

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=source_runs,
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow run repository.full_name must match accepted record "
        "example/remote-ops-workspace, got 'other/remote-ops-workspace'"
    ) in errors
    assert (
        "linux-i386 source workflow run head_repository.full_name must match accepted record "
        "example/remote-ops-workspace, got 'example/forked-remote-ops-workspace'"
    ) in errors


def test_remote_release_audit_requires_source_artifact_inventory(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=_workflow_runs_for(record),
        source_artifacts_by_run={},
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow artifacts missing for "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    ) in errors


def test_remote_release_audit_rejects_bad_source_artifact_metadata(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    source_artifacts = _source_artifacts_for(record)
    run_url = str(record["release_asset_source"]["workflow_run_url"])
    artifact = source_artifacts[run_url]["artifacts"][0]
    artifact["expired"] = True
    artifact["size_in_bytes"] = 0
    artifact["archive_download_url"] = "https://api.github.com/repos/example/remote-ops-workspace/actions/artifacts/99/zip"
    artifact["workflow_run"]["head_sha"] = "b" * 40

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=_workflow_runs_for(record),
        source_artifacts_by_run=source_artifacts,
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "must not be expired, got True"
    ) in errors
    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "size_in_bytes must be positive, got 0"
    ) in errors
    assert any(
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "archive_download_url must be "
        in error
        and "artifacts/99/zip" in error
        for error in errors
    )
    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        f"workflow_run.head_sha must match accepted record {'a' * 40}, got {('b' * 40)!r}"
    ) in errors


def test_required_release_assets_include_native_review_bundle_and_final_record() -> None:
    checker = _load_checker()
    promotion = checker.read_json(checker.PROMOTION_PATH)

    assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-armhf", "windows-xp-native-x86"),
    )

    assert "remote-ops-workspace-v1.0.2-linux-armhf.deb" in assets["linux-armhf"]
    assert "extended-linux-evidence-bundle-linux-armhf-v1.0.2.zip" in assets["linux-armhf"]
    assert "platform-verified-evidence-linux-armhf-final.json" in assets["linux-armhf"]
    assert (
        "remote-ops-workspace-v1.0.2-windows-xp-x86-native.zip"
        in assets["windows-xp-native-x86"]
    )
    assert (
        "xp-native-evidence-bundle-windows-xp-native-x86-v1.0.2-SHA256SUMS.txt"
        in assets["windows-xp-native-x86"]
    )
    assert (
        "platform-verified-evidence-windows-xp-native-x86-final.json"
        in assets["windows-xp-native-x86"]
    )


def test_source_run_attempt_api_url_uses_exact_attempt_endpoint() -> None:
    checker = _load_checker()

    assert checker.source_run_attempt_api_url("example/remote-ops-workspace", "12345", 2) == (
        "https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345/attempts/2"
    )


def test_github_api_headers_use_environment_token() -> None:
    checker = _load_checker()
    original_gh_token = os.environ.get("GH_TOKEN")
    original_github_token = os.environ.get("GITHUB_TOKEN")
    try:
        os.environ["GH_TOKEN"] = "secret-token"
        os.environ.pop("GITHUB_TOKEN", None)

        headers = checker.github_api_headers()
    finally:
        _restore_env("GH_TOKEN", original_gh_token)
        _restore_env("GITHUB_TOKEN", original_github_token)

    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def _release_with_assets(asset_names: list[str]) -> dict[str, Any]:
    return {
        "tag_name": "v1.0.2",
        "draft": False,
        "prerelease": False,
        "assets": [{"name": name} for name in asset_names],
    }


def _release_with_record_assets(
    checker: Any,
    record: dict[str, Any],
    asset_names: list[str],
) -> dict[str, Any]:
    expected = checker.expected_published_assets(record)
    assets = []
    for index, name in enumerate(asset_names, start=1):
        metadata = expected.get(name, {})
        assets.append(
            {
                "name": name,
                "state": "uploaded",
                "size": metadata.get("size", 1024 + index),
                "digest": f"sha256:{metadata.get('sha256', '0' * 64)}",
                "browser_download_url": metadata.get(
                    "browser_download_url",
                    f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/{name}",
                ),
            }
        )
    return {
        "tag_name": "v1.0.2",
        "draft": False,
        "prerelease": False,
        "assets": assets,
    }


def _release_asset(release: dict[str, Any], name: str) -> dict[str, Any]:
    for asset in release["assets"]:
        if asset["name"] == name:
            return asset
    raise AssertionError(f"missing release asset fixture {name}")


def _workflow_runs_for(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    source = record["release_asset_source"]
    run_url = str(source["workflow_run_url"])
    run_id = int(run_url.rstrip("/").rsplit("/", 1)[-1])
    workflow = str(source["workflow"])
    repository = _repository_from_run_url(run_url)
    return {
        workflow: {
            "workflow_runs": [
                {
                    "id": run_id,
                    "html_url": run_url,
                    "repository": {"full_name": repository},
                    "head_repository": {"full_name": repository},
                    "status": "completed",
                    "conclusion": "success",
                    "event": "workflow_dispatch",
                    "head_sha": source["head_sha"],
                    "run_attempt": source["run_attempt"],
                    "path": workflow,
                }
            ]
        }
    }


def _source_runs_for(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    source = record["release_asset_source"]
    run_url = str(source["workflow_run_url"])
    run_id = int(run_url.rstrip("/").rsplit("/", 1)[-1])
    workflow = str(source["workflow"])
    repository = _repository_from_run_url(run_url)
    return {
        run_url: {
            "id": run_id,
            "htmlUrl": run_url,
            "repository": {"full_name": repository},
            "head_repository": {"full_name": repository},
            "status": "completed",
            "conclusion": "success",
            "event": "workflow_dispatch",
            "headSha": source["head_sha"],
            "attempt": source["run_attempt"],
            "path": workflow,
        }
    }


def _repository_from_run_url(run_url: str) -> str:
    return run_url.split("https://github.com/", 1)[1].split("/actions/runs/", 1)[0]


def _source_artifacts_for(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    source = record["release_asset_source"]
    run_url = str(source["workflow_run_url"])
    run_id = int(run_url.rstrip("/").rsplit("/", 1)[-1])
    artifact_id = 98765
    return {
        run_url: {
            "total_count": 1,
            "artifacts": [
                {
                    "id": artifact_id,
                    "name": source["artifact_name"],
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        f"actions/artifacts/{artifact_id}/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": 4096,
                    "workflow_run": {
                        "id": run_id,
                        "head_sha": source["head_sha"],
                    },
                }
            ],
        }
    }


def _registry_with(record: dict[str, Any]) -> dict[str, Any]:
    registry = json.loads(Path("configs/platform_verified_evidence.json").read_text(encoding="utf-8"))
    return {**registry, "accepted_evidence": [record]}


def _empty_registry() -> dict[str, Any]:
    registry = json.loads(Path("configs/platform_verified_evidence.json").read_text(encoding="utf-8"))
    return {**registry, "accepted_evidence": []}


def _load_checker() -> Any:
    path = Path("scripts/check_platform_release_evidence_remote.py")
    spec = importlib.util.spec_from_file_location("check_platform_release_evidence_remote", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_verified_evidence_helpers() -> Any:
    path = Path("tests/test_platform_verified_evidence.py")
    spec = importlib.util.spec_from_file_location("platform_verified_remote_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
