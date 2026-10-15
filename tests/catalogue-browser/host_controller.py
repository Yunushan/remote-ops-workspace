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

from browser_probe import (
    SW_PROBE,
    Driver,
    driver_start_fields,
    prepare_driver_start,
)
from cft_runtime import (
    chrome_version_argv,
    chrome_version_match,
    observe_policy_tasks,
    policy_evidence,
    runtime_readback,
    selected_runtime,
)
from gate_contract import (
    CHROME_FILE_STAGES,
    LIMITS,
    PREPARATION_STEPS,
    GateRefusal,
    api_read_diagnostic,
    decode,
    driver_start_diagnostic,
    need,
    runtime_diagnostic,
    validate,
)

DIRECTORY = Path(__file__).resolve().parent
WORKFLOW = '.github/workflows/ubuntu-catalogue-browser.yml'
PUBLIC_REPO = 'Yunushan/remote-ops-workspace'
SW_HOST_STAGES = ('case-mark', 'connect', 'controller', 'asset-inventory', 'seed-probe', 'seed-result-guard', 'event-before', 'refresh', 'event-after', 'refresh-event-proof', 'finish-probe', 'finish-result-guard', 'event-final', 'static-event-guard', 'case-facts', 'case-record')
SW_PROBE_STAGES = ('controller', 'cache-inventory', 'cache-open', 'api-canary-seed', 'api-canary-read', 'api-canary-remove', 'healthz-fetch', 'api-health-fetch', 'policy-fetch', 'healthz-response', 'api-health-response', 'policy-response', 'healthz-cache', 'api-health-cache', 'policy-cache', 'auth-static-canary', 'no-store-static-canary', 'auth-static-fetch', 'no-store-static-fetch', 'auth-static-response', 'no-store-static-response', 'static-canary-remove', 'static-restore-fetch', 'static-restore-response', 'static-restore-put', 'final-cache-inventory', 'final-entry-request', 'final-entry-policy', 'final-entry-bytes')
SW_CASE_FACTS = ('controlled', 'api_canary_bypassed', 'fresh_server_get', 'health_policy_not_cached', 'auth_static_canary_bypassed', 'no_store_static_canary_bypassed', 'canaries_removed', 'final_cache_public_exact', 'storage_private_absent')


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


def source_guard(repo, context, registry, env, deadline, *, preparation=None, workflow_path=WORKFLOW,
        source_directory=None, git_command=None, source_diagnostic=None):
    def source_stage(value):
        if source_diagnostic is not None:
            source_diagnostic(value)
    source_stage('contract')
    need(workflow_path in (WORKFLOW, '.github/workflows/chrome-for-testing-acquisition.yml'))
    directory = DIRECTORY if source_directory is None else Path(source_directory)
    need(directory == repo / 'tests' / 'catalogue-browser')
    if git_command is not None:
        need(os.getuid() == os.geteuid() == 0 and source_directory is not None and callable(git_command))
    git = Path('/usr/bin/git')
    source_stage('git-file-pin')
    file_pin(git, root_owned=True, elf=True,
        diagnostic=(lambda value: source_stage('git-file-' + value)) if source_diagnostic is not None else None)
    def git_output(*args):
        argv = [str(git), '-c', 'core.hooksPath=/dev/null', *args]
        if git_command is not None:
            return git_command(argv)
        return command(registry, argv, repo, env, deadline)
    source_stage('git-head')
    head = git_output('rev-parse', 'HEAD').decode('ascii').strip()
    source_stage('git-tree')
    tree = git_output('rev-parse', 'HEAD^{tree}').decode('ascii').strip()
    source_stage('head-tree-match')
    need(head == context['source'] and re.fullmatch(r'[0-9a-f]{40}', tree))
    source_stage('git-diff')
    need(git_output('diff', '--no-ext-diff', '--exit-code', 'HEAD') == b'')
    source_stage('manifest-decode')
    manifest = decode((directory / 'source-inputs.json').read_bytes(), 65536)
    rows = []
    for entry in manifest['product_inputs']:
        path = repo / entry['path']
        source_stage('product-path')
        need(path.is_relative_to(repo))
        source_stage('product-file-pin')
        pin = file_pin(path, maximum=1048576)
        source_stage('product-bytes')
        need(pin['sha256'] == entry['sha256'] and pin['size'] == entry['size'])
        rows.append({'path': entry['path'], 'sha256': pin['sha256'], 'size': pin['size']})
    source_stage('gate-membership')
    need({path.name for path in directory.iterdir()} == set(manifest['gate_inputs']))
    for path in sorted(directory.iterdir()):
        if path.name in manifest['gate_inputs']:
            source_stage('gate-file-pin')
            pin = file_pin(path, maximum=1048576)
            rows.append({'path': path.relative_to(repo).as_posix(), 'sha256': pin['sha256'], 'size': pin['size']})
    source_stage('gate-row-membership')
    need(set(manifest['gate_inputs']) == {row['path'].split('/')[-1] for row in rows if row['path'].startswith('tests/catalogue-browser/')})
    source_stage('workflow-file-pin')
    workflow = file_pin(repo / workflow_path, maximum=65536)
    source_stage('workflow-context')
    workflow_sha = os.environ.get('GITHUB_WORKFLOW_SHA', '')
    need(re.fullmatch(r'[0-9a-f]{40}', workflow_sha))
    workflow_ref = os.environ.get('GITHUB_WORKFLOW_REF', '')
    need(workflow_ref.startswith(PUBLIC_REPO + '/' + workflow_path + '@'))
    if preparation is not None:
        preparation('workflow-command')
    source_stage('workflow-command')
    observed_workflow = git_output('show', workflow_sha + ':' + workflow_path)
    if preparation is not None:
        preparation('workflow-bytes')
    source_stage('workflow-bytes')
    need(hashed(observed_workflow) == workflow['sha256'])
    rows.append({'path': workflow_path, 'sha256': workflow['sha256'], 'size': workflow['size']})
    if preparation is not None:
        preparation('source-summary')
    source_stage('source-summary')
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


