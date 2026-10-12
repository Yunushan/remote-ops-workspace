"""Finite, refusing config/attribute preflight for a future disposable-host lane.

This is source only. It does not start Git, import product code or grant root
execution authority. Before/after snapshots do not exclude concurrent mutation.
"""
import hashlib
import os
import re
import stat
import time
from pathlib import Path

MAX_CONFIG = 16384
MAX_NODES = 20000
MAX_DEPTH = 32
ATTRIBUTES = (
    '*.sh text eol=lf', '*.ps1 text eol=crlf', '*.py text eol=lf',
    '*.md text eol=lf', '*.yml text eol=lf', '*.yaml text eol=lf',
    '*.json text eol=lf', 'requirements-release.txt text eol=lf',
    'requirements-locks/*.txt text eol=lf',
    'requirements-locks/inputs/*.in text eol=lf',
    'redistribution-evidence/*.txt text eol=lf', '*.png binary',
)
ALLOWED = {
    'core': {
        'repositoryformatversion': {'0'}, 'filemode': {'true'},
        'bare': {'false'}, 'logallrefupdates': {'true'},
        'ignorecase': {'false'}, 'autocrlf': {'false'},
    },
    'remote "origin"': {
        'url': {'https://github.com/Yunushan/remote-ops-workspace',
                'https://github.com/Yunushan/remote-ops-workspace.git'},
        'fetch': {'+refs/heads/*:refs/remotes/origin/*'},
    },
    'branch "main"': {'remote': {'origin'}, 'merge': {'refs/heads/main'}},
}


CONFIG_REFUSAL_CODES = ('clock-1', 'config-values-1', 'config-values-2', 'config-values-3', 'config-values-4', 'config-values-5', 'config-values-6', 'config-values-7', 'stable-bytes-1', 'stable-bytes-2', 'stable-bytes-3', 'stable-bytes-4', 'stable-bytes-5', 'stable-bytes-6', 'snapshot-1', 'snapshot-2', 'snapshot-3', 'snapshot-4', 'snapshot-5', 'snapshot-6', 'snapshot-7', 'snapshot-8', 'snapshot-9', 'snapshot-10', 'snapshot-11', 'snapshot-12', 'snapshot-13', 'snapshot-14', 'snapshot-15', 'snapshot-16', 'check-refused', 'config-encoding', 'raw-close-unproved', 'required-absent')


class ConfigRefusal(ValueError):
    pass


def need(value, code='check-refused'):
    if not value:
        error = ConfigRefusal('cft-git-config-refused')
        error.fixed_refusal_code = code
        raise error


def clock(deadline):
    need(time.monotonic() < deadline, 'clock-1')


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def config_values(raw):
    """Accept a literal checkout subset, without interpreting Git syntax.

    Includes, extensions, filters, external commands, credentials, quote/escape
    syntax, continuations and duplicate keys/sections are refused by construction.
    This deliberately refuses valid Git configs outside this exact subset.
    """
    need(type(raw) is bytes and len(raw) <= MAX_CONFIG and b'\x00' not in raw, 'config-values-1')
    try:
        text = raw.decode('ascii')
    except UnicodeDecodeError:
        error = ConfigRefusal('cft-git-config-refused')
        error.fixed_refusal_code = 'config-encoding'
        raise error from None
    need('\r' not in text and '\\' not in text, 'config-values-2')
    sections = set()
    values = {}
    section = None
    for line in text.split('\n'):
        line = line.strip(' \t')
        if not line:
            continue
        match = re.fullmatch(r'\[([^\[\]]+)\]', line)
        if match is not None:
            section = match.group(1)
            need(section in ALLOWED and section not in sections, 'config-values-3')
            sections.add(section)
            continue
        match = re.fullmatch(r'([a-z]+)\s*=\s*([^\r\n]+)', line)
        need(section is not None and match is not None, 'config-values-4')
        key, value = match.groups()
        value = value.strip(' \t')
        need(key in ALLOWED[section] and value in ALLOWED[section][key], 'config-values-5')
        pair = (section, key)
        need(pair not in values, 'config-values-6')
        values[pair] = value
    need(values.get(('core', 'repositoryformatversion')) == '0'
         and values.get(('core', 'bare')) == 'false'
         and values.get(('remote "origin"', 'url')) in ALLOWED['remote "origin"']['url'], 'config-values-7')
    return values


def stable_bytes(path, uid, gid, maximum, deadline):
    clock(deadline)
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_uid == uid and before.st_gid == gid
         and before.st_nlink == 1 and not before.st_mode & 0o022
         and before.st_size <= maximum, 'stable-bytes-1')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    # This function remains the sole descriptor owner; no wrapper transfer.
    try:
        need(identity(os.fstat(descriptor)) == identity(before), 'stable-bytes-2')
        content = bytearray()
        while True:
            clock(deadline)
            chunk = os.read(descriptor, min(4096, maximum + 1 - len(content)))
            if not chunk:
                break
            need(len(content) + len(chunk) <= maximum, 'stable-bytes-3')
            content.extend(chunk)
        need(len(content) == before.st_size, 'stable-bytes-4')
        need(identity(os.fstat(descriptor)) == identity(before), 'stable-bytes-5')
        raw = bytes(content)
    finally:
        # Attempt once. A failed close refuses and is never retried as proof.
        try:
            os.close(descriptor)
        except BaseException:
            error = ConfigRefusal('cft-git-config-close-unproved')
            error.fixed_refusal_code = 'raw-close-unproved'
            raise error from None
    need(identity(path.lstat()) == identity(before), 'stable-bytes-6')
    result = (raw, identity(before))
    clock(deadline)
    return result


