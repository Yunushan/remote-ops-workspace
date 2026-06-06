from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.gui_designs import GUI_DESIGN_PRESETS  # noqa: E402

REQUESTED_SIZE = (1420, 820)
MIN_CAPTURE_SIZE = (1100, 680)
MANIFEST_NAME = "real-gui-render-manifest.json"
COMMON_REQUIRED_WIDGETS = {
    "profileTree": "profile tree",
    "sessionTabs": "session tabs",
    "mainToolbar": "main toolbar",
}
NON_MOBA_REQUIRED_WIDGETS = {
    "designSelect": "view preset selector",
    "layoutToolbar": "layout toolbar",
    "toolbarSearch": "toolbar search",
    "activityLog": "activity log",
}
MOBA_REQUIRED_WIDGETS = {
    "quickConnect": "Moba quick connect field",
    "mobaRail": "Moba side rail",
    "mobaRibbonButton": "Moba ribbon action",
    "mobaXServerAction": "Moba X server action",
}
REQUIRED_WIDGETS = {
    **COMMON_REQUIRED_WIDGETS,
    **NON_MOBA_REQUIRED_WIDGETS,
}
MIN_DISTINCT_COLORS = 18
MIN_LUMINANCE_RANGE = 40
MIN_NON_BACKGROUND_RATIO = 0.08


@dataclass(frozen=True)
class RenderMetrics:
    width: int
    height: int
    sampled_pixels: int
    distinct_colors: int
    luminance_range: int
    non_background_ratio: float

    def to_dict(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "sampled_pixels": self.sampled_pixels,
            "distinct_colors": self.distinct_colors,
            "luminance_range": self.luminance_range,
            "non_background_ratio": round(self.non_background_ratio, 4),
        }


@dataclass(frozen=True)
class CaptureResult:
    preset_id: str
    preset_label: str
    metrics: RenderMetrics
    path: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "preset_id": self.preset_id,
            "preset_label": self.preset_label,
            "metrics": self.metrics.to_dict(),
        }
        if self.path is not None:
            payload["path"] = self.path
        if self.size_bytes is not None:
            payload["size_bytes"] = self.size_bytes
        if self.sha256 is not None:
            payload["sha256"] = self.sha256
        return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that the real PyQt6 GUI renders visible pixels.")
    parser.add_argument(
        "--preset",
        action="append",
        choices=[preset.id for preset in GUI_DESIGN_PRESETS],
        help="Preset id to capture. Can be passed more than once. Defaults to every preset.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Write live PyQt6 screenshots and a manifest to this directory.",
    )
    parser.add_argument(
        "--require-pyqt6",
        action="store_true",
        help="Fail instead of using the fail-closed branch when PyQt6 is not installed.",
    )
    args = parser.parse_args(argv)

    selected = select_presets(args.preset)
    errors, messages = check_real_gui_render(
        selected,
        out_dir=args.out_dir,
        require_pyqt6=args.require_pyqt6,
    )
    for message in messages:
        print(f"real GUI render: {message}")
    if errors:
        for error in errors:
            print(f"real GUI render: {error}", file=sys.stderr)
        return 1
    print("real GUI render check passed")
    return 0


def select_presets(ids: list[str] | None) -> list[str]:
    if not ids:
        return [preset.id for preset in GUI_DESIGN_PRESETS]
    seen: set[str] = set()
    selected: list[str] = []
    for preset_id in ids:
        if preset_id not in seen:
            selected.append(preset_id)
            seen.add(preset_id)
    return selected


def check_real_gui_render(
    preset_ids: list[str] | None = None,
    *,
    out_dir: Path | None = None,
    require_pyqt6: bool = False,
) -> tuple[list[str], list[str]]:
    from remote_ops_workspace import gui

    selected = preset_ids or [preset.id for preset in GUI_DESIGN_PRESETS]
    if not module_available("PyQt6"):
        try:
            gui.create_main_window(["row-real-gui-render-check"], show=False)
        except gui.GuiDependencyError:
            message = "PyQt6 unavailable; GUI factory fail-closed path verified"
            if require_pyqt6:
                return ["PyQt6 is required for live GUI render capture"], [message]
            return [], [message]
        return ["GUI factory must raise GuiDependencyError when PyQt6 is unavailable"], []

    return capture_live_gui(selected, out_dir=out_dir)


