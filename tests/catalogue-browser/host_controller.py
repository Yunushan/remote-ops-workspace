"""Official Ubuntu host controller. This file is never run by local pure tests."""
import hashlib
import http.client
import json
import os
import platform
import queue
import re
import secrets
import select
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from browser_probe import SW_PROBE, Driver
from gate_contract import CHROME_FILE_STAGES, LIMITS, PREPARATION_STEPS, decode, need, validate

DIRECTORY = Path(__file__).resolve().parent
WORKFLOW = '.github/workflows/ubuntu-catalogue-browser.yml'
PUBLIC_REPO = 'Yunushan/remote-ops-workspace'


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


def hashed(value):
    return hashlib.sha256(value).hexdigest()


def file_pin(path, *, root_owned=False, trusted_owner=False, elf=False, maximum=536870912, diagnostic=None):
    def stage(value):
        if diagnostic is not None:
            diagnostic(value)
    path = Path(path)
    stage('lstat-before')
    before = path.lstat()
    stage('regular-file')
    need(stat.S_ISREG(before.st_mode))
    stage('single-link')
    need(before.st_nlink == 1)
    stage('size-bound')
    need(before.st_size <= maximum)
    stage('nonempty')
    need(before.st_size > 0)
    stage('write-mode')
    need(not before.st_mode & 0o022)
    if root_owned:
        stage('root-owner')
        need(before.st_uid == 0)
    if trusted_owner:
        stage('trusted-owner')
        need(before.st_uid in (0, os.getuid()))
    stage('open')
    with path.open('rb') as stream:
        stage('header-read')
        header = stream.read(4)
        stage('rewind')
        stream.seek(0)
        stage('sha256-read')
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if elf:
        stage('elf-header')
        need(header == b'\x7fELF')
        stage('executable-mode')
        need(before.st_mode & 0o111 != 0)
    stage('lstat-after')
    after = path.lstat()
    stage('stable-identity')
    need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
         == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns))
    return {'sha256': digest, 'size': before.st_size, 'device': before.st_dev,
        'inode': before.st_ino, 'mtime_ns': before.st_mtime_ns, 'ctime_ns': before.st_ctime_ns,
        'mode': stat.S_IMODE(before.st_mode), 'uid': before.st_uid}


def proc_identity(pid):
    raw = Path('/proc', str(pid), 'stat').read_text(encoding='ascii')
    fields = raw.rsplit(') ', 1)[1].split()
    return {'pid': pid, 'group': int(fields[2]), 'session': int(fields[3]), 'start': int(fields[19]), 'state': fields[0]}


def group_members(group):
    result = []
    for entry in Path('/proc').iterdir():
        if entry.name.isdecimal():
            try:
                row = proc_identity(int(entry.name))
            except (FileNotFoundError, ProcessLookupError):
                continue
            if row['group'] == group:
                result.append(row)
    need(len(result) <= 256)
    return result


def listener_inodes(port):
    result = {}
    for name, accepted in (('tcp', '0100007F'), ('tcp6', '00000000000000000000000001000000')):
        for line in Path('/proc/net', name).read_text(encoding='ascii').splitlines()[1:]:
            fields = line.split()
            address, raw_port = fields[1].split(':')
            if int(raw_port, 16) == port and fields[3] == '0A':
                need(address == accepted)
                result[fields[9]] = address
    return result


def owned_listener(owner, port):
    need(owner.process.poll() is None)
    current = proc_identity(owner.process.pid)
    need(all(current[key] == owner.identity[key] for key in ('pid', 'group', 'session', 'start')))
    observed = listener_inodes(port)
    need(bool(observed))
    fds = set()
    for entry in Path('/proc', str(owner.process.pid), 'fd').iterdir():
        try:
            target = os.readlink(entry)
        except FileNotFoundError:
            continue
        match = re.fullmatch(r'socket:\[([0-9]+)\]', target)
        if match:
            fds.add(match[1])
    need(set(observed).issubset(fds))


def child_env(private):
    # No GitHub token, inherited ROW paths, plugins, proxy credentials or user config.
    return {'HOME': str(private), 'ROW_HOME': str(private / 'state'), 'TMPDIR': str(private / 'tmp'),
        'XDG_CONFIG_HOME': str(private / 'config'), 'XDG_CACHE_HOME': str(private / 'cache'),
        'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'PATH': '/usr/bin:/bin',
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}


