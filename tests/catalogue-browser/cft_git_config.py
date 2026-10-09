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


class ConfigRefusal(ValueError):
    pass


def need(value):
    if not value:
        raise ConfigRefusal('cft-git-config-refused')


def clock(deadline):
    need(time.monotonic() < deadline)


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def config_values(raw):
    """Accept a literal checkout subset, without interpreting Git syntax.

    Includes, extensions, filters, external commands, credentials, quote/escape
    syntax, continuations and duplicate keys/sections are refused by construction.
    This deliberately refuses valid Git configs outside this exact subset.
    """
    need(type(raw) is bytes and len(raw) <= MAX_CONFIG and b'\x00' not in raw)
    try:
        text = raw.decode('ascii')
    except UnicodeDecodeError:
        raise ConfigRefusal('cft-git-config-refused') from None
    need('\r' not in text and '\\' not in text)
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
            need(section in ALLOWED and section not in sections)
            sections.add(section)
            continue
        match = re.fullmatch(r'([a-z]+)\s*=\s*([^\r\n]+)', line)
        need(section is not None and match is not None)
        key, value = match.groups()
        value = value.strip(' \t')
        need(key in ALLOWED[section] and value in ALLOWED[section][key])
        pair = (section, key)
        need(pair not in values)
        values[pair] = value
    need(values.get(('core', 'repositoryformatversion')) == '0'
         and values.get(('core', 'bare')) == 'false'
         and values.get(('remote "origin"', 'url')) in ALLOWED['remote "origin"']['url'])
    return values


def stable_bytes(path, uid, gid, maximum, deadline):
    clock(deadline)
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_uid == uid and before.st_gid == gid
         and before.st_nlink == 1 and not before.st_mode & 0o022
         and before.st_size <= maximum)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    # This function remains the sole descriptor owner; no wrapper transfer.
    try:
        need(identity(os.fstat(descriptor)) == identity(before))
        content = bytearray()
        while True:
            clock(deadline)
            chunk = os.read(descriptor, min(4096, maximum + 1 - len(content)))
            if not chunk:
                break
            need(len(content) + len(chunk) <= maximum)
            content.extend(chunk)
        need(len(content) == before.st_size)
        need(identity(os.fstat(descriptor)) == identity(before))
        raw = bytes(content)
    finally:
        # Attempt once. A failed close refuses and is never retried as proof.
        try:
            os.close(descriptor)
        except BaseException:
            raise ConfigRefusal('cft-git-config-close-unproved') from None
    need(identity(path.lstat()) == identity(before))
    result = (raw, identity(before))
    clock(deadline)
    return result


def absent(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise ConfigRefusal('cft-git-config-refused')


def snapshot(repo, uid, gid, deadline):
    """Record current finite config and every attribute-file location.

    Only ordinary same-owner checkout nodes are accepted. The future bootstrap
    must verify account/runtime/source custody separately and compare this entire
    result before and after Git. This is not an atomic lock or hostile-user proof.
    """
    need(type(uid) is int and type(gid) is int and uid > 0 and gid > 0)
    need(type(deadline) in (int, float) and deadline == deadline
         and deadline not in (float('inf'), float('-inf')))
    repo = Path(repo)
    need(repo.is_absolute() and '..' not in repo.parts)
    clock(deadline)
    root = repo.lstat()
    need(stat.S_ISDIR(root.st_mode) and root.st_uid == uid and root.st_gid == gid
         and not root.st_mode & 0o022)
    git_dir = repo / '.git'
    git_info = git_dir.lstat()
    need(stat.S_ISDIR(git_info.st_mode) and git_info.st_uid == uid and git_info.st_gid == gid
         and not git_info.st_mode & 0o022)
    # Reject worktree indirection and per-worktree config before any Git read.
    for name in ('commondir', 'config.worktree'):
        absent(git_dir / name)
    info_dir = git_dir / 'info'
    info = info_dir.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == uid and info.st_gid == gid
         and not info.st_mode & 0o022)
    absent(info_dir / 'attributes')
    config_raw, config_identity = stable_bytes(git_dir / 'config', uid, gid, MAX_CONFIG, deadline)
    config_values(config_raw)
    attrs_raw, attrs_identity = stable_bytes(repo / '.gitattributes', uid, gid, 4096, deadline)
    # Exact finite grammar only. Raw bytes are retained in the snapshot hash;
    # LF/CRLF layout is never normalized for a source or workflow pin.
    safe_lf = ('\n'.join(ATTRIBUTES) + '\n').encode('ascii')
    safe_crlf = ('\r\n'.join(ATTRIBUTES) + '\r\n').encode('ascii')
    need(attrs_raw in (safe_lf, safe_crlf))
    rows = []
    pending = [(repo, 0)]
    nodes = 0
    while pending:
        directory, depth = pending.pop()
        need(depth <= MAX_DEPTH)
        clock(deadline)
        with os.scandir(directory) as entries:
            for entry in entries:
                nodes += 1
                need(nodes <= MAX_NODES)
                clock(deadline)
                path = Path(entry.path)
                if path == git_dir:
                    continue
                observed = entry.stat(follow_symlinks=False)
                need(observed.st_uid == uid and observed.st_gid == gid
                     and not observed.st_mode & 0o022)
                if entry.name == '.gitattributes':
                    need(path == repo / '.gitattributes' and identity(observed) == attrs_identity)
                need(stat.S_ISREG(observed.st_mode) or stat.S_ISDIR(observed.st_mode))
                need(not stat.S_ISREG(observed.st_mode) or observed.st_nlink == 1)
                rows.append((path.relative_to(repo).as_posix(), identity(observed)))
                if stat.S_ISDIR(observed.st_mode):
                    pending.append((path, depth + 1))
    need(identity(repo.lstat()) == identity(root)
         and identity(git_dir.lstat()) == identity(git_info)
         and identity(info_dir.lstat()) == identity(info))
    absent(info_dir / 'attributes')
    for name in ('commondir', 'config.worktree'):
        absent(git_dir / name)
    need(stable_bytes(git_dir / 'config', uid, gid, MAX_CONFIG, deadline)
         == (config_raw, config_identity))
    need(stable_bytes(repo / '.gitattributes', uid, gid, 4096, deadline)
         == (attrs_raw, attrs_identity))
    result = {'config_sha256': hashlib.sha256(config_raw).hexdigest(),
              'attributes_sha256': hashlib.sha256(attrs_raw).hexdigest(),
              'config_identity': config_identity, 'attributes_identity': attrs_identity,
              'root_identity': identity(root), 'git_identity': identity(git_info),
              'info_identity': identity(info), 'nodes': sorted(rows)}
    clock(deadline)
    return result