def capture_live_gui(
    preset_ids: list[str],
    *,
    out_dir: Path | None = None,
) -> tuple[list[str], list[str]]:
    old_qpa = os.environ.get("QT_QPA_PLATFORM")
    old_home = os.environ.get("ROW_HOME")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    captures: list[CaptureResult] = []
    errors: list[str] = []
    messages: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="row-real-gui-") as raw_tmp:
            os.environ["ROW_HOME"] = str(Path(raw_tmp) / "row-home")
            captures, errors, messages = _capture_live_gui(preset_ids, out_dir=out_dir)
    finally:
        restore_env("QT_QPA_PLATFORM", old_qpa)
        restore_env("ROW_HOME", old_home)

    if out_dir is not None and not errors:
        write_manifest(out_dir, captures)
        messages.append(f"wrote live screenshot manifest to {display(out_dir / MANIFEST_NAME)}")
    return errors, messages


def _capture_live_gui(
    preset_ids: list[str],
    *,
    out_dir: Path | None,
) -> tuple[list[CaptureResult], list[str], list[str]]:
    from PyQt6.QtCore import QCoreApplication
    from PyQt6.QtWidgets import QComboBox

    from remote_ops_workspace import gui

    app, window = gui.create_main_window(["row-real-gui-render-check"], show=True)
    captures: list[CaptureResult] = []
    errors: list[str] = []
    messages: list[str] = []
    try:
        window.resize(*REQUESTED_SIZE)
        window.show()
        process_events(app)

        widget_errors = check_required_widgets(window, COMMON_REQUIRED_WIDGETS)
        if widget_errors:
            return captures, widget_errors, messages

        design_select = window.findChild(QComboBox, "designSelect")
        if design_select is None:
            return captures, ["real GUI render could not locate design selector"], messages

        for preset_id in preset_ids:
            preset = next((item for item in GUI_DESIGN_PRESETS if item.id == preset_id), None)
            if preset is None:
                errors.append(f"unknown GUI preset requested: {preset_id}")
                continue
            index = design_select.findData(preset.id)
            if index < 0:
                errors.append(f"live GUI design selector missing preset: {preset.id}")
                continue
            design_select.setCurrentIndex(index)
            window.resize(*REQUESTED_SIZE)
            process_events(app)

            preset_widget_errors = check_required_widgets(
                window,
                required_widgets_for_preset(preset.id),
                context=f"{preset.id} live GUI",
            )
            if preset_widget_errors:
                errors.extend(preset_widget_errors)
                continue

            pixmap = window.grab()
            metrics = metrics_from_qimage(pixmap.toImage())
            errors.extend(validate_metrics(preset.id, metrics))

            artifact = artifact_metadata(out_dir, pixmap, preset.id) if out_dir is not None else {}
            captures.append(
                CaptureResult(
                    preset_id=preset.id,
                    preset_label=preset.label,
                    metrics=metrics,
                    path=artifact.get("path"),
                    size_bytes=artifact.get("size_bytes"),
                    sha256=artifact.get("sha256"),
                )
            )
            messages.append(
                f"{preset.id} captured {metrics.width}x{metrics.height}, "
                f"{metrics.distinct_colors} sampled colors"
            )
    finally:
        window.close()
        process_events(app)
        QCoreApplication.processEvents()
    return captures, errors, messages


def process_events(app: Any) -> None:
    for _ in range(4):
        app.processEvents()


def required_widgets_for_preset(preset_id: str) -> dict[str, str]:
    if preset_id == "mobaxterm":
        return {
            **COMMON_REQUIRED_WIDGETS,
            **MOBA_REQUIRED_WIDGETS,
        }
    return {
        **COMMON_REQUIRED_WIDGETS,
        **NON_MOBA_REQUIRED_WIDGETS,
    }