class Owned:
    def __init__(self, registry, argv, cwd, env, deadline, *, frames=False):
        need(time.monotonic() < deadline)
        self.deadline = deadline
        self.frames = frames
        self.queue = queue.Queue(maxsize=128)
        self.output = bytearray()
        self.errors = bytearray()
        self.overflow = threading.Event()
        self.reaped = False
        self.finished = False
        self.identity = None
        self.threads = []
        self.stop_drains = threading.Event()
        self.process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, close_fds=True)
        # Retain the process handle before any proc/pipe observation that can fail.
        registry.append(self)
        observed_identity = proc_identity(self.process.pid)
        need(observed_identity['group'] == self.process.pid and observed_identity['session'] == self.process.pid)
        self.identity = observed_identity
        self.threads = [threading.Thread(target=self.drain, args=(self.process.stdout, self.output, frames)),
            threading.Thread(target=self.drain, args=(self.process.stderr, self.errors, False))]
        for thread in self.threads:
            thread.start()

    def drain(self, stream, target, frames):
        pending = bytearray()
        try:
            while not self.stop_drains.is_set():
                remaining = min(0.1, self.deadline - time.monotonic())
                if remaining <= 0:
                    self.overflow.set()
                    break
                if not select.select([stream], [], [], remaining)[0]:
                    continue
                chunk = os.read(stream.fileno(), 4096)
                if not chunk:
                    break
                if self.overflow.is_set():
                    pending.clear()
                    continue
                if len(target) + len(chunk) > 65536:
                    self.overflow.set()
                    pending.clear()
                    continue
                target.extend(chunk)
                if frames:
                    if len(pending) + len(chunk) > 32769:
                        self.overflow.set()
                        pending.clear()
                        continue
                    pending.extend(chunk)
                    while b'\n' in pending:
                        raw, _, pending = pending.partition(b'\n')
                        try:
                            self.queue.put_nowait(raw)
                        except queue.Full:
                            self.overflow.set()
        except OSError:
            self.overflow.set()
        finally:
            stream.close()

    def receive(self):
        need(self.frames and not self.overflow.is_set())
        remaining = min(10, self.deadline - time.monotonic())
        need(remaining > 0)
        raw = self.queue.get(timeout=remaining)
        need(not self.overflow.is_set())
        return decode(bytes(raw), 32768)

    def send(self, value):
        raw = packed(value) + b'\n'
        need(self.frames and len(raw) <= 4096 and time.monotonic() < self.deadline)
        self.process.stdin.write(raw)
        self.process.stdin.flush()

    def finish(self, timeout=10):
        remaining = min(timeout, self.deadline - time.monotonic())
        need(remaining > 0)
        result = self.process.wait(timeout=remaining)
        self.reaped = True
        self.process.stdin.close()
        for thread in self.threads:
            thread.join(timeout=max(0, min(1, self.deadline - time.monotonic())))
        need(result == 0 and not self.overflow.is_set() and all(not thread.is_alive() for thread in self.threads)
             and group_members(self.identity['group']) == [])
        self.finished = True
        return bytes(self.output)

    def refuse_cleanup(self):
        # An unreaped retained child cannot have its PID reused by the OS. This
        # controller is its sole waiter. Without birth qualification, Popen's
        # checked leader terminate/kill/wait can clean up only that owned child;
        # it does not grant group/descendant authority or successful completion.
        if self.process.poll() is None:
            if self.identity is None:
                self.process.terminate()
            else:
                observed = proc_identity(self.process.pid)
                need(observed['start'] == self.identity['start'] and observed['group'] == self.identity['group'])
                os.killpg(self.identity['group'], signal.SIGTERM)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                if self.identity is None:
                    self.process.kill()
                else:
                    observed = proc_identity(self.process.pid)
                    need(observed['start'] == self.identity['start'] and observed['group'] == self.identity['group'])
                    os.killpg(self.identity['group'], signal.SIGKILL)
                self.process.wait(timeout=2)
            self.reaped = True
        elif not self.reaped:
            self.process.wait(timeout=0)
            self.reaped = True
        for stream in (self.process.stdin,):
            if stream is not None and not stream.closed:
                stream.close()
        self.stop_drains.set()
        for thread in getattr(self, 'threads', []):
            thread.join(timeout=0.5)
        if not self.threads:
            for stream in (self.process.stdout, self.process.stderr):
                stream.close()

    def cleanup_observed(self):
        # After a leader is reaped, never signal a potentially reused group ID.
        # Surviving/unobserved descendants leave refusal cleanup incomplete;
        # the disposable runner's destruction remains the final boundary.
        return self.reaped and self.identity is not None and all(not thread.is_alive() for thread in self.threads) and group_members(self.identity['group']) == []


