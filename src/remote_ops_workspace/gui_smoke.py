"""Bounded packaged-GUI startup, storage, selection and paint verification."""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from . import __version__
from .file_safety import write_bytes_atomic, write_json_atomic
from .models import Profile
from .storage import ProfileStore


def run(output: Path) -> int:
    """Exercise the real GUI in an explicitly selected empty temporary home.

    Installer smoke invokes this through the packaged GUI entrypoint. Normal
    user profiles are never reused, and no protocol connection is launched.
    """
    raw_home = os.environ.get("ROW_HOME")
    if not raw_home:
        raise ValueError("GUI smoke requires ROW_HOME pointing to an empty temporary directory")
    home = Path(raw_home).resolve()
    output = output.resolve()
    if not output.is_relative_to(home):
        raise ValueError("GUI smoke output must be inside the temporary ROW_HOME")
    if home.exists() and any(home.iterdir()):
        raise ValueError("GUI smoke refuses to modify a nonempty ROW_HOME")

    from PyQt6.QtCore import QT_VERSION_STR, QBuffer, QByteArray, QIODevice, Qt, QTimer
    from PyQt6.QtWidgets import QTreeWidgetItemIterator

    from .gui import create_main_window

    profile = Profile(name="Production GUI smoke profile", protocol="ssh", host="127.0.0.1")
    store = ProfileStore()
    store.init(with_examples=False)
    store.add(profile)
    app, window = create_main_window(["row-gui-smoke"], show=True)
    result: dict[str, object] = {
        "schema_version": 1,
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "qt_version": QT_VERSION_STR,
        "qt_platform": app.platformName(),
        "workflow": "packaged-startup-profile-selection-and-paint",
        "success": False,
    }

    def verify() -> None:
        try:
            persisted = window.store.load(resolve=False)
            if [item.to_dict() for item in persisted] != [profile.to_dict()]:
                raise RuntimeError("packaged GUI did not load the persisted smoke profile")
            iterator = QTreeWidgetItemIterator(window.profile_list)
            selected = None
            while True:
                item = iterator.value()
                if item is None:
                    break
                if item.data(0, Qt.ItemDataRole.UserRole) == profile.name:
                    selected = item
                    break
                iterator += 1
            if selected is None:
                raise RuntimeError("persisted profile did not appear in the GUI tree")
            window.profile_list.setCurrentItem(selected)
            app.processEvents()
            if window.profile_list.currentItem() is not selected or not window.isVisible():
                raise RuntimeError("packaged GUI profile selection or visibility failed")
            image = window.grab().toImage()
            if image.isNull() or image.width() < 100 or image.height() < 100:
                raise RuntimeError("packaged GUI did not produce a window-sized image")
            colours = {
                image.pixelColor(x, y).rgba()
                for x in range(0, image.width(), max(1, image.width() // 16))
                for y in range(0, image.height(), max(1, image.height() // 16))
            }
            if len(colours) < 3:
                raise RuntimeError("packaged GUI paint was blank or uniform")
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            if not image.save(buffer, "PNG"):
                raise RuntimeError("packaged GUI image encoding failed")
            buffer.close()
            pixels = data.data()
            screenshot = output.with_suffix(".png")
            write_bytes_atomic(screenshot, pixels, private=True)
            result.update({
                "success": True,
                "profile_persisted": True,
                "profile_selected": True,
                "window_visible": True,
                "paint_colour_count": len(colours),
                "image_width": image.width(),
                "image_height": image.height(),
                "screenshot_sha256": hashlib.sha256(pixels).hexdigest(),
            })
            write_json_atomic(output, result, private=True)
            app.exit(0)
        except Exception as exc:
            # This isolated verifier must make callback failure observable to CI.
            result["error"] = f"{type(exc).__name__}: {exc}"
            try:
                write_json_atomic(output, result, private=True)
            except OSError as report_error:
                print(f"GUI smoke could not save failure evidence: {report_error}", file=sys.stderr)
            app.exit(1)

    paint_timer = QTimer(window)
    paint_timer.setSingleShot(True)
    paint_timer.timeout.connect(verify)
    paint_timer.start(750)
    deadline = QTimer(window)
    deadline.setSingleShot(True)
    deadline.timeout.connect(lambda: app.exit(1))
    deadline.start(15_000)
    try:
        return int(app.exec())
    finally:
        paint_timer.stop()
        deadline.stop()
        window.close()
        app.processEvents()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return run(args.out)
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(f"GUI smoke: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
