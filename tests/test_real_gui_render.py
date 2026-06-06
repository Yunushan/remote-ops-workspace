from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_real_gui_render_checker_passes_or_verifies_fail_closed_path(tmp_path: Path) -> None:
    checker = _load_checker()

    errors, messages = checker.check_real_gui_render(["native"], out_dir=tmp_path)

    assert errors == []
    assert any("captured" in message or "fail-closed" in message for message in messages)


def test_real_gui_render_main_passes_current_environment() -> None:
    checker = _load_checker()

    assert checker.main(["--preset", "native"]) == 0


def test_real_gui_render_require_pyqt6_fails_when_missing() -> None:
    checker = _load_checker()

    if checker.module_available("PyQt6"):
        return

    errors, messages = checker.check_real_gui_render(["native"], require_pyqt6=True)

    assert errors == ["PyQt6 is required for live GUI render capture"]
    assert any("fail-closed" in message for message in messages)


def test_real_gui_render_metrics_reject_blank_capture() -> None:
    checker = _load_checker()
    samples = [(255, 255, 255)] * 100

    metrics = checker.metrics_from_samples(1180, 720, samples)

    assert metrics.distinct_colors == 1
    assert metrics.luminance_range == 0
    assert checker.validate_metrics("native", metrics)


def test_real_gui_render_metrics_accept_detailed_capture() -> None:
    checker = _load_checker()
    samples = []
    for index in range(120):
        samples.append(((index * 13) % 255, (index * 29) % 255, (index * 47) % 255))

    metrics = checker.metrics_from_samples(1180, 720, samples)

    assert metrics.distinct_colors >= checker.MIN_DISTINCT_COLORS
    assert metrics.luminance_range >= checker.MIN_LUMINANCE_RANGE
    assert metrics.non_background_ratio >= checker.MIN_NON_BACKGROUND_RATIO
    assert checker.validate_metrics("native", metrics) == []


def test_real_gui_render_manifest_contract_names_required_widgets() -> None:
    checker = _load_checker()

    assert checker.MANIFEST_NAME == "real-gui-render-manifest.json"
    assert checker.REQUIRED_WIDGETS["designSelect"] == "view preset selector"
    assert checker.REQUIRED_WIDGETS["layoutToolbar"] == "layout toolbar"
    assert checker.REQUIRED_WIDGETS["activityLog"] == "activity log"


def test_real_gui_render_uses_preset_specific_widget_contracts() -> None:
    checker = _load_checker()

    native_widgets = checker.required_widgets_for_preset("native")
    moba_widgets = checker.required_widgets_for_preset("mobaxterm")

    assert native_widgets["designSelect"] == "view preset selector"
    assert native_widgets["toolbarSearch"] == "toolbar search"
    assert "designSelect" not in moba_widgets
    assert "toolbarSearch" not in moba_widgets
    assert moba_widgets["quickConnect"] == "Moba quick connect field"
    assert moba_widgets["mobaRibbonButton"] == "Moba ribbon action"


def _load_checker():
    path = Path("scripts/check_real_gui_render.py")
    spec = importlib.util.spec_from_file_location("check_real_gui_render_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
