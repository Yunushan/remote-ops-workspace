from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import sys
import zipfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def test_xp_native_evidence_bundle_packages_valid_x86_evidence(tmp_path: Path) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    assets = tmp_path / "native-dist" / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x86", "SP3", tag, names)
    evidence_root = tmp_path / "evidence" / target / tag
    _attach_smoke_evidence_files(evidence_root, evidence_data)
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets, work_root=tmp_path)
    out_dir = tmp_path / "xp-evidence-output" / target / tag

    with _pushd(tmp_path):
        errors = bundler.make_xp_native_evidence_bundle(
            target=target,
            evidence=evidence.relative_to(tmp_path),
            candidate_record=candidate.relative_to(tmp_path),
            assets_dir=assets.relative_to(tmp_path),
            evidence_dir=evidence_root.relative_to(tmp_path),
            out_dir=out_dir.relative_to(tmp_path),
        )

    assert errors == []
    manifest = out_dir / f"xp-native-evidence-bundle-{target}-{tag}.json"
    archive = out_dir / f"xp-native-evidence-bundle-{target}-{tag}.zip"
    sidecar = out_dir / f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["target"] == target
    assert data["release_tag"] == tag
    assert data["bundle_type"] == "windows-xp-native-host-evidence"
    assert data["host_identity"] == evidence_data["host_identity"]
    assert data["candidate_record"]["file"] == candidate.name
    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
    assert data["release_asset_urls"] == candidate_data["release_asset_urls"]
    assert data["workflow"] == candidate_data["workflow"]
    assert data["workflow_inputs"] == candidate_data["workflow_inputs"]
    assert data["release_asset_source"] == candidate_data["release_asset_source"]
    assert data["xp_evidence_sources"] == candidate_data["xp_evidence_sources"]
    assert data["validated_commands"] == [
        (
            "python scripts/check_xp_native_evidence.py "
            f"--evidence {evidence.relative_to(tmp_path).as_posix()} "
            f"--assets-dir {assets.relative_to(tmp_path).as_posix()} "
            f"--evidence-dir {evidence_root.relative_to(tmp_path).as_posix()}"
        ),
        (
            "python scripts/check_platform_promotion_artifacts.py "
            f"--target {target} --assets-dir {assets.relative_to(tmp_path).as_posix()} --tag {tag} --strict"
        ),
        candidate_data["local_evidence_preflight_command"],
        candidate_data["staged_upload_command"],
        "python scripts/check_platform_verified_evidence.py",
    ]
    assert all("<" not in command and ">" not in command for command in data["validated_commands"])
    assert len(data["artifacts"]) == len(names)
    assert {item["id"] for item in data["smoke_evidence"]} == {
        "cli_launch",
        "gui_or_legacy_host_ui_launch",
        "loopback_profile_dry_run",
        "artifact_manifest_validation",
        "legacy_crypto_profile_scoped",
        "modern_defaults_unchanged",
    }
    with zipfile.ZipFile(archive) as zipped:
        names_in_archive = set(zipped.namelist())
        assert "xp-evidence.json" in names_in_archive
        assert candidate.name in names_in_archive
        assert manifest.name in names_in_archive
        assert "xp-smoke-evidence/cli_launch.txt" in names_in_archive
        assert set(names).issubset(names_in_archive)
        assert_zip_entries_are_regular_files(zipped)
    assert f"{_sha256(manifest)}  {manifest.name}" in sidecar.read_text(encoding="utf-8")
    assert f"{_sha256(archive)}  {archive.name}" in sidecar.read_text(encoding="utf-8")


def test_xp_native_evidence_bundle_rejects_ambiguous_archive_entry_names() -> None:
    bundler = _load_bundle_script()

    errors = bundler.check_bundle_archive_entry_names(
        [
            "xp-evidence.json",
            "xp-evidence.json",
            "Readme.txt",
            "readme.txt",
            "xp-smoke-evidence",
            "xp-smoke-evidence/cli_launch.txt",
            "../escape.txt",
        ],
        label="XP archive",
    )

    assert "XP archive entries must be unique; duplicate entries: ['xp-evidence.json']" in errors
    assert "XP archive entries must use safe relative paths: ['../escape.txt']" in errors
    assert (
        "XP archive entries must not collide on case-insensitive filesystems: "
        "['Readme.txt', 'readme.txt']"
    ) in errors
    assert (
        "XP archive entries must not contain file/path-prefix collisions: "
        "['xp-smoke-evidence -> xp-smoke-evidence/cli_launch.txt']"
    ) in errors


def test_xp_native_evidence_bundle_rejects_duplicate_final_archive_entry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    assets = tmp_path / "native-dist" / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x86", "SP3", tag, names)
    evidence_root = tmp_path / "evidence" / target / tag
    _attach_smoke_evidence_files(evidence_root, evidence_data)
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets, work_root=tmp_path)
    out_dir = tmp_path / "xp-evidence-output" / target / tag
    monkeypatch.setattr(bundler, "artifact_records", lambda _assets_dir: [{"file": "xp-evidence.json"}])

    with _pushd(tmp_path):
        errors = bundler.make_xp_native_evidence_bundle(
            target=target,
            evidence=evidence.relative_to(tmp_path),
            candidate_record=candidate.relative_to(tmp_path),
            assets_dir=assets.relative_to(tmp_path),
            evidence_dir=evidence_root.relative_to(tmp_path),
            out_dir=out_dir.relative_to(tmp_path),
        )

    assert errors == [
        "XP native evidence bundle archive entries must be unique; "
        "duplicate entries: ['xp-evidence.json']"
    ]