def check_required_widgets(
    window: Any,
    required_widgets: dict[str, str] | None = None,
    *,
    context: str = "live GUI",
) -> list[str]:
    from PyQt6.QtWidgets import QWidget

    errors: list[str] = []
    widgets = required_widgets or REQUIRED_WIDGETS
    for object_name, label in widgets.items():
        widget = window.findChild(QWidget, object_name)
        if widget is None:
            errors.append(f"{context} missing {label}: {object_name}")
            continue
        geometry = widget.geometry()
        if geometry.width() <= 0 or geometry.height() <= 0:
            errors.append(f"{context} {label} has empty geometry: {object_name}")
        if hasattr(widget, "isVisible") and not widget.isVisible():
            errors.append(f"{context} {label} is not visible: {object_name}")
    return errors


def metrics_from_qimage(image: Any) -> RenderMetrics:
    width = int(image.width())
    height = int(image.height())
    samples: list[tuple[int, int, int]] = []
    x_step = max(1, width // 48)
    y_step = max(1, height // 36)
    for y in range(0, height, y_step):
        for x in range(0, width, x_step):
            color = image.pixelColor(x, y)
            samples.append((int(color.red()), int(color.green()), int(color.blue())))
    return metrics_from_samples(width, height, samples)


def metrics_from_samples(
    width: int,
    height: int,
    samples: list[tuple[int, int, int]],
) -> RenderMetrics:
    if not samples:
        return RenderMetrics(width, height, 0, 0, 0, 0.0)
    distinct = len(set(samples))
    luminance_values = [int(round((red * 0.2126) + (green * 0.7152) + (blue * 0.0722))) for red, green, blue in samples]
    background = most_common_color(samples)
    non_background = sum(1 for color in samples if color_distance(color, background) > 6)
    return RenderMetrics(
        width=width,
        height=height,
        sampled_pixels=len(samples),
        distinct_colors=distinct,
        luminance_range=max(luminance_values) - min(luminance_values),
        non_background_ratio=non_background / len(samples),
    )


def validate_metrics(preset_id: str, metrics: RenderMetrics) -> list[str]:
    errors: list[str] = []
    if metrics.width < MIN_CAPTURE_SIZE[0] or metrics.height < MIN_CAPTURE_SIZE[1]:
        errors.append(
            f"{preset_id} live GUI capture dimensions {(metrics.width, metrics.height)} "
            f"must be at least {MIN_CAPTURE_SIZE}"
        )
    if metrics.distinct_colors < MIN_DISTINCT_COLORS:
        errors.append(f"{preset_id} live GUI capture has too few sampled colors: {metrics.distinct_colors}")
    if metrics.luminance_range < MIN_LUMINANCE_RANGE:
        errors.append(f"{preset_id} live GUI capture luminance range is too small: {metrics.luminance_range}")
    if metrics.non_background_ratio < MIN_NON_BACKGROUND_RATIO:
        errors.append(
            f"{preset_id} live GUI capture non-background ratio is too small: "
            f"{metrics.non_background_ratio:.4f}"
        )
    return errors


def most_common_color(samples: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    counts: dict[tuple[int, int, int], int] = {}
    for color in samples:
        counts[color] = counts.get(color, 0) + 1
    return max(counts, key=counts.get)


def color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return abs(left[0] - right[0]) + abs(left[1] - right[1]) + abs(left[2] - right[2])


def artifact_metadata(out_dir: Path, pixmap: Any, preset_id: str) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{preset_id}-live.png"
    if not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"failed to save GUI screenshot: {display(path)}")
    data = path.read_bytes()
    return {
        "path": path.name,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def write_manifest(out_dir: Path, captures: list[CaptureResult]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "renderer": "scripts/check_real_gui_render.py",
        "capture_mode": "live-pyqt6-offscreen",
        "requested_window_size": {"width": REQUESTED_SIZE[0], "height": REQUESTED_SIZE[1]},
        "minimum_capture_size": {"width": MIN_CAPTURE_SIZE[0], "height": MIN_CAPTURE_SIZE[1]},
        "required_widgets": REQUIRED_WIDGETS,
        "common_required_widgets": COMMON_REQUIRED_WIDGETS,
        "preset_required_widgets": {
            "default": NON_MOBA_REQUIRED_WIDGETS,
            "mobaxterm": MOBA_REQUIRED_WIDGETS,
        },
        "captures": [capture.to_dict() for capture in captures],
    }
    (out_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def module_available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def restore_env(name: str, old_value: str | None) -> None:
    if old_value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = old_value


def display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
