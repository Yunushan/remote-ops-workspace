"""Isolated stdlib bootstrap; no user/site packages or cwd import fallback."""
import runpy
import sys
from pathlib import Path

if __name__ == '__main__':
    if sys.flags.isolated != 1 or sys.flags.no_site != 1 or not sys.dont_write_bytecode:
        raise SystemExit('catalogue-isolation-refused')
    directory = Path(__file__).resolve(strict=True).parent
    targets = {'run': 'host_controller.py', 'fixture': 'fixture_server.py', 'publish': 'upload_guard.py'}
    if len(sys.argv) != 2 or sys.argv[1] not in targets:
        raise SystemExit('catalogue-entry-refused')
    target = directory / targets[sys.argv[1]]
    sys.path.insert(0, str(directory))
    sys.argv = [str(target)]
    runpy.run_path(str(target), run_name='__main__')
