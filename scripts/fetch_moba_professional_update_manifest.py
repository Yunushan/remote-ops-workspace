"""Download the organization update manifest through the release HTTPS trust settings."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for location in (ROOT, ROOT / "src"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace import update_channel  # noqa: E402
from scripts.check_moba_professional_deployment_evidence import (  # noqa: E402
    approved_update_origins,
    decode_object,
)


def fetch(url: str, origins: list[str], output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise ValueError("update manifest output must be a new file")
    settings = {
        "allowed_origins": approved_update_origins(origins, published=True),
        "limits": {"redirects": 3, "http_timeout_seconds": 20},
    }
    update_channel._approved_url(url, settings)
    raw = b"".join(update_channel._chunks(url, settings, time.monotonic() + 60, 1024 * 1024))
    manifest = decode_object(raw, "hosted update manifest")
    if manifest.get("update_url") != url:
        raise ValueError("the hosted update manifest must identify the approved manifest URL")
    with output.open("xb") as stream:
        stream.write(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--origin", action="append", default=[], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        fetch(args.url, args.origin, args.out)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Could not download the organization update manifest: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
