"""Fixed pinned CfT preparation and non-root runtime selection, hosted only.

Import is inert. Root preparation is an explicitly authorized workflow operation,
not acquisition qualification, and never starts a vendor executable.
"""
import math
import os
import platform
import re
import secrets
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path

import cft_bundle as bundle
from cft_git_config import CONFIG_REFUSAL_CODES, ConfigRefusal
from cft_git_owner import GIT_REFUSAL_CODES, GitObservationRefusal
from gate_contract import CHROME_FILE_STAGES, GateRefusal

WORKFLOW = '.github/workflows/ubuntu-catalogue-browser.yml'
PUBLIC_REPO = 'Yunushan/remote-ops-workspace'
POLICY_NAME = 'cft-runtime-policy.json'
STAGE_FILES = ('browser_probe.py', 'cft_bundle.py', 'cft_git_config.py', 'cft_git_owner.py',
    'cft_runtime.py', 'gate_contract.py', 'host_controller.py', POLICY_NAME)
MAX_POINTER = 4096
PHASES = ('context', 'source-checks', 'acquisition', 'installation', 'source-readback', 'publication')


SOURCE_STEPS = ('unobserved', 'contract', 'git-file-pin', 'git-head', 'git-tree', 'head-tree-match',
    'git-diff', 'manifest-decode', 'product-path', 'product-file-pin', 'product-bytes',
    'gate-membership', 'gate-file-pin', 'gate-row-membership', 'workflow-file-pin',
    'workflow-context', 'workflow-command', 'workflow-bytes', 'source-summary') + tuple(
    'git-file-' + name for name in CHROME_FILE_STAGES)


def preparation_diagnostic(error, phase, source_step):
    family, code = 'operation-exception', 'unobserved'
    if type(error) is ConfigRefusal:
        family, allowed = 'git-config', CONFIG_REFUSAL_CODES
    elif type(error) is GitObservationRefusal:
        family, allowed = 'git-owner', GIT_REFUSAL_CODES
    else:
        allowed = ()
        if type(error) is bundle.BundleRefusal:
            family = 'bundle'
        elif type(error) is GateRefusal:
            family = 'source-contract'
        elif type(error) is FileNotFoundError:
            family = 'missing-input'
        elif type(error) is PermissionError:
            family = 'input-access'
    if allowed:
        value = error.__dict__.get('fixed_refusal_code')
        if type(value) is str and value in allowed:
            code = value
    if type(phase) is not str or phase not in PHASES:
        phase = 'context'
    if type(source_step) is not str or source_step not in SOURCE_STEPS:
        source_step = 'unobserved'
    if phase not in ('source-checks', 'source-readback'):
        source_step = 'unobserved'
    raw = bundle.packed({'schema': 'row.cft-preparation.v2', 'status': 'refused', 'phase': phase,
        'source_step': source_step, 'refusal_family': family, 'refusal_code': code, 'readiness_credit': 0})
    if len(raw) > 512:
        return b'{"schema":"row.cft-preparation.v2","status":"refused","phase":"context","source_step":"unobserved","refusal_family":"operation-exception","refusal_code":"unobserved","readiness_credit":0}'
    return raw


def require(value):
    if not value:
        raise bundle.BundleRefusal('cft-runtime-preparation-refused')


def runner_account():
    require(sys.platform == 'linux')
    import pwd
    account = pwd.getpwnam('runner')
    require(account.pw_name == 'runner' and account.pw_uid > 0 and account.pw_gid > 0
        and account.pw_dir == '/home/runner')
    return account.pw_uid, account.pw_gid


def operation_binding(source, context, env):
    require(source['head'] == context['source'])
    value = {'source_head': source['head'], 'source_tree': source['tree'],
        'source_bytes_sha256': source['bytes'], 'workflow_sha256': source['workflow'],
        'event_sha': context['event'], 'run_id': env['GITHUB_RUN_ID'],
        'run_attempt': env['GITHUB_RUN_ATTEMPT']}
    return bundle.binding_contract(value)


def pointer_path(binding):
    bundle.binding_contract(binding)
    return Path('/var/lib') / ('row-cft-operation-' + binding['run_id'] + '-' + binding['run_attempt'] + '.json')


