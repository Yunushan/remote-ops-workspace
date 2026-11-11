"""Keep the minimum GUI runtime inputs tied to the supported-version policy."""

from __future__ import annotations

import json
import re
from pathlib import Path


def test_minimum_pyqt_runtime_lock_is_complete_and_hash_pinned() -> None:
    policy = json.loads(Path("configs/release_toolchain.json").read_text(encoding="utf-8"))
    text = Path("tests/fixtures/pyqt6-minimum-requirements.txt").read_text(encoding="utf-8")
    blocks = re.findall(r"(?m)^([a-z0-9-]+)==([^\s]+) \\\n((?:[ \t]+--hash=sha256:[0-9a-f]{64}(?: \\)?\n)+)", text)
    versions = {name: version for name, version, _hashes in blocks}

    assert len(blocks) == 3
    assert versions == {
        "pyqt6": policy["pyqt6_support"]["minimum_version"],
        "pyqt6-qt6": "6.11.2",
        "pyqt6-sip": "13.13.0",
    }
    assert all(re.search(r"--hash=sha256:[0-9a-f]{64}", hashes) for _, _, hashes in blocks)
