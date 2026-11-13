from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest


def load_checker(monkeypatch, name="check_xp_candidate_build_inputs"):
    scripts = Path("scripts").resolve()
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        name, scripts / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (None, None),
        (("run_attempt", 2), "successful exact-tag build attempt"),
        (("head_sha", "2" * 40), "successful exact-tag build attempt"),
        (("event", "workflow_dispatch"), "successful exact-tag build attempt"),
        (("path", ".github/workflows/ci.yml"), "legacy candidate workflow"),
        (("repository", {"full_name": "elsewhere/project"}), "different repository"),
    ],
)
def test_xp_candidate_authenticates_exact_github_run(monkeypatch, change, expected) -> None:
    checker = load_checker(monkeypatch, "check_xp_candidate_run")
    run = {
        "id": 100,
        "run_attempt": 1,
        "event": "push",
        "head_branch": "v1.2.3",
        "head_sha": "1" * 40,
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "example/project"},
        "path": ".github/workflows/xp-legacy-candidate.yml@refs/tags/v1.2.3",
    }
    if change:
        key, value = change
        run[key] = value
    kwargs = {"repository": "example/project", "tag": "v1.2.3", "sha": "1" * 40, "run_id": 100, "attempt": 1}
    if expected:
        with pytest.raises(ValueError, match=expected):
            checker.check_run(run, **kwargs)
    else:
        checker.check_run(run, **kwargs)


