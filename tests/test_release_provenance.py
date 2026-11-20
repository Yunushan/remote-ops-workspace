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


@pytest.mark.parametrize(("change", "error"), [
    (None, None),
    ("digest", "does not match the independently approved candidate bytes"),
    ("size", "does not match the independently approved candidate bytes"),
    ("missing", "file sets differ"),
    ("extra", "file sets differ"),
    ("duplicate", "duplicated file record"),
    ("unsafe", "invalid or duplicated file record"),
])
def test_certification_requires_every_standard_file_from_the_reviewed_inventory(change, error) -> None:
    checker = _load_checker()
    deb = "remote-ops-workspace-v1.0.28-linux-amd64.deb"
    manifest = "remote-ops-workspace-v1.0.28-macos-arm64-native-manifest.json"
    reviewed = [
        {"files": [{"path": deb, "size": 10, "sha256": "a" * 64}]},
        {"files": [{"path": manifest, "size": 20, "sha256": "b" * 64}]},
    ]
    published = {deb: (10, "a" * 64), manifest: (20, "b" * 64)}
    if change == "digest":
        published[manifest] = (20, "c" * 64)
    elif change == "size":
        published[manifest] = (21, "b" * 64)
    elif change == "missing":
        reviewed.pop()
    elif change == "extra":
        reviewed.append({"files": [{"path": "unreviewed.bin", "size": 30, "sha256": "d" * 64}]})
    elif change == "duplicate":
        reviewed.append(reviewed[0])
    elif change == "unsafe":
        reviewed[1]["files"][0]["path"] = "../" + manifest
    if error is None:
        checker.check_published_candidate_files(reviewed, published)
    else:
        with pytest.raises(ValueError, match=error):
            checker.check_published_candidate_files(reviewed, published)


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
        ("reviewed-bytes-valid", ""),
        ("reviewed-bytes-disagree", "does not match the independently reviewed SHA-256"),
        ("mutable", "must have GitHub immutable releases enabled"),
        ("unpublished", "must not be a draft"),
        ("malformed-page", "paginated lists"),
        ("missing-standard", "published release assets missing standard files"),
        ("wrong-bytes", "digest must match downloaded bytes"),
        ("replaced-before-attestation", "statement does not contain the downloaded asset digest"),
        ("replaced-after-attestation", "local release asset changed during verification"),
        ("wrong-tag-commit", "live release tag v1.2.3 must resolve to the attested source commit"),
        ("wrong-source", "source repository digest"),
        ("failed-run", "no common certificate-bound release workflow run attempt completed successfully"),
        ("wrong-publication-time", "release publication time falls outside the successful publication step"),
        ("native-valid", ""),
        ("native-replaced-before", "local release asset changed before platform signature verification"),
        ("native-replaced-during", "local release asset changed during verification"),
        ("native-refused", "platform installer signature check failed"),
        ("native-mutable", "must have GitHub immutable releases enabled"),
    ],
)
def test_single_asset_cli_checks_the_exact_published_release(
    tmp_path: Path, monkeypatch, capsys, condition, expected_error,
) -> None:
    checker = _load_checker()
    repository, tag, sha = "example/project", "v1.2.3", "a" * 40
    native = condition.startswith("native-")
    name = "installer.exe" if native else "installer.bin"
    published = tmp_path / "published"
    published.mkdir()
    (published / name).write_bytes(b"installer")
    (published / "other.bin").write_bytes(b"other")
    asset = tmp_path / name
    asset.write_bytes(b"tampering" if condition == "wrong-bytes" else b"installer")
    release = _release(checker, published, repository, tag)
    release["published_at"] = (
        "2026-11-01T12:03:00Z" if condition == "wrong-publication-time" else "2026-11-01T12:02:00Z"
    )
    installer, other = release.pop("assets")
    if condition in {"mutable", "native-mutable"}:
        release["immutable"] = False
    if condition == "unpublished":
        release["draft"] = True
    pages: list[object] = [[other], [installer]]
    if condition == "malformed-page":
        pages = [[other], installer]
    if condition == "missing-standard":
        pages = [[installer]]
    monkeypatch.setattr(checker, "expected_release_assets", lambda _matrix, *, tag: {name, "other.bin"})

    calls: list[list[str]] = []
    signature_checks: list[list[list[str]]] = []
    signature_commands = [["local-platform-verifier", str(asset)]]
    monkeypatch.setattr(checker, "native_installer_signature_commands", lambda _asset: signature_commands)

    def platform_verify(commands):
        signature_checks.append(commands)
        assert len(calls) == 7 and asset.read_bytes() == b"installer"
        if condition == "native-refused":
            raise RuntimeError("platform installer signature check failed")
        if condition == "native-replaced-during":
            asset.write_bytes(b"replaced!")

    monkeypatch.setattr(checker, "verify_platform_signature", platform_verify)

    def fake_run(args: list[str], _label: str, _timeout: int):
        calls.append(args)
        if args == ["api", f"repos/{repository}/releases/tags/{tag}"]:
            return release
        if args == ["api", "--paginate", "--slurp", f"repos/{repository}/releases/77/assets?per_page=100"]:
            return pages
        if args == ["api", "--hostname", "github.com", f"repos/{repository}/git/ref/tags/{tag}"]:
            return {"object": {"type": "tag", "sha": "d" * 40}}
        if args == ["api", "--hostname", "github.com", f"repos/{repository}/git/tags/{'d' * 40}"]:
            return {"object": {"type": "commit", "sha": "b" * 40 if condition == "wrong-tag-commit" else sha}}
        if args[:3] == ["attestation", "verify", str(asset)]:
            if condition == "replaced-before-attestation":
                asset.write_bytes(b"replaced!")
            return _attestation(
                checker,
                repository=repository,
                sha="b" * 40 if condition == "wrong-source" else sha,
                tag=tag,
                digest=hashlib.sha256(asset.read_bytes()).hexdigest(),
            )
        if args == ["api", f"repos/{repository}/actions/runs/123/attempts/2"]:
            if condition in {"replaced-after-attestation", "native-replaced-before"}:
                asset.write_bytes(b"replaced!")
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
        if args == [
            "api", "--hostname", "github.com", "--paginate", "--slurp",
            f"repos/{repository}/actions/runs/123/attempts/2/jobs?per_page=100",
        ]:
            return [{"jobs": [{
                "name": checker.PUBLICATION_JOB,
                "run_id": 123,
                "run_attempt": 2,
                "head_sha": sha,
                "status": "completed",
                "conclusion": "success",
                "steps": [{
                    "name": checker.PUBLICATION_STEP,
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": "2026-11-01T12:01:59Z",
                    "completed_at": "2026-11-01T12:02:01Z",
                }],
            }]}]
        raise AssertionError(f"unexpected GitHub CLI arguments: {args}")

    monkeypatch.setattr(checker, "run_gh_json", fake_run)
    signature_args = ["--verify-platform-signature"] if native else []
    reviewed = None
    if condition.startswith("reviewed-bytes-"):
        reviewed = {name: "c" * 64 if condition == "reviewed-bytes-disagree"
                    else hashlib.sha256(asset.read_bytes()).hexdigest()}
    result = checker.main([
        "--asset", str(asset), "--repository", repository, "--tag", tag, "--sha", sha, *signature_args,
    ], reviewed_asset_hashes=reviewed)
    output = capsys.readouterr()
    assert signature_checks == (
        [signature_commands] if condition in {"native-valid", "native-replaced-during", "native-refused"} else []
    )
    if expected_error:
        assert result == 1
        assert expected_error in output.err
        assert output.out == ""
        if condition == "reviewed-bytes-disagree":
            assert all(call[0] != "attestation" for call in calls)
    else:
        assert result == 0
        assert f"{name} matches immutable v1.2.3" in output.out
        assert ("platform installer signature passed" in output.out) is native
        assert len(calls) == 7
        assert "--source-digest" in calls[4]
        assert f"refs/tags/{tag}" in calls[4]


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


