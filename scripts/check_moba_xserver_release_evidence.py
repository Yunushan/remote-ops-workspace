from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.x11 import validate_moba_x_server_release_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify MobaXterm-style packaged X server release evidence.")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = validate_moba_x_server_release_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    elif result.passed:
        print("moba xserver release evidence passed")
    else:
        for error in result.errors:
            print(f"moba xserver release evidence: {error}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
