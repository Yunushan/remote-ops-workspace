from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.moba_customizer import validate_professional_update_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a MobaXterm Professional-style signed update manifest.",
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--channel", default="")
    parser.add_argument("--organization", default="")
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = validate_professional_update_manifest(
        args.manifest,
        public_key=args.public_key,
        expected_channel=args.channel,
        expected_organization=args.organization,
        assets_dir=args.assets_dir,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    elif result.passed:
        print("moba professional update manifest passed")
    else:
        for error in result.errors:
            print(f"moba professional update manifest: {error}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
