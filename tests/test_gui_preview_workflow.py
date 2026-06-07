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


def test_gui_visual_metrics_checker_passes_current_tree() -> None:
    checker = _load_visual_metrics_checker()

    assert checker.main() == 0


def test_gui_visual_metrics_cover_every_preview_preset() -> None:
    checker = _load_visual_metrics_checker()
    metrics = checker.load_json(checker.METRICS_PATH)
    manifest = checker.load_json(checker.PREVIEW_MANIFEST_PATH)

    assert set(metrics["presets"]) == {item["id"] for item in manifest["presets"]}
    assert metrics["preview_size"] == [1280, 760]
    assert checker.count_regions(metrics) == 54
    assert checker.count_color_anchors(metrics) == 36
    assert checker.count_line_anchors(metrics) == 44
    assert checker.count_topology_contracts(metrics) == 25
    assert len(metrics["presets"]["mobaxterm"]["line_anchors"]) == 16
    assert len(metrics["presets"]["securecrt"]["line_anchors"]) == 7
    assert len(metrics["presets"]["securecrt"]["topology"]) == 5
    assert len(metrics["presets"]["termius"]["line_anchors"]) == 7
    assert len(metrics["presets"]["termius"]["topology"]) == 5
    assert len(metrics["presets"]["remmina"]["line_anchors"]) == 7
    assert len(metrics["presets"]["remmina"]["topology"]) == 5
    assert len(metrics["presets"]["mremoteng"]["line_anchors"]) == 7
    assert len(metrics["presets"]["mremoteng"]["topology"]) == 5
    assert len(metrics["presets"]["mobaxterm"]["topology"]) == 5
    assert len(metrics["presets"]["mobaxterm"]["color_anchors"]) == 8
    assert len(metrics["presets"]["securecrt"]["color_anchors"]) == 7
    assert len(metrics["presets"]["termius"]["color_anchors"]) == 7
    assert len(metrics["presets"]["remmina"]["color_anchors"]) == 7
    assert len(metrics["presets"]["mremoteng"]["color_anchors"]) == 7


def test_gui_visual_metrics_reject_visual_anchor_drift() -> None:
    checker = _load_visual_metrics_checker()
    image = checker.read_png_rgb(checker.PREVIEW_DIR / "mobaxterm.png")
    anchor = {
        "id": "broken-anchor",
        "point": [10, 110],
        "rgb_min": [250, 250, 250],
        "rgb_max": [255, 255, 255],
    }

    assert checker.check_color_anchor("mobaxterm", image, anchor)


def test_gui_visual_metrics_reject_line_anchor_drift() -> None:
    checker = _load_visual_metrics_checker()
    image = checker.read_png_rgb(checker.PREVIEW_DIR / "mobaxterm.png")
    anchor = {
        "id": "broken-line",
        "from": [4, 110],
        "to": [386, 110],
        "rgb_min": [250, 250, 250],
        "rgb_max": [255, 255, 255],
        "min_match_ratio": 0.95,
    }

    assert checker.check_line_anchor("mobaxterm", image, anchor)


def test_gui_visual_metrics_reject_topology_drift() -> None:
    checker = _load_visual_metrics_checker()
    metrics = checker.load_json(checker.METRICS_PATH)
    contract = {
        "id": "broken-topology",
        "from": "connected-left-dock",
        "relation": "left_of",
        "to": "connected-terminal",
        "min_gap": 40,
    }

    assert checker.check_topology_contract("mobaxterm", metrics["presets"]["mobaxterm"], contract)


def _load_checker():
    path = Path("scripts/check_gui_design_previews.py")
    spec = importlib.util.spec_from_file_location("check_gui_design_previews_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_visual_metrics_checker():
    path = Path("scripts/check_gui_visual_metrics.py")
    spec = importlib.util.spec_from_file_location("check_gui_visual_metrics_script", path)
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