def command(registry, argv, repo, env, deadline):
    child = Owned(registry, argv, repo, env, deadline)
    return child.finish()


def host_context():
    need(sys.platform == 'linux' and platform.machine() == 'x86_64' and platform.python_version() == '3.14.7')
    need(sys.flags.isolated == 1 and sys.flags.no_site == 1 and sys.dont_write_bytecode)
    need(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
         and os.environ.get('GITHUB_REPOSITORY') == PUBLIC_REPO and os.environ.get('ImageOS') == 'ubuntu24')
    image_version = os.environ.get('ImageVersion', '')
    need(re.fullmatch(r'[0-9.]{1,64}', image_version))
    release = Path('/etc/os-release').read_text(encoding='ascii')
    need(re.search(r'^ID=ubuntu$', release, re.MULTILINE)
         and re.search(r'^VERSION_ID="24\.04"$', release, re.MULTILINE))
    event_name = os.environ.get('GITHUB_EVENT_NAME')
    event_path = Path(os.environ['GITHUB_EVENT_PATH'])
    event = decode(event_path.read_bytes(), 1048576)
    need(event['repository']['full_name'] == PUBLIC_REPO and event['repository']['private'] is False)
    expected = os.environ.get('QUALIFICATION_SOURCE_SHA', '')
    event_sha = os.environ.get('GITHUB_SHA', '')
    need(re.fullmatch(r'[0-9a-f]{40}', expected) and re.fullmatch(r'[0-9a-f]{40}', event_sha))
    if event_name == 'pull_request':
        pr = event['pull_request']
        need(pr['head']['repo']['full_name'] == PUBLIC_REPO and pr['head']['sha'] == expected
             and pr['base']['ref'] == 'main' and event['action'] in ('opened', 'reopened', 'synchronize'))
    else:
        need(event_name == 'push' and event['ref'] == 'refs/heads/main' and event['after'] == expected == event_sha)
    for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
        need(re.fullmatch(r'[1-9][0-9]{0,19}', os.environ.get(key, '')))
    need(os.environ.get('CHROMEWEBDRIVER') == '/usr/local/share/chromedriver-linux64')
    return {'source': expected, 'event': event_sha, 'image_version': image_version}


def preparation_note(public, step):
    # Last entered fixed preparation check only; never exception text or a cause claim.
    need(public['phase'] == 'preparation' and type(step) is str and step in PREPARATION_STEPS)
    public['preparation_step'] = step


def chrome_file_note(public, stage):
    # Entered guard/operation only; no observed value, raw path, exception or cause.
    need(public['phase'] == 'preparation' and public.get('preparation_step') == 'chrome-file-pin'
         and type(stage) is str and stage in CHROME_FILE_STAGES)
    public['chrome_file_stage'] = stage