def runtime_note(public, stage, versions=None):
    need(public['phase'] == 'host-runtime-observation')
    fields = runtime_diagnostic(stage, versions)
    public.pop('runtime_versions', None)
    public.update(fields)


def inert_runtime_note(public, stage):
    try:
        runtime_note(public, stage)
    except BaseException:
        pass


def driver_start_note(public, error, context):
    try:
        if type(public) is not dict:
            return
        public.pop('driver_start', None)
        if (public.get('status') != 'refused' or public.get('phase') != 'host-runtime-observation'
                or public.get('runtime_stage') != 'browser-session-start'
                or public.get('complete') is not False):
            return
        fields = driver_start_fields(context, error)
        if fields is not None:
            public['driver_start'] = driver_start_diagnostic(fields)
    except BaseException:
        pass


DRIVER_STDERR_PREFIX_BYTES = 65536
DRIVER_STDERR_MARKERS = (
    (1, (b'Running as root without --', b' is not supported. See https://crbug.com/638180.')),
    (2, (b'No usable sandbox!',)),
    (4, (b'The SUID sandbox helper binary was found, but is not configured correctly.',)),
    (8, (b'Socket path too long:',)),
    (16, (b'Failed to create socket directory.',)),
    (32, (b'Failed to create symlinks.',)),
)


def _driver_stderr_bits(controller, registry):
    """Partial positive private-stream literals; not Chrome origin or host cause."""
    try:
        if (type(controller) is not Owned or type(registry) is not list
                or not 1 <= len(registry) <= 128
                or not any(owner is controller for owner in registry)):
            return None
        errors = controller.errors
        if type(errors) is not bytearray or len(errors) > DRIVER_STDERR_PREFIX_BYTES:
            return None
        snapshot = bytes(errors)
        bits = sum(bit for bit, literals in DRIVER_STDERR_MARKERS
                   if all(literal in snapshot for literal in literals))
        return bits if 1 <= bits <= 63 else None
    except BaseException:
        return None


def driver_stderr_note(public, error, context, controller, registry):
    try:
        if type(public) is not dict:
            return
        previous = public.get('driver_start')
        if type(previous) is dict:
            previous.pop('stderr_bits', None)
        if (public.get('status') != 'refused' or public.get('complete') is not False
                or public.get('phase') != 'host-runtime-observation'
                or public.get('runtime_stage') != 'browser-session-start'):
            return
        fields = driver_start_fields(context, error)
        if (type(fields) is not dict or type(previous) is not dict or previous != fields
                or fields.get('operation') != 'session-create'
                or fields.get('step') != 'response-guard'
                or fields.get('exception') != 'gate-refusal'
                or type(fields.get('http_status')) is not int or fields['http_status'] != 500
                or fields.get('webdriver_error') != 'session not created'):
            return
        bits = _driver_stderr_bits(controller, registry)
        if type(bits) is not int or not 1 <= bits <= 63:
            return
        candidate = {**fields, 'stderr_bits': bits}
        validated = driver_start_diagnostic(candidate)
        if type(validated) is dict and validated == candidate:
            public['driver_start'] = validated
    except BaseException:
        pass