def test_xp_native_evidence_bundle_reruns_local_protected_goal_preflight(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    assets = tmp_path / "native-dist" / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x86", "SP3", tag, names)
    evidence_root = tmp_path / "evidence" / target / tag
    _attach_smoke_evidence_files(evidence_root, evidence_data)
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets, work_root=tmp_path)
    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
    calls: list[dict[str, Any]] = []

    def fail_preflight(**kwargs):
        calls.append(kwargs)
        return ["sentinel local preflight failure"]

    monkeypatch.setattr(bundler, "check_local_protected_goal_preflight", fail_preflight)

    with _pushd(tmp_path):
        errors = bundler.make_xp_native_evidence_bundle(
            target=target,
            evidence=evidence.relative_to(tmp_path),
            candidate_record=candidate.relative_to(tmp_path),
            assets_dir=assets.relative_to(tmp_path),
            evidence_dir=evidence_root.relative_to(tmp_path),
            out_dir=Path("bundle") / target / tag,
        )

    assert errors == ["sentinel local preflight failure"]
    assert calls[0]["target"] == target
    assert calls[0]["candidate"] == candidate_data
    assert not (tmp_path / "bundle" / target / tag / f"xp-native-evidence-bundle-{target}-{tag}.json").exists()


def test_xp_native_evidence_bundle_preflight_rejects_malformed_candidate_source_fields() -> None:
    bundler = _load_bundle_script()
    target = "windows-xp-native-x86"
    candidate = {
        "local_evidence_preflight_command": "python scripts/check_platform_goal_local_evidence.py --root .",
        "release_asset_source": {
            "workflow_run_url": False,
            "head_sha": ["a" * 40],
            "run_attempt": 0,
        },
    }

    errors = bundler.check_local_protected_goal_preflight(
        target=target,
        release_tag="v1.0.2",
        assets_dir=Path("native-dist/windows-xp/windows-xp-native-x86/v1.0.2"),
        evidence=Path("xp-evidence.json"),
        evidence_root=Path("evidence/windows-xp-native-x86/v1.0.2"),
        candidate=candidate,
    )

    assert (
        f"local protected-goal preflight failed: {target} candidate "
        "release_asset_source.workflow_run_url must be a string"
    ) in errors
    assert (
        f"local protected-goal preflight failed: {target} candidate "
        "release_asset_source.head_sha must be a string"
    ) in errors
    assert (
        f"local protected-goal preflight failed: {target} candidate "
        "release_asset_source.run_attempt must be a positive integer"
    ) in errors


def test_xp_native_evidence_bundle_rejects_malformed_evidence_release_tag_before_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_bundle_script()
    target = "windows-xp-native-x86"
    assets = tmp_path / "native-dist" / "windows-xp" / target / "v1.0.2"
    assets.mkdir(parents=True)
    evidence_root = tmp_path / "evidence" / target / "v1.0.2"
    evidence_root.mkdir(parents=True)
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(json.dumps({"target": target, "release_tag": True}) + "\n", encoding="utf-8")
    candidate = tmp_path / "platform-verified-evidence-windows-xp-native-x86.json"
    candidate.write_text("{}\n", encoding="utf-8")

    def fail_artifact_validation(*_args: Any, **_kwargs: Any) -> list[str]:
        raise AssertionError("artifact validation should not run for malformed evidence release_tag")

    monkeypatch.setattr(bundler, "check_platform_promotion_artifacts", fail_artifact_validation)

    errors = bundler.make_xp_native_evidence_bundle(
        target=target,
        evidence=evidence,
        candidate_record=candidate,
        assets_dir=assets,
        evidence_dir=evidence_root,
        out_dir=tmp_path / "bundle" / target / "v1.0.2",
    )

    assert errors == ["XP evidence release_tag must be a non-empty string, got True"]


def test_xp_native_evidence_bundle_rejects_unscoped_output_directory() -> None:
    bundler = _load_bundle_script()

    errors = bundler.check_target_release_path_segments(
        "windows-xp-native-x86",
        "v1.0.2",
        Path("bundle"),
        label="XP native evidence bundle output directory",
    )

    assert any(
        "XP native evidence bundle output directory must include target path segment "
        "'windows-xp-native-x86'" in error
        for error in errors
    )
    assert any(
        "XP native evidence bundle output directory must include release_tag path segment 'v1.0.2'" in error
        for error in errors
    )


def test_xp_native_evidence_bundle_rejects_reserved_workspace_artifact_directory() -> None:
    bundler = _load_bundle_script()
    assets = Path(".github") / "windows-xp-native-x86" / "v1.0.2" / "artifacts"

    errors = bundler.make_xp_native_evidence_bundle(
        target="windows-xp-native-x86",
        evidence=Path("xp-evidence.json"),
        candidate_record=Path("platform-verified-evidence-windows-xp-native-x86.json"),
        assets_dir=assets,
        out_dir=Path("xp-evidence-output") / "windows-xp-native-x86" / "v1.0.2",
    )

    assert (
        "XP native artifact directory must not point inside reserved workspace directory "
        f"'.github': {assets}"
    ) in errors


def test_xp_native_evidence_bundle_rejects_reserved_workspace_input_paths() -> None:
    bundler = _load_bundle_script()
    evidence = Path(".git") / "xp-evidence.json"
    evidence_dir = Path(".agents") / "windows-xp-native-x86" / "v1.0.2"

    errors = bundler.check_input_symlinks(
        evidence,
        Path("platform-verified-evidence-windows-xp-native-x86.json"),
        evidence_dir=evidence_dir,
    )

    assert (
        "evidence must not point inside reserved workspace directory "
        f"'.git': {evidence}"
    ) in errors
    assert (
        "evidence directory must not point inside reserved workspace directory "
        f"'.agents': {evidence_dir}"
    ) in errors


