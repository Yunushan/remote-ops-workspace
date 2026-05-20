#!/usr/bin/env python3
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from remote_ops_workspace.doctor import run_doctor
from remote_ops_workspace.paths import data_dir


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = Path.cwd() / f"support-bundle-{stamp}.zip"
    report = run_doctor().to_dict()
    report["note"] = "Review before sharing. This bundle intentionally excludes vault.json and private keys."
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doctor.json", json.dumps(report, indent=2))
        profiles = data_dir() / "profiles.json"
        if profiles.exists():
            zf.write(profiles, "profiles.redaction-required.json")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
