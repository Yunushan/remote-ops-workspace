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
from gate_contract import CHROME_FILE_STAGES, GateRefusal, host_policy_evidence

WORKFLOW = '.github/workflows/ubuntu-catalogue-browser.yml'
PUBLIC_REPO = 'Yunushan/remote-ops-workspace'
POLICY_NAME = 'cft-runtime-policy.json'
STAGE_FILES = ('browser_probe.py', 'cft_bundle.py', 'cft_git_config.py', 'cft_git_owner.py',
    'cft_runtime.py', 'gate_contract.py', 'host_controller.py', POLICY_NAME)
MAX_POINTER = 4096
PHASES = ('context', 'source-checks', 'acquisition', 'installation', 'source-readback', 'publication', 'host-policy')


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
        'manifest_sha256', 'complete', 'vendor_binary_executed', 'sandbox_policy', 'host_policy', 'readiness_credit'})
    require(value['schema'] == 'row.cft-runtime-operation.v2'
        and value['binding'] == expected_binding and value['version'] == bundle.VERSION
        and value['policy_sha256'] == bundle.hashed(policy_raw) and value['complete'] is True
        and value['vendor_binary_executed'] is False
        and value['sandbox_policy'] == 'default-browser-with-scoped-host-userns-profile'
        and type(value['readiness_credit']) is int and value['readiness_credit'] == 0)
    bundle.digest(value['manifest_sha256'])
    root_path(value['root'])
    host_policy_evidence(value['host_policy'])
    require(value['host_policy']['task_label_initial_observed'] is False
        and value['host_policy']['task_label_final_observed'] is False)
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
    host_policy = select_host_policy(value, deadline)
    state = {'provider': 'pinned-cft', 'policy_file': directory / POLICY_NAME, 'policy_pin': policy_pin, 'policy_raw': policy_raw,
        'pointer': pointer, 'pointer_pin': pointer_pin, 'binding': binding, 'root': root, 'installed': installed, 'host_policy': host_policy}
    return root / bundle.EXECUTABLES['chrome'], root / bundle.EXECUTABLES['chromedriver'], state


def runtime_readback(state, deadline):
    root_bases()
    require(bundle.stable_file(state['policy_file'], bundle.MAX_METADATA, deadline) == state['policy_pin'])
    require(bundle.stable_file(state['pointer'], MAX_POINTER, deadline, root_owned=True) == state['pointer_pin'])
    require(bundle.verify_installed(state['policy_raw'], state['root'], deadline, state['binding']) == state['installed'])
    policy_readback(state['host_policy'], deadline)


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


def publish_pointer(path, record, deadline, *, packed_input=False, maximum=MAX_POINTER):
    raw = record if packed_input else bundle.packed(record)
    require(type(raw) is bytes and type(maximum) is int and 0 <= maximum <= 1048576 and len(raw) <= maximum)
    with bundle.owned_binary(path, 'wb', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            deadline, mode=0o600) as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
        os.fchmod(stream.fileno(), 0o444)
    _, observed = bundle.stable_file(path, maximum, deadline, root_owned=True, raw=True)
    require(observed == raw)



APPARMOR_TOOL = Path('/usr/sbin/apparmor_parser')
APPARMOR_ABI = Path('/etc/apparmor.d/abi/4.0')
POLICY_MAX = 65536
KERNEL_SCALARS = (
    '/sys/module/apparmor/parameters/enabled',
    '/sys/kernel/security/apparmor/features/namespaces/mask',
    '/proc/sys/kernel/apparmor_restrict_unprivileged_userns',
    '/proc/sys/kernel/unprivileged_userns_clone',
    '/proc/sys/user/max_user_namespaces',
)


def policy_record_path(binding, kind):
    bundle.binding_contract(binding)
    require(kind in ('intent', 'cleanup'))
    return Path('/var/lib') / ('row-cft-policy-' + kind + '-' + binding['run_id'] + '-' + binding['run_attempt'] + '.json')


def policy_names(root):
    root = root_path(str(root))
    nonce = root.name[len('row-cft-'):]
    return 'row-cft-userns-' + nonce, Path('/var/lib') / ('row-cft-userns-' + nonce)