def test_xp_native_evidence_bundle_rejects_reserved_workspace_output_directory() -> None:
    bundler = _load_bundle_script()
    out_dir = Path(".codex") / "windows-xp-native-x86" / "v1.0.2" / "bundle"
    outputs = (out_dir / "bundle.json", out_dir / "bundle.zip", out_dir / "bundle-SHA256SUMS.txt")

    errors = bundler.prepare_output_paths(out_dir=out_dir, outputs=outputs, force=True)

    assert (
        "XP native evidence bundle output directory must not point inside "
        f"reserved workspace directory '.codex': {out_dir}"
    ) in errors
    assert not out_dir.exists()


def test_xp_native_evidence_bundle_rejects_target_mismatch(tmp_path: Path) -> None:
    bundler = _load_bundle_script()
    evidence = tmp_path / "xp-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target": "windows-xp-native-x86",
                "release_tag": "v1.0.2",
            }
        ),
        encoding="utf-8",
    )
    candidate = tmp_path / "platform-verified-evidence-windows-xp-native-x86.json"
    candidate.write_text(
        json.dumps(
            {
                "target": "windows-xp-native-x86",
                "release_tag": "v1.0.2",
                "xp_evidence_sha256": _sha256(evidence),
                "xp_smoke_evidence_sha256": {},
                "artifact_sha256": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assets = tmp_path / "assets"
    assets.mkdir(parents=True)

    errors = bundler.make_xp_native_evidence_bundle(
        target="windows-xp-native-x64",
        evidence=evidence,
        candidate_record=candidate,
        assets_dir=assets,
        out_dir=tmp_path / "bundle",
    )

    assert "bundle target windows-xp-native-x64 must match evidence target 'windows-xp-native-x86'" in errors


def test_xp_native_evidence_bundle_rejects_symlinked_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_bundle_script()
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    candidate = tmp_path / "platform-verified-evidence-windows-xp-native-x86.json"
    candidate.write_text("{}\n", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    symlink_names = {evidence.name, candidate.name, evidence_root.name}

    def fake_is_symlink(self: Path) -> bool:
        return self.name in symlink_names

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = bundler.make_xp_native_evidence_bundle(
        target="windows-xp-native-x86",
        evidence=evidence,
        candidate_record=candidate,
        assets_dir=assets,
        evidence_dir=evidence_root,
        out_dir=tmp_path / "bundle",
    )

    assert f"evidence must not be a symlink: {evidence}" in errors
    assert f"candidate evidence record must not be a symlink: {candidate}" in errors
    assert f"evidence directory must not be a symlink: {evidence_root}" in errors


def test_xp_native_evidence_bundle_rechecks_smoke_sources_before_writing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    assets = tmp_path / "native-dist" / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x86", "SP3", tag, names)
    evidence_root = tmp_path / "evidence" / target / tag
    _attach_smoke_evidence_files(evidence_root, evidence_data)
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets, work_root=tmp_path)
    out_dir = tmp_path / "xp-evidence-output" / target / tag
    symlinked_smoke = (
        evidence_root.relative_to(tmp_path) / "xp-smoke-evidence" / "cli_launch.txt"
    )
    original_is_symlink = type(tmp_path).is_symlink

    def fake_is_symlink(self: Path) -> bool:
        return self == symlinked_smoke or original_is_symlink(self)

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)
    monkeypatch.setattr(bundler, "check_xp_native_evidence", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bundler, "check_local_protected_goal_preflight", lambda **_kwargs: [])

    with _pushd(tmp_path):
        errors = bundler.make_xp_native_evidence_bundle(
            target=target,
            evidence=evidence.relative_to(tmp_path),
            candidate_record=candidate.relative_to(tmp_path),
            assets_dir=assets.relative_to(tmp_path),
            evidence_dir=evidence_root.relative_to(tmp_path),
            out_dir=out_dir.relative_to(tmp_path),
        )

    assert f"{target} smoke evidence source file must not be a symlink: {symlinked_smoke}" in errors
    assert not (out_dir / f"xp-native-evidence-bundle-{target}-{tag}.json").exists()


def test_xp_native_evidence_bundle_source_maps_do_not_coerce_malformed_smoke_fields(
    tmp_path: Path,
) -> None:
    bundler = _load_bundle_script()
    evidence = tmp_path / "xp-evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    smoke_dir = tmp_path / "xp-smoke-evidence"
    smoke_dir.mkdir()
    smoke_file = smoke_dir / "cli_launch.txt"
    smoke_file.write_text("cli smoke proof\n", encoding="utf-8")
    escaped_smoke_file = tmp_path / "escape.txt"
    escaped_smoke_file.write_text("escaped smoke proof\n", encoding="utf-8")
    evidence_data = {
        "smoke_results": [
            {"id": True, "evidence_file": "xp-smoke-evidence/coerced-id.txt"},
            {"id": "coerced_file", "evidence_file": True},
            {"id": "escape_file", "evidence_file": "../escape.txt"},
            {"id": "missing_file", "evidence_file": "xp-smoke-evidence/missing.txt"},
            {"id": "cli_launch", "evidence_file": "xp-smoke-evidence/cli_launch.txt"},
        ]
    }

    records = bundler.smoke_records(evidence_data, tmp_path)
    sources = bundler.xp_evidence_sources(
        evidence=evidence,
        evidence_data=evidence_data,
        evidence_root=tmp_path,
    )

    assert records == [
        {
            "id": "cli_launch",
            "file": "xp-smoke-evidence/cli_launch.txt",
            "size_bytes": smoke_file.stat().st_size,
            "sha256": _sha256(smoke_file),
        }
    ]
    assert sources["smoke_evidence"] == {
        "cli_launch": {
            "file": "xp-smoke-evidence/cli_launch.txt",
            "size_bytes": smoke_file.stat().st_size,
            "sha256": _sha256(smoke_file),
        }
    }
    assert "True" not in json.dumps(sources)
    assert "../escape.txt" not in json.dumps(sources)


def test_xp_native_evidence_bundle_rejects_symlinked_input_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_bundle_script()
    linked_root = tmp_path / "linked-evidence-root"
    evidence_root = linked_root / "evidence"
    evidence = evidence_root / "xp-evidence.json"
    candidate = linked_root / "platform-verified-evidence-windows-xp-native-x86.json"

    def fake_is_symlink(self: Path) -> bool:
        return self == linked_root

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = bundler.make_xp_native_evidence_bundle(
        target="windows-xp-native-x86",
        evidence=evidence,
        candidate_record=candidate,
        assets_dir=tmp_path / "assets",
        evidence_dir=evidence_root,
        out_dir=tmp_path / "bundle",
    )

    assert f"evidence path must not contain symlinked directories: {linked_root}" in errors
    assert (
        f"candidate evidence record path must not contain symlinked directories: {linked_root}"
    ) in errors
    assert (
        f"evidence directory path must not contain symlinked directories: {linked_root}"
    ) in errors


def test_xp_native_evidence_bundle_rejects_finalized_candidate_record(
    tmp_path: Path,
) -> None:
    bundler = _load_bundle_script()
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    candidate = tmp_path / "platform-verified-evidence-windows-xp-native-x86.json"
    candidate.write_text(
        json.dumps(
            {
                "target": "windows-xp-native-x86",
                "release_tag": "v1.0.2",
                "finalized_record_release_asset_url": (
                    "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
                    "platform-verified-evidence-windows-xp-native-x86-final.json"
                ),
                "review_bundle": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    errors = bundler.make_xp_native_evidence_bundle(
        target="windows-xp-native-x86",
        evidence=evidence,
        candidate_record=candidate,
        assets_dir=tmp_path / "assets",
        evidence_dir=evidence_root,
        out_dir=tmp_path / "bundle",
    )

    assert errors == [
        "candidate evidence record must be unfinalized before bundling; "
        "remove fields: ['finalized_record_release_asset_url', 'review_bundle']"
    ]


def test_xp_native_evidence_bundle_reports_json_read_os_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_bundle_script()
    evidence = tmp_path / "xp-evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self == evidence:
            raise OSError("permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    errors: list[str] = []

    data = bundler.load_json_file(evidence, "evidence", errors)

    assert data is None
    assert errors == [f"evidence file is not readable JSON: {evidence}: permission denied"]


def test_xp_native_evidence_bundle_rejects_missing_artifact_directory_before_hashing(
    tmp_path: Path,
) -> None:
    bundler = _load_bundle_script()
    target = "windows-xp-native-x86"
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(
        json.dumps({"target": target, "release_tag": "v1.0.2"}, indent=2) + "\n",
        encoding="utf-8",
    )
    candidate = tmp_path / "platform-verified-evidence-windows-xp-native-x86.json"
    candidate.write_text(
        json.dumps({"target": target, "release_tag": "v1.0.2"}, indent=2) + "\n",
        encoding="utf-8",
    )
    missing_assets = tmp_path / "missing-assets"

    errors = bundler.make_xp_native_evidence_bundle(
        target=target,
        evidence=evidence,
        candidate_record=candidate,
        assets_dir=missing_assets,
        evidence_dir=evidence_root,
        out_dir=tmp_path / "bundle",
    )

    assert f"artifact directory missing: {missing_assets}" in errors


def test_xp_native_evidence_bundle_rejects_non_path_proof_inputs() -> None:
    bundler = _load_bundle_script()

    errors = bundler.make_xp_native_evidence_bundle(
        target="windows-xp-native-x86",
        evidence=True,
        candidate_record="platform-verified-evidence-windows-xp-native-x86.json",
        assets_dir=False,
        evidence_dir=123,
        out_dir="bundle",
    )

    assert errors == [
        "XP native evidence file path must be a pathlib.Path, got True",
        "candidate evidence record path must be a pathlib.Path, "
        "got 'platform-verified-evidence-windows-xp-native-x86.json'",
        "XP native artifact directory path must be a pathlib.Path, got False",
        "XP native evidence bundle output directory path must be a pathlib.Path, got 'bundle'",
        "XP evidence directory path must be a pathlib.Path, got 123",
    ]


def test_xp_native_evidence_bundle_path_helpers_reject_non_path_values() -> None:
    bundler = _load_bundle_script()

    assert bundler.check_path_parent_symlinks(True, "XP evidence") == [
        "XP evidence path must be a pathlib.Path, got True"
    ]
    assert bundler.check_directory_path_hint("bundle", "output directory") == [
        "output directory path must be a pathlib.Path, got 'bundle'"
    ]
    assert bundler.check_path_not_reserved_workspace_root(False, "artifact directory") == [
        "artifact directory path must be a pathlib.Path, got False"
    ]
    assert bundler.check_target_release_path_segments(
        "windows-xp-native-x86",
        "v1.0.2",
        0,
        label="XP native evidence bundle output directory",
    ) == [
        "XP native evidence bundle output directory path must be a pathlib.Path, got 0"
    ]
    assert bundler.check_bundle_source_file(True, "XP evidence source file") == [
        "XP evidence source file path must be a pathlib.Path, got True"
    ]
    assert bundler.prepare_output_paths(out_dir=True, outputs=("bundle.zip",), force=True) == [
        "XP native evidence bundle output directory path must be a pathlib.Path, got True",
        "XP native evidence bundle output file path must be a pathlib.Path, got 'bundle.zip'",
    ]


def test_xp_native_evidence_bundle_rejects_file_shaped_directory_inputs(
    tmp_path: Path,
) -> None:
    bundler = _load_bundle_script()
    assets = tmp_path / "assets.zip"
    evidence_root = tmp_path / "xp-evidence-output.zip"
    assets.mkdir()
    evidence_root.mkdir()

    errors = bundler.make_xp_native_evidence_bundle(
        target="windows-xp-native-x86",
        evidence=evidence_root / "xp-evidence.json",
        candidate_record=tmp_path / "platform-verified-evidence-windows-xp-native-x86.json",
        assets_dir=assets,
        evidence_dir=evidence_root,
        out_dir=tmp_path / "bundle",
    )

    assert f"XP native artifact directory must be a directory path, got {assets.as_posix()!r}" in errors
    assert f"XP evidence directory must be a directory path, got {evidence_root.as_posix()!r}" in errors


def test_xp_native_evidence_bundle_rejects_symlinked_output_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_bundle_script()
    out_dir = tmp_path / "bundle"
    out_dir.mkdir()
    outputs = (out_dir / "bundle.json", out_dir / "bundle.zip", out_dir / "bundle-SHA256SUMS.txt")

    def fake_is_symlink(self: Path) -> bool:
        return self == out_dir

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = bundler.prepare_output_paths(out_dir=out_dir, outputs=outputs, force=True)

    assert errors == [
        f"XP native evidence bundle output directory must not be a symlink: {out_dir}"
    ]


def test_xp_native_evidence_bundle_rejects_file_shaped_output_directory(
    tmp_path: Path,
) -> None:
    bundler = _load_bundle_script()
    out_dir = tmp_path / "bundle.zip"
    outputs = (out_dir / "bundle.json", out_dir / "bundle.zip", out_dir / "bundle-SHA256SUMS.txt")

    errors = bundler.prepare_output_paths(out_dir=out_dir, outputs=outputs, force=True)

    assert errors == [
        "XP native evidence bundle output directory "
        f"must be a directory path, got {out_dir.as_posix()!r}"
    ]
    assert not out_dir.exists()


def test_xp_native_evidence_bundle_rejects_symlinked_output_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_bundle_script()
    out_parent = tmp_path / "linked-bundle-root"
    out_dir = out_parent / "bundle"
    outputs = (out_dir / "bundle.json", out_dir / "bundle.zip", out_dir / "bundle-SHA256SUMS.txt")

    def fake_is_symlink(self: Path) -> bool:
        return self == out_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = bundler.prepare_output_paths(out_dir=out_dir, outputs=outputs, force=True)

    assert errors == [
        f"XP native evidence bundle output directory path must not contain symlinked directories: {out_parent}"
    ]


def test_xp_native_evidence_bundle_rejects_unsafe_output_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_bundle_script()
    out_dir = tmp_path / "bundle"
    out_dir.mkdir()
    symlink_output = out_dir / "bundle.json"
    symlink_output.write_text("old manifest\n", encoding="utf-8")
    directory_output = out_dir / "bundle.zip"
    directory_output.mkdir()
    sidecar_output = out_dir / "bundle-SHA256SUMS.txt"

    def fake_is_symlink(self: Path) -> bool:
        return self == symlink_output

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = bundler.prepare_output_paths(
        out_dir=out_dir,
        outputs=(symlink_output, directory_output, sidecar_output),
        force=True,
    )

    assert "XP native evidence bundle output file must not be a symlink: bundle.json" in errors
    assert "XP native evidence bundle output must be a regular file: bundle.zip" in errors


def test_xp_native_evidence_bundle_rejects_candidate_mismatch(tmp_path: Path) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    assets = tmp_path / "native-dist" / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x86", "SP3", tag, names)
    evidence_root = tmp_path / "evidence" / target / tag
    _attach_smoke_evidence_files(evidence_root, evidence_data)
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets, work_root=tmp_path)
    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
    candidate_data["xp_evidence_sha256"] = "0" * 64
    candidate.write_text(json.dumps(candidate_data, indent=2) + "\n", encoding="utf-8")

    with _pushd(tmp_path):
        errors = bundler.make_xp_native_evidence_bundle(
            target=target,
            evidence=evidence.relative_to(tmp_path),
            candidate_record=candidate.relative_to(tmp_path),
            assets_dir=assets.relative_to(tmp_path),
            evidence_dir=evidence_root.relative_to(tmp_path),
            out_dir=Path("bundle"),
        )

    assert "candidate record xp_evidence_sha256 must match XP evidence file" in errors


def test_xp_native_evidence_bundle_rejects_malformed_candidate_artifact_hashes(
    tmp_path: Path,
) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    assets = tmp_path / "native-dist" / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x86", "SP3", tag, names)
    evidence_root = tmp_path / "evidence" / target / tag
    _attach_smoke_evidence_files(evidence_root, evidence_data)
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets, work_root=tmp_path)
    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
    artifact_hashes = candidate_data["artifact_sha256"]
    malformed_artifact = next(iter(artifact_hashes))
    artifact_hashes[malformed_artifact] = True
    artifact_hashes[False] = "a" * 64

    errors = bundler.validate_candidate_record(
        target,
        tag,
        candidate,
        candidate_data,
        evidence,
        evidence_data,
        assets,
        evidence_root,
    )

    assert "candidate record artifact_sha256 key must be a string, got False" in errors
    assert (
        f"candidate record artifact_sha256 for {malformed_artifact} "
        "must be a string SHA-256 hex digest"
    ) in errors
    assert "candidate record artifact_sha256 must exactly match XP artifact files" in errors


def test_xp_native_evidence_bundle_rejects_suffixed_candidate_filename(tmp_path: Path) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    assets = tmp_path / "native-dist" / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x86", "SP3", tag, names)
    evidence_root = tmp_path / "evidence" / target / tag
    _attach_smoke_evidence_files(evidence_root, evidence_data)
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}-copy.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets, work_root=tmp_path)

    with _pushd(tmp_path):
        errors = bundler.make_xp_native_evidence_bundle(
            target=target,
            evidence=evidence.relative_to(tmp_path),
            candidate_record=candidate.relative_to(tmp_path),
            assets_dir=assets.relative_to(tmp_path),
            evidence_dir=evidence_root.relative_to(tmp_path),
            out_dir=Path("bundle"),
        )

    assert (
        f"candidate record file name must be platform-verified-evidence-{target}.json, "
        f"got 'platform-verified-evidence-{target}-copy.json'"
    ) in errors


def test_xp_native_evidence_bundle_rejects_candidate_source_map_mismatch(tmp_path: Path) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x64"
    assets = tmp_path / "native-dist" / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x64", "SP2", tag, names)
    evidence_root = tmp_path / "evidence" / target / tag
    _attach_smoke_evidence_files(evidence_root, evidence_data)
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets, work_root=tmp_path)
    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
    candidate_data["xp_evidence_sources"]["evidence"]["size_bytes"] = 1
    candidate.write_text(json.dumps(candidate_data, indent=2) + "\n", encoding="utf-8")

    with _pushd(tmp_path):
        errors = bundler.make_xp_native_evidence_bundle(
            target=target,
            evidence=evidence.relative_to(tmp_path),
            candidate_record=candidate.relative_to(tmp_path),
            assets_dir=assets.relative_to(tmp_path),
            evidence_dir=evidence_root.relative_to(tmp_path),
            out_dir=Path("bundle"),
        )

    assert "candidate record xp_evidence_sources must match bundled XP evidence files" in errors


def test_xp_native_evidence_bundle_rejects_stale_staged_upload_output_dir(tmp_path: Path) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    assets = tmp_path / "native-dist" / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x86", "SP3", tag, names)
    evidence_root = tmp_path / "evidence" / target / tag
    _attach_smoke_evidence_files(evidence_root, evidence_data)
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets, work_root=tmp_path)
    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
    actual_output = (Path("xp-evidence-output") / target / tag).as_posix()
    stale_output = Path("stale-output") / target / tag / "bundle"
    candidate_data["staged_upload_command"] = str(candidate_data["staged_upload_command"]).replace(
        actual_output,
        stale_output.as_posix(),
    )
    candidate.write_text(json.dumps(candidate_data, indent=2) + "\n", encoding="utf-8")
    out_dir = tmp_path / "xp-evidence-output" / target / tag

    with _pushd(tmp_path):
        errors = bundler.make_xp_native_evidence_bundle(
            target=target,
            evidence=evidence.relative_to(tmp_path),
            candidate_record=candidate.relative_to(tmp_path),
            assets_dir=assets.relative_to(tmp_path),
            evidence_dir=evidence_root.relative_to(tmp_path),
            out_dir=out_dir.relative_to(tmp_path),
        )

    assert errors == [
        f"{target} candidate staged_upload_command --evidence-output-dir must match "
        f"bundle output directory {actual_output!r}, got [{stale_output.as_posix()!r}]"
    ]


