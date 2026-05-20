#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
NAME = "remote-ops-workspace"

if __name__ == "__main__":
    DIST.mkdir(exist_ok=True)
    archive = shutil.make_archive(str(DIST / NAME), "zip", ROOT)
    print(f"created {archive}")
