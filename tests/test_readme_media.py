from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_readme_media_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_readme_media_manifest_tracks_required_assets() -> None:
    checker = _load_checker()
    manifest = checker.json.loads(checker.MANIFEST_PATH.read_text(encoding="utf-8"))
    paths = {item["path"] for item in manifest["assets"]}

    assert set(checker.REQUIRED_ASSETS) == paths
    assert manifest["renderer"] == "scripts/render_readme_media.py"


def test_readme_media_dimensions_match_manifest() -> None:
    checker = _load_checker()
    manifest = checker.json.loads(checker.MANIFEST_PATH.read_text(encoding="utf-8"))

    for item in manifest["assets"]:
        data = (checker.ROOT / item["path"]).read_bytes()
        if item["kind"] == "png":
            dimensions = checker.png_dimensions(data)
        else:
            dimensions = checker.gif_dimensions(data)
        assert dimensions == (item["width"], item["height"])


def test_readme_references_generated_visuals() -> None:
    checker = _load_checker()
    readme = checker.README_PATH.read_text(encoding="utf-8")

    assert "## Visual Overview" in readme
    for path in checker.REQUIRED_ASSETS:
        assert path in readme
    assert checker.PREVIEW_CONTACT_SHEET in readme


def _load_checker():
    path = Path("scripts/check_readme_media.py")
    spec = importlib.util.spec_from_file_location("check_readme_media_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