def root_bases():
    for path in (Path('/'), Path('/var'), Path('/var/lib')):
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)


def root_path(value):
    require(type(value) is str and re.fullmatch(r'/var/lib/row-cft-[0-9a-f]{32}', value) is not None)
    return Path(value)


def chrome_version_argv(binary, provider):
    require(type(provider) is str and provider in ('image', 'pinned-cft'))
    return [str(binary), '--version' if provider == 'image' else '--product-version']


def chrome_version_match(raw, provider):
    require(type(raw) is bytes and type(provider) is str and provider in ('image', 'pinned-cft'))
    if provider == 'image':
        pattern = rb'Google Chrome ([0-9]+(?:\.[0-9]+){3})\s*'
    else:
        pattern = rb'([0-9]+(?:\.[0-9]+){3})\s*'
    return re.fullmatch(pattern, raw)


def pointer_contract(raw, expected_binding, policy_raw):
    value = bundle.decode(raw, MAX_POINTER)
    bundle.exact(value, {'schema', 'root', 'binding', 'version', 'policy_sha256',
        'manifest_sha256', 'complete', 'vendor_binary_executed', 'sandbox_policy', 'readiness_credit'})
    require(value['schema'] == 'row.cft-runtime-operation.v1'
        and value['binding'] == expected_binding and value['version'] == bundle.VERSION
        and value['policy_sha256'] == bundle.hashed(policy_raw) and value['complete'] is True
        and value['vendor_binary_executed'] is False
        and value['sandbox_policy'] == 'unchanged-default-no-fallback'
        and type(value['readiness_credit']) is int and value['readiness_credit'] == 0)
    bundle.digest(value['manifest_sha256'])
    root_path(value['root'])
    return value


def selected_runtime(directory, source, context, deadline):
    uid, gid = runner_account()
    require(os.getuid() == os.geteuid() == uid and os.getgid() == os.getegid() == gid)
    root_bases()
    policy_pin, policy_raw = bundle.stable_file(directory / POLICY_NAME,
        bundle.MAX_METADATA, deadline, raw=True)
    bundle.policy(policy_raw, enabled=True)
    binding = operation_binding(source, context, os.environ)
    pointer = pointer_path(binding)
    pointer_pin, pointer_raw = bundle.stable_file(pointer, MAX_POINTER, deadline, root_owned=True, raw=True)
    value = pointer_contract(pointer_raw, binding, policy_raw)
    root = root_path(value['root'])
    installed = bundle.verify_installed(policy_raw, root, deadline, binding)
    require(installed['manifest_sha256'] == value['manifest_sha256']
        and installed['version'] == bundle.VERSION and installed['root_owned'] is True)
    state = {'provider': 'pinned-cft', 'policy_file': directory / POLICY_NAME, 'policy_pin': policy_pin, 'policy_raw': policy_raw,
        'pointer': pointer, 'pointer_pin': pointer_pin, 'binding': binding, 'root': root, 'installed': installed}
    return root / bundle.EXECUTABLES['chrome'], root / bundle.EXECUTABLES['chromedriver'], state


def runtime_readback(state, deadline):
    root_bases()
    require(bundle.stable_file(state['policy_file'], bundle.MAX_METADATA, deadline) == state['policy_pin'])
    require(bundle.stable_file(state['pointer'], MAX_POINTER, deadline, root_owned=True) == state['pointer_pin'])
    require(bundle.verify_installed(state['policy_raw'], state['root'], deadline, state['binding']) == state['installed'])