def source_guard(repo, context, registry, env, deadline, *, preparation=None):
    git = Path('/usr/bin/git')
    file_pin(git, root_owned=True, elf=True)
    def git_output(*args):
        return command(registry, [str(git), '-c', 'core.hooksPath=/dev/null', *args], repo, env, deadline)
    head = git_output('rev-parse', 'HEAD').decode('ascii').strip()
    tree = git_output('rev-parse', 'HEAD^{tree}').decode('ascii').strip()
    need(head == context['source'] and re.fullmatch(r'[0-9a-f]{40}', tree))
    need(git_output('diff', '--no-ext-diff', '--exit-code', 'HEAD') == b'')
    manifest = decode((DIRECTORY / 'source-inputs.json').read_bytes(), 65536)
    rows = []
    for entry in manifest['product_inputs']:
        path = repo / entry['path']
        need(path.is_relative_to(repo))
        pin = file_pin(path, maximum=1048576)
        need(pin['sha256'] == entry['sha256'] and pin['size'] == entry['size'])
        rows.append({'path': entry['path'], 'sha256': pin['sha256'], 'size': pin['size']})
    need({path.name for path in DIRECTORY.iterdir()} == set(manifest['gate_inputs']))
    for path in sorted(DIRECTORY.iterdir()):
        if path.name in manifest['gate_inputs']:
            pin = file_pin(path, maximum=1048576)
            rows.append({'path': path.relative_to(repo).as_posix(), 'sha256': pin['sha256'], 'size': pin['size']})
    need(set(manifest['gate_inputs']) == {row['path'].split('/')[-1] for row in rows if row['path'].startswith('tests/catalogue-browser/')})
    workflow = file_pin(repo / WORKFLOW, maximum=65536)
    workflow_sha = os.environ.get('GITHUB_WORKFLOW_SHA', '')
    need(re.fullmatch(r'[0-9a-f]{40}', workflow_sha))
    workflow_ref = os.environ.get('GITHUB_WORKFLOW_REF', '')
    need(workflow_ref.startswith(PUBLIC_REPO + '/' + WORKFLOW + '@'))
    if preparation is not None:
        preparation('workflow-command')
    observed_workflow = git_output('show', workflow_sha + ':' + WORKFLOW)
    if preparation is not None:
        preparation('workflow-bytes')
    need(hashed(observed_workflow) == workflow['sha256'])
    rows.append({'path': WORKFLOW, 'sha256': workflow['sha256'], 'size': workflow['size']})
    if preparation is not None:
        preparation('source-summary')
    return {'head': head, 'tree': tree, 'bytes': hashed(packed(rows)), 'workflow': workflow['sha256']}


def loaded_runtime(owner):
    files = {}
    for member in group_members(owner.identity['group']):
        raw = Path('/proc', str(member['pid']), 'maps').read_text(encoding='ascii')
        for line in raw.splitlines():
            fields = line.split(maxsplit=5)
            # Executable mappings only. Writable browser state/resources are not
            # described as immutable executable/library runtime provenance.
            if len(fields) == 6 and 'x' in fields[1] and fields[5].startswith('/'):
                path = fields[5]
                need(not path.endswith(' (deleted)') and '\\' not in path)
                if path not in files:
                    files[path] = file_pin(path, trusted_owner=True)
    need(1 <= len(files) <= 4096)
    return files


def inventories_row(phase, inventory):
    need(type(inventory['count']) is int and inventory['count'] == len(inventory['profiles']))
    return {'phase': phase, 'count': inventory['count'], 'digest': inventory['digest']}


def disk_dom(snapshot, inventory):
    expected = []
    for row in inventory['profiles']:
        host = row.get('host') or ''
        host = '[' + host + ']' if ':' in host else host
        port = row.get('port')
        target = row.get('url') or (host + (':' + str(port) if port is not None else '') if host else 'No public target')
        expected.append(row['protocol'] + ' • ' + row['name'] + ' • ' + target)
    need(snapshot['texts'] == expected and len(snapshot['rows']) == inventory['count'])
    return True