def test_platform_signature_flag_requires_a_single_asset(capsys) -> None:
    checker = _load_checker()
    assert checker.main([
        "--assets-dir", "downloads", "--verify-platform-signature",
        "--repository", "example/project", "--tag", "v1.2.3", "--sha", "a" * 40,
    ]) == 1
    assert "--verify-platform-signature requires --asset" in capsys.readouterr().err


@pytest.mark.parametrize("suffix", [".exe", ".msi"])
def test_windows_installer_signature_uses_the_windows_sdk(monkeypatch, tmp_path, suffix) -> None:
    checker = _load_checker()
    monkeypatch.setattr(checker.sys, "platform", "win32")
    sdk_tool = tmp_path / "Windows SDK/signtool.exe"
    monkeypatch.setattr(checker, "find_windows_signtool", lambda: sdk_tool)
    installer = tmp_path / f"file with spaces{suffix}"
    assert checker.native_installer_signature_commands(installer) == [[
        str(sdk_tool), "verify", "/pa", "/all", "/tw", str(installer),
    ]]


def test_windows_sign_tool_uses_the_newest_sdk_for_the_host_architecture(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    checker = _load_checker()
    sdk = tmp_path / "Windows Kits" / "10"
    candidates = [
        sdk / "bin/10.0.9.0/x64/signtool.exe",
        sdk / "bin/10.0.10.0/x64/signtool.exe",
        sdk / "bin/10.0.11.0/x86/signtool.exe",
    ]
    for candidate in candidates:
        candidate.parent.mkdir(parents=True)
        candidate.touch()
    def missing_key(*_args, **_kwargs):
        raise FileNotFoundError

    registry = SimpleNamespace(
        KEY_WOW64_32KEY=1, KEY_WOW64_64KEY=2, KEY_READ=4, HKEY_LOCAL_MACHINE=0, OpenKey=missing_key,
    )
    monkeypatch.setitem(checker.sys.modules, "winreg", registry)
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path))
    monkeypatch.setenv("PROCESSOR_ARCHITEW6432", "AMD64")
    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "x86")
    assert checker.find_windows_signtool() == candidates[1]