def root_context(deadline):
    require(sys.platform == 'linux' and platform.machine() == 'x86_64'
        and platform.python_version_tuple()[:2] == ('3', '12'))
    require(os.getuid() == os.geteuid() == 0 and os.getgid() == os.getegid() == 0 and sys.flags.isolated == 1
        and sys.flags.no_site == 1 and sys.dont_write_bytecode)
    uid, gid = runner_account()
    env = os.environ
    require(env.get('GITHUB_ACTIONS') == 'true' and env.get('RUNNER_ENVIRONMENT') == 'github-hosted'
        and env.get('GITHUB_REPOSITORY') == PUBLIC_REPO and env.get('ImageOS') == 'ubuntu24')
    image = env.get('ImageVersion', '')
    require(re.fullmatch(r'[0-9.]{1,64}', image) is not None)
    _, release = bundle.stable_file(Path('/etc/os-release').resolve(strict=True), 4096,
        deadline, root_owned=True, raw=True)
    require(re.search(rb'^ID=ubuntu$', release, re.MULTILINE) is not None
        and re.search(rb'^VERSION_ID="24\.04"$', release, re.MULTILINE) is not None)
    repo = Path(env['GITHUB_WORKSPACE'])
    require(str(repo) == '/home/runner/work/remote-ops-workspace/remote-ops-workspace')
    for path in (repo, repo / 'tests', repo / 'tests' / 'catalogue-browser'):
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == uid and info.st_gid == gid
            and not info.st_mode & 0o022)
    source, event_sha = env.get('QUALIFICATION_SOURCE_SHA', ''), env.get('GITHUB_SHA', '')
    require(re.fullmatch(r'[0-9a-f]{40}', source) is not None
        and re.fullmatch(r'[0-9a-f]{40}', event_sha) is not None)
    _, event_raw = bundle.stable_file(Path(env['GITHUB_EVENT_PATH']), 1048576, deadline, raw=True)
    event = bundle.decode(event_raw, 1048576)
    require(event['repository']['full_name'] == PUBLIC_REPO and event['repository']['private'] is False)
    if env.get('GITHUB_EVENT_NAME') == 'pull_request':
        pr = event['pull_request']
        require(pr['head']['repo']['full_name'] == PUBLIC_REPO and pr['head']['sha'] == source
            and pr['base']['ref'] == 'main' and event['action'] in ('opened', 'reopened', 'synchronize'))
    else:
        require(env.get('GITHUB_EVENT_NAME') == 'push' and event['ref'] == 'refs/heads/main'
            and event['after'] == source == event_sha)
    for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
        require(re.fullmatch(r'[1-9][0-9]{0,19}', env.get(key, '')) is not None)
    require(re.fullmatch(r'[0-9a-f]{40}', env.get('GITHUB_WORKFLOW_SHA', '')) is not None
        and env.get('GITHUB_WORKFLOW_REF', '').startswith(PUBLIC_REPO + '/' + WORKFLOW + '@'))
    root_bases()
    return repo, uid, gid, {'source': source, 'event': event_sha, 'image_version': image}


def stage_readback(repo, deadline):
    stage = Path(__file__).resolve(strict=True).parent
    require(re.fullmatch(r'/var/lib/row-cft-source-[0-9a-f]{32}', str(stage)) is not None)
    info = stage.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o555)
    stage_pin, raw = bundle.stable_file(stage / 'stage.json', bundle.MAX_METADATA,
        deadline, root_owned=True, raw=True)
    value = bundle.decode(raw, bundle.MAX_METADATA)
    bundle.exact(value, {'source_directory', 'pins'})
    require(value['source_directory'] == str(repo / 'tests' / 'catalogue-browser')
        and type(value['pins']) is dict and set(value['pins']) == set(STAGE_FILES))
    require({p.name for p in stage.iterdir()} == set(STAGE_FILES) | {'stage.json'})
    for name, expected in value['pins'].items():
        bundle.exact(expected, {'bytes', 'sha256'})
        staged = bundle.stable_file(stage / name, 1048576, deadline, root_owned=True)
        origin = bundle.stable_file(repo / 'tests' / 'catalogue-browser' / name, 1048576, deadline)
        require({key: staged[key] for key in ('bytes', 'sha256')} == expected
            and {key: origin[key] for key in ('bytes', 'sha256')} == expected)
    require(bundle.stable_file(stage / 'stage.json', bundle.MAX_METADATA, deadline, root_owned=True) == stage_pin)
    return stage_pin


def publish_pointer(path, record, deadline):
    raw = bundle.packed(record)
    require(len(raw) <= MAX_POINTER)
    with bundle.owned_binary(path, 'wb', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            deadline, mode=0o600) as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
        os.fchmod(stream.fileno(), 0o444)
    _, observed = bundle.stable_file(path, MAX_POINTER, deadline, root_owned=True, raw=True)
    require(observed == raw)


