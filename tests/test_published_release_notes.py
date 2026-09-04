from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_checker():
    path = Path("scripts/check_published_release_notes.py")
    spec = importlib.util.spec_from_file_location("check_published_release_notes", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload() -> dict[str, object]:
    return {
        "tag_name": "v1.0.24",
        "name": "v1.0.24 (UNSIGNED PREVIEW)",
        "draft": False,
        "prerelease": True,
        "body": (
            "# v1.0.24\n\n"
            "**Channel: unsigned preview.**\n\n"
            "## Support boundaries\n"
        ),
    }


def test_published_release_notes_accepts_unsigned_preview() -> None:
    checker = _load_checker()

    assert checker.check_release_notes(_payload(), tag="v1.0.24", channel="unsigned-preview") == []


def test_published_release_notes_rejects_empty_body() -> None:
    checker = _load_checker()
    payload = _payload()
    payload["body"] = None

    errors = checker.check_release_notes(payload, tag="v1.0.24", channel="unsigned-preview")

    assert "published release body must contain boundary-aware release notes" in errors


def test_published_release_notes_main_accepts_offline_fixture(tmp_path: Path) -> None:
    checker = _load_checker()
    fixture = tmp_path / "release.json"
    fixture.write_text(json.dumps(_payload()), encoding="utf-8")

    assert (
        checker.main(
            [
                "--repository",
                "Yunushan/remote-ops-workspace",
                "--tag",
                "v1.0.24",
                "--channel",
                "unsigned-preview",
                "--release-json",
                str(fixture),
            ]
        )
        == 0
    )
