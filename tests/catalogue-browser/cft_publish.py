"""Sole small public acquisition JSON; never uploads archives/executables/private logs."""
import os
import time
from pathlib import Path

from cft_bundle import MAX_PUBLIC, public_bytes, stable_file


def main():
    repo = Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
    source = repo / '.tmp' / 'catalogue-cft-public' / 'acquisition.json'
    directory = Path(__file__).resolve(strict=True).parent
    if directory != repo / 'tests' / 'catalogue-browser':
        raise ValueError('cft-publish-source-refused')
    _pin, raw = stable_file(source, MAX_PUBLIC, time.monotonic() + 10, raw=True)
    policy_raw = (directory / 'cft-provider-policy.json').read_bytes()
    public_bytes(raw, policy_raw)
    output = repo / '.tmp' / 'catalogue-cft-upload'
    if output.exists():
        raise ValueError('cft-publish-fresh-output-required')
    output.mkdir(mode=0o700)
    with (output / 'acquisition.json').open('xb') as stream:
        stream.write(raw)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit('cft-public-receipt-refused') from None