def test_xp_native_evidence_bundle_rejects_candidate_summary_mismatch(tmp_path: Path) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x64"
    assets = tmp_path / "native-dist" / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x64", "SP2", tag, names)
    evidence_root = tmp_path / "evidence" / target / tag
    _attach_smoke_evidence_files(evidence_root, evidence_data)
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets, work_root=tmp_path)
    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
    candidate_data["xp_evidence_summary"]["security"]["modern_defaults_unchanged"] = False
    candidate.write_text(json.dumps(candidate_data, indent=2) + "\n", encoding="utf-8")

    with _pushd(tmp_path):
        errors = bundler.make_xp_native_evidence_bundle(
            target=target,
            evidence=evidence.relative_to(tmp_path),
            candidate_record=candidate.relative_to(tmp_path),
            assets_dir=assets.relative_to(tmp_path),
            evidence_dir=evidence_root.relative_to(tmp_path),
            out_dir=Path("bundle"),
        )

    assert "candidate record xp_evidence_summary must match XP evidence file" in errors


def test_xp_native_evidence_bundle_rejects_host_identity_mismatch(tmp_path: Path) -> None:
    bundler = _load_bundle_script()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    assets = tmp_path / "native-dist" / "windows-xp" / target / tag
    assets.mkdir(parents=True)
    names = _required_artifact_names(artifact_checker, target, tag)
    _write_artifact_set(assets, names)
    evidence_data = _valid_evidence(target, "x86", "SP3", tag, names)
    evidence_root = tmp_path / "evidence" / target / tag
    _attach_smoke_evidence_files(evidence_root, evidence_data)
    evidence = evidence_root / "xp-evidence.json"
    evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate = tmp_path / f"platform-verified-evidence-{target}.json"
    _write_candidate_record(candidate, target, tag, evidence, evidence_data, assets, work_root=tmp_path)
    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
    candidate_data["xp_host_identity_sha256"] = "0" * 64
    candidate.write_text(json.dumps(candidate_data, indent=2) + "\n", encoding="utf-8")

    with _pushd(tmp_path):
        errors = bundler.make_xp_native_evidence_bundle(
            target=target,
            evidence=evidence.relative_to(tmp_path),
            candidate_record=candidate.relative_to(tmp_path),
            assets_dir=assets.relative_to(tmp_path),
            evidence_dir=evidence_root.relative_to(tmp_path),
            out_dir=Path("bundle"),
        )

    assert "candidate record xp_host_identity_sha256 must match XP host identity" in errors


