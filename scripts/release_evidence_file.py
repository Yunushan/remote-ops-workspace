"""Publish staged release evidence despite short-lived Windows file locks."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path


def retry_evidence_operation(operation: Callable[[], None]) -> None:
    for delay in (0.01, 0.02, 0.04, 0.08, 0.16):
        try:
            operation()
            return
        except PermissionError as error:
            # Windows may deny a rename while another process briefly opens either file.
            if getattr(error, "winerror", None) not in {5, 32, 33}:
                raise
            time.sleep(delay)
    operation()


def replace_evidence_file(staged: Path, destination: Path) -> None:
    retry_evidence_operation(lambda: os.replace(staged, destination))
