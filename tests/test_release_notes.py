from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from remote_ops_workspace import __version__


def _load_release_notes():
    path = Path("scripts/write_release_notes.py")
    spec = importlib.util.spec_from_file_location("write_release_notes_for_tests", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load release notes helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_unsigned_preview_notes_report_boundaries(tmp_path: Path, monkeypatch) -> None:
    helper = _load_release_notes()
    output = tmp_path / "release-notes.md"
    tag = f"v{__version__}"
    load_json = helper.load_json

    def release_inputs(root: Path, relative: str) -> dict:
        payload = load_json(root, relative)
        if relative == "redistribution-evidence/preview.json":
            payload["release_tag"] = tag
        elif relative in {
            "configs/platform_verified_evidence.json", "configs/mobaxterm_parity_evidence.json",
        }:
            payload["accepted_evidence"] = []
        return payload

    monkeypatch.setattr(helper, "load_json", release_inputs)
    helper.write_notes(
        tag=tag,
        channel="unsigned-preview",
        repository="Yunushan/remote-ops-workspace",
        output=output,
        root=Path("."),
    )
    notes = output.read_text(encoding="utf-8")
    assert "Channel: unsigned preview" in notes
    assert "This lane does not use production signing or notarization credentials." in notes
    assert "selected signed promotion registry" not in notes
    assert f"remote-ops-workspace-{tag}-windows.zip" in notes
    assert "Native jobs: windows-native, macos-native, linux-native." in notes
    assert "Native macOS DMG and PKG packages require macOS 14.4 or later." in notes
    assert "Protected platform evidence accepted for this source is 0/4" in notes
    assert "Strict MobaXterm parity evidence accepted for this source is 0/8" in notes
    assert "must not be treated as trusted production artifacts" in notes
    assert "GUI package licenses and corresponding source" in notes
    assert "PyQt6 6.12.0 source" in notes
    assert "Qt 6.12.0 source" in notes
    assert "d3e021b716bae880224422f9d1b894d2d53de7e60e60dbc43f860723f9cc300b" in notes


def test_release_notes_reject_invalid_tag_and_channel(tmp_path: Path) -> None:
    helper = _load_release_notes()
    with pytest.raises(ValueError, match="release tag"):
        helper.write_notes(
            tag="1.0.27",
            channel="unsigned-preview",
            repository="Yunushan/remote-ops-workspace",
            output=tmp_path / "notes.md",
        )
    with pytest.raises(ValueError, match="unsupported release channel"):
        helper.write_notes(
            tag="v1.0.27",
            channel="preview",
            repository="Yunushan/remote-ops-workspace",
            output=tmp_path / "notes.md",
        )


def test_release_notes_count_only_accepted_protected_targets() -> None:
    helper = _load_release_notes()
    tag = "v2.0.0"
    base = {"release_tag": tag, "status": "accepted", "readiness_percent": 100.0}
    registry = {
        "accepted_evidence": [
            {**base, "target": "linux-i386"},
            {**base, "target": "linux-armhf", "readiness_percent": 99.0},
            {**base, "target": "windows-xp-native-x86", "status": "candidate"},
            {**base, "target": "windows-xp-native-x64", "release_tag": "v1.0.0"},
            {**base, "target": "windows-x64"},
        ],
    }
    assert helper.accepted_target_ids(registry, tag=tag) == {"linux-i386"}
