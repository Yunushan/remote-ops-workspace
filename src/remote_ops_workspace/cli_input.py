"""Read secrets supplied through CLI environment variables."""

from __future__ import annotations

import os


def secret_from_env(name: str, label: str) -> str:
    if name not in os.environ:
        raise ValueError(f"{label} environment variable is not set: {name}")
    value = os.environ[name]
    if value == "":
        raise ValueError(f"{label} environment variable is empty: {name}")
    return value