def emit_runtime_refusal(public):
    try:
        need(public['status'] == 'refused' and public['complete'] is False
             and public['phase'] == 'host-runtime-observation')
        fields = runtime_diagnostic(public['runtime_stage'], public.get('runtime_versions'))
        diagnostic = {'schema': 'row.catalogue-runtime-refusal.v1', 'status': 'refused',
            'phase': 'host-runtime-observation', 'readiness_credit': 0, **fields}
        if 'driver_start' in public:
            need(public['runtime_stage'] == 'browser-session-start' and 'runtime_versions' not in public)
            diagnostic['driver_start'] = driver_start_diagnostic(public['driver_start'])
        raw = packed(diagnostic)
        need(len(raw) <= 512)
        sys.stderr.write(raw.decode('ascii') + '\n')
    except BaseException:
        pass


def emit_service_worker_refusal(public, error, stage, probe=None, facts=None):
    """Only current caller-local fixed stages and exact primitive failed facts are public."""
    try:
        need(type(public) is dict and type(public.get('phase')) is str
             and public['phase'] == 'service-worker-api-cache-boundary'
             and type(public.get('status')) is str and public['status'] == 'refused'
             and public.get('complete') is False and type(stage) is str and stage in SW_HOST_STAGES)
        categories = {GateRefusal: 'gate-refusal', KeyError: 'key-error', IndexError: 'index-error',
            TypeError: 'type-error', ValueError: 'value-error', TimeoutError: 'timeout-error', OSError: 'os-error'}
        diagnostic = {'schema': 'row.catalogue-service-worker-refusal.v1', 'status': 'refused',
            'phase': 'service-worker-api-cache-boundary', 'readiness_credit': 0,
            'entered_stage': stage, 'exception_category': categories.get(type(error), 'other-exact-type')}
        if type(error) is GateRefusal and stage in ('seed-result-guard', 'finish-result-guard'):
            try:
                if (type(probe) is dict and all(type(key) is str for key in probe)
                        and set(probe) == {'controlled', 'entered_stage'} and probe['controlled'] is False
                        and type(probe['entered_stage']) is str and probe['entered_stage'] in SW_PROBE_STAGES
                        and (probe['entered_stage'] in ('controller', 'cache-inventory', 'cache-open', 'api-canary-seed')
                            if stage == 'seed-result-guard' else probe['entered_stage'] != 'api-canary-seed')):
                    diagnostic['probe_stage'] = probe['entered_stage']
            except BaseException:
                pass
        if type(error) is GateRefusal and stage == 'case-record':
            try:
                if (type(facts) is dict and all(type(key) is str for key in facts) and set(facts) == set(SW_CASE_FACTS)
                        and all(type(facts[key]) is bool for key in SW_CASE_FACTS)):
                    bits = sum(1 << index for index, key in enumerate(SW_CASE_FACTS) if facts[key] is False)
                    if bits:
                        diagnostic['case_failure_bits'] = bits
            except BaseException:
                pass
        raw = packed(diagnostic)
        need(len(raw) + 1 <= 512)
        sys.stderr.write(raw.decode('ascii') + '\n')
    except BaseException:
        pass


def emit_case_refusal(public):
    """Emit only a fixed entered phase; no exception or private observation is read."""
    try:
        need(type(public) is dict and type(public.get('status')) is str
             and public['status'] == 'refused' and public.get('complete') is False)
        phase = public['phase']
        need(type(phase) is str and phase in ('api-create-refresh',
            'restart-persistence-auth-rotation', 'disconnect-token-state',
            'pagehide-new-document', 'service-worker-api-cache-boundary',
            'owned-server-down', 'cleanup'))
        raw = packed({'schema': 'row.catalogue-case-refusal.v1', 'status': 'refused',
            'phase': phase, 'readiness_credit': 0})
        need(len(raw) + 1 <= 512)
        sys.stderr.write(raw.decode('ascii') + '\n')
    except BaseException:
        pass


