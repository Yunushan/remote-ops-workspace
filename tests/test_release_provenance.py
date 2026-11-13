from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


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


@pytest.mark.parametrize(
    ("condition", "expected_error"),
    [
        ("valid", ""),
        ("mutable", "must have GitHub immutable releases enabled"),
        ("unpublished", "must not be a draft"),
        ("malformed-page", "paginated lists"),
        ("missing-standard", "published release assets missing standard files"),
        ("wrong-bytes", "digest must match downloaded bytes"),
        ("wrong-source", "source repository digest"),
        ("failed-run", "no common certificate-bound release workflow run attempt completed successfully"),
    ],
)
def test_single_asset_cli_checks_the_exact_published_release(
    tmp_path: Path, monkeypatch, capsys, condition, expected_error,
) -> None:
    checker = _load_checker()
    repository, tag, sha = "example/project", "v1.2.3", "a" * 40
    published = tmp_path / "published"
    published.mkdir()
    (published / "installer.bin").write_bytes(b"installer")
    (published / "other.bin").write_bytes(b"other")
    asset = tmp_path / "installer.bin"
    asset.write_bytes(b"tampering" if condition == "wrong-bytes" else b"installer")
    release = _release(checker, published, repository, tag)
    installer, other = release.pop("assets")
    if condition == "mutable":
        release["immutable"] = False
    if condition == "unpublished":
        release["draft"] = True
    pages: list[object] = [[other], [installer]]
    if condition == "malformed-page":
        pages = [[other], installer]
    if condition == "missing-standard":
        pages = [[installer]]
    monkeypatch.setattr(checker, "expected_release_assets", lambda _matrix, *, tag: {"installer.bin", "other.bin"})

    calls: list[list[str]] = []

    def fake_run(args: list[str], _label: str, _timeout: int):
        calls.append(args)
        if args == ["api", f"repos/{repository}/releases/tags/{tag}"]:
            return release
        if args == ["api", "--paginate", "--slurp", f"repos/{repository}/releases/77/assets?per_page=100"]:
            return pages
        if args[:3] == ["attestation", "verify", str(asset)]:
            return _attestation(
                checker,
                repository=repository,
                sha="b" * 40 if condition == "wrong-source" else sha,
                tag=tag,
                digest=hashlib.sha256(b"installer").hexdigest(),
            )
        if args == ["api", f"repos/{repository}/actions/runs/123/attempts/2"]:
            return {
                "id": 123,
                "run_attempt": 2,
                "path": f"{checker.RELEASE_WORKFLOW}@refs/tags/{tag}",
                "head_sha": sha,
                "head_branch": tag,
                "event": "workflow_dispatch",
                "status": "completed",
                "conclusion": "failure" if condition == "failed-run" else "success",
                "repository": {"full_name": repository},
                "head_repository": {"full_name": repository},
            }
        raise AssertionError(f"unexpected GitHub CLI arguments: {args}")

    monkeypatch.setattr(checker, "run_gh_json", fake_run)
    result = checker.main(["--asset", str(asset), "--repository", repository, "--tag", tag, "--sha", sha])
    output = capsys.readouterr()
    if expected_error:
        assert result == 1
        assert expected_error in output.err
        assert output.out == ""
    else:
        assert result == 0
        assert "installer.bin matches immutable v1.2.3" in output.out
        assert len(calls) == 4
        assert "--source-digest" in calls[2]
        assert f"refs/tags/{tag}" in calls[2]


def test_single_asset_mode_rejects_draft_transactions_before_contacting_github(capsys) -> None:
    checker = _load_checker()
    result = checker.main([
        "--asset", "installer.bin",
        "--repository", "example/project",
        "--tag", "v1.2.3",
        "--sha", "a" * 40,
        "--draft-release-id", "77",
        "--draft-transaction-run-id", "123",
        "--draft-transaction-run-attempt", "1",
    ])
    assert result == 1
    assert "requires a completed published release" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["draft", "published-transaction", "published"])
