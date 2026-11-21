"""Guard fixtures that run installers or daemons in a disposable container."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Linux capability numbers from linux/capability.h.
NETWORK_OR_NAMESPACE_CAPABILITIES = (1 << 12) | (1 << 13) | (1 << 21)


def require_offline_container() -> None:
    if sys.platform != "linux" or not Path("/.dockerenv").is_file() or os.geteuid() != 0:
        raise ValueError("capture requires root inside a disposable Linux Docker container")
    interfaces = Path("/proc/net/dev").read_text(encoding="ascii").splitlines()[2:]
    if {line.partition(":")[0].strip() for line in interfaces} != {"lo"}:
        raise ValueError("capture requires Docker --network none")
    status = Path("/proc/self/status").read_text(encoding="ascii").splitlines()
    capabilities = next(line.split()[1] for line in status if line.startswith("CapBnd:"))
    if int(capabilities, 16) & NETWORK_OR_NAMESPACE_CAPABILITIES:
        raise ValueError("capture requires dropping NET_ADMIN, NET_RAW, and SYS_ADMIN")
