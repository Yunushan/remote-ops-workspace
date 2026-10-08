"""Hosted-only stdin controller around the actual ProfileStore/API/handler.

No sockets or product imports occur during import. Frames and logs stay private.
"""
import hashlib
import json
import os
import select
import sys
import threading
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit

from gate_contract import CASES, decode, exact, integer, need


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


def frame():
    need(bool(select.select([sys.stdin.buffer], [], [], 15)[0]))
    raw = sys.stdin.buffer.readline(4097)
    need(bool(raw) and len(raw) <= 4096 and raw.endswith(b'\n'))
    return decode(raw, 4096)


def emit(value):
    raw = packed(value)
    need(len(raw) <= 32768)
    sys.stdout.buffer.write(raw + b'\n')
    sys.stdout.buffer.flush()


def main():
    need(sys.platform == 'linux' and sys.flags.isolated == 1 and sys.flags.no_site == 1)
    config = frame()
    exact(config, {'repo', 'home', 'port', 'token', 'nonce', 'launch'})
    integer(config['port'], 65535)
    integer(config['launch'], 2, 1)
    need(type(config['token']) is str and len(config['token']) == 64)
    need(type(config['nonce']) is str and len(config['nonce']) == 64)
    repo = Path(config['repo']).resolve(strict=True)
    home = Path(config['home']).resolve(strict=True)
    need(home == Path(os.environ['ROW_HOME']).resolve(strict=True) and home.stat().st_mode & 0o777 == 0o700)
    inventory = decode((Path(__file__).parent / 'product-source-inventory.json').read_bytes(), 65536)
    pins = {row['path']: row for row in inventory['files']}
    src = repo / 'src'
    sys.path.insert(0, str(src))
    # Imports are intentionally inside the hosted entry point, never pure fixtures.
    from remote_ops_workspace.enterprise_policy import machine_enterprise_policy_path
    from remote_ops_workspace.models import Profile
    from remote_ops_workspace.storage import ProfileStore
    from remote_ops_workspace.web_server import QuietHandler, ReusableTCPServer, WebProfileApi

    def machine_policy_absent():
        policy = machine_enterprise_policy_path()
        need(policy == Path('/etc/remote-ops-workspace/policy.json'))
        try:
            policy.lstat()
        except FileNotFoundError:
            return True
        need(False)  # No override, deletion or weakened machine-policy authority.

    need(machine_policy_absent())

    def loaded_sources():
        rows = []
        for name, module in sorted(sys.modules.items()):
            if name == 'remote_ops_workspace' or name.startswith('remote_ops_workspace.'):
                path = Path(module.__file__).resolve(strict=True)
                need(path.is_relative_to(src))
                relative = path.relative_to(repo).as_posix()
                raw = path.read_bytes()
                expected = pins.get(relative)
                need(expected is not None and expected['size'] == len(raw)
                     and expected['sha256'] == hashlib.sha256(raw).hexdigest())
                rows.append({'relative': relative, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        need(1 <= len(rows) <= 65)
        return hashlib.sha256(packed(rows)).hexdigest()

    loaded_before = loaded_sources()
    store = ProfileStore(home / 'profiles.json')
    if config['launch'] == 1:
        need(not store.path.exists())
        # Synthetic private references, no real key/secret/client or external connection.
        store.save([Profile(name='catalogue seed', protocol='ssh', host='seed.example.invalid', port=22,
            credential_ref='catalogue-private-reference', identity_file='catalogue-private-key')])
    else:
        need(store.path.is_file())
    events = []
    state = {'case': 'api-read', 'posts': [], 'active': 0}
    lock = threading.Lock()

    class ObservedApi(WebProfileApi):
        def add_profile(self, payload):
            # Observe the actual envelope, then delegate every decision/write unchanged.
            with lock:
                state['posts'].append(type(payload) is dict and payload.get('replace') is False)
            return super().add_profile(payload)

    class ObservedHandler(QuietHandler):
        def handle(self):
            with lock:
                state['active'] += 1
            try:
                super().handle()
            finally:
                with lock:
                    state['active'] -= 1

        def log_message(self, _format, *_args):
            # Do not write request URLs, headers, private metadata or product errors.
            pass

        def send_response(self, code, message=None):
            self.observed_status = code
            self.observed_no_store = False
            super().send_response(code, message)

        def send_header(self, keyword, value):
            if keyword.lower() == 'cache-control' and value == 'no-store':
                self.observed_no_store = True
            super().send_header(keyword, value)

        def end_headers(self):
            super().end_headers()
            path = urlsplit(self.path).path
            route = {'/api/v1/profiles': 'catalogue', '/api/v1/health': 'health', '/healthz': 'health',
                '/enterprise-policy.json': 'policy'}.get(path, 'static')
            if route == 'static' and path not in ('/', '/index.html', '/styles.css', '/app.js', '/manifest.json', '/sw.js'):
                return
            with lock:
                need(len(events) < 128)
                events.append({'launch': config['launch'], 'ordinal': len(events) + 1,
                    'case': state['case'], 'method': self.command, 'route': route,
                    'status': self.observed_status, 'no_store': self.observed_no_store,
                    'authorization_present': self.headers.get('Authorization') is not None})

    api = ObservedApi(store, config['token'])
    ObservedHandler.api = api
    server = ReusableTCPServer(('127.0.0.1', config['port']),
        partial(ObservedHandler, directory=str(repo / 'apps' / 'web')))
    server.daemon_threads = False
    server.block_on_close = True
    server.timeout = 1
    worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05})
    worker.start()

    def inspect():
        public = api.profiles()
        raw = packed(public)
        disk = store.path.read_bytes()
        need(len(raw) <= 262144 and len(disk) <= 262144)
        need(all('credential_ref' not in row and 'identity_file' not in row for row in public))
        with lock:
            return {'profiles': public, 'count': len(public), 'digest': hashlib.sha256(raw).hexdigest(),
                'disk_digest': hashlib.sha256(disk).hexdigest(), 'events': list(events),
                'posts_replace_false': list(state['posts']), 'loaded_source_digest': loaded_sources()}

    emit({'ready': True, 'nonce': config['nonce'], 'port': server.server_address[1], 'inventory': inspect()})
    try:
        while True:
            request = frame()
            exact(request, {'op', 'nonce', 'case'})
            need(request['nonce'] == config['nonce'] and request['case'] in CASES)
            need(request['op'] in ('mark', 'inspect', 'stop'))
            with lock:
                state['case'] = request['case']
            if request['op'] == 'stop':
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)
                with lock:
                    need(state['active'] == 0 and not worker.is_alive())
                need(loaded_sources() == loaded_before)
                need(machine_policy_absent())
                emit({'stopped': True, 'nonce': config['nonce'], 'inventory': inspect()})
                return
            emit({'nonce': config['nonce'], 'inventory': inspect()})
    finally:
        if worker.is_alive():
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Private stdin/stdout protocol still receives only a fixed refusal.
        sys.stderr.write('catalogue-fixture-refused\n')
        raise SystemExit(1) from None
