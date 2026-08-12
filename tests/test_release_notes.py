from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_release_notes():
    path = Path("scripts/write_release_notes.py")
    spec = importlib.util.spec_from_file_location("write_release_notes_for_tests", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load release notes helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_unsigned_preview_notes_report_boundaries(tmp_path: Path) -> None:
    helper = _load_release_notes()
    output = tmp_path / "release-notes.md"
    helper.write_notes(
        tag="v1.0.16",
        channel="unsigned-preview",
        repository="Yunushan/remote-ops-workspace",
        output=output,
        root=Path("."),
    )
    notes = output.read_text(encoding="utf-8")
    assert "Channel: unsigned preview" in notes
    assert "remote-ops-workspace-v1.0.16-windows.zip" in notes
    assert "Native jobs: windows-native, macos-native, linux-native." in notes
    assert "Protected platform evidence accepted for this source is 0/4" in notes
    assert "Strict MobaXterm parity evidence accepted for this source is 0/7" in notes
    assert "must not be treated as trusted production artifacts" in notes


def test_release_notes_reject_invalid_tag_and_channel(tmp_path: Path) -> None:
    helper = _load_release_notes()
    with pytest.raises(ValueError, match="release tag"):
        helper.write_notes(
            tag="1.0.16",
            channel="unsigned-preview",
            repository="Yunushan/remote-ops-workspace",
            output=tmp_path / "notes.md",
        )
    with pytest.raises(ValueError, match="unsupported release channel"):
        helper.write_notes(
            tag="v1.0.16",
            channel="preview",
            repository="Yunushan/remote-ops-workspace",
            output=tmp_path / "notes.md",
        )