def test_complete_inventory_rejects_unapproved_asset_on_a_later_api_page(
    tmp_path: Path, monkeypatch, capsys, mode: str,
) -> None:
    checker = _load_checker()
    repository, tag, sha = "example/project", "v1.2.3", "a" * 40
    published = tmp_path / "published"
    published.mkdir()
    (published / "installer.bin").write_bytes(b"installer")
    (published / "unexpected.bin").write_bytes(b"unexpected")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "installer.bin").write_bytes(b"installer")
    release = _release(checker, published, repository, tag)
    expected, unexpected = release["assets"]
    release["assets"] = [expected]
    endpoint = f"repos/{repository}/releases/77"
    transaction_args: list[str] = []
    if mode == "draft":
        release.update(draft=True, immutable=False)
        transaction_args = [
            "--draft-release-id", "77",
            "--draft-transaction-run-id", "123",
            "--draft-transaction-run-attempt", "1",
        ]
    elif mode == "published-transaction":
        transaction_args = [
            "--published-release-id", "77",
            "--current-transaction-run-id", "123",
            "--current-transaction-run-attempt", "1",
        ]
    else:
        endpoint = f"repos/{repository}/releases/tags/{tag}"
    monkeypatch.setattr(checker, "expected_release_assets", lambda _matrix, *, tag: {"installer.bin"})
    calls: list[list[str]] = []
    pages = ["api", "--paginate", "--slurp", f"repos/{repository}/releases/77/assets?per_page=100"]

    def fake_run(args: list[str], _label: str, _timeout: int):
        calls.append(args)
        if args == ["api", endpoint]:
            return release
        if args == pages:
            return [[expected], [unexpected]]
        raise AssertionError(f"unexpected GitHub CLI arguments: {args}")

    monkeypatch.setattr(checker, "run_gh_json", fake_run)
    result = checker.main([
        "--assets-dir", str(downloads), "--repository", repository, "--tag", tag, "--sha", sha,
        *transaction_args,
    ])
    output = capsys.readouterr()
    assert result == 1
    assert "downloaded release directory missing published files: ['unexpected.bin']" in output.err
    assert output.out == ""
    assert calls == [["api", endpoint], pages]


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