def inventories_row(phase, inventory):
    need(type(inventory['count']) is int and inventory['count'] == len(inventory['profiles']))
    return {'phase': phase, 'count': inventory['count'], 'digest': inventory['digest']}


def api_read_refusal(public, error, stage, facts=None):
    """Project only a fresh caller-local selected failure; never inspect exception attributes."""
    try:
        need(type(public) is dict and public['status'] == 'refused'
             and public['complete'] is False and public['phase'] == 'api-read')
        categories = {GateRefusal: 'gate-refusal', KeyError: 'key-error', IndexError: 'index-error',
            TypeError: 'type-error', ValueError: 'value-error', TimeoutError: 'timeout-error',
            OSError: 'os-error'}
        result = {'entered_stage': stage, 'exception_category': categories.get(type(error), 'other-exact-type')}
        if stage == 'case-contract' and type(error) is GateRefusal:
            expected = {'status': 200, 'dom_seed': True, 'input_cleared': True, 'no_store': True, 'public_only': True}
            if (type(facts) is dict and all(type(key) is str for key in facts)
                    and set(facts) == set(expected)
                    and all(type(facts[key]) is type(value) for key, value in expected.items())):
                bits = sum(1 << index for index, (key, value) in enumerate(expected.items()) if facts[key] != value)
                if bits:
                    result['case_failure_bits'] = bits
        return api_read_diagnostic(result)
    except BaseException:
        return None


def emit_api_read_refusal(public, diagnostic):
    try:
        need(type(public) is dict and public['status'] == 'refused'
             and public['complete'] is False and public['phase'] == 'api-read')
        fields = api_read_diagnostic(diagnostic)
        raw = packed({'schema': 'row.catalogue-api-read-refusal.v1', 'status': 'refused',
            'phase': 'api-read', 'readiness_credit': 0, **fields})
        need(len(raw) + 1 <= 512)
        sys.stderr.write(raw.decode('ascii') + '\n')
    except BaseException:
        pass


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



