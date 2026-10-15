from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import tomllib
from candidate_windows_owned import owned_result_succeeded, run_owned, utc


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_record(path, record):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(record, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(
        description="Separate console diagnostic; never proves original windowed artifact success"
    )
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    root = Path.cwd()
    output = root / "build/candidate-proof" / args.target / "console-diagnostic"
    output.mkdir(parents=True, exist_ok=True)
    record = {
        "scope": "different console artifact from the same candidate source and locked environment; no original-artifact GUI success claim",
        "started_at_utc": utc(),
        "build": None,
        "launch": None,
        "diagnostic_success": False,
    }
    report = output / "diagnostic.json"
    save_record(report, record)
    try:
        original = root / "build/native/windows/pyinstaller-dist/row-gui.exe"
        record["original_windowed_sha256"] = sha(original)
        launcher = output / "diagnostic_launcher.py"
        launcher.write_text(
            "from remote_ops_workspace.gui import main\nraise SystemExit(main())\n",
            encoding="utf-8",
        )
        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--onefile",
            "--console",
            "--name",
            "row-gui-diagnostic",
            "--distpath",
            str(output / "dist"),
            "--workpath",
            str(output / "work"),
            "--specpath",
            str(output),
            "--collect-submodules",
            "remote_ops_workspace",
            "--collect-data",
            "remote_ops_workspace",
            "--add-data",
            str(root / "configs") + ";remote_ops_workspace/configs",
            "--add-data",
            str(root / "apps/web") + ";remote_ops_workspace/web",
            "--copy-metadata",
            "remote-ops-workspace",
            "--collect-submodules",
            "pyftpdlib",
            "--collect-submodules",
            "OpenSSL",
            "--hidden-import",
            "asyncore",
            "--hidden-import",
            "asynchat",
            "--hidden-import",
            "PyQt6.QtCore",
            "--hidden-import",
            "PyQt6.QtGui",
            "--hidden-import",
            "PyQt6.QtWidgets",
            str(launcher),
        ]
        record["build_command"] = command
        save_record(report, record)
        build_output = output / "build.json"
        build_env = os.environ.copy()
        for key in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
            build_env.pop(key, None)
        record["build"] = run_owned(
            Path(command[0]), command[1:], build_env, build_output, 600
        )
        save_record(build_output, record["build"])
        record["build_returncode"] = record["build"].get("exit_code")
        save_record(report, record)
        if not owned_result_succeeded(record["build"]):
            raise RuntimeError("diagnostic build failed or owned cleanup was not confirmed")
        executable = output / "dist/row-gui-diagnostic.exe"
        record["diagnostic_artifact_sha256"] = sha(executable)
        home = output / "fresh-row-home"
        home.mkdir()
        env = os.environ.copy()
        for key in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
            env.pop(key, None)
        env.update({"ROW_HOME": str(home), "QT_QPA_PLATFORM": "windows"})
        launch_output = output / "launch.json"
        record["launch"] = run_owned(
            executable, ["--smoke-json", str(home / "smoke.json")], env, launch_output, 45
        )
        save_record(launch_output, record["launch"])
        save_record(report, record)
        if not owned_result_succeeded(record["launch"]):
            raise RuntimeError("diagnostic launch failed or owned cleanup was not confirmed")
        payload = json.loads((home / "smoke.json").read_text(encoding="utf-8"))
        record["diagnostic_smoke_result"] = payload
        expected_version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]["version"]
        screenshot = home / "smoke.png"
        valid = (
            payload.get("success") is True
            and payload.get("frozen") is True
            and payload.get("qt_platform") == "windows"
            and payload.get("version") == expected_version
            and all(
                payload.get(key) is True
                for key in ("profile_persisted", "profile_selected", "window_visible")
            )
            and payload.get("paint_colour_count", 0) >= 3
            and screenshot.is_file()
            and sha(screenshot) == payload.get("screenshot_sha256")
        )
        if not valid:
            raise RuntimeError("diagnostic GUI report or screenshot verification failed")
        record["diagnostic_success"] = True
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        record["finished_at_utc"] = utc()
        save_record(report, record)
    print(json.dumps(record, indent=2))
    return 0 if record["diagnostic_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
