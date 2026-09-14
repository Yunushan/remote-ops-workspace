from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path


def _load_checker():
    path = Path("scripts/check_release_provenance.py")
    spec = importlib.util.spec_from_file_location("check_release_provenance", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load check_release_provenance.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_release_provenance"] = module
    spec.loader.exec_module(module)
    return module


def _release(checker, root: Path, repository: str, tag: str) -> dict:
    assets = []
    for index, path in enumerate(sorted(root.iterdir()), start=1):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assets.append(
            {
                "id": index,
                "url": f"https://api.github.com/repos/{repository}/releases/assets/{index}",
                "name": path.name,
                "state": "uploaded",
                "size": path.stat().st_size,
                "digest": f"sha256:{digest}",
                "browser_download_url": (
                    f"https://github.com/{repository}/releases/download/{tag}/{path.name}"
                ),
            }
        )
    return {
        "tag_name": tag,
        "id": 77,
        "target_commitish": "a" * 40,
        "draft": False,
        "prerelease": False,
        "immutable": True,
        "assets": assets,
    }


def _attestation(
    checker,
    *,
    repository: str,
    sha: str,
    tag: str,
    digest: str,
    run_id: int = 123,
    attempt: int = 2,
) -> list[dict]:
    return [
        {
            "verificationResult": {
                "verifiedTimestamps": [{"type": "tlog"}],
                "signature": {
                    "certificate": {
                        "sourceRepositoryURI": f"https://github.com/{repository}",
                        "sourceRepositoryDigest": sha,
                        "sourceRepositoryRef": f"refs/tags/{tag}",
                        "runnerEnvironment": "github-hosted",
                        "buildTrigger": "workflow_dispatch",
                        "runInvocationURI": (
                            f"https://github.com/{repository}/actions/runs/"
                            f"{run_id}/attempts/{attempt}"
                        ),
                    }
                },
                "statement": {
                    "predicateType": checker.PREDICATE_TYPE,
                    "subject": [{"name": "artifact", "digest": {"sha256": digest}}],
                },
            }
        }
    ]


def test_release_asset_bytes_match_every_local_and_remote_file(tmp_path: Path) -> None:
    checker = _load_checker()
    repository = "example/project"
    tag = "v1.2.3"
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    local = {path.name: path for path in (first, second)}

    assert (
        checker.check_release_asset_bytes(
            _release(checker, tmp_path, repository, tag),
            local,
            repository=repository,
            tag=tag,
            required_standard_assets={"first.bin", "second.bin"},
        )
        == []
    )


def test_release_asset_bytes_reject_remote_digest_drift_and_inventory_gap(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    repository = "example/project"
    tag = "v1.2.3"
    asset = tmp_path / "first.bin"
    asset.write_bytes(b"first")
    local = {asset.name: asset}
    release = _release(checker, tmp_path, repository, tag)
    release["assets"][0]["digest"] = f"sha256:{'0' * 64}"
    release["assets"].append(
        {
            "name": "remote-only.bin",
            "state": "uploaded",
            "size": 1,
            "digest": f"sha256:{'1' * 64}",
            "browser_download_url": (
                f"https://github.com/{repository}/releases/download/{tag}/remote-only.bin"
            ),
        }
    )

    errors = checker.check_release_asset_bytes(
        release,
        local,
        repository=repository,
        tag=tag,
        required_standard_assets={"first.bin", "missing-standard.bin"},
    )

    assert any("digest must match downloaded bytes" in error for error in errors)
    assert "local release assets missing standard files: ['missing-standard.bin']" in errors
    assert "downloaded release directory missing published files: ['remote-only.bin']" in errors


def test_release_asset_bytes_requires_explicit_remote_immutability(tmp_path: Path) -> None:
    checker = _load_checker()
    repository = "example/project"
    tag = "v1.2.3"
    asset = tmp_path / "first.bin"
    asset.write_bytes(b"first")
    local = {asset.name: asset}

    for value in (False, None):
        release = _release(checker, tmp_path, repository, tag)
        if value is None:
            release.pop("immutable")
        else:
            release["immutable"] = value
        errors = checker.check_release_asset_bytes(
            release,
            local,
            repository=repository,
            tag=tag,
            required_standard_assets={asset.name},
        )
        assert "published production release must have GitHub immutable releases enabled" in errors


def test_verified_attestation_binds_digest_source_ref_and_run_attempt() -> None:
    checker = _load_checker()
    repository = "example/project"
    sha = "a" * 40
    tag = "v1.2.3"
    digest = "b" * 64

    invocations, errors = checker.verified_run_invocations(
        _attestation(
            checker,
            repository=repository,
            sha=sha,
            tag=tag,
            digest=digest,
        ),
        asset_name="asset.bin",
        asset_sha256=digest,
        repository=repository,
        sha=sha,
        tag=tag,
    )

    assert errors == []
    assert invocations == {checker.RunInvocation(repository, 123, 2)}


def test_verified_attestation_rejects_wrong_source_ref_and_unwitnessed_result() -> None:
    checker = _load_checker()
    repository = "example/project"
    sha = "a" * 40
    tag = "v1.2.3"
    digest = "b" * 64
    payload = _attestation(
        checker,
        repository=repository,
        sha=sha,
        tag=tag,
        digest=digest,
    )
    payload[0]["verificationResult"]["signature"]["certificate"][
        "sourceRepositoryRef"
    ] = "refs/heads/untrusted"
    payload.append(
        {
            **_attestation(
                checker,
                repository=repository,
                sha=sha,
                tag=tag,
                digest=digest,
            )[0],
        }
    )
    payload[1]["verificationResult"]["verifiedTimestamps"] = []

    invocations, errors = checker.verified_run_invocations(
        payload,
        asset_name="asset.bin",
        asset_sha256=digest,
        repository=repository,
        sha=sha,
        tag=tag,
    )

    assert invocations == set()
    assert any("no acceptable exact-SHA release attestation" in error for error in errors)
    assert "source repository ref" in errors[0]
    assert "no verified transparency/timestamp witness" in errors[0]


def test_verified_attestation_rejects_tag_push_for_final_promotion_assets() -> None:
    checker = _load_checker()
    repository = "example/project"
    sha = "a" * 40
    tag = "v1.2.3"
    digest = "b" * 64
    payload = _attestation(
        checker,
        repository=repository,
        sha=sha,
        tag=tag,
        digest=digest,
    )
    payload[0]["verificationResult"]["signature"]["certificate"][
        "buildTrigger"
    ] = "push"

    invocations, errors = checker.verified_run_invocations(
        payload,
        asset_name="asset.bin",
        asset_sha256=digest,
        repository=repository,
        sha=sha,
        tag=tag,
    )

    assert invocations == set()
    assert any("exact-tag release promotion dispatch" in error for error in errors)


def test_draft_transaction_metadata_allows_draft_before_single_promotion(tmp_path: Path) -> None:
    checker = _load_checker()
    repository = "example/project"
    tag = "v1.2.3"
    asset = tmp_path / "asset.bin"
    asset.write_bytes(b"asset")
    release = _release(checker, tmp_path, repository, tag)
    release["draft"] = True
    release["immutable"] = False

    assert checker.check_release_asset_bytes(
        release,
        {asset.name: asset},
        repository=repository,
        tag=tag,
        required_standard_assets={asset.name},
        expected_draft=True,
        require_immutable=False,
        expected_release_id=77,
    ) == []


def test_draft_transaction_rejects_wrong_release_id_and_asset_api_url(tmp_path: Path) -> None:
    checker = _load_checker()
    repository = "example/project"
    tag = "v1.2.3"
    asset = tmp_path / "asset.bin"
    asset.write_bytes(b"asset")
    release = _release(checker, tmp_path, repository, tag)
    release["draft"] = True
    release["immutable"] = False
    release["assets"][0]["url"] = "https://api.github.com/repos/example/project/releases/assets/999"

    errors = checker.check_release_asset_bytes(
        release,
        {asset.name: asset},
        repository=repository,
        tag=tag,
        required_standard_assets={asset.name},
        expected_draft=True,
        require_immutable=False,
        expected_release_id=78,
    )

    assert "draft release id must be 78" in errors
    assert any("draft release asset asset.bin API url" in error for error in errors)


def test_attestation_verifier_uses_exact_release_identity(monkeypatch, tmp_path: Path) -> None:
    checker = _load_checker()
    asset = tmp_path / "asset.bin"
    asset.write_bytes(b"asset")
    observed: dict[str, object] = {}

    def fake_run(args: list[str], label: str, timeout: int):
        observed.update(args=args, label=label, timeout=timeout)
        return []

    monkeypatch.setattr(checker, "run_gh_json", fake_run)

    assert (
        checker.verify_attestation(
            asset,
            repository="example/project",
            sha="a" * 40,
            tag="v1.2.3",
        )
        == []
    )
    args = observed["args"]
    assert isinstance(args, list)
    assert args[:3] == ["attestation", "verify", str(asset)]
    assert args[args.index("--repo") + 1] == "example/project"
    assert args[args.index("--signer-workflow") + 1] == (
        "example/project/.github/workflows/release-promotion.yml"
    )
    assert args[args.index("--source-digest") + 1] == "a" * 40
    assert args[args.index("--source-ref") + 1] == "refs/tags/v1.2.3"
    assert "--deny-self-hosted-runners" in args
    assert args[args.index("--predicate-type") + 1] == checker.PREDICATE_TYPE


def test_all_standard_assets_must_share_one_attesting_run() -> None:
    checker = _load_checker()
    first = checker.RunInvocation("example/project", 123, 1)
    second = checker.RunInvocation("example/project", 456, 1)

    assert checker.common_run_invocations({"a": {first, second}, "b": {second}}) == {second}
    assert checker.common_run_invocations({"a": {first}, "b": {second}}) == set()


def test_certified_inventory_scope_is_not_limited_to_standard_matrix_assets() -> None:
    source = Path("scripts/check_release_provenance.py").read_text(encoding="utf-8")

    assert "for name in sorted(local_assets):" in source
    assert "for name in sorted(standard_assets):" not in source


def test_certificate_bound_release_run_must_be_exact_and_successful() -> None:
    checker = _load_checker()
    repository = "example/project"
    sha = "a" * 40
    invocation = checker.RunInvocation(repository, 123, 2)
    run = {
        "id": 123,
        "run_attempt": 2,
        "path": ".github/workflows/release-promotion.yml@refs/tags/v1.2.3",
        "head_sha": sha,
        "head_branch": "v1.2.3",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": repository},
        "head_repository": {"full_name": repository},
    }

    assert (
        checker.check_release_run(
            run,
            invocation=invocation,
            repository=repository,
            sha=sha,
            tag="v1.2.3",
        )
        == []
    )

    run["conclusion"] = "failure"
    errors = checker.check_release_run(
        run,
        invocation=invocation,
        repository=repository,
        sha=sha,
        tag="v1.2.3",
    )
    assert any("conclusion must be 'success'" in error for error in errors)