def _valid_evidence(
    target: str,
    arch: str,
    service_pack: str,
    release_tag: str,
    artifacts: list[str],
) -> dict[str, Any]:
    smoke_ids = [
        "cli_launch",
        "gui_or_legacy_host_ui_launch",
        "loopback_profile_dry_run",
        "artifact_manifest_validation",
        "legacy_crypto_profile_scoped",
        "modern_defaults_unchanged",
    ]
    os_record = {
        "name": "Windows XP",
        "architecture": arch,
        "service_pack": service_pack,
    }
    if arch == "x64":
        os_record["edition"] = "Professional x64 Edition"
    host_identity = {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "host_label": f"xp-{arch}-lab-01",
        "evidence_run_id": f"xp-{arch}-{release_tag.removeprefix('v').replace('.', '-')}-20260620t120000z",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "operator_private_data_redacted": True,
        "os": dict(os_record),
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "Separate legacy XP-capable native host toolchain",
        },
    }
    release_source = _xp_release_source()
    security_patch = {
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
        "security_update_channel": "vendor-security-updates-2026-06",
        "cve_review_reference": "vendor-cve-advisory-review-2026-06",
    }
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "release_source": release_source,
        "os": os_record,
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "Separate legacy XP-capable native host toolchain",
        },
        "host_identity": host_identity,
        "artifact_validation": {
            "passed": True,
            "command": (
                "python scripts/check_platform_promotion_artifacts.py "
                f"--target {target} --assets-dir native-dist/windows-xp/{target}/{release_tag} "
                f"--tag {release_tag} --strict"
            ),
        },
        "artifacts": artifacts,
        "smoke_results": [
            {
                "id": smoke_id,
                "passed": True,
                "command": (
                    f"scripts/xp_smoke_runner.cmd --target {target} --release-tag {release_tag} "
                    f"--smoke-id {smoke_id} --evidence-file xp-smoke-evidence/{smoke_id}.txt "
                    f"--proof-file xp-smoke-proof/{smoke_id}.txt "
                    f"--host-label {host_identity['host_label']} "
                    f"--evidence-run-id {host_identity['evidence_run_id']} "
                    f"--observed-at-utc {host_identity['observed_at_utc']} "
                    f"--source-workflow-run-url {release_source['workflow_run_url']} "
                    f"--source-head-sha {release_source['head_sha']} "
                    f"--source-run-attempt {release_source['run_attempt']} "
                    f"--security-update-channel {security_patch['security_update_channel']} "
                    f"--cve-review-reference {security_patch['cve_review_reference']} "
                    f'--os-name "{os_record["name"]}" '
                    f"--os-architecture {os_record['architecture']} "
                    f"--os-service-pack {os_record['service_pack']}"
                    + (
                        f' --os-edition "{os_record["edition"]}"'
                        if "edition" in os_record
                        else ""
                    )
                ),
                "evidence_file": f"xp-smoke-evidence/{smoke_id}.txt",
                "evidence_sha256": hashlib.sha256(smoke_id.encode()).hexdigest(),
            }
            for smoke_id in smoke_ids
        ],
        "security": {
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
            "patch_evidence": security_patch,
        },
    }