def bind_host_policy_cleanup():
    from cft_runtime import (
        MAX_POINTER,
        POLICY_MAX,
        POLICY_NAME,
        bundle,
        pointer_contract,
        pointer_path,
        policy_digests,
        policy_readback,
        policy_record_path,
        policy_state_contract,
    )
    from gate_contract import host_policy_cleanup, host_policy_evidence, public_bytes
    context = host_context()
    need(os.getuid() == os.geteuid() and os.getuid() > 0
        and os.getgid() == os.getegid() and os.getgid() > 0)
    need(os.environ.get('ROW_CFT_CLEANUP_OUTCOME') == 'success')
    deadline = time.monotonic() + 20
    repo = Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
    directory = repo / '.tmp/catalogue-browser-public'
    info = directory.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700)
    source = directory / 'result.json'
    info = source.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid())
    source_pin, raw = bundle.stable_file(source, 65536, deadline, raw=True)
    record = decode(raw)
    partial = {'source_head': context['source'], 'source_tree': '0' * 40,
        'source_bytes_sha256': '0' * 64, 'workflow_sha256': '0' * 64,
        'event_sha': context['event'], 'run_id': os.environ['GITHUB_RUN_ID'],
        'run_attempt': os.environ['GITHUB_RUN_ATTEMPT']}
    cleanup_path = policy_record_path(partial, 'cleanup')
    cleanup_pin, cleanup_raw = bundle.stable_file(cleanup_path, POLICY_MAX, deadline, root_owned=True, raw=True)
    cleanup = decode(cleanup_raw)
    need(type(cleanup) is dict and set(cleanup) == {'schema', 'binding', 'observation', 'readiness_credit'})
    need(cleanup['schema'] == 'row.cft-userns-cleanup.v1' and type(cleanup['readiness_credit']) is int
        and cleanup['readiness_credit'] == 0)
    binding = bundle.binding_contract(cleanup['binding'])
    need(binding['source_head'] == context['source'] and binding['event_sha'] == context['event']
        and binding['run_id'] == partial['run_id'] and binding['run_attempt'] == partial['run_attempt'])
    workflow_pin = file_pin(repo / WORKFLOW, maximum=65536)
    need(binding['workflow_sha256'] == workflow_pin['sha256'])
    complete = record.get('complete') is True
    if complete:
        need({key: record['binding'][key] for key in binding} == binding)
        validate(raw, {'binding': record['binding'], 'runtime': record['runtime']}, policy_cleanup_pending=True)
    else:
        public_bytes(raw)
    observation = host_policy_cleanup(cleanup['observation'], record.get('host_policy'), complete=complete)
    intent_path = policy_record_path(binding, 'intent')
    pointer = pointer_path(binding)
    holder = None
    intent_pin = None
    pointer_pin = None
    policy_pin = None
    if observation['status'] in ('removed', 'already-absent'):
        intent_pin, intent_raw = bundle.stable_file(intent_path, POLICY_MAX, deadline, root_owned=True, raw=True)
        intent = policy_state_contract(intent_raw, binding)
        holder = {'state': intent, 'intent_pin': intent_pin}
        policy_readback(holder, deadline)
        expected = policy_digests(holder)
        need(all(observation[key] == value for key, value in expected.items()))
        if 'host_policy' in record:
            host_policy_evidence(record['host_policy'], complete=complete)
            need(all(record['host_policy'][key] == value for key, value in expected.items()))
        if complete or pointer.exists():
            policy_pin, policy_raw = bundle.stable_file(DIRECTORY / POLICY_NAME,
                bundle.MAX_METADATA, deadline, raw=True)
            bundle.policy(policy_raw, enabled=True)
            pointer_pin, pointer_raw = bundle.stable_file(pointer, MAX_POINTER, deadline, root_owned=True, raw=True)
            prepared = pointer_contract(pointer_raw, binding, policy_raw)
            need(prepared['root'] == intent['root']
                and all(prepared['host_policy'][key] == value for key, value in expected.items()))
        else:
            need(not pointer.is_symlink())
    else:
        need(not complete and 'host_policy' not in record and not intent_path.exists()
            and not intent_path.is_symlink() and not pointer.exists() and not pointer.is_symlink())
    record['host_policy_cleanup'] = observation
    merged = packed(record)
    public_bytes(merged)
    need(bundle.stable_file(source, 65536, deadline) == source_pin
        and bundle.stable_file(cleanup_path, POLICY_MAX, deadline, root_owned=True) == cleanup_pin
        and file_pin(repo / WORKFLOW, maximum=65536) == workflow_pin)
    if holder is not None:
        policy_readback(holder, deadline)
        need(bundle.stable_file(intent_path, POLICY_MAX, deadline, root_owned=True) == intent_pin)
    if pointer_pin is not None:
        need(bundle.stable_file(pointer, MAX_POINTER, deadline, root_owned=True) == pointer_pin
            and bundle.stable_file(DIRECTORY / POLICY_NAME, bundle.MAX_METADATA, deadline) == policy_pin)
    elif not complete:
        need(not pointer.exists() and not pointer.is_symlink())
    if observation['status'] == 'not-needed':
        need(not intent_path.exists() and not intent_path.is_symlink())
    bundle.remaining(deadline)
    temporary = directory / 'host-policy-result.tmp'
    with bundle.owned_binary(temporary, 'wb', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            deadline, mode=0o600) as stream:
        need(stream.write(merged) == len(merged))
        stream.flush()
        os.fsync(stream.fileno())
    bundle.remaining(deadline)
    temporary.replace(source)
    need(bundle.stable_file(source, 65536, deadline, raw=True)[1] == merged)
    bundle.remaining(deadline)


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
    public = {'schema': 'row.ubuntu-actual-catalogue-webdriver.v2', 'status': 'refused',
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
    driver_start_context = None
    api_read_stage = None
    api_read_facts = None
    api_read_failure = None
    service_worker_stage = service_worker_facts = None
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
            chrome, chrome_driver, runtime_state = selected_runtime(DIRECTORY, source_before, context, deadline)
            public['host_policy'] = policy_evidence(runtime_state['host_policy'])
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
            runtime_note(public, 'chrome-version-command')
            chrome_raw = command(registry, chrome_version_argv(chrome, runtime_state['provider']), repo, env, deadline)
            runtime_note(public, 'driver-version-command')
            driver_raw = command(registry, [str(chrome_driver), '--version'], repo, env, deadline)
            chrome_match = chrome_version_match(chrome_raw, runtime_state['provider'])
            driver_match = re.fullmatch(rb'ChromeDriver ([0-9]+(?:\.[0-9]+){3})(?: [^\r\n]{1,512})?\s*', driver_raw)
            runtime_note(public, 'version-equality')
            if chrome_match is not None and driver_match is not None and len(chrome_match[1]) <= 64 and len(driver_match[1]) <= 64:
                runtime_note(public, 'version-equality', {'chrome': chrome_match[1].decode('ascii'), 'driver': driver_match[1].decode('ascii')})
            need(chrome_match is not None and driver_match is not None and chrome_match[1] == driver_match[1]
                and chrome_match[1].decode('ascii') == runtime_state['installed']['version'])
            inert_runtime_note(public, 'session-setup')
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
            inert_runtime_note(public, 'initial-fixture-startup')
            fixture, ready = launch(1, 0)
            first_fixture = fixture
            port = ready['port']
            origin = 'http://127.0.0.1:' + str(port)
            inert_runtime_note(public, 'initial-fixture-inventory')
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
            inert_runtime_note(public, 'driver-service-birth')
            controller = Owned(registry, [str(chrome_driver), '--port=0', '--enable-chrome-logs'], repo, env, deadline)
            inert_runtime_note(public, 'driver-port-wait')
            launch_limit = min(deadline, time.monotonic() + 20)
            driver_port = None
            while time.monotonic() < launch_limit:
                need(controller.process.poll() is None and not controller.overflow.is_set())
                match = re.search(rb'ChromeDriver was started successfully on port ([0-9]+)', bytes(controller.output))
                if match:
                    driver_port = int(match[1])
                    break
                time.sleep(0.05)
            inert_runtime_note(public, 'driver-port-validation')
            need(driver_port is not None and 1 <= driver_port <= 65535)
            inert_runtime_note(public, 'driver-listener')
            owned_listener(controller, driver_port)
            retained_ports.append(driver_port)
            inert_runtime_note(public, 'browser-client')
            driver = Driver(driver_port, min(deadline - 10, time.monotonic() + 180))
            driver.origin = origin
            inert_runtime_note(public, 'browser-session-start')
            try:
                driver_start_context = prepare_driver_start(driver)
            except BaseException:
                driver_start_context = None
            capabilities = driver.start(chrome, private / 'browser')
            inert_runtime_note(public, 'browser-capabilities')
            need(capabilities['browserVersion'] == version
                 and capabilities['chrome']['chromedriverVersion'].split(' ', 1)[0] == version
                 and capabilities['chrome']['userDataDir'] == str(private / 'browser'))
            inert_runtime_note(public, 'loaded-runtime-inventory')
            public['host_policy'] = observe_policy_tasks(runtime_state['host_policy'], controller, deadline, checkpoint='initial')
            runtime_before = loaded_runtime(controller)
            inert_runtime_note(public, 'loaded-runtime-tools')
            need(str(chrome) in runtime_before and str(chrome_driver) in runtime_before)
            public.pop('runtime_stage', None)
            public.pop('runtime_versions', None)
            checkpoint('api-read')
            api_read_stage = 'navigation-command'
            driver.command('/url', {'url': origin + '/index.html'})
            api_read_stage = 'browser-connect'
            snapshot = driver.connect(tokens[0], 1)
            api_read_stage = 'fixture-inspection'
            first = observe('api-read')
            api_read_stage = 'disk-dom-inventory'
            disk_dom(snapshot, first)
            api_read_stage = 'catalogue-event-selection'
            read_event = [event for event in first['events'] if event['route'] == 'catalogue'][-1]
            api_read_stage = 'case-contract'
            api_read_facts = {'status': read_event['status'], 'dom_seed': snapshot['texts'] == ['ssh • catalogue seed • seed.example.invalid:22'],
                'input_cleared': snapshot['inputEmpty'], 'no_store': read_event['no_store'],
                'public_only': all('credential_ref' not in row and 'identity_file' not in row for row in first['profiles'])}
            record('api-read', api_read_facts)
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
            service_worker_stage = 'case-mark'
            frame('mark', 'service-worker-api-cache-boundary')
            service_worker_stage = 'connect'
            driver.connect(tokens[1], 3)
            service_worker_stage = 'controller'
            driver.controlled()
            service_worker_stage = 'asset-inventory'
            assets = {('/' if name == 'index.html' else '/' + name): hashed((repo / 'apps' / 'web' / name).read_bytes())
                for name in ('index.html', 'styles.css', 'app.js', 'manifest.json')}
            assets['/index.html'] = assets['/']
            service_worker_stage = 'seed-probe'
            seed = driver.execute(SW_PROBE, tokens[1], assets, 'seed-api', async_=True)
            service_worker_stage = 'seed-result-guard'
            need(seed['controlled'] is True and seed['seeded'] is True)
            service_worker_stage = 'event-before'
            before = observe('service-worker-api-cache-boundary')['events']
            service_worker_stage = 'refresh'
            snapshot = driver.refresh(3)
            service_worker_stage = 'event-after'
            after = observe('service-worker-api-cache-boundary')['events']
            service_worker_stage = 'refresh-event-proof'
            real_get = any(event['route'] == 'catalogue' and event['method'] == 'GET' and event['status'] == 200
                and event['authorization_present'] is True for event in after[len(before):])
            service_worker_stage = 'finish-probe'
            sw = driver.execute(SW_PROBE, tokens[1], assets, 'finish', async_=True)
            service_worker_stage = 'finish-result-guard'
            need(sw['controlled'] is True)
            service_worker_stage = 'event-final'
            final_events = observe('service-worker-api-cache-boundary')['events']
            static_events = final_events[len(after):]
            service_worker_stage = 'static-event-guard'
            need(any(event['route'] == 'static' and event['authorization_present'] for event in static_events)
                 and sum(event['route'] == 'static' and event['status'] == 200 for event in static_events) >= 3)
            service_worker_stage = 'case-facts'
            service_worker_facts = {'controlled': sw['controlled'],
                'api_canary_bypassed': disk_dom(snapshot, created_two) and not any('qualification-cache-canary' in text for text in snapshot['texts']),
                'fresh_server_get': real_get, 'health_policy_not_cached': sw['healthPolicyAbsent'],
                'auth_static_canary_bypassed': sw['authBypass'], 'no_store_static_canary_bypassed': sw['noStoreBypass'],
                'canaries_removed': sw['removed'], 'final_cache_public_exact': sw['exact'],
                'storage_private_absent': driver.private_storage_absent(tokens, names)}
            service_worker_stage = 'case-record'
            record('service-worker-api-cache-boundary', service_worker_facts)
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
            public['host_policy'] = observe_policy_tasks(runtime_state['host_policy'], controller, deadline, checkpoint='final')
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
            runtime_readback(runtime_state, deadline)
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
            public = {'schema': 'row.ubuntu-actual-catalogue-webdriver.v2', 'status': 'observations-complete-with-limits',
                'complete': True, 'binding': binding, 'runtime': runtime, 'checks': checks, 'inventories': inventories, 'events': events,
                'cleanup': {'all_retained_zero': all(owner.process.returncode == 0 for owner in registry),
                    'all_reaped': all(owner.reaped for owner in registry),
                    'owned_groups_gone': all(group_members(owner.identity['group']) == [] for owner in registry),
                    'listeners_gone': all(not listener_inodes(number) for number in retained_ports),
                    'forced_cleanup': False, 'descendants_complete': False},
                'elapsed_ms': int((time.monotonic() - started) * 1000), 'server_down_ms': down_ms,
                'source_unchanged': source_before == source_after, 'runtime_unchanged': tools_before == tools_after,
                'limits': LIMITS, 'readiness_credit': 0, 'host_policy': public['host_policy'],
                'host_policy_cleanup': {'status': 'pending'}}
            raw = packed(public)
            validate(raw, {'binding': binding, 'runtime': runtime}, policy_cleanup_pending=True)
            (output / 'result.json').write_bytes(raw)
            return 0
        except Exception as error:
            try:
                emit_service_worker_refusal(public, error, service_worker_stage,
                    seed if service_worker_stage == 'seed-result-guard' else sw if service_worker_stage == 'finish-result-guard' else None,
                    service_worker_facts)
            except BaseException:
                pass
            try:
                api_read_failure = api_read_refusal(public, error, api_read_stage, api_read_facts)
            except BaseException:
                api_read_failure = None
            try:
                driver_start_note(public, error, driver_start_context)
            except BaseException:
                pass
            try:
                driver_stderr_note(public, error, driver_start_context, controller, registry)
            except BaseException:
                pass
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
                emit_runtime_refusal(public)
                try:
                    emit_api_read_refusal(public, api_read_failure)
                except BaseException:
                    pass
                try:
                    emit_case_refusal(public)
                except BaseException:
                    pass
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