def main():
    started = time.monotonic()
    deadline = float(os.environ['ROW_CFT_PREP_DEADLINE'])
    require(math.isfinite(deadline) and started < deadline <= started + 150)
    watchdog = threading.Timer(deadline - started + 10, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()
    registry = []
    phase = 'context'
    source_step = 'unobserved'
    def source_note(value):
        nonlocal source_step
        source_step = value
    success_eligible = False
    try:
        repo, uid, gid, context = root_context(deadline)
        stage_before = stage_readback(repo, deadline)
        # All imported project dependencies are root-staged exact pinned bytes.
        from cft_git_owner import RunnerGit
        from host_controller import source_guard
        def observed_git(argv):
            return RunnerGit(registry, argv, repo, deadline, uid=uid, gid=gid).finish()
        phase = 'source-checks'
        before = source_guard(repo, context, registry, {}, deadline, workflow_path=WORKFLOW,
            source_directory=repo / 'tests' / 'catalogue-browser', git_command=observed_git, source_diagnostic=source_note)
        binding = operation_binding(before, context, os.environ)
        pointer = pointer_path(binding)
        require(not pointer.exists() and not pointer.is_symlink())
        policy_raw = bundle.stable_file(Path(__file__).parent / POLICY_NAME,
            bundle.MAX_METADATA, deadline, root_owned=True, raw=True)[1]
        bundle.policy(policy_raw, enabled=True)
        destination = Path('/var/lib') / ('row-cft-' + secrets.token_hex(16))
        with tempfile.TemporaryDirectory(prefix='row-cft-private-', dir='/var/lib') as temp:
            private = Path(temp)
            phase = 'acquisition'
            bundle.acquire(policy_raw, private, deadline, require_pins=True)
            phase = 'installation'
            installed = bundle.install_pinned(policy_raw, private, destination, deadline, binding)
        require(not private.exists())
        phase = 'source-readback'
        after = source_guard(repo, context, registry, {}, deadline, workflow_path=WORKFLOW,
            source_directory=repo / 'tests' / 'catalogue-browser', git_command=observed_git, source_diagnostic=source_note)
        require(before == after and stage_before == stage_readback(repo, deadline))
        require(all(owner.finished and owner.reaped and not owner.failed and not owner.forced_cleanup
            and owner.closed_pipes == {0, 1} and owner.process.returncode == 0 for owner in registry))
        phase = 'publication'
        record = {'schema': 'row.cft-runtime-operation.v1', 'root': str(destination), 'binding': binding,
            'version': bundle.VERSION, 'policy_sha256': bundle.hashed(policy_raw),
            'manifest_sha256': installed['manifest_sha256'], 'complete': True,
            'vendor_binary_executed': False, 'sandbox_policy': 'unchanged-default-no-fallback', 'readiness_credit': 0}
        publish_pointer(pointer, record, deadline)
        bundle.remaining(deadline)
        # This bounded line is provisional; CLI success follows finalization and the final clock.
        print('{"schema":"row.cft-preparation.v1","status":"prepared-unqualified-pending-finalization","provisional":true,"readiness_credit":0}', flush=True)
        success_eligible = True
    except BaseException as error:
        success_eligible = False
        # Fixed phase/substage/family/predicate only; no error, path, output, descriptor or private data.
        try:
            print(preparation_diagnostic(error, phase, source_step).decode('ascii'), file=sys.stderr)
        except BaseException:
            pass
    finally:
        cleanup_failed = False
        for owner in reversed(registry):
            if not owner.finished:
                try:
                    owner.refuse_cleanup()
                except BaseException:
                    cleanup_failed = True
        watchdog.cancel()
        if cleanup_failed:
            raise bundle.BundleRefusal('cft-root-cleanup-unproved') from None
    if not success_eligible:
        return 1
    bundle.remaining(deadline)
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except BaseException:
        try:
            sys.stderr.write('cft-preparation-refused\n')
        except BaseException:
            pass
        code = 1
    raise SystemExit(code)
