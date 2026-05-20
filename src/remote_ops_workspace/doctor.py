from __future__ import annotations

import json
import platform
import shutil
import sys
from dataclasses import dataclass

from .launcher import protocol_clients
from .paths import data_dir


@dataclass(slots=True)
class DoctorResult:
    platform: str
    python: str
    data_dir: str
    executables: dict[str, dict[str, bool]]

    def to_dict(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "python": self.python,
            "data_dir": self.data_dir,
            "executables": self.executables,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def run_doctor() -> DoctorResult:
    executables: dict[str, dict[str, bool]] = {}
    for protocol, candidates in protocol_clients().items():
        executables[protocol] = {candidate: shutil.which(candidate) is not None for candidate in candidates}
    return DoctorResult(
        platform=f"{platform.system()} {platform.release()} ({platform.machine()})",
        python=sys.version.split()[0],
        data_dir=str(data_dir()),
        executables=executables,
    )