@pytest.mark.parametrize(("suffix", "signature", "assessment"), [
    (".PKG", ["/usr/sbin/pkgutil", "--check-signature"], ["--type", "install"]),
    (".dmg", ["/usr/bin/codesign", "--verify", "--strict"], ["--type", "open", "--context", "context:primary-signature"]),
])
def test_macos_installer_signature_requires_signature_ticket_and_gatekeeper(monkeypatch, tmp_path, suffix, signature, assessment) -> None:
    checker = _load_checker()
    monkeypatch.setattr(checker.sys, "platform", "darwin")
    installer = tmp_path / f"file with spaces{suffix}"
    path = str(installer)
    assert checker.native_installer_signature_commands(installer) == [
        [*signature, path],
        ["/usr/bin/xcrun", "stapler", "validate", path],
        ["/usr/sbin/spctl", "--assess", *assessment, path],
    ]


@pytest.mark.parametrize(("suffix", "expected"), [
    (".exe", "verify Windows installer signatures on Windows"),
    (".dmg", "verify macOS installer signatures on macOS"),
    (".AppImage", "supports Windows EXE/MSI and macOS PKG/DMG"),
])
def test_native_installer_refuses_wrong_host_or_unsupported_format(monkeypatch, suffix, expected) -> None:
    checker = _load_checker()
    monkeypatch.setattr(checker.sys, "platform", "linux")
    with pytest.raises(ValueError, match=expected):
        checker.native_installer_signature_commands(Path(f"installer{suffix}"))


@pytest.mark.parametrize("outcome", ["pass", "warning", "timeout"])
def test_platform_signature_runner_refuses_failures_and_timeouts(monkeypatch, outcome) -> None:
    checker = _load_checker()
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs == {"stdin": checker.subprocess.DEVNULL, "capture_output": True, "check": False, "timeout": 120}
        if outcome == "timeout":
            raise checker.subprocess.TimeoutExpired(command, 120)
        return checker.subprocess.CompletedProcess(command, 2 if outcome == "warning" else 0)

    monkeypatch.setattr(checker.subprocess, "run", run)
    commands = [["first-verify"], ["second-verify"]]
    if outcome == "pass":
        checker.verify_platform_signature(commands)
        assert calls == commands
    else:
        message = "exited with 2" if outcome == "warning" else "timed out: first-verify"
        with pytest.raises(RuntimeError, match=message):
            checker.verify_platform_signature(commands)
        assert calls == commands[:1]


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


