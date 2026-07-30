from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI_MODULE = "src/remote_ops_workspace/gui.py"
GUI_ERROR_BASELINE = 382
MYPY_PLATFORMS = ("linux", "win32", "darwin")
ERROR_RE = re.compile(r"^(?P<path>.*?):\d+(?::\d+)?: error:")


def check_mypy_output(output: str, returncode: int) -> tuple[list[str], int]:
    errors: list[str] = []
    paths: list[str] = []
    for line in output.splitlines():
        match = ERROR_RE.match(line)
        if match:
            paths.append(match.group("path").replace("\\", "/"))

    if returncode not in {0, 1}:
        errors.append(f"mypy execution failed with exit {returncode}")
    if returncode == 0 and paths:
        errors.append("mypy reported errors despite a successful exit")
    if returncode == 1 and not paths:
        errors.append("mypy failed without parseable source errors")

    unexpected = sorted({path for path in paths if path != GUI_MODULE})
    for path in unexpected:
        errors.append(f"non-GUI production type error reported in {path}")

    gui_errors = sum(path == GUI_MODULE for path in paths)
    if gui_errors > GUI_ERROR_BASELINE:
        errors.append(
            f"GUI type errors increased from the {GUI_ERROR_BASELINE}-error baseline to {gui_errors}"
        )
    return errors, gui_errors


def main() -> int:
    if importlib.util.find_spec("mypy") is None:
        print("non-GUI type gate: mypy is not installed", file=sys.stderr)
        return 2
    results: list[str] = []
    failed = False
    for platform in MYPY_PLATFORMS:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "mypy",
                "src",
                "--platform",
                platform,
                "--no-incremental",
                "--no-pretty",
                "--show-error-codes",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        errors, gui_errors = check_mypy_output(output, completed.returncode)
        results.append(f"{platform}={gui_errors}/{GUI_ERROR_BASELINE}")
        if not errors:
            continue
        failed = True
        for error in errors:
            print(f"non-GUI type gate [{platform}]: {error}", file=sys.stderr)
        for line in output.splitlines():
            match = ERROR_RE.match(line)
            if match and match.group("path").replace("\\", "/") != GUI_MODULE:
                print(f"non-GUI type gate [{platform}]: {line}", file=sys.stderr)
    if failed:
        return 1
    print("non-GUI production type gate passed; " + ", ".join(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
