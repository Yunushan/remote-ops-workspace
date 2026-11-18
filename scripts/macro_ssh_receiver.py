"""Log test keystrokes from the disposable macro fixture's authenticated PTY."""

from __future__ import annotations

import json
import os
import sys
import time
import tty
from pathlib import Path


def main() -> int:
    connection = os.environ["SSH_CONNECTION"]
    descriptor = sys.stdin.fileno()
    tty.setraw(descriptor)
    pid = os.getpid()
    sys.stdout.write(f"ROW_MACRO_READY_{pid} {connection}\r\n")
    sys.stdout.flush()
    with (Path.home() / "observed-input.jsonl").open("a", encoding="utf-8") as log:
        for index in range(1, 513):
            payload = os.read(descriptor, 1)
            if not payload:
                return 0
            value, at = payload.hex(), time.monotonic_ns()
            log.write(json.dumps({"index": index, "hex": value, "monotonic_ns": at, "pid": pid}) + "\n")
            log.flush()
            sys.stdout.write(f"ROW_INPUT_{index}_{value}_{at}\r\n")
            sys.stdout.flush()
    raise ValueError("macro fixture exceeded its input limit")


if __name__ == "__main__":
    raise SystemExit(main())
