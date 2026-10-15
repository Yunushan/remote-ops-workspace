from __future__ import annotations

import hashlib
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from remote_ops_workspace import gui_smoke


def test_smoke_refuses_existing_operator_state(monkeypatch, tmp_path) -> None:
    sentinel = tmp_path / "operator-profile.json"
    sentinel.write_bytes(b"preserve operator bytes")
    monkeypatch.setenv("ROW_HOME", str(tmp_path))

    with pytest.raises(ValueError, match="nonempty"):
        gui_smoke.run(tmp_path / "result.json")

    assert sentinel.read_bytes() == b"preserve operator bytes"
    assert sorted(path.name for path in tmp_path.iterdir()) == [sentinel.name]


def test_smoke_requires_explicit_temporary_home(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ROW_HOME", raising=False)
    assert gui_smoke.main(["--out", str(tmp_path / "result.json")]) == 1


def test_module_entrypoint_reports_missing_temporary_home(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ROW_HOME", raising=False)
    monkeypatch.setattr(sys, "argv", ["row-gui-smoke", "--out", str(tmp_path / "result.json")])
    monkeypatch.delitem(sys.modules, "remote_ops_workspace.gui_smoke")
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("remote_ops_workspace.gui_smoke", run_name="__main__")
    assert stopped.value.code == 1


def test_smoke_rejects_output_outside_temporary_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "home"))
    with pytest.raises(ValueError, match="inside"):
        gui_smoke.run(tmp_path / "result.json")
    assert not (tmp_path / "home").exists()


def test_real_gui_smoke_renders_and_selects_persisted_profile(tmp_path) -> None:
    pytest.importorskip("PyQt6")
    home = tmp_path / "isolated-home"
    output = home / "result.json"
    environment = {**os.environ, "ROW_HOME": str(home), "QT_QPA_PLATFORM": "offscreen"}
    environment["PYTHONPATH"] = str(Path("src").resolve())
    completed = subprocess.run(
        [sys.executable, "-m", "remote_ops_workspace.gui_smoke", "--out", str(output)],
        env=environment, capture_output=True, text=True, timeout=25, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["success"] is True
    assert report["profile_persisted"] is True
    assert report["profile_selected"] is True
    assert report["window_visible"] is True
    assert report["paint_colour_count"] >= 3
    assert report["qt_platform"] == "offscreen"
    assert report["screenshot_sha256"] == hashlib.sha256(output.with_suffix(".png").read_bytes()).hexdigest()


def test_smoke_main_verifies_real_gui_in_process(monkeypatch, tmp_path) -> None:
    pytest.importorskip("PyQt6")
    home = tmp_path / "gui-home"
    monkeypatch.setenv("ROW_HOME", str(home))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    assert gui_smoke.main(["--out", str(home / "result.json")]) == 0
    assert json.loads((home / "result.json").read_text(encoding="utf-8"))["success"] is True


@pytest.mark.parametrize("failure", [
    "storage", "persisted-mismatch", "missing-profile", "selection", "visibility",
    "blank-paint", "invalid-image", "narrow-image", "short-image", "encoding", "report-write",
])
def test_gui_failure_is_bounded_and_observable(monkeypatch, tmp_path, failure) -> None:
    pytest.importorskip("PyQt6")
    from PyQt6.QtGui import QImage

    from remote_ops_workspace import gui

    home = tmp_path / "gui-home"
    monkeypatch.setenv("ROW_HOME", str(home))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    original = gui.create_main_window

    def create_window(*args, **kwargs):
        app, window = original(*args, **kwargs)
        if failure == "storage":
            def denied(*_args, **_kwargs):
                raise PermissionError("simulated storage denial")
            monkeypatch.setattr(window.store, "load", denied)
        elif failure == "persisted-mismatch":
            monkeypatch.setattr(window.store, "load", lambda **_kwargs: [])
        elif failure == "missing-profile":
            window.profile_list.clear()
        elif failure == "visibility":
            window.hide()
        elif failure == "selection":
            monkeypatch.setattr(window.profile_list, "currentItem", lambda: None)
        elif failure in {"blank-paint", "invalid-image", "narrow-image", "short-image", "encoding"}:
            class Frame:
                def toImage(self):
                    width = 50 if failure == "narrow-image" else 200
                    height = 50 if failure == "short-image" else 200
                    image = QImage(width, height, QImage.Format.Format_RGB32)
                    image.fill(0)
                    if failure == "invalid-image":
                        monkeypatch.setattr(image, "isNull", lambda: True)
                    elif failure == "encoding":
                        image.setPixel(0, 0, 0xFF0000)
                        image.setPixel(12, 0, 0x00FF00)
                        monkeypatch.setattr(image, "save", lambda *_args: False)
                    return image
            monkeypatch.setattr(window, "grab", lambda: Frame())
        return app, window

    monkeypatch.setattr(gui, "create_main_window", create_window)
    if failure == "report-write":
        def denied_report(*_args, **_kwargs):
            raise PermissionError("simulated report write denial")
        monkeypatch.setattr(gui_smoke, "write_json_atomic", denied_report)

    output = home / "result.json"
    assert gui_smoke.run(output) == 1
    if failure == "report-write":
        assert not output.exists()
    else:
        report = json.loads(output.read_text(encoding="utf-8"))
        assert report["success"] is False
        assert report["error"]


def test_gui_startup_dependency_failure_is_reported(monkeypatch, tmp_path) -> None:
    from remote_ops_workspace import gui

    monkeypatch.setenv("ROW_HOME", str(tmp_path / "gui-home"))

    def unavailable(*_args, **_kwargs):
        raise ImportError("simulated unavailable desktop backend")

    monkeypatch.setattr(gui, "create_main_window", unavailable)
    assert gui_smoke.main(["--out", str(tmp_path / "gui-home/result.json")]) == 1


def test_gui_smoke_timeout_cancels_pending_paint(monkeypatch, tmp_path) -> None:
    pytest.importorskip("PyQt6")
    from PyQt6.QtCore import QTimer

    monkeypatch.setenv("ROW_HOME", str(tmp_path / "timed-out-home"))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    start = QTimer.start

    def deadline_now(timer, milliseconds):
        return start(timer, 1 if milliseconds == 15_000 else milliseconds)

    with monkeypatch.context() as patch:
        patch.setattr(QTimer, "start", deadline_now)
        assert gui_smoke.run(tmp_path / "timed-out-home/result.json") == 1
    assert not (tmp_path / "timed-out-home/result.json").exists()
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "next-home"))
    assert gui_smoke.run(tmp_path / "next-home/result.json") == 0
