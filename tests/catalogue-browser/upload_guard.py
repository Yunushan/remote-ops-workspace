"""Only a fixed-schema bounded receipt reaches the sole upload file."""
import json
import os
import stat
from pathlib import Path

from gate_contract import need, public_bytes


def main():
    need(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
         and os.environ.get('GITHUB_REPOSITORY') == 'Yunushan/remote-ops-workspace')
    repo = Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
    source = repo / '.tmp' / 'catalogue-browser-public' / 'result.json'
    directory = source.parent
    info = directory.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700)
    info = source.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid() and info.st_size <= 65536)
    raw = public_bytes(source.read_bytes())
    destination = repo / '.tmp' / 'catalogue-browser-upload'
    need(not destination.exists())
    destination.mkdir(mode=0o700)
    with (destination / 'result.json').open('xb') as stream:
        stream.write(raw)
        stream.flush()
    diagnostic = json.loads(raw)
    fields = ('schema', 'status', 'complete', 'phase', 'preparation_step', 'chrome_file_stage',
        'forced_cleanup_attempted', 'cleanup_complete', 'readiness_credit')
    summary = {key: diagnostic[key] for key in fields if key in diagnostic}
    line = json.dumps(summary, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    need(len(line.encode('ascii')) <= 2048)
    print('catalogue-public-diagnostic=' + line, flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('catalogue-public-receipt-refused') from None