def policy_profile(root):
    name, _directory = policy_names(root)
    return ('profile ' + name + ' ' + str(root / bundle.EXECUTABLES['chrome'])
        + ' flags=(unconfined) {\n  userns,\n}\n').encode('ascii')


def kernel_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_nlink)


def kernel_read(path, maximum, deadline, *, uid=0):
    # Kernel virtual files may have synthetic/zero sizes. This is a sampled read,
    # not ordinary-file immutability or a lease on global kernel state.
    path = Path(path)
    bundle.remaining(deadline)
    for parent in path.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0, uid))
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_uid in (0, uid))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        require(kernel_identity(os.fstat(fd)) == kernel_identity(before))
        data = bytearray()
        while True:
            bundle.remaining(deadline)
            chunk = os.read(fd, min(4096, maximum + 1 - len(data)))
            if not chunk:
                break
            require(len(data) + len(chunk) <= maximum)
            data.extend(chunk)
        require(kernel_identity(os.fstat(fd)) == kernel_identity(before))
        answer = bytes(data)
    finally:
        os.close(fd)  # One raw descriptor owner and one close attempt.
    require(kernel_identity(path.lstat()) == kernel_identity(before))
    bundle.remaining(deadline)
    return answer


def host_features(deadline):
    rows = [kernel_read(Path(name), 4096, deadline) for name in KERNEL_SCALARS]
    require(rows[0] in (b'Y', b'Y\n') and rows[1] in (b'userns_create', b'userns_create\n'))
    require(rows[2] in (b'1', b'1\n') and rows[3] in (b'1', b'1\n'))
    require(re.fullmatch(rb'[1-9][0-9]{0,9}\n?', rows[4]) is not None
        and int(rows[4]) <= 2147483647)
    return bundle.hashed(bundle.packed([bundle.hashed(raw) for raw in rows]))


def caller_unconfined(deadline):
    require(kernel_read(Path('/proc') / str(os.getpid()) / 'attr/apparmor/current',
        4096, deadline, uid=os.getuid()) in (b'unconfined', b'unconfined\n'))


def profile_membership(name, chrome, deadline):
    require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
    require(type(name) is str and re.fullmatch(r'row-cft-userns-[0-9a-f]{32}', name) is not None)
    raw = kernel_read(Path('/sys/kernel/security/apparmor/profiles'), 1048576, deadline)
    require(all(char in (10,) or 32 <= char <= 126 for char in raw))
    rows = raw.decode('ascii').splitlines()
    require(len(rows) <= 4096)
    own = []
    for row in rows:
        require(len(row) <= 4096)
        match = re.fullmatch(r'(.+) \((enforce|complain|unconfined|kill|prompt|default_allow)\)', row)
        require(match is not None)
        require(match[1] != str(chrome))  # A known exact attachment/name collision refuses.
        if match[1] == name:
            own.append(match[2])
    require(len(own) <= 1)
    require(not own or own[0] in ('unconfined', 'default_allow'))
    return bool(own)


def policy_tool(deadline):
    for parent in APPARMOR_TOOL.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)
    pin = bundle.stable_file(APPARMOR_TOOL, 536870912, deadline, root_owned=True)
    fd = os.open(APPARMOR_TOOL, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        require(list(bundle.identity(os.fstat(fd))) == pin['identity'])
        require(os.read(fd, 4) == b'\x7fELF' and os.fstat(fd).st_mode & 0o111 != 0)
    finally:
        os.close(fd)
    require(list(bundle.identity(APPARMOR_TOOL.lstat())) == pin['identity'])
    bundle.remaining(deadline)
    return pin


def policy_inputs(state, deadline):
    directory = Path(state['directory'])
    require(str(directory) == str(policy_names(Path(state['root']))[1]))
    info = directory.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o555)
    require({p.name for p in directory.iterdir()} == {'profile', 'config', 'abi'})
    observed = {}
    for name, maximum in (('profile', 4096), ('config', 0), ('abi', 1048576)):
        pin, raw = bundle.stable_file(directory / name, maximum, deadline, root_owned=True, raw=True)
        require(stat.S_IMODE((directory / name).lstat().st_mode) == 0o444)
        if name == 'profile':
            require(raw == policy_profile(Path(state['root'])))
        elif name == 'config':
            require(raw == b'')
        else:
            require(0 < len(raw) <= 1048576 and b'userns_create' in raw
                and all(char in (9, 10) or 32 <= char <= 126 for char in raw))
        observed[name] = pin
    require(observed == state['input_pins'])
    require(policy_tool(deadline) == state['tool_pin'])
    return observed