def _xp_release_source() -> dict[str, object]:
    return {
        "workflow": ".github/workflows/xp-native-evidence.yml",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/54321",
        "head_sha": "a" * 40,
        "run_attempt": 1,
    }


def _attach_smoke_evidence_files(root: Path, evidence: dict[str, Any]) -> None:
    host_identity = evidence["host_identity"]
    release_source = evidence["release_source"]
    host_probe_lines = _xp_host_probe_lines(evidence["target"], evidence["os"])
    for result in evidence["smoke_results"]:
        path = root / result["evidence_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        security_lines = _xp_security_smoke_lines(str(result["id"]))
        path.write_text(
            f"xp smoke target: {evidence['target']}\n"
            f"xp smoke release: {evidence['release_tag']}\n"
            f"xp smoke id: {result['id']}\n"
            f"xp smoke os name: {evidence['os']['name']}\n"
            f"xp smoke os architecture: {evidence['os']['architecture']}\n"
            f"xp smoke os service pack: {evidence['os']['service_pack']}\n"
            + (
                f"xp smoke os edition: {evidence['os']['edition']}\n"
                if "edition" in evidence["os"]
                else ""
            )
            + host_probe_lines
            + f"xp smoke host label: {host_identity['host_label']}\n"
            f"xp smoke evidence run id: {host_identity['evidence_run_id']}\n"
            f"xp smoke observed at utc: {host_identity['observed_at_utc']}\n"
            f"xp smoke source workflow run: {release_source['workflow_run_url']}\n"
            f"xp smoke source head sha: {release_source['head_sha']}\n"
            f"xp smoke source run attempt: {release_source['run_attempt']}\n"
            f"{_xp_artifact_manifest_smoke_lines(evidence, str(result['id']))}"
            f"{security_lines}"
            f"{result['id']} passed on Windows XP evidence host\n",
            encoding="utf-8",
        )
        result["evidence_sha256"] = _sha256(path)


def _xp_host_probe_lines(target: str, os_identity: dict[str, Any]) -> str:
    if target.endswith("x64"):
        ver_output = "Microsoft Windows [Version 5.2.3790]"
        processor_architecture = "AMD64"
        caption = "Microsoft Windows XP Professional x64 Edition"
    else:
        ver_output = "Microsoft Windows XP [Version 5.1.2600]"
        processor_architecture = "x86"
        caption = "Microsoft Windows XP Professional"
    service_pack = str(os_identity["service_pack"]).removeprefix("SP")
    return (
        "xp smoke host probe command: ver\n"
        f"xp smoke host probe output: {ver_output}\n"
        f"xp smoke processor architecture env: {processor_architecture}\n"
        "xp smoke processor architecture w6432 env: \n"
        f"xp smoke wmic os caption: {caption}\n"
        f"xp smoke wmic os csdversion: Service Pack {service_pack}\n"
    )


def _xp_security_smoke_lines(smoke_id: str) -> str:
    if smoke_id == "legacy_crypto_profile_scoped":
        return (
            "legacy compatibility profile: isolated-opt-in\n"
            "legacy crypto scope: profile-only\n"
            "weak crypto global default: false\n"
            "security update channel: vendor-security-updates-2026-06\n"
            "CVE review reference: vendor-cve-advisory-review-2026-06\n"
        )
    if smoke_id == "modern_defaults_unchanged":
        return (
            "modern TLS minimum: TLS 1.2\n"
            "modern TLS preferred: TLS 1.3\n"
            "modern defaults unchanged: true\n"
            "weak crypto global default: false\n"
            "security update channel: vendor-security-updates-2026-06\n"
            "CVE review reference: vendor-cve-advisory-review-2026-06\n"
        )
    return ""


def _xp_artifact_manifest_smoke_lines(evidence: dict[str, Any], smoke_id: str) -> str:
    if smoke_id != "artifact_manifest_validation":
        return ""
    return (
        "".join(f"xp smoke artifact file: {name}\n" for name in evidence["artifacts"])
        + "xp smoke artifact manifest validated: true\n"
        + "xp smoke artifact sha256s validated: true\n"
    )


def _required_artifact_names(checker: Any, target: str, tag: str) -> list[str]:
    promotion = checker.read_json(Path("configs/platform_parity_promotion.json"))
    entries = checker.promotion_entries(promotion, [])
    version = checker.version_from_tag(tag, [])
    return [checker.expand_version(name, version) for name in checker.required_artifacts(entries[target])]


def _write_artifact_set(root: Path, names: list[str]) -> None:
    payload_names = [
        name
        for name in names
        if not name.endswith("SHA256SUMS.txt") and not name.endswith("manifest.json")
    ]
    manifest_name = next(name for name in names if name.endswith("manifest.json"))
    sidecar_name = next(name for name in names if name.endswith("SHA256SUMS.txt"))
    for name in payload_names:
        (root / name).write_bytes(_payload_bytes(name))
    records = [
        {
            "file": name,
            **_manifest_record_metadata(name),
            "size_bytes": (root / name).stat().st_size,
            "sha256": _sha256(root / name),
        }
        for name in payload_names
    ]
    (root / manifest_name).write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    sidecar_names = [*payload_names, manifest_name]
    (root / sidecar_name).write_text(
        "".join(f"{_sha256(root / name)}  {name}\n" for name in sidecar_names),
        encoding="utf-8",
    )


def _manifest_record_metadata(name: str) -> dict[str, str]:
    if name.endswith(".zip"):
        return {"architecture": _artifact_architecture(name), "format": "zip"}
    return {}


def _artifact_architecture(name: str) -> str:
    if "-windows-xp-x86-native." in name:
        return "x86"
    if "-windows-xp-x64-native." in name:
        return "x64"
    return ""


def _write_candidate_record(
    path: Path,
    target: str,
    release_tag: str,
    evidence: Path,
    evidence_data: dict[str, Any],
    assets_dir: Path,
    *,
    work_root: Path,
) -> None:
    generator = _load_platform_verified_evidence_record_generator()
    with _pushd(work_root):
        errors, record = generator.build_evidence_record(
            SimpleNamespace(
                target=target,
                release_tag=release_tag,
                assets_dir=assets_dir.relative_to(work_root),
                release_asset_base_url=(
                    f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}"
                ),
                release_source_workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/54321",
                release_source_artifact_name=f"xp-native-evidence-{target}-{release_tag}",
                release_source_head_sha="a" * 40,
                release_source_run_attempt=1,
                workflow_run_url="",
                runner_label=[],
                builder_evidence=None,
                linux_smoke_evidence=None,
                xp_evidence=evidence.relative_to(work_root),
                xp_evidence_dir=evidence.parent.relative_to(work_root),
            )
        )
    assert errors == []
    assert record["xp_host_identity_sha256"] == _json_sha256(evidence_data["host_identity"])
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


@contextmanager
def _pushd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _payload_bytes(name: str) -> bytes:
    payload = f"{name}\n".encode()
    with io.BytesIO() as raw:
        with zipfile.ZipFile(raw, mode="w") as archive:
            archive.writestr("Remote Ops Workspace XP native evidence payload.txt", payload)
        return raw.getvalue()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha256(data: dict[str, object]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def assert_zip_entries_are_regular_files(archive: zipfile.ZipFile) -> None:
    for info in archive.infolist():
        assert ((info.external_attr >> 16) & 0o170000) == 0o100000
        assert ((info.external_attr >> 16) & 0o777) == 0o644


def _load_bundle_script():
    path = Path("scripts/make_xp_native_evidence_bundle.py")
    spec = importlib.util.spec_from_file_location("make_xp_native_evidence_bundle_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_promotion_artifacts_checker():
    path = Path("scripts/check_platform_promotion_artifacts.py")
    spec = importlib.util.spec_from_file_location("check_platform_promotion_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_verified_evidence_record_generator():
    path = Path("scripts/make_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("make_platform_verified_evidence_record", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