@pytest.mark.parametrize(
    ("published_at", "signature_attempt", "expected_error"),
    [
        ("2026-11-01T12:02:00Z", 1, None),
        ("2026-11-01T12:05:00Z", 1, "tag governance attestation has expired"),
        ("2026-11-01T11:59:59Z", 1, "observed_at must not be in the future"),
        ("2026-11-01T12:02:00Z", 2, "governance proof and signature must bind"),
    ],
)
def test_published_governance_uses_live_time_and_common_signed_attempt(
    tmp_path: Path, monkeypatch, capsys, published_at: str, signature_attempt: int, expected_error: str | None
) -> None:
    checker = _load_checker()
    repository, tag, sha = "example/project", "v1.2.3", "a" * 40
    root = tmp_path / "release-assets"
    root.mkdir()
    asset = root / "release.bin"
    asset.write_bytes(b"release asset")
    release = {**_release(checker, root, repository, tag), "published_at": published_at}
    attestation = tmp_path / "governance.json"
    attestation.write_text(
        json.dumps({
            "schema_version": 1,
            "decision": "approved",
            "source": "github-rulesets-api",
            "repository": repository,
            "release_tag": tag,
            "release_sha": sha,
            "tag_update_blocked": True,
            "tag_deletion_blocked": True,
            "bypass_actors": [],
            "ruleset_ids": [42],
            "auditor": {"kind": "github-app", "identity": "fixture-auditor"},
            "observed_at": "2026-11-01T12:00:00Z",
            "expires_at": "2026-11-01T12:05:00Z",
            "promotion_transaction": {
                "run_id": 123,
                "run_attempt": 1,
                "operation": "publish",
                "draft_release_id": 77,
            },
        }),
        encoding="utf-8",
    )
    signer = Ed25519PrivateKey.generate()
    signature = tmp_path / "governance.sig.json"
    signature.write_text(
        json.dumps({
            "schema_version": 1,
            "algorithm": "ed25519",
            "key_id": "auditor",
            "signature": base64.b64encode(signer.sign(attestation.read_bytes())).decode(),
        }),
        encoding="utf-8",
    )
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({
            "tag_governance_attestation": {
                "state": "enforced",
                "max_validity_seconds": 300,
                "trusted_ed25519_keys": [{
                    "key_id": "auditor",
                    "public_key": base64.b64encode(signer.public_key().public_bytes_raw()).decode(),
                }],
            },
        }),
        encoding="utf-8",
    )
    run = {
        "id": 123,
        "run_attempt": 1,
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
        "path": f"{checker.RELEASE_WORKFLOW}@refs/tags/{tag}",
        "event": "workflow_dispatch",
        "head_branch": tag,
        "repository": {"full_name": repository},
        "head_repository": {"full_name": repository},
        "run_started_at": "2026-11-01T12:00:30Z",
        "updated_at": "2026-11-01T12:04:00Z",
    }

    def gh_api(args: list[str], _label: str, _timeout: int):
        endpoint = args[-1]
        if endpoint in {f"repos/{repository}/releases/tags/{tag}", f"repos/{repository}/releases/77"}:
            return release
        if endpoint == f"repos/{repository}/releases/77/assets?per_page=100":
            return [release["assets"]]
        assert endpoint == f"repos/{repository}/actions/runs/123/attempts/1"
        return run

    def attestation_api(path: Path, **_kwargs):
        return _attestation(
            checker, repository=repository, sha=sha, tag=tag, digest=checker.sha256_file(path),
            attempt=signature_attempt if path == signature else 1,
        )

    monkeypatch.setattr(checker, "POLICY_PATH", policy)
    monkeypatch.setattr(checker, "expected_release_assets", lambda *_args, **_kwargs: {asset.name})
    monkeypatch.setattr(checker, "run_gh_json", gh_api)
    monkeypatch.setattr(checker, "verify_attestation", attestation_api)
    args = [
        "--assets-dir", str(root), "--repository", repository, "--sha", sha, "--tag", tag,
        "--governance-attestation", str(attestation), "--governance-signature", str(signature),
    ]

    if expected_error:
        assert checker.main(args) == 1
        assert expected_error in capsys.readouterr().err
    else:
        assert checker.main(args) == 0
        approved = tmp_path / "release-evidence.json"
        approved.write_bytes(b'{"decision":"approved"}')
        approved_sig = tmp_path / "release-evidence.sig.json"
        approved_sig.write_bytes(b'{"signature":"fixture"}')
        inputs = {path: checker.sha256_file(path) for path in (approved, approved_sig)}
        assert checker.main(args, audited_inputs=inputs) == 0
        assert checker.main(args, audited_inputs={**inputs, approved_sig: "b" * 64}) == 1

        def mismatched_input_attempt(path: Path, **kwargs):
            if path == approved_sig:
                return _attestation(
                    checker, repository=repository, sha=sha, tag=tag,
                    digest=checker.sha256_file(path), attempt=2,
                )
            return attestation_api(path, **kwargs)

        monkeypatch.setattr(checker, "verify_attestation", mismatched_input_attempt)
        assert checker.main(args, audited_inputs=inputs) == 1
        assert "signed redistribution approval must share" in capsys.readouterr().err
        monkeypatch.setattr(checker, "verify_attestation", attestation_api)
        publication_times = []

        def check_approval(published):
            publication_times.append(published.isoformat())
            from check_release_license_compliance import check_review_window

            return check_review_window(
                {
                    "reviewed_at": "2026-11-01T11:00:00Z",
                    "expires_at": "2026-11-01T12:02:30Z",
                },
                now=published,
            )

        assert checker.main(args, check_published_at=check_approval) == 0
        assert publication_times == ["2026-11-01T12:02:00+00:00"]
        assert checker.main(args, check_published_at=lambda _published: ["approval expired at publication"]) == 1
        assert "approval expired at publication" in capsys.readouterr().err
        current_args = [
            *args, "--published-release-id", "77",
            "--current-transaction-run-id", "123", "--current-transaction-run-attempt", "1",
        ]
        assert checker.main(current_args) == 0
        approval_args = ["--redistribution-evidence", str(approved), "--redistribution-signature", str(approved_sig)]
        assert checker.main([*current_args, *approval_args]) == 0
        assert checker.main([*current_args, *approval_args[:2]]) == 1
        assert checker.main([*args, *approval_args]) == 1
        monkeypatch.setattr(checker, "verify_attestation", mismatched_input_attempt)
        assert checker.main([*current_args, *approval_args]) == 1
        assert "signed redistribution approval must share" in capsys.readouterr().err
        monkeypatch.setattr(checker, "verify_attestation", attestation_api)
        run["run_started_at"] = "2026-11-01T12:03:00Z"
        assert checker.main(args, check_published_at=check_approval) == 1
        assert publication_times == ["2026-11-01T12:02:00+00:00"]
        assert "release publication time falls outside" in capsys.readouterr().err