def policy_argv(state, action):
    require(action in ('add', 'remove'))
    directory = Path(state['directory'])
    require(str(directory) == str(policy_names(Path(state['root']))[1]))
    return [str(APPARMOR_TOOL), '--config-file', str(directory / 'config'), '--skip-cache',
        '--jobs=0', '--abort-on-error', '--Werror', '--policy-features', str(directory / 'abi'),
        '--' + action, str(directory / 'profile')]


def policy_owner(registry, argv, deadline):
    from host_controller import Owned
    class PolicyOwned(Owned):
        def drain(self, stream, target, frames):
            try:
                super().drain(stream, target, frames)
            except BaseException:
                self.overflow.set()  # Ambiguous drain/close cannot qualify this new loader.
    return PolicyOwned(registry, argv, Path('/var/lib'), {}, deadline)


def run_policy(state, action, registry, deadline):
    policy_inputs(state, deadline)
    owner = policy_owner(registry, policy_argv(state, action), deadline)
    owner.finish(timeout=min(20, bundle.remaining(deadline)))
    require(owner.finished and owner.reaped and not owner.overflow.is_set() and owner.errors == bytearray()
        and all(not thread.is_alive() for thread in owner.threads) and owner.process.returncode == 0
        and all(stream.closed is True for stream in (owner.process.stdin, owner.process.stdout, owner.process.stderr)))
    policy_inputs(state, deadline)
    bundle.remaining(deadline)


def policy_state_contract(raw, binding):
    state = bundle.decode(raw, POLICY_MAX)
    bundle.exact(state, {'schema', 'root', 'directory', 'name', 'binding', 'input_pins', 'tool_pin',
        'features_sha256', 'profile_sha256', 'abi_sha256', 'host_policy_change_planned', 'readiness_credit'})
    require(state['schema'] == 'row.cft-userns-intent.v1' and state['binding'] == binding
        and state['host_policy_change_planned'] is True and type(state['readiness_credit']) is int
        and state['readiness_credit'] == 0)
    name, directory = policy_names(root_path(state['root']))
    require(state['name'] == name and state['directory'] == str(directory))
    bundle.exact(state['input_pins'], {'profile', 'config', 'abi'})
    for pin in (*state['input_pins'].values(), state['tool_pin']):
        bundle.exact(pin, {'bytes', 'sha256', 'identity'})
        bundle.digest(pin['sha256'])
        require(type(pin['bytes']) is int and 0 <= pin['bytes'] <= 536870912
            and type(pin['identity']) is list and len(pin['identity']) == 8
            and all(type(value) is int for value in pin['identity']))
    for key in ('features_sha256', 'profile_sha256', 'abi_sha256'):
        bundle.digest(state[key])
    require(state['profile_sha256'] == state['input_pins']['profile']['sha256']
        and state['abi_sha256'] == state['input_pins']['abi']['sha256'])
    return state