def absent(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return
    error = ConfigRefusal('cft-git-config-refused')
    error.fixed_refusal_code = 'required-absent'
    raise error


def snapshot(repo, uid, gid, deadline):
    """Record current finite config and every attribute-file location.

    Only ordinary same-owner checkout nodes are accepted. The future bootstrap
    must verify account/runtime/source custody separately and compare this entire
    result before and after Git. This is not an atomic lock or hostile-user proof.
    """
    need(type(uid) is int and type(gid) is int and uid > 0 and gid > 0, 'snapshot-1')
    need(type(deadline) in (int, float) and deadline == deadline
         and deadline not in (float('inf'), float('-inf')), 'snapshot-2')
    repo = Path(repo)
    need(repo.is_absolute() and '..' not in repo.parts, 'snapshot-3')
    clock(deadline)
    root = repo.lstat()
    need(stat.S_ISDIR(root.st_mode) and root.st_uid == uid and root.st_gid == gid
         and not root.st_mode & 0o022, 'snapshot-4')
    git_dir = repo / '.git'
    git_info = git_dir.lstat()
    need(stat.S_ISDIR(git_info.st_mode) and git_info.st_uid == uid and git_info.st_gid == gid
         and not git_info.st_mode & 0o022, 'snapshot-5')
    # Reject worktree indirection and per-worktree config before any Git read.
    for name in ('commondir', 'config.worktree'):
        absent(git_dir / name)
    info_dir = git_dir / 'info'
    info = info_dir.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == uid and info.st_gid == gid
         and not info.st_mode & 0o022, 'snapshot-6')
    absent(info_dir / 'attributes')
    config_raw, config_identity = stable_bytes(git_dir / 'config', uid, gid, MAX_CONFIG, deadline)
    config_values(config_raw)
    attrs_raw, attrs_identity = stable_bytes(repo / '.gitattributes', uid, gid, 4096, deadline)
    # Exact finite grammar only. Raw bytes are retained in the snapshot hash;
    # LF/CRLF layout is never normalized for a source or workflow pin.
    safe_lf = ('\n'.join(ATTRIBUTES) + '\n').encode('ascii')
    safe_crlf = ('\r\n'.join(ATTRIBUTES) + '\r\n').encode('ascii')
    need(attrs_raw in (safe_lf, safe_crlf), 'snapshot-7')
    rows = []
    pending = [(repo, 0)]
    nodes = 0
    while pending:
        directory, depth = pending.pop()
        need(depth <= MAX_DEPTH, 'snapshot-8')
        clock(deadline)
        with os.scandir(directory) as entries:
            for entry in entries:
                nodes += 1
                need(nodes <= MAX_NODES, 'snapshot-9')
                clock(deadline)
                path = Path(entry.path)
                if path == git_dir:
                    continue
                observed = entry.stat(follow_symlinks=False)
                need(observed.st_uid == uid and observed.st_gid == gid
                     and not observed.st_mode & 0o022, 'snapshot-10')
                if entry.name == '.gitattributes':
                    need(path == repo / '.gitattributes' and identity(observed) == attrs_identity, 'snapshot-11')
                need(stat.S_ISREG(observed.st_mode) or stat.S_ISDIR(observed.st_mode), 'snapshot-12')
                need(not stat.S_ISREG(observed.st_mode) or observed.st_nlink == 1, 'snapshot-13')
                rows.append((path.relative_to(repo).as_posix(), identity(observed)))
                if stat.S_ISDIR(observed.st_mode):
                    pending.append((path, depth + 1))
    need(identity(repo.lstat()) == identity(root)
         and identity(git_dir.lstat()) == identity(git_info)
         and identity(info_dir.lstat()) == identity(info), 'snapshot-14')
    absent(info_dir / 'attributes')
    for name in ('commondir', 'config.worktree'):
        absent(git_dir / name)
    need(stable_bytes(git_dir / 'config', uid, gid, MAX_CONFIG, deadline)
         == (config_raw, config_identity), 'snapshot-15')
    need(stable_bytes(repo / '.gitattributes', uid, gid, 4096, deadline)
         == (attrs_raw, attrs_identity), 'snapshot-16')
    result = {'config_sha256': hashlib.sha256(config_raw).hexdigest(),
              'attributes_sha256': hashlib.sha256(attrs_raw).hexdigest(),
              'config_identity': config_identity, 'attributes_identity': attrs_identity,
              'root_identity': identity(root), 'git_identity': identity(git_info),
              'info_identity': identity(info), 'nodes': sorted(rows)}
    clock(deadline)
    return result