@pytest.mark.parametrize(
    ("change", "expected_error"),
    [
        ("none", None),
        ("attempt", "must bind the exact promotion run attempt"),
        ("duplicate", "must bind the exact promotion run attempt"),
        ("notes", "differ from the generated promotion notes"),
    ],
)
def test_recheck_draft_requires_original_notes_and_run_marker(
    tmp_path: Path, monkeypatch, capsys, change: str, expected_error: str | None,
) -> None:
    checker = _load_checker()
    repository, tag, sha = "example/project", "v1.2.3", "a" * 40
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "installer.bin").write_bytes(b"installer")
    notes = tmp_path / "release-notes.md"
    original_notes = "Support boundaries\n"
    notes.write_text(original_notes, encoding="utf-8")
    marker = f"<!-- remote-ops-release-transaction:{tag}:{sha}:123:1 -->"
    body = f"{original_notes}\n{marker}\n"
    if change == "attempt":
        body = body.replace(":123:1", ":123:2")
    elif change == "duplicate":
        body += marker + "\n"
    elif change == "notes":
        body = body.replace("Support boundaries", "Edited notes")
    release = _release(checker, assets, repository, tag)
    release.update(draft=True, immutable=False, body=body)

    def fake_run(args: list[str], _label: str, _timeout: int):
        if args == ["api", f"repos/{repository}/releases/77"]:
            return release
        if args == ["api", "--paginate", "--slurp", f"repos/{repository}/releases/77/assets?per_page=100"]:
            return [release["assets"]]
        raise AssertionError(f"unexpected GitHub CLI arguments: {args}")

    monkeypatch.setattr(checker, "run_gh_json", fake_run)
    monkeypatch.setattr(checker, "expected_release_assets", lambda _matrix, *, tag: {"installer.bin"})
    result = checker.main([
        "--assets-dir", str(assets), "--repository", repository, "--tag", tag, "--sha", sha,
        "--draft-release-id", "77", "--draft-transaction-run-id", "123",
        "--draft-transaction-run-attempt", "1", "--draft-release-notes", str(notes), "--recheck-draft-bytes",
    ])
    output = capsys.readouterr()
    if expected_error:
        assert result == 1 and expected_error in output.err
    else:
        assert result == 0 and "unchanged draft assets" in output.out


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


