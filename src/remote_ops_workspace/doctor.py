from __future__ import annotations

import json
import platform
import shutil
import sys
from dataclasses import dataclass

from .launcher import SSH_V1_PROTOCOLS, protocol_clients
from .paths import data_dir

SSHV1_DOCTOR_NOTES = [
    "SSHv1 is insecure and disabled by default in Remote Ops Workspace.",
    "Launching requires a profile option such as allow_insecure_sshv1=true.",
    "Modern OpenSSH builds commonly remove or disable SSH protocol v1 support.",
    "Doctor checks client presence only; it does not prove protocol v1 negotiation works.",
]


@dataclass(slots=True)
class DoctorResult:
    platform: str
    python: str
    data_dir: str
    executables: dict[str, dict[str, bool]]
    protocol_status: dict[str, dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "python": self.python,
            "data_dir": self.data_dir,
            "executables": self.executables,
            "protocol_status": self.protocol_status,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def run_doctor() -> DoctorResult:
    executables: dict[str, dict[str, bool]] = {}
    for protocol, candidates in protocol_clients().items():
        executables[protocol] = {candidate: shutil.which(candidate) is not None for candidate in candidates}
    protocol_status = {
        protocol: _protocol_status(protocol, candidates)
        for protocol, candidates in executables.items()
    }
    return DoctorResult(
        platform=f"{platform.system()} {platform.release()} ({platform.machine()})",
        python=sys.version.split()[0],
        data_dir=str(data_dir()),
        executables=executables,
        protocol_status=protocol_status,
    )


def _protocol_status(protocol: str, candidates: dict[str, bool]) -> dict[str, object]:
    available_clients = [name for name, ok in candidates.items() if ok]
    client_present = bool(available_clients)
    if protocol in SSH_V1_PROTOCOLS:
        status = "legacy-insecure-opt-in" if client_present else "missing-client"
        client_summary = ", ".join(available_clients) if available_clients else "missing ssh client"
        return {
            "status": status,
            "client_present": client_present,
            "launchable_by_default": False,
            "requires_profile_opt_in": True,
            "available_clients": available_clients,
            "summary": (
                f"{status}: {client_summary}; requires allow_insecure_sshv1=true; "
                "protocol v1 support is not verified"
            ),
            "notes": SSHV1_DOCTOR_NOTES,
        }
    return {
        "status": "available" if client_present else "missing",
        "client_present": client_present,
        "launchable_by_default": client_present,
        "requires_profile_opt_in": False,
        "available_clients": available_clients,
        "summary": ", ".join(available_clients) if available_clients else "missing",
        "notes": [],
    }