def main():
    started = time.monotonic()
    deadline = started + 295
    watchdog = threading.Timer(300, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()  # Bounds main/startup/cleanup; not prior Python stdlib imports.
    context = host_context()  # Must pass before any subprocess, socket or private-state creation.
    repo = Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
    need(DIRECTORY == repo / 'tests' / 'catalogue-browser')
    output = repo / '.tmp' / 'catalogue-browser-public'
    need(not output.exists())
    output.mkdir(mode=0o700, parents=True)
    public = {'schema': 'row.ubuntu-actual-catalogue-webdriver.v1', 'status': 'refused',
        'complete': False, 'phase': 'preparation', 'readiness_credit': 0, 'limits': LIMITS}
    def checkpoint(phase):
        public['phase'] = phase
        raw = packed(public)
        need(len(raw) <= 65536)
        temporary = output / 'result.tmp'
        with temporary.open('wb') as stream:
            stream.write(raw)
        temporary.replace(output / 'result.json')
    checkpoint('preparation')
    registry = []
    retained_ports = []
    driver = None
    forced = False
    # Fresh private root; actual product/server/browser files are never public artifacts.
    with tempfile.TemporaryDirectory(prefix='catalogue-owned-', dir=os.environ['RUNNER_TEMP']) as temp:
        private = Path(temp)
        os.chmod(private, 0o700)
        for name in ('state', 'tmp', 'cache', 'config', 'browser'):
            (private / name).mkdir(mode=0o700)
        env = child_env(private)
        try:
            def preparation(step):
                preparation_note(public, step)
            preparation('source-checks')
            source_before = source_guard(repo, context, registry, env, deadline, preparation=preparation)
            chrome = Path('/opt/google/chrome/chrome')
            chrome_driver = Path('/usr/local/share/chromedriver-linux64/chromedriver')
            preparation('python-path')
            python = Path(sys.executable).resolve(strict=True)
            tools_before = {}
            for step, path in (('chrome-file-pin', chrome), ('driver-file-pin', chrome_driver),
                ('python-file-pin', python), ('git-file-pin', Path('/usr/bin/git'))):
                preparation(step)
                diagnostic = (lambda stage: chrome_file_note(public, stage)) if step == 'chrome-file-pin' else None
                tools_before[str(path)] = file_pin(path, trusted_owner=True, elf=True, diagnostic=diagnostic)
                public.pop('chrome_file_stage', None)
            preparation('runtime-tool-owners')
            need(tools_before[str(chrome)]['uid'] == 0 and tools_before[str(chrome_driver)]['uid'] == 0)
            preparation('runtime-checkpoint')
            checkpoint('host-runtime-observation')
            public.pop('preparation_step', None)
            chrome_raw = command(registry, [str(chrome), '--version'], repo, env, deadline)
            driver_raw = command(registry, [str(chrome_driver), '--version'], repo, env, deadline)
            chrome_match = re.fullmatch(rb'Google Chrome ([0-9]+(?:\.[0-9]+){3})\s*', chrome_raw)
            driver_match = re.fullmatch(rb'ChromeDriver ([0-9]+(?:\.[0-9]+){3})(?: [^\r\n]{1,512})?\s*', driver_raw)
            need(chrome_match is not None and driver_match is not None and chrome_match[1] == driver_match[1])
            version = chrome_match[1].decode('ascii')
            nonce = secrets.token_hex(32)
            tokens = [secrets.token_hex(32), secrets.token_hex(32)]
            need(tokens[0] != tokens[1])
            events = []
            inventories = []
            checks = []
            def launch(number, port):
                child = Owned(registry, [str(python), '-I', '-S', '-B', str(DIRECTORY / 'entry.py'), 'fixture'], repo, env, deadline, frames=True)
                child.send({'repo': str(repo), 'home': str(private / 'state'), 'port': port,
                    'token': tokens[number - 1], 'nonce': nonce, 'launch': number})
                ready = child.receive()
                need(ready['ready'] is True and ready['nonce'] == nonce and type(ready['port']) is int and 1 <= ready['port'] <= 65535)
                owned_listener(child, ready['port'])
                retained_ports.append(ready['port'])
                return child, ready
            fixture, ready = launch(1, 0)
            first_fixture = fixture
            port = ready['port']
            origin = 'http://127.0.0.1:' + str(port)
            inventories.append(inventories_row('seed', ready['inventory']))
            need(ready['inventory']['count'] == 1)
            def frame(op, case):
                fixture.send({'op': op, 'case': case, 'nonce': nonce})
                reply = fixture.receive()
                need(reply['nonce'] == nonce)
                return reply
            def observe(case):
                return frame('inspect', case)['inventory']
            def record(case, facts):
                from gate_contract import check_case
                check_case(case, facts)
                checks.append({'id': case, 'facts': facts})
            # ChromeDriver itself chooses a private ephemeral port and reports it on its private log.
            controller = Owned(registry, [str(chrome_driver), '--port=0', '--allowed-ips=127.0.0.1'], repo, env, deadline)
            launch_limit = min(deadline, time.monotonic() + 20)
            driver_port = None
            while time.monotonic() < launch_limit:
                need(controller.process.poll() is None and not controller.overflow.is_set())
                match = re.search(rb'ChromeDriver was started successfully on port ([0-9]+)', bytes(controller.output))
                if match:
                    driver_port = int(match[1])
                    break
                time.sleep(0.05)
            need(driver_port is not None and 1 <= driver_port <= 65535)
            owned_listener(controller, driver_port)
            retained_ports.append(driver_port)
            driver = Driver(driver_port, min(deadline - 10, time.monotonic() + 180))
            driver.origin = origin
            capabilities = driver.start(chrome, private / 'browser')
            need(capabilities['browserVersion'] == version
                 and capabilities['chrome']['chromedriverVersion'].split(' ', 1)[0] == version
                 and capabilities['chrome']['userDataDir'] == str(private / 'browser'))
            runtime_before = loaded_runtime(controller)
            need(str(chrome) in runtime_before and str(chrome_driver) in runtime_before)
            checkpoint('api-read')
            driver.command('/url', {'url': origin + '/index.html'})
            snapshot = driver.connect(tokens[0], 1)
            first = observe('api-read')
            disk_dom(snapshot, first)
            read_event = [event for event in first['events'] if event['route'] == 'catalogue'][-1]
            record('api-read', {'status': read_event['status'], 'dom_seed': snapshot['texts'] == ['ssh • catalogue seed • seed.example.invalid:22'],
                'input_cleared': snapshot['inputEmpty'], 'no_store': read_event['no_store'],
                'public_only': all('credential_ref' not in row and 'identity_file' not in row for row in first['profiles'])})
            checkpoint('api-create-refresh')
            frame('mark', 'api-create-refresh')
            driver.create('catalogue created one', 'one.example.invalid:2222', 2)
            snapshot = driver.refresh(2)
            created = observe('api-create-refresh')
            inventories.append(inventories_row('created', created))
            post = [event for event in created['events'] if event['method'] == 'POST'][-1]
            get = [event for event in created['events'] if event['route'] == 'catalogue' and event['method'] == 'GET'][-1]
            record('api-create-refresh', {'post_status': post['status'], 'get_status': get['status'],
                'replace_false': created['posts_replace_false'] == [True], 'disk_count': created['count'], 'disk_dom_agree': disk_dom(snapshot, created)})
            checkpoint('restart-persistence-auth-rotation')
            stopped = frame('stop', 'restart-persistence-auth-rotation')
            fixture.finish()
            first_listener_gone = not listener_inodes(port)
            need(first_listener_gone)
            events.extend(stopped['inventory']['events'])
            fixture, ready = launch(2, port)
            restarted = ready['inventory']
            inventories.append(inventories_row('restarted', restarted))
            frame('mark', 'restart-persistence-auth-rotation')
            driver.click('#catalogue-refresh')
            rejected = driver.wait(lambda value: not value['busy'] and value['authRefused'])
            old_events = observe('restart-persistence-auth-rotation')['events']
            old_status = [event for event in old_events if event['route'] == 'catalogue'][-1]['status']
            driver.connect(tokens[1], 2)
            driver.create('catalogue created two', 'two.example.invalid:2200', 3)
            snapshot = driver.refresh(3)
            created_two = observe('restart-persistence-auth-rotation')
            inventories.append(inventories_row('second-created', created_two))
            new_get = [event for event in created_two['events'] if event['route'] == 'catalogue' and event['method'] == 'GET'][-1]
            new_post = [event for event in created_two['events'] if event['method'] == 'POST'][-1]
            record('restart-persistence-auth-rotation', {'first_zero_reaped': first_fixture.reaped and first_fixture.process.returncode == 0,
                'listener_gone': first_listener_gone, 'old_status': old_status,
                'old_auth_cleared': rejected['tokenEmpty'] and rejected['rows'] == [] and rejected['inputEmpty'],
                'new_status': new_get['status'], 'persisted_digest_equal': restarted['digest'] == created['digest'] and restarted['disk_digest'] == created['disk_digest'],
                'second_post_status': new_post['status'], 'disk_count': created_two['count'],
                'disk_dom_agree': disk_dom(snapshot, created_two), 'token_digests_distinct': hashed(tokens[0].encode()) != hashed(tokens[1].encode())})
            names = ['catalogue seed', 'catalogue created one', 'catalogue created two', 'seed.example.invalid', 'one.example.invalid', 'two.example.invalid']
            checkpoint('disconnect-token-state')
            frame('mark', 'disconnect-token-state')
            before = observe('disconnect-token-state')['events']
            driver.click('#catalogue-disconnect')
            snapshot = driver.wait(lambda value: not value['busy'] and value['tokenEmpty'])
            driver.click('#catalogue-refresh')  # Actual disabled DOM control; no synthetic handler call.
            driver.click('#profile-submit')
            after = observe('disconnect-token-state')['events']
            record('disconnect-token-state', {'token_empty': snapshot['tokenEmpty'], 'rows_empty': snapshot['rows'] == [],
                'input_empty': snapshot['inputEmpty'], 'controls_disabled': snapshot['refreshDisabled'] and snapshot['saveDisabled'],
                'no_authenticated_request_after_disconnect': not any(event['authorization_present'] for event in after[len(before):]),
                'storage_private_absent': driver.private_storage_absent(tokens, names)})
            checkpoint('pagehide-new-document')
            frame('mark', 'pagehide-new-document')
            record('pagehide-new-document', driver.lifecycle(origin, tokens[1], nonce))
            checkpoint('service-worker-api-cache-boundary')
            frame('mark', 'service-worker-api-cache-boundary')
            driver.connect(tokens[1], 3)
            driver.controlled()
            assets = {('/' if name == 'index.html' else '/' + name): hashed((repo / 'apps' / 'web' / name).read_bytes())
                for name in ('index.html', 'styles.css', 'app.js', 'manifest.json')}
            assets['/index.html'] = assets['/']
            seed = driver.execute(SW_PROBE, tokens[1], assets, 'seed-api', async_=True)
            need(seed['controlled'] is True and seed['seeded'] is True)
            before = observe('service-worker-api-cache-boundary')['events']
            snapshot = driver.refresh(3)
            after = observe('service-worker-api-cache-boundary')['events']
            real_get = any(event['route'] == 'catalogue' and event['method'] == 'GET' and event['status'] == 200
                and event['authorization_present'] is True for event in after[len(before):])
            sw = driver.execute(SW_PROBE, tokens[1], assets, 'finish', async_=True)
            need(sw['controlled'] is True)
            final_events = observe('service-worker-api-cache-boundary')['events']
            static_events = final_events[len(after):]
            need(any(event['route'] == 'static' and event['authorization_present'] for event in static_events)
                 and sum(event['route'] == 'static' and event['status'] == 200 for event in static_events) >= 3)
            record('service-worker-api-cache-boundary', {'controlled': sw['controlled'],
                'api_canary_bypassed': disk_dom(snapshot, created_two) and not any('qualification-cache-canary' in text for text in snapshot['texts']),
                'fresh_server_get': real_get, 'health_policy_not_cached': sw['healthPolicyAbsent'],
                'auth_static_canary_bypassed': sw['authBypass'], 'no_store_static_canary_bypassed': sw['noStoreBypass'],
                'canaries_removed': sw['removed'], 'final_cache_public_exact': sw['exact'],
                'storage_private_absent': driver.private_storage_absent(tokens, names)})
            checkpoint('owned-server-down')
            stopped = frame('stop', 'owned-server-down')
            fixture.finish()
            need(not listener_inodes(port))
            events.extend(stopped['inventory']['events'])
            down_started = time.monotonic()
            driver.click('#catalogue-refresh')
            snapshot = driver.wait(lambda value: not value['busy'] and value['serverRefused'], timeout=5.5)
            down_ms = int((time.monotonic() - down_started) * 1000)
            record('owned-server-down', {'second_zero_reaped': fixture.reaped and fixture.process.returncode == 0,
                'listener_gone': not listener_inodes(port), 'visible_refusal': snapshot['serverRefused'],
                'token_rows_cleared': snapshot['tokenEmpty'] and snapshot['rows'] == [] and snapshot['inputEmpty'],
                'api_mode_retained': snapshot['mode'] == 'api', 'stale_or_demo_returned': snapshot['texts'] != []})
            checkpoint('cleanup')
            runtime_after = loaded_runtime(controller)
            need(set(runtime_before).issubset(runtime_after))
            for path, pin in runtime_before.items():
                need(runtime_after[path] == pin)
            driver.close()
            # Normal ChromeDriver service shutdown; no signal cleanup can satisfy success.
            connection = http.client.HTTPConnection('127.0.0.1', driver_port, timeout=min(5, deadline - time.monotonic()))
            try:
                connection.request('GET', '/shutdown')
                response = connection.getresponse()
                need(response.status == 200 and len(response.read(65537)) <= 65536)
            finally:
                connection.close()
            controller.finish()
            need(all(not listener_inodes(number) for number in retained_ports))
            source_after = source_guard(repo, context, registry, env, deadline)
            need(source_before == source_after)
            tools_after = {path: file_pin(path, trusted_owner=True, elf=True) for path in tools_before}
            need(tools_before == tools_after)
            for path, pin in runtime_after.items():
                need(file_pin(path, trusted_owner=True) == pin)
            runtime_rows = [{'path_digest': hashed(path.encode()), **pin} for path, pin in sorted(runtime_after.items())]
            runtime = {'chrome_version': version, 'driver_version': version, 'python_version': platform.python_version(),
                'tool_inventory_sha256': hashed(packed(tools_before)), 'loaded_runtime_sha256': hashed(packed(runtime_rows)),
                'loaded_runtime_files': len(runtime_rows)}
            binding = {'nonce': nonce, 'source_head': source_before['head'], 'source_tree': source_before['tree'],
                'source_bytes_sha256': source_before['bytes'], 'workflow_sha256': source_before['workflow'],
                'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                'event_sha': context['event'], 'image_version': context['image_version'], 'image_os': 'ubuntu24'}
            public = {'schema': 'row.ubuntu-actual-catalogue-webdriver.v1', 'status': 'observations-complete-with-limits',
                'complete': True, 'binding': binding, 'runtime': runtime, 'checks': checks, 'inventories': inventories, 'events': events,
                'cleanup': {'all_retained_zero': all(owner.process.returncode == 0 for owner in registry),
                    'all_reaped': all(owner.reaped for owner in registry),
                    'owned_groups_gone': all(group_members(owner.identity['group']) == [] for owner in registry),
                    'listeners_gone': all(not listener_inodes(number) for number in retained_ports),
                    'forced_cleanup': False, 'descendants_complete': False},
                'elapsed_ms': int((time.monotonic() - started) * 1000), 'server_down_ms': down_ms,
                'source_unchanged': source_before == source_after, 'runtime_unchanged': tools_before == tools_after,
                'limits': LIMITS, 'readiness_credit': 0}
            raw = packed(public)
            validate(raw, {'binding': binding, 'runtime': runtime})
            (output / 'result.json').write_bytes(raw)
            return 0
        except Exception:
            public['status'] = 'refused'
            public['complete'] = False
            # Hash/count only for private output; no path, URL, token, exception message or body.
            public['private_streams'] = [{'stdout_bytes': len(owner.output), 'stdout_sha256': hashed(bytes(owner.output)),
                'stderr_bytes': len(owner.errors), 'stderr_sha256': hashed(bytes(owner.errors)),
                'overflow': owner.overflow.is_set()} for owner in registry]
            return 1
        finally:
            for owner in reversed(registry):
                if not owner.finished:
                    forced = True
                    try:
                        owner.refuse_cleanup()
                    except Exception:
                        pass
            if public['complete'] is not True:
                public['forced_cleanup_attempted'] = forced
                try:
                    public['cleanup_complete'] = all(owner.cleanup_observed() for owner in registry)
                except Exception:
                    public['cleanup_complete'] = False
                (output / 'result.json').write_bytes(packed(public))
            watchdog.cancel()


if __name__ == '__main__':
    try:
        code = main()
    except Exception:
        # Host-context failures occur before runtime launch and intentionally expose no internals.
        sys.stderr.write('catalogue-host-context-refused\n')
        code = 1
    raise SystemExit(code)