def test_release_cli_verification_targets_github_dot_com(monkeypatch) -> None:
    checker = _load_checker()
    monkeypatch.setenv("GH_HOST", "fixture.invalid")
    monkeypatch.setattr(checker.shutil, "which", lambda _: "gh")

    def fake_run(args, *, cwd, check, capture_output, text, timeout, env):
        assert args[0] == "gh"
        assert args[1] in {"api", "attestation"}
        assert env["GH_HOST"] == "github.com"
        return checker.subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    monkeypatch.setattr(checker.subprocess, "run", fake_run)
    assert checker.run_gh_json(["api", "repos/example/project"], "release API", 60) == {}
    assert checker.verify_attestation(Path("asset.bin"), repository="example/project", sha="a" * 40, tag="v1.2.3") == {}


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
    asset = root / f"remote-ops-workspace-{tag}-linux-amd64.deb"
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
    reviewer = Ed25519PrivateKey.generate()
    policy.write_text(
        json.dumps({
            "trusted_ed25519_keys": [{
                "key_id": "reviewer",
                "public_key": base64.b64encode(reviewer.public_key().public_bytes_raw()).decode(),
            }],
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
    publish_step = {
        "name": "Publish verified draft by numeric ID once",
        "status": "completed",
        "conclusion": "success",
        "started_at": "2026-11-01T12:02:00.250Z",
        "completed_at": "2026-11-01T12:02:01.750Z",
    }
    publish_job = {
        "name": "promote-production-release",
        "run_id": 123,
        "run_attempt": 1,
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
        "steps": [publish_step],
    }
    job_pages = [{"jobs": []}, {"jobs": [publish_job]}]

    def gh_api(args: list[str], _label: str, _timeout: int):
        endpoint = args[-1]
        if endpoint in {f"repos/{repository}/releases/tags/{tag}", f"repos/{repository}/releases/77"}:
            return release
        if endpoint == f"repos/{repository}/releases/77/assets?per_page=100":
            return [release["assets"]]
        if endpoint == f"repos/{repository}/git/ref/tags/{tag}":
            return {"object": {"type": "commit", "sha": sha}}
        if endpoint == f"repos/{repository}/actions/runs/123/attempts/1/jobs?per_page=100":
            assert args[:-1] == ["api", "--hostname", "github.com", "--paginate", "--slurp"]
            return job_pages
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
        completed_args = [*args, "--published-release-id", "77", "--completed-promotion-run-id", "123"]
        assert checker.main(completed_args) == 1
        assert checker.main([*completed_args, "--completed-promotion-run-attempt", "1"]) == 0
        assert checker.main([*completed_args, "--completed-promotion-run-attempt", "2"]) == 1
        assert "do not share the triggering promotion" in capsys.readouterr().err
        with monkeypatch.context() as native:
            def rejected_native_manifest(assets, names, *, native_release_channel):
                assert (assets, names, native_release_channel) == (root, {asset.name}, "production-signed")
                return ["stapled package not bound to its Apple notarization receipt"]

            native.setattr(checker, "check_native_release_signing_metadata", rejected_native_manifest)
            assert checker.main([*completed_args, "--completed-promotion-run-attempt", "1"]) == 1
            assert "not bound to its Apple notarization receipt" in capsys.readouterr().err
        approved = tmp_path / "release-evidence.json"
        approved_sig = tmp_path / "release-evidence.sig.json"

        def write_approval(expires_at, candidate=None):
            approval = {
                "schema_version": 1,
                "decision": "approved",
                "repository": repository,
                "release_tag": tag,
                "release_sha": sha,
                "policy_sha256": checker.sha256_file(policy),
                "reviewed_at": "2026-11-01T11:00:00Z",
                "expires_at": expires_at,
            }
            if candidate is not None:
                approval["candidate_inventory"] = {
                    "reference": "attested sealed candidate inventory",
                    "file": candidate.name,
                    "size_bytes": candidate.stat().st_size,
                    "sha256": checker.sha256_file(candidate),
                }
            approved.write_text(json.dumps(approval), encoding="utf-8")
            approved_sig.write_text(json.dumps({
                "schema_version": 1,
                "algorithm": "ed25519",
                "key_id": "reviewer",
                "signature": base64.b64encode(reviewer.sign(approved.read_bytes())).decode(),
            }), encoding="utf-8")

        write_approval("2026-11-01T12:02:30Z")
        inputs = {path: checker.sha256_file(path) for path in (approved, approved_sig)}
        assert checker.main(args, audited_inputs=inputs) == 0
        # The compliance caller has already authenticated this exact policy.
        # The standalone verifier's tracked default has no enrolled auditor.
        selected_policy = checker.read_json_object(policy, "selected policy")
        with monkeypatch.context() as custom:
            custom.setattr(checker, "POLICY_PATH", Path("configs/release_compliance_policy.json"))
            assert checker.main(args, audited_inputs=inputs) == 1
            assert "tag governance attestation policy is not enforced" in capsys.readouterr().err
            assert checker.main(
                args, audited_inputs=inputs, check_published_at=lambda _time: [],
                audited_policy=selected_policy,
            ) == 0
            assert checker.main(args, audited_policy=selected_policy) == 1
            assert "audited policy requires a delegated compliance audit" in capsys.readouterr().err
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
        exact_completed = [*completed_args, "--completed-promotion-run-attempt", "1", *approval_args]
        assert checker.main([*current_args, *approval_args]) == 0
        assert checker.main(exact_completed) == 0
        assert checker.main([*current_args, *approval_args[:2]]) == 1
        assert checker.main([*args, *approval_args]) == 1
        monkeypatch.setattr(checker, "verify_attestation", mismatched_input_attempt)
        assert checker.main([*current_args, *approval_args]) == 1
        assert "signed redistribution approval must share" in capsys.readouterr().err
        monkeypatch.setattr(checker, "verify_attestation", attestation_api)

        prior_policy = policy.read_bytes()
        debian_policy = {**json.loads(prior_policy), "production_targets": ["linux-x86_64"]}
        policy.write_text(json.dumps(debian_policy), encoding="utf-8")
        candidate = tmp_path / "release-candidate-inventory.json"
        candidate.write_text('{"sealed_candidate_fixture": true}', encoding="utf-8")
        write_approval("2026-11-01T12:02:30Z", candidate)
        qualified = []

        def verify_exact_deb(value, **kwargs):
            assert value == {"sealed_candidate_fixture": True}
            qualified.append(kwargs)
            return [{"files": [{"path": asset.name, "size": asset.stat().st_size, "sha256": checker.sha256_file(asset)}]}]

        monkeypatch.setattr(checker, "validate_managed_release_qualification", verify_exact_deb)
        assert checker.main(exact_completed) == 1
        assert "audited candidate inventory is required" in capsys.readouterr().err
        candidate_args = [*exact_completed, "--candidate-inventory", str(candidate)]
        assert checker.main(candidate_args) == 0
        assert qualified == [{
            "repository": repository, "release_tag": tag, "release_sha": sha,
            "deb_sha256": checker.sha256_file(asset),
        }]

        package = root / f"remote-ops-workspace-{tag}-macos-arm64.pkg"
        package.write_bytes(b"alternate package with valid GitHub provenance")
        original_assets = release["assets"]
        release["assets"] = _release(checker, root, repository, tag)["assets"]
        with monkeypatch.context() as alternate:
            alternate.setattr(checker, "expected_release_assets", lambda *_args, **_kwargs: {asset.name, package.name})

            def previously_reviewed_candidate(value, **kwargs):
                records = verify_exact_deb(value, **kwargs)
                records.append({"files": [{"path": package.name, "size": package.stat().st_size, "sha256": "f" * 64}]})
                return records

            alternate.setattr(checker, "validate_managed_release_qualification", previously_reviewed_candidate)
            assert checker.main(candidate_args) == 1
            assert f"published standard asset {package.name} does not match" in capsys.readouterr().err
        package.unlink()
        release["assets"] = original_assets

        def candidate_attested_by_other_attempt(path: Path, **kwargs):
            if path == candidate:
                return _attestation(
                    checker, repository=repository, sha=sha, tag=tag,
                    digest=checker.sha256_file(path), attempt=2,
                )
            return attestation_api(path, **kwargs)

        monkeypatch.setattr(checker, "verify_attestation", candidate_attested_by_other_attempt)
        assert checker.main(candidate_args) == 1
        assert "must share the successful promotion attempt" in capsys.readouterr().err
        monkeypatch.setattr(checker, "verify_attestation", attestation_api)
        candidate.write_text("{}", encoding="utf-8")
        assert checker.main(candidate_args) == 1
        assert "does not match the signed redistribution approval" in capsys.readouterr().err
        policy.write_bytes(prior_policy)

        write_approval("2026-11-01T12:01:59Z")
        assert checker.main(exact_completed) == 1
        assert "expired" in capsys.readouterr().err
        publish_step["started_at"] = "2026-11-01T12:02:01.250Z"
        assert checker.main(args, check_published_at=check_approval) == 1
        assert publication_times == ["2026-11-01T12:02:00+00:00"]
        assert "release publication time falls outside the successful publication step" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("wrong-run", "successful exact-source promotion attempt"),
        ("wrong-attempt", "successful exact-source promotion attempt"),
        ("boolean-attempt", "successful exact-source promotion attempt"),
        ("wrong-source", "successful exact-source promotion attempt"),
        ("duplicate-step", "one exact publication step"),
        ("missing-step", "one exact publication step"),
        ("failed-step", "publication step must have completed successfully"),
        ("published-after-step", "release publication time falls outside the successful publication step"),
    ],
)
def test_publication_requires_the_exact_successful_step(monkeypatch, mutation, error) -> None:
    checker = _load_checker()
    sha = "a" * 40
    invocation = checker.RunInvocation("example/project", 123, 1)
    release = {"published_at": "2026-11-01T12:02:00Z"}
    step = {
        "name": "Publish verified draft by numeric ID once",
        "status": "completed",
        "conclusion": "success",
        "started_at": "2026-11-01T12:01:58Z",
        "completed_at": "2026-11-01T12:02:01Z",
    }
    job = {
        "name": "promote-production-release",
        "run_id": 123,
        "run_attempt": 1,
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
        "steps": [step],
    }
    if mutation == "wrong-run":
        job["run_id"] = 999
    elif mutation == "wrong-attempt":
        job["run_attempt"] = 2
    elif mutation == "boolean-attempt":
        job["run_attempt"] = True
    elif mutation == "wrong-source":
        job["head_sha"] = "b" * 40
    elif mutation == "duplicate-step":
        job["steps"] = [step, step.copy()]
    elif mutation == "missing-step":
        job["steps"] = []
    elif mutation == "failed-step":
        step["conclusion"] = "failure"
    elif mutation == "published-after-step":
        release["published_at"] = "2026-11-01T12:02:02Z"
    monkeypatch.setattr(checker, "run_gh_json", lambda *_args: [{"jobs": [job]}])
    assert error in checker.check_publication_in_run(release, invocation, sha)[0]
