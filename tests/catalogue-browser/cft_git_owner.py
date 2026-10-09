"""Bounded Git observations for a future reviewed disposable-host root bootstrap.

Only fixed local Git reads run, as a previously verified nonzero runner UID/GID.
This module has no import-time host operation and grants no provisioning authority.
"""
import math
import os
import re
import select
import signal
import subprocess
import time
from pathlib import Path

from cft_git_config import snapshot

MAX_OUTPUT = 65536
WORKFLOW = '.github/workflows/chrome-for-testing-provisioning.yml'


class GitObservationRefusal(ValueError):
    pass


def require(value):
    if not value:
        raise GitObservationRefusal('cft-git-observation-refused')


def identity(pid):
    fields = Path('/proc', str(pid), 'stat').read_text(encoding='ascii').rsplit(') ', 1)[1].split()
    return {'pid': pid, 'group': int(fields[2]), 'session': int(fields[3]), 'start': int(fields[19])}


def members(group):
    result = []
    for path in Path('/proc').iterdir():
        if path.name.isdecimal():
            try:
                observed = identity(int(path.name))
            except (FileNotFoundError, ProcessLookupError):
                continue
            if observed['group'] == group:
                result.append(observed)
                require(len(result) <= 256)
    return result


def checked_argv(argv):
    require(type(argv) is list and all(type(value) is str for value in argv))
    require(argv[:3] == ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null'])
    tail = argv[3:]
    accepted = tail in (['rev-parse', 'HEAD'], ['rev-parse', 'HEAD^{tree}'],
        ['diff', '--no-ext-diff', '--exit-code', 'HEAD'])
    if len(tail) == 2 and tail[0] == 'show':
        accepted = re.fullmatch(r'[0-9a-f]{40}:' + re.escape(WORKFLOW), tail[1]) is not None
    require(accepted)
    if tail[0] == 'diff':
        tail = [tail[0], '--no-textconv', *tail[1:]]
    # Suppress mutable configuration behaviors for these read-only observations.
    return ['/usr/bin/git', '--no-pager', '--no-optional-locks', '-c', 'core.hooksPath=/dev/null',
        '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
        '-c', 'core.pager=cat', '-c', 'core.attributesFile=/dev/null', *tail]


def git_env():
    return {'HOME': '/nonexistent', 'XDG_CONFIG_HOME': '/nonexistent', 'PATH': '/usr/bin:/bin',
        'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'GIT_CONFIG_NOSYSTEM': '1',
        'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0',
        'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0', 'GIT_ATTR_NOSYSTEM': '1'}


class RunnerGit:
    """Retain one direct child and two pipes; drain synchronously, without threads.

    Group observations are bounded snapshots, not complete descendant proof.
    Failure retains uncertainty for disposable-host destruction; it never passes.
    """
    def __init__(self, registry, argv, repo, deadline, *, uid, gid):
        require(type(registry) is list)
        require(os.getuid() == os.geteuid() == 0)
        require(type(uid) is int and type(gid) is int and uid > 0 and gid > 0)
        require(type(deadline) in (int, float) and math.isfinite(deadline))
        require(time.monotonic() < deadline)
        self.deadline = deadline
        self.identity = None
        self.reaped = False
        self.finished = False
        self.failed = False
        self.forced_cleanup = False
        self.close_attempted = set()
        self.closed_pipes = set()
        command = checked_argv(argv)
        self.repo, self.uid, self.gid = repo, uid, gid
        self.config_before = snapshot(repo, uid, gid, deadline)
        self.process = subprocess.Popen(command, cwd=repo, env=git_env(),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            close_fds=True, start_new_session=True, user=uid, group=gid, extra_groups=[])
        # Retain the returned child before proc, descriptor or pipe observations.
        registry.append(self)
        candidate = identity(self.process.pid)
        require(candidate['pid'] == candidate['group'] == candidate['session'] == self.process.pid
            and candidate['start'] > 0)
        self.identity = candidate

    def remaining(self, maximum):
        result = self.deadline - time.monotonic()
        require(result > 0)
        return min(result, maximum)

    def close_pipes(self):
        first = None
        for number, stream in enumerate((self.process.stdout, self.process.stderr)):
            if number in self.close_attempted:
                continue
            self.close_attempted.add(number)
            try:
                stream.close()
                require(stream.closed is True)
                self.closed_pipes.add(number)
            except BaseException as error:
                self.failed = True
                if first is None:
                    first = error
        if first is not None:
            raise first

    def finish(self):
        try:
            stdout = self.process.stdout.fileno()
            stderr = self.process.stderr.fileno()
            require(stdout != stderr)
            output = {stdout: bytearray(), stderr: bytearray()}
            active = set(output)
            while active:
                ready, _, _ = select.select(list(active), [], [], self.remaining(0.1))
                for descriptor in ready:
                    chunk = os.read(descriptor, 4096)
                    if not chunk:
                        active.remove(descriptor)
                    else:
                        require(len(output[descriptor]) + len(chunk) <= MAX_OUTPUT)
                        output[descriptor].extend(chunk)
            result = self.process.wait(timeout=self.remaining(2))
            self.reaped = True
            require(result == 0 and self.identity is not None and members(self.identity['group']) == [])
        except BaseException:
            self.failed = True
            raise
        finally:
            self.close_pipes()
        try:
            result_bytes = bytes(output[stdout])
            require(snapshot(self.repo, self.uid, self.gid, self.deadline) == self.config_before)
            self.remaining(1)
            require(not self.failed and not self.forced_cleanup and self.closed_pipes == {0, 1})
        except BaseException:
            self.failed = True
            raise
        self.finished = True
        return result_bytes

    def signal_owned(self, requested):
        # Never signal a group after the direct leader was reaped or lost birth binding.
        require(not self.reaped and self.process.poll() is None)
        if self.identity is None:
            if requested == signal.SIGTERM:
                self.process.terminate()
            else:
                self.process.kill()
        else:
            require(identity(self.process.pid) == self.identity)
            os.killpg(self.identity['group'], requested)

    def refuse_cleanup(self):
        self.forced_cleanup = True
        self.failed = True
        first = None
        def attempt(operation):
            nonlocal first
            try:
                operation()
            except BaseException as error:
                if first is None:
                    first = error
        def reap(timeout):
            self.process.wait(timeout=timeout)
            self.reaped = True
        if not self.reaped:
            attempt(lambda: self.signal_owned(signal.SIGTERM))
            attempt(lambda: reap(2))
            if not self.reaped:
                attempt(lambda: self.signal_owned(signal.SIGKILL))
                attempt(lambda: reap(2))
        attempt(self.close_pipes)
        if first is not None:
            raise first

    def cleanup_observed(self):
        return (self.reaped and self.identity is not None and self.closed_pipes == {0, 1}
            and members(self.identity['group']) == [])
