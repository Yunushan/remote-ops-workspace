"""Hash and publish release evidence files."""

from __future__ import annotations

import hashlib
import os
import stat
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO


def stream_sha256(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


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


def publish_evidence_directory(staged: Path, destination: Path, *, label: str) -> None:
    expected = staged.lstat()

    def publish() -> None:
        current = staged.lstat()
        if (
            not stat.S_ISDIR(current.st_mode)
            or getattr(current, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            or (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino)
        ):
            raise ValueError(f"{label} staging directory changed before publication")
        if os.path.lexists(destination):
            raise ValueError(f"{label} appeared before publication")
        staged.rename(destination)

    retry_evidence_operation(publish)
