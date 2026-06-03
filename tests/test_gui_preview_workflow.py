from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from remote_ops_workspace.gui_designs import GUI_DESIGN_PRESETS


def test_gui_preview_workflow_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_preview_manifest_tracks_every_gui_design_preset() -> None:
    checker = _load_checker()
    manifest = checker.json.loads((checker.PREVIEW_DIR / "preview-manifest.json").read_text(encoding="utf-8"))

    assert [item["id"] for item in manifest["presets"]] == [preset.id for preset in GUI_DESIGN_PRESETS]
    assert manifest["preview_size"] == {"width": 1280, "height": 760}


def test_preview_png_dimensions_match_manifest() -> None:
    checker = _load_checker()
    manifest = checker.json.loads((checker.PREVIEW_DIR / "preview-manifest.json").read_text(encoding="utf-8"))

    for item in manifest["presets"]:
        image = item["image"]
        path = checker.PREVIEW_DIR / image["path"]
        assert checker.png_dimensions(path) == (image["width"], image["height"])


def test_preview_gallery_links_all_preset_images() -> None:
    checker = _load_checker()
    manifest = checker.json.loads((checker.PREVIEW_DIR / "preview-manifest.json").read_text(encoding="utf-8"))
    gallery = (checker.PREVIEW_DIR / "index.html").read_text(encoding="utf-8")

    assert "all-gui-designs-contact-sheet.png" in gallery
    for item in manifest["presets"]:
        assert item["label"] in gallery
        assert item["image"]["path"] in gallery


def test_renderer_list_mode_does_not_require_pillow() -> None:
    renderer = _load_renderer()

    assert renderer.main(["--list"]) == 0


def _load_checker():
    path = Path("scripts/check_gui_design_previews.py")
    spec = importlib.util.spec_from_file_location("check_gui_design_previews_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_renderer():
    path = Path("scripts/render_gui_design_previews.py")
    spec = importlib.util.spec_from_file_location("render_gui_design_previews_script_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