def prepare_host_policy(root, binding, deadline, registry, holder):
    root_bases()
    caller_unconfined(deadline)
    features = host_features(deadline)
    tool = policy_tool(deadline)
    name, directory = policy_names(root)
    chrome = root / bundle.EXECUTABLES['chrome']
    require(not profile_membership(name, chrome, deadline))
    intent = policy_record_path(binding, 'intent')
    cleanup = policy_record_path(binding, 'cleanup')
    require(not intent.exists() and not intent.is_symlink() and not cleanup.exists() and not cleanup.is_symlink())
    for ancestor in APPARMOR_ABI.parents:
        info = ancestor.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)
    abi_pin, abi_raw = bundle.stable_file(APPARMOR_ABI, 1048576, deadline, root_owned=True, raw=True)
    require(abi_raw and b'userns_create' in abi_raw and all(char in (9, 10) or 32 <= char <= 126 for char in abi_raw))
    parent = os.open('/var/lib', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    child = None
    try:
        before = Path('/var/lib').lstat()
        require(bundle.identity(os.fstat(parent)) == bundle.identity(before))
        os.mkdir(directory.name, mode=0o700, dir_fd=parent)
        child = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        require(bundle.identity(os.fstat(child)) == bundle.identity(directory.lstat()))
        pins = {}
        for filename, raw in (('profile', policy_profile(root)), ('config', b''), ('abi', abi_raw)):
            publish_pointer(directory / filename, raw, deadline, packed_input=True, maximum=1048576)
            pins[filename] = bundle.stable_file(directory / filename, 1048576, deadline, root_owned=True)
        os.fchmod(child, 0o555)
        require(bundle.identity(os.fstat(child)) == bundle.identity(directory.lstat()))
        after = Path('/var/lib').lstat()
        require(after.st_uid == 0 and not after.st_mode & 0o022
            and (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino))
    finally:
        first = None
        for fd in (child, parent):
            if fd is not None:
                try:
                    os.close(fd)
                except BaseException as error:
                    if first is None:
                        first = error
        if first is not None:
            raise first
    state = {'schema': 'row.cft-userns-intent.v1', 'root': str(root), 'directory': str(directory),
        'name': name, 'binding': binding, 'input_pins': pins, 'tool_pin': tool,
        'features_sha256': features, 'profile_sha256': pins['profile']['sha256'],
        'abi_sha256': pins['abi']['sha256'], 'host_policy_change_planned': True, 'readiness_credit': 0}
    policy_inputs(state, deadline)
    require(bundle.stable_file(APPARMOR_ABI, 1048576, deadline, root_owned=True) == abi_pin)
    publish_pointer(intent, state, deadline, maximum=POLICY_MAX)
    intent_pin, intent_raw = bundle.stable_file(intent, POLICY_MAX, deadline, root_owned=True, raw=True)
    require(policy_state_contract(intent_raw, binding) == state)
    holder.update({'state': state, 'intent_pin': intent_pin})  # Retain before parser birth.
    require(host_features(deadline) == features and not profile_membership(name, chrome, deadline))
    run_policy(state, 'add', registry, deadline)
    require(profile_membership(name, chrome, deadline) and host_features(deadline) == features)
    policy_readback(holder, deadline)
    bundle.remaining(deadline)
    holder['preparation_loaded_observed'] = True
    holder['samples'] = {'initial': {'observed': False, 'count': 0}, 'final': {'observed': False, 'count': 0}}
    return holder


def policy_digests(holder):
    require(type(holder) is dict and type(holder.get('state')) is dict)
    state = holder['state']
    require(policy_state_contract(bundle.packed(state), state['binding']) == state)
    pin = holder['intent_pin']
    bundle.exact(pin, {'bytes', 'sha256', 'identity'})
    bundle.digest(pin['sha256'])
    require(type(pin['bytes']) is int and 0 < pin['bytes'] <= POLICY_MAX
        and type(pin['identity']) is list and len(pin['identity']) == 8
        and all(type(value) is int for value in pin['identity']))
    return {'profile_sha256': state['profile_sha256'], 'abi_sha256': state['abi_sha256'],
        'tool_sha256': state['tool_pin']['sha256'], 'features_sha256': state['features_sha256'],
        'intent_sha256': pin['sha256']}


def policy_evidence(holder):
    digests = policy_digests(holder)
    require(holder.get('preparation_loaded_observed') is True)
    samples = holder['samples']
    bundle.exact(samples, {'initial', 'final'})
    for row in samples.values():
        bundle.exact(row, {'observed', 'count'})
        require(type(row['observed']) is bool and type(row['count']) is int and 0 <= row['count'] <= 256)
        require(row['count'] >= 1 if row['observed'] else row['count'] == 0)
    require(not samples['final']['observed'] or samples['initial']['observed'])
    return {'scope': 'exact-pinned-chrome-userns', 'host_policy_changed': True,
        'default_browser_sandbox_requested': True, 'profile_loaded_preparation_observed': True,
        'task_label_initial_observed': samples['initial']['observed'],
        'initial_observed_chrome_tasks': samples['initial']['count'],
        'task_label_final_observed': samples['final']['observed'],
        'final_observed_chrome_tasks': samples['final']['count'], **digests}


def select_host_policy(value, deadline):
    binding = value['binding']
    intent_pin, intent_raw = bundle.stable_file(policy_record_path(binding, 'intent'),
        POLICY_MAX, deadline, root_owned=True, raw=True)
    state = policy_state_contract(intent_raw, binding)
    holder = {'state': state, 'intent_pin': intent_pin, 'preparation_loaded_observed': True,
        'samples': {'initial': {'observed': False, 'count': 0}, 'final': {'observed': False, 'count': 0}}}
    require(state['root'] == value['root'] and policy_evidence(holder) == value['host_policy'])
    caller_unconfined(deadline)
    policy_readback(holder, deadline)
    return holder


def policy_readback(holder, deadline):
    state = holder['state']
    pin, raw = bundle.stable_file(policy_record_path(state['binding'], 'intent'), POLICY_MAX,
        deadline, root_owned=True, raw=True)
    require(pin == holder['intent_pin'] and policy_state_contract(raw, state['binding']) == state)
    policy_inputs(state, deadline)
    require(host_features(deadline) == state['features_sha256'])
    policy_digests(holder)
    bundle.remaining(deadline)


def observe_policy_tasks(holder, owner, deadline, *, checkpoint):
    from host_controller import group_members, proc_identity
    require(type(checkpoint) is str and checkpoint in ('initial', 'final'))
    evidence = policy_evidence(holder)
    require(evidence['task_label_initial_observed'] is False if checkpoint == 'initial'
        else evidence['task_label_initial_observed'] is True and evidence['task_label_final_observed'] is False)
    state = holder['state']
    policy_readback(holder, deadline)
    require(owner.identity is not None and owner.process.poll() is None)
    leader = proc_identity(owner.process.pid)
    require(all(leader[key] == owner.identity[key] for key in ('pid', 'group', 'session', 'start')))
    chrome = str(root_path(state['root']) / bundle.EXECUTABLES['chrome'])
    count = 0
    for row in group_members(owner.identity['group']):
        pid = row['pid']
        before = proc_identity(pid)
        require(before == row and before['group'] == owner.identity['group'])
        target = os.readlink(Path('/proc') / str(pid) / 'exe')
        if target == chrome:
            label = kernel_read(Path('/proc') / str(pid) / 'attr/apparmor/current', 4096,
                deadline, uid=os.getuid())
            require(label in ((state['name'] + ' (unconfined)\n').encode(),
                (state['name'] + ' (default_allow)\n').encode()))
            count += 1
        require(proc_identity(pid) == before)
    require(1 <= count <= 256 and owner.process.poll() is None)
    final_leader = proc_identity(owner.process.pid)
    require(all(final_leader[key] == leader[key] for key in ('pid', 'group', 'session', 'start')))
    policy_readback(holder, deadline)
    bundle.remaining(deadline)
    holder['samples'][checkpoint] = {'observed': True, 'count': count}
    return policy_evidence(holder)


def remove_host_policy(holder, deadline, registry):
    state = holder['state']
    root_bases()
    caller_unconfined(deadline)
    policy_readback(holder, deadline)
    chrome = root_path(state['root']) / bundle.EXECUTABLES['chrome']
    present = profile_membership(state['name'], chrome, deadline)
    if present:
        run_policy(state, 'remove', registry, deadline)
    require(not profile_membership(state['name'], chrome, deadline))
    policy_readback(holder, deadline)
    bundle.remaining(deadline)
    return {'status': 'removed' if present else 'already-absent',
        'profile_present_pre_remove_observed': present, 'remove_attempted': present,
        'profile_absent_observed': True, 'scalar_state_unchanged': True,
        'host_disposal_required': True, 'descendants_complete': False, **policy_digests(holder)}


def cleanup_main():
    started = time.monotonic()
    deadline = float(os.environ['ROW_CFT_PREP_DEADLINE'])
    require(math.isfinite(deadline) and started < deadline <= started + 30)
    watchdog = threading.Timer(deadline - started + 5, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()
    registry, policy_registry = [], []
    result = None
    selected_error = None
    try:
        repo, uid, gid, context = root_context(deadline)
        stage_before = stage_readback(repo, deadline)
        from cft_git_owner import RunnerGit
        from host_controller import source_guard
        def observed_git(argv):
            return RunnerGit(registry, argv, repo, deadline, uid=uid, gid=gid).finish()
        source = source_guard(repo, context, registry, {}, deadline, workflow_path=WORKFLOW,
            source_directory=repo / 'tests/catalogue-browser', git_command=observed_git)
        binding = operation_binding(source, context, os.environ)
        intent = policy_record_path(binding, 'intent')
        if not intent.exists():
            require(not intent.is_symlink() and not pointer_path(binding).exists()
                and not pointer_path(binding).is_symlink())
            observation = {'status': 'not-needed', 'intent_absent_observed': True,
                'host_disposal_required': True, 'descendants_complete': False}
        else:
            pin, raw = bundle.stable_file(intent, POLICY_MAX, deadline, root_owned=True, raw=True)
            holder = {'state': policy_state_contract(raw, binding), 'intent_pin': pin}
            observation = remove_host_policy(holder, deadline, policy_registry)
        require(source_guard(repo, context, registry, {}, deadline, workflow_path=WORKFLOW,
            source_directory=repo / 'tests/catalogue-browser', git_command=observed_git) == source
            and stage_readback(repo, deadline) == stage_before)
        require(all(owner.finished and owner.reaped and not owner.failed and not owner.forced_cleanup
            and owner.closed_pipes == {0, 1} and owner.process.returncode == 0 for owner in registry))
        require(all(owner.finished and owner.reaped and not owner.overflow.is_set()
            and owner.errors == bytearray() and owner.process.returncode == 0
            and owner.cleanup_observed() for owner in policy_registry))
        result = {'schema': 'row.cft-userns-cleanup.v1', 'binding': binding,
            'observation': observation, 'readiness_credit': 0}
        bundle.remaining(deadline)
        publish_pointer(policy_record_path(binding, 'cleanup'), result, deadline, maximum=POLICY_MAX)
        print('{"schema":"row.cft-userns-cleanup.v1","status":"sampled-cleanup-recorded","provisional":true,"readiness_credit":0}', flush=True)
    except BaseException as error:
        selected_error = error
        raise
    finally:
        cleanup_failed = False
        for owner in reversed(policy_registry):
            if not owner.finished:
                try:
                    owner.refuse_cleanup()
                except BaseException:
                    cleanup_failed = True
        for owner in reversed(registry):
            if not owner.finished:
                try:
                    owner.refuse_cleanup()
                except BaseException:
                    cleanup_failed = True
        try:
            watchdog.cancel()
        except BaseException:
            cleanup_failed = True
        if cleanup_failed and selected_error is None:
            raise bundle.BundleRefusal('cft-root-policy-cleanup-unproved') from None
    require(result is not None)
    bundle.remaining(deadline)
    return 0



def policy_cleanup_fence(registry):
    """Refusal-resource samples only; forced cleanup never mints natural success."""
    proved = True
    try:
        for owner in reversed(registry):
            try:
                if owner.finished is not True:
                    owner.refuse_cleanup()
            except BaseException:
                proved = False
            try:
                result = owner.process.poll()
                observed = (owner.reaped is True and type(result) is int
                    and owner.process.returncode == result
                    and all(stream is not None and stream.closed is True
                        for stream in (owner.process.stdin, owner.process.stdout, owner.process.stderr))
                    and all(thread.is_alive() is False for thread in owner.threads)
                    and owner.cleanup_observed() is True)
                if not observed:
                    proved = False
            except BaseException:
                proved = False
    except BaseException:
        proved = False
    return proved


def late_failure_policy_removal(holder, productive_deadline):
    """Same absolute refusal horizon; the caller always rethrows its selected error."""
    registry = []
    guard = None
    cleanup_deadline = productive_deadline + 10
    try:
        remaining = bundle.remaining(cleanup_deadline)
        guard = threading.Timer(remaining, lambda: os._exit(124))
        guard.daemon = True
        guard.start()  # Must succeed before any removal provider birth.
        remove_host_policy(holder, cleanup_deadline, registry)
    except BaseException:
        pass
    finally:
        proved = False
        try:
            proved = policy_cleanup_fence(registry)
        except BaseException:
            pass
        if proved and guard is not None:
            try:
                guard.cancel()
            except BaseException:
                pass
        # An unproved fence leaves the daemon guard armed. Normal interpreter
        # exit can precede it; this is not a scheduling or descendant guarantee.


def main():
    started = time.monotonic()
    deadline = float(os.environ['ROW_CFT_PREP_DEADLINE'])
    require(math.isfinite(deadline) and started < deadline <= started + 150)
    watchdog = threading.Timer(deadline - started + 10, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()
    registry = []
    policy_registry = []
    policy_holder = {}
    selected_error = None
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
        phase = 'host-policy'
        policy_holder = prepare_host_policy(destination, binding, deadline, policy_registry, policy_holder)
        phase = 'source-readback'
        after = source_guard(repo, context, registry, {}, deadline, workflow_path=WORKFLOW,
            source_directory=repo / 'tests' / 'catalogue-browser', git_command=observed_git, source_diagnostic=source_note)
        require(before == after and stage_before == stage_readback(repo, deadline))
        require(all(owner.finished and owner.reaped and not owner.failed and not owner.forced_cleanup
            and owner.closed_pipes == {0, 1} and owner.process.returncode == 0 for owner in registry))
        phase = 'publication'
        record = {'schema': 'row.cft-runtime-operation.v2', 'root': str(destination), 'binding': binding,
            'version': bundle.VERSION, 'policy_sha256': bundle.hashed(policy_raw),
            'manifest_sha256': installed['manifest_sha256'], 'complete': True,
            'vendor_binary_executed': False, 'sandbox_policy': 'default-browser-with-scoped-host-userns-profile',
            'host_policy': policy_evidence(policy_holder), 'readiness_credit': 0}
        publish_pointer(pointer, record, deadline)
        bundle.remaining(deadline)
        # This bounded line is provisional; CLI success follows finalization and the final clock.
        print('{"schema":"row.cft-preparation.v1","status":"prepared-unqualified-pending-finalization","provisional":true,"readiness_credit":0}', flush=True)
        success_eligible = True
    except BaseException as error:
        selected_error = error
        success_eligible = False
        if policy_holder:
            try:
                remove_host_policy(policy_holder, deadline + 10, policy_registry)
            except BaseException:
                pass  # Same-run always cleanup/disposal remains mandatory.
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
        policy_cleanup_proved = False
        try:
            policy_cleanup_proved = policy_cleanup_fence(policy_registry)
        except BaseException:
            pass
        if policy_cleanup_proved:
            watchdog.cancel()
        if cleanup_failed:
            raise bundle.BundleRefusal('cft-root-cleanup-unproved') from None
        if not policy_cleanup_proved:
            success_eligible = False
            if selected_error is None:
                raise bundle.BundleRefusal('cft-policy-cleanup-unproved') from None
    if not success_eligible:
        return 1
    try:
        bundle.remaining(deadline)
    except BaseException:
        if policy_holder:
            try:
                late_failure_policy_removal(policy_holder, deadline)
            except BaseException:
                pass
        raise
    return 0


if __name__ == '__main__':
    try:
        action = os.environ.get('ROW_CFT_ACTION', 'prepare')
        require(action in ('prepare', 'cleanup'))
        code = cleanup_main() if action == 'cleanup' else main()
    except BaseException:
        try:
            sys.stderr.write('cft-preparation-refused\n')
        except BaseException:
            pass
        code = 1
    raise SystemExit(code)