@pytest.mark.parametrize("matches", [True, False])
def test_xp_candidate_resolves_annotated_tag(monkeypatch, matches: bool) -> None:
    checker = load_checker(monkeypatch, "check_xp_candidate_run")
    expected = "1" * 40
    annotated = "2" * 40
    responses = {
        "git/ref/tags/v1.2.3": {
            "ref": "refs/tags/v1.2.3",
            "object": {"type": "tag", "sha": annotated},
        },
        f"git/tags/{annotated}": {
            "object": {"type": "commit", "sha": expected if matches else "3" * 40},
        },
    }

    class Client:
        def json(self, endpoint):
            return responses[endpoint]

    if matches:
        checker.check_tag(Client(), "v1.2.3", expected)
    else:
        with pytest.raises(ValueError, match="does not resolve to the expected source SHA"):
            checker.check_tag(Client(), "v1.2.3", expected)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (None, None),
        (("created_at", "2026-11-13T14:00:00Z"), "outside the candidate job window"),
        (("digest", "sha256:" + "2" * 64), "does not match the GitHub archive bytes"),
        (("workflow_run", {"id": 101, "head_sha": "1" * 40}), "not bound to the approved build run"),
    ],
)
def test_xp_candidate_authenticates_archive_bytes(tmp_path, monkeypatch, change, expected) -> None:
    checker = load_checker(monkeypatch, "check_xp_candidate_run")
    path = tmp_path / "candidate.zip"
    path.write_bytes(b"fixture archive bytes")
    metadata = {
        "id": 50,
        "name": "windows-xp-legacy-candidate-x64-1",
        "expired": False,
        "digest": f"sha256:{digest(path.read_bytes())}",
        "size_in_bytes": path.stat().st_size,
        "created_at": "2026-11-13T15:05:00Z",
        "workflow_run": {"id": 100, "head_sha": "1" * 40},
    }
    if change:
        key, value = change
        metadata[key] = value

    class Client:
        def json(self, endpoint):
            assert endpoint == "actions/artifacts/50"
            return metadata

    kwargs = {
        "artifact_id": 50, "name": "windows-xp-legacy-candidate-x64-1",
        "run_id": 100, "sha": "1" * 40, "started": datetime(2026, 11, 13, 15, tzinfo=timezone.utc),
        "ended": datetime(2026, 11, 13, 15, 10, tzinfo=timezone.utc),
    }
    if expected:
        with pytest.raises(ValueError, match=expected):
            checker.verify_archive(Client(), path, **kwargs)
    else:
        checker.verify_archive(Client(), path, **kwargs)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("", ""),
        ("attempt", "build receipt run_attempt does not match"),
        ("archive", "build receipt archive_sha256 does not match"),
        ("reference", "build receipt reference_assemblies does not match"),
        ("executable", "build receipt executable digest does not match"),
        ("architecture", "does not have the expected x64 PE headers"),
        ("extra", "must contain exactly the executable"),
    ],
)
def test_build_receipt_matches_exact_xp_candidate(
    tmp_path: Path, monkeypatch, change: str, expected: str,
) -> None:
    checker = load_checker(monkeypatch)
    assets = tmp_path / "candidate"
    assets.mkdir()
    tag = f"v{checker.read_project_version()}"
    base = f"remote-ops-workspace-{tag}-windows-xp-x64-native"
    archive = assets / f"{base}.zip"
    manifest = assets / f"{base}-manifest.json"
    exe = bytearray(90)
    exe[:2] = b"MZ"
    exe[60:64] = (64).to_bytes(4, "little")
    exe[64:70] = b"PE\0\0\x64\x86"
    exe[88:90] = b"\x0b\x02"
    if change == "architecture":
        exe[68:70] = b"\x4c\x01"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("bin/row-xp-host.exe", bytes(exe))
        bundle.writestr("README_XP.txt", "XP companion")
        for name in ("LICENSE", "NOTICE"):
            bundle.writestr(f"docs/{name}", (checker.ROOT / name).read_bytes())
        if change == "extra":
            bundle.writestr("bin/extra.dll", "unexpected runtime")
    manifest.write_text(json.dumps([{
        "file": archive.name,
        "architecture": "x64",
        "format": "zip",
        "size_bytes": archive.stat().st_size,
        "sha256": digest(archive.read_bytes()),
    }]), encoding="utf-8")
    (assets / f"{base}-SHA256SUMS.txt").write_text(
        f"{digest(archive.read_bytes())}  {archive.name}\n"
        f"{digest(manifest.read_bytes())}  {manifest.name}\n", encoding="utf-8",
    )
    identity = {
        "repository": "example/project",
        "tag": tag,
        "source_ref": f"refs/tags/{tag}",
        "source_sha": "1" * 40,
        "run_id": "100",
        "run_attempt": "1",
    }
    lock_file = checker.ROOT / "legacy/xp_host/net40-references.json"
    lock = json.loads(lock_file.read_bytes())
    source = checker.ROOT / "legacy/xp_host/RemoteOpsXpHost.template.cs"
    record = {
        **{key: value for key, value in identity.items() if key != "tag"},
        "schema_version": 1,
        "target": "windows-xp-native-x64",
        "release_tag": tag,
        "compiler": {"name": "csc.exe", "file_version": "4.8", "sha256": "2" * 64},
        "reference_lock_sha256": digest(lock_file.read_bytes()),
        "reference_package": lock["package"],
        "reference_package_version": lock["version"],
        "reference_package_sha256": lock["sha256"],
        "reference_assemblies": lock["assemblies"],
        "generated_source_sha256": digest(source.read_text(encoding="utf-8").replace("@VERSION@", tag[1:]).encode()),
        "executable_sha256": digest(exe),
        "archive_sha256": digest(archive.read_bytes()),
        "native_manifest_sha256": digest(manifest.read_bytes()),
    }
    corrupt = {
        "attempt": ("run_attempt", "2"),
        "archive": ("archive_sha256", "3" * 64),
        "reference": ("reference_assemblies", {}),
        "executable": ("executable_sha256", "4" * 64),
    }
    if change in corrupt:
        key, replacement = corrupt[change]
        record[key] = replacement
    receipt = tmp_path / "xp-build-inputs.json"
    receipt.write_text(json.dumps(record), encoding="utf-8")

    errors = checker.check_build_inputs(receipt, assets, arch="x64", **identity)

    if expected:
        assert any(expected in error for error in errors)
    else:
        assert errors == []
