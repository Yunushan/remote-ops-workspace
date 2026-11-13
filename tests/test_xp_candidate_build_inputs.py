from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest


def load_checker(monkeypatch):
    scripts = Path("scripts").resolve()
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "check_xp_candidate_build_inputs", scripts / "check_xp_candidate_build_inputs.py"
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
