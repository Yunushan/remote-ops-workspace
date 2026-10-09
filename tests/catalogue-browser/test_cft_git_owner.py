"""Fault-case source for future hosted verification; never run locally."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


class FakePipe:
    def __init__(self, descriptor, *, close_error=False, fileno_error=False):
        self.descriptor = descriptor
        self.close_error = close_error
        self.fileno_error = fileno_error
        self.closed = False
        self.close_calls = 0

    def fileno(self):
        if self.fileno_error:
            raise ValueError('mock-fileno-refusal')
        return self.descriptor

    def close(self):
        self.close_calls += 1
        if self.close_error:
            raise OSError('mock-close-refusal')
        self.closed = True


class FakeProcess:
    def __init__(self):
        self.pid = 123
        self.stdout = FakePipe(10)
        self.stderr = FakePipe(11)
        self.wait_calls = 0
        self.terminate_calls = 0

    def poll(self):
        return None

    def terminate(self):
        self.terminate_calls += 1

    def wait(self, timeout):
        self.wait_calls += 1
        return 0


@unittest.skipUnless(os.name == 'posix', 'POSIX runner UID/GID fault-case source')
class RunnerGitFaultCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name('cft_git_owner.py')
        spec = importlib.util.spec_from_file_location('reviewed_cft_git_owner', path)
        dependency_spec = importlib.util.spec_from_file_location('cft_git_config',
            path.with_name('cft_git_config.py'))
        dependency = importlib.util.module_from_spec(dependency_spec)
        dependency_spec.loader.exec_module(dependency)
        cls.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'cft_git_config': dependency}):
            spec.loader.exec_module(cls.module)

    def setUp(self):
        guard = patch.object(self.module, 'snapshot', return_value={'synthetic': 'stable'})
        self.snapshots = guard.start()
        self.addCleanup(guard.stop)

    def make_owner(self, registry, process, *, birth_error=False, identity_override=None):
        module = self.module
        observed = {'pid': 123, 'group': 123, 'session': 123, 'start': 1}
        if identity_override is not None:
            observed = identity_override
        with (
            patch.object(module.os, 'getuid', return_value=0),
            patch.object(module.os, 'geteuid', return_value=0),
            patch.object(module.time, 'monotonic', return_value=1),
            patch.object(module.subprocess, 'Popen', return_value=process),
            patch.object(module, 'identity', side_effect=ValueError('birth-refusal')
                if birth_error else lambda pid: observed),
        ):
            return module.RunnerGit(registry, ['/usr/bin/git', '-c',
                'core.hooksPath=/dev/null', 'rev-parse', 'HEAD'], '/mock-repo', 100,
                uid=1001, gid=1001)

    def test_close_failure_attempts_other_pipe_but_cannot_claim_closure(self):
        for failed_pipe in (0, 1):
            with self.subTest(failed_pipe=failed_pipe):
                registry = []
                process = FakeProcess()
                pipes = (process.stdout, process.stderr)
                pipes[failed_pipe].close_error = True
                owner = self.make_owner(registry, process)
                owner.reaped = True
                with self.assertRaises(OSError):
                    owner.close_pipes()
                self.assertIs(registry[0], owner)
                self.assertEqual([pipe.close_calls for pipe in pipes], [1, 1])
                self.assertEqual(owner.closed_pipes, {1 - failed_pipe})
                self.assertTrue(owner.failed)
                with patch.object(self.module, 'members', return_value=[]):
                    self.assertFalse(owner.cleanup_observed())
                owner.close_pipes()
                self.assertEqual([pipe.close_calls for pipe in pipes], [1, 1])

    def test_fileno_failure_retains_child_and_closes_both_pipes(self):
        for failed_pipe in (0, 1):
            with self.subTest(failed_pipe=failed_pipe):
                registry = []
                process = FakeProcess()
                pipes = (process.stdout, process.stderr)
                pipes[failed_pipe].fileno_error = True
                owner = self.make_owner(registry, process)
                with self.assertRaises(ValueError):
                    owner.finish()
                self.assertIs(registry[0], owner)
                self.assertEqual([pipe.close_calls for pipe in pipes], [1, 1])
                self.assertEqual(process.wait_calls, 0)
                self.assertTrue(owner.failed)
                self.assertFalse(owner.finished)
                self.assertFalse(owner.reaped)

    def test_birth_observation_failure_keeps_returned_child_registered(self):
        registry = []
        process = FakeProcess()
        with self.assertRaises(ValueError):
            self.make_owner(registry, process, birth_error=True)
        self.assertEqual(len(registry), 1)
        self.assertIs(registry[0].process, process)
        self.assertIsNone(registry[0].identity)
        self.assertFalse(registry[0].finished)

    def test_clock_expiry_after_wait_and_pipe_close_cannot_complete(self):
        registry = []
        process = FakeProcess()
        owner = self.make_owner(registry, process)
        with (
            patch.object(self.module.time, 'monotonic', side_effect=[1, 1, 101]),
            patch.object(self.module.select, 'select', return_value=([10, 11], [], [])),
            patch.object(self.module.os, 'read', return_value=b''),
            patch.object(self.module, 'members', return_value=[]),
        ):
            with self.assertRaises(self.module.GitObservationRefusal):
                owner.finish()
        self.assertEqual(process.wait_calls, 1)
        self.assertEqual(owner.closed_pipes, {0, 1})
        self.assertTrue(owner.reaped)
        self.assertTrue(owner.failed)
        self.assertFalse(owner.finished)

    def test_non_list_registry_refuses_before_child_birth(self):
        with patch.object(self.module.subprocess, 'Popen') as birth:
            with self.assertRaises(self.module.GitObservationRefusal):
                self.module.RunnerGit((), ['/usr/bin/git', '-c',
                    'core.hooksPath=/dev/null', 'rev-parse', 'HEAD'], '/mock-repo', 100,
                    uid=1001, gid=1001)
            birth.assert_not_called()

    def test_mismatched_birth_cannot_authorize_group_signalling(self):
        for refused in (
            {'pid': 123, 'group': 999, 'session': 123, 'start': 1},
            {'pid': 123, 'group': 123, 'session': 999, 'start': 1},
        ):
            with self.subTest(refused=refused):
                registry = []
                process = FakeProcess()
                with self.assertRaises(self.module.GitObservationRefusal):
                    self.make_owner(registry, process, identity_override=refused)
                self.assertEqual(len(registry), 1)
                self.assertIsNone(registry[0].identity)
                with patch.object(self.module.os, 'killpg') as group_signal:
                    registry[0].signal_owned(self.module.signal.SIGTERM)
                group_signal.assert_not_called()
                self.assertEqual(process.terminate_calls, 1)

    def test_result_conversion_expiry_cannot_complete(self):
        registry = []
        process = FakeProcess()
        owner = self.make_owner(registry, process)
        clock = [1]

        def convert(value):
            clock[0] = 101
            return bytes(value)

        with (
            patch.object(self.module.time, 'monotonic', side_effect=lambda: clock[0]),
            patch.object(self.module.select, 'select', return_value=([10, 11], [], [])),
            patch.object(self.module.os, 'read', return_value=b''),
            patch.object(self.module, 'members', return_value=[]),
            patch.object(self.module, 'bytes', side_effect=convert, create=True) as conversion,
        ):
            with self.assertRaises(self.module.GitObservationRefusal):
                owner.finish()
        conversion.assert_called_once()
        self.assertEqual(owner.closed_pipes, {0, 1})
        self.assertTrue(owner.reaped)
        self.assertTrue(owner.failed)
        self.assertFalse(owner.finished)

    def test_nonfinite_deadline_refuses_before_child_birth(self):
        for deadline in (float('inf'), float('-inf'), float('nan')):
            with (
                self.subTest(deadline=deadline),
                patch.object(self.module.os, 'getuid', return_value=0),
                patch.object(self.module.os, 'geteuid', return_value=0),
                patch.object(self.module.subprocess, 'Popen') as birth,
            ):
                with self.assertRaises(self.module.GitObservationRefusal):
                    self.module.RunnerGit([], ['/usr/bin/git', '-c',
                        'core.hooksPath=/dev/null', 'rev-parse', 'HEAD'], '/mock-repo',
                        deadline, uid=1001, gid=1001)
                birth.assert_not_called()

    def test_result_conversion_error_cannot_mark_completion(self):
        registry = []
        process = FakeProcess()
        owner = self.make_owner(registry, process)
        with (
            patch.object(self.module.time, 'monotonic', return_value=1),
            patch.object(self.module.select, 'select', return_value=([10, 11], [], [])),
            patch.object(self.module.os, 'read', return_value=b''),
            patch.object(self.module, 'members', return_value=[]),
            patch.object(self.module, 'bytes', side_effect=MemoryError, create=True),
        ):
            with self.assertRaises(MemoryError):
                owner.finish()
        self.assertEqual(owner.closed_pipes, {0, 1})
        self.assertTrue(owner.reaped)
        self.assertTrue(owner.failed)
        self.assertFalse(owner.finished)

    def test_all_fixed_commands_suppress_pagers_and_system_attributes(self):
        prefix = ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null']
        for tail in (['rev-parse', 'HEAD'], ['rev-parse', 'HEAD^{tree}'],
                     ['diff', '--no-ext-diff', '--exit-code', 'HEAD'],
                     ['show', 'a' * 40 + ':' + self.module.WORKFLOW]):
            with self.subTest(tail=tail):
                result = self.module.checked_argv(prefix + tail)
                self.assertEqual(result[:10], ['/usr/bin/git', '--no-pager',
                    '--no-optional-locks', '-c', 'core.hooksPath=/dev/null',
                    '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false', '-c'])
                self.assertEqual(result[10:13], ['core.pager=cat', '-c',
                    'core.attributesFile=/dev/null'])
                expected_tail = ['diff', '--no-textconv', *tail[1:]] if tail[0] == 'diff' else tail
                self.assertEqual(result[13:], expected_tail)
        self.assertEqual(self.module.git_env()['GIT_ATTR_NOSYSTEM'], '1')
        self.assertEqual(set(self.module.git_env()), {'HOME', 'XDG_CONFIG_HOME', 'PATH',
            'LANG', 'LC_ALL', 'GIT_CONFIG_NOSYSTEM', 'GIT_CONFIG_GLOBAL',
            'GIT_TERMINAL_PROMPT', 'GIT_NO_LAZY_FETCH', 'GIT_OPTIONAL_LOCKS',
            'GIT_ATTR_NOSYSTEM'})

    def test_preflight_refusal_does_not_birth_or_register_child(self):
        registry = []
        refusal = ValueError('synthetic config refusal')
        self.snapshots.side_effect = refusal
        with (
            patch.object(self.module.os, 'getuid', return_value=0),
            patch.object(self.module.os, 'geteuid', return_value=0),
            patch.object(self.module.time, 'monotonic', return_value=1),
            patch.object(self.module.subprocess, 'Popen') as birth,
        ):
            with self.assertRaises(ValueError) as observed:
                self.module.RunnerGit(registry, ['/usr/bin/git', '-c',
                    'core.hooksPath=/dev/null', 'rev-parse', 'HEAD'], '/mock-repo', 100,
                    uid=1001, gid=1001)
        self.assertIs(observed.exception, refusal)
        self.assertEqual(registry, [])
        birth.assert_not_called()
        self.snapshots.assert_called_once_with('/mock-repo', 1001, 1001, 100)

    def test_preflight_precedes_birth(self):
        order = []
        process = FakeProcess()
        registry = []
        self.snapshots.side_effect = lambda *args: order.append('snapshot') or {'synthetic': 'stable'}
        with (
            patch.object(self.module.os, 'getuid', return_value=0),
            patch.object(self.module.os, 'geteuid', return_value=0),
            patch.object(self.module.time, 'monotonic', return_value=1),
            patch.object(self.module.subprocess, 'Popen',
                side_effect=lambda *args, **kwargs: order.append('birth') or process),
            patch.object(self.module, 'identity', return_value={
                'pid': 123, 'group': 123, 'session': 123, 'start': 1}),
        ):
            owner = self.module.RunnerGit(registry, ['/usr/bin/git', '-c',
                'core.hooksPath=/dev/null', 'rev-parse', 'HEAD'], '/mock-repo', 100,
                uid=1001, gid=1001)
        self.assertEqual(order, ['snapshot', 'birth'])
        self.assertIs(registry[0], owner)
        self.assertEqual(owner.config_before, {'synthetic': 'stable'})

    def test_postflight_change_or_error_refuses_after_child_cleanup(self):
        for case in ('change', 'error'):
            with self.subTest(case=case):
                process = FakeProcess()
                registry = []
                self.snapshots.side_effect = None
                self.snapshots.return_value = {'synthetic': 'before'}
                owner = self.make_owner(registry, process)
                refusal = OSError('synthetic postflight refusal')
                self.snapshots.side_effect = refusal if case == 'error' else None
                self.snapshots.return_value = {'synthetic': 'after'}
                with (
                    patch.object(self.module.time, 'monotonic', return_value=1),
                    patch.object(self.module.select, 'select', return_value=([10, 11], [], [])),
                    patch.object(self.module.os, 'read', return_value=b''),
                    patch.object(self.module, 'members', return_value=[]),
                ):
                    expected = OSError if case == 'error' else self.module.GitObservationRefusal
                    with self.assertRaises(expected) as observed:
                        owner.finish()
                if case == 'error':
                    self.assertIs(observed.exception, refusal)
                self.assertTrue(owner.reaped)
                self.assertEqual(owner.closed_pipes, {0, 1})
                self.assertEqual([process.stdout.close_calls, process.stderr.close_calls], [1, 1])
                self.assertTrue(owner.failed)
                self.assertFalse(owner.finished)

    def test_postflight_expiry_latches_failure_before_completion(self):
        process = FakeProcess()
        owner = self.make_owner([], process)
        timer = [1]
        def snapshot_after(*args):
            self.assertTrue(owner.reaped)
            self.assertEqual(owner.closed_pipes, {0, 1})
            timer[0] = 101
            return {'synthetic': 'stable'}
        self.snapshots.side_effect = snapshot_after
        with (
            patch.object(self.module.time, 'monotonic', side_effect=lambda: timer[0]),
            patch.object(self.module.select, 'select', return_value=([10, 11], [], [])),
            patch.object(self.module.os, 'read', return_value=b''),
            patch.object(self.module, 'members', return_value=[]),
        ):
            with self.assertRaises(self.module.GitObservationRefusal):
                owner.finish()
        self.assertTrue(owner.failed)
        self.assertFalse(owner.finished)

    def test_success_observes_same_snapshot_after_pipe_close(self):
        process = FakeProcess()
        owner = self.make_owner([], process)
        def snapshot_after(*args):
            self.assertTrue(owner.reaped)
            self.assertEqual(owner.closed_pipes, {0, 1})
            self.assertFalse(owner.finished)
            return {'synthetic': 'stable'}
        self.snapshots.side_effect = snapshot_after
        with (
            patch.object(self.module.time, 'monotonic', return_value=1),
            patch.object(self.module.select, 'select', return_value=([10, 11], [], [])),
            patch.object(self.module.os, 'read', return_value=b''),
            patch.object(self.module, 'members', return_value=[]),
        ):
            self.assertEqual(owner.finish(), b'')
        self.assertEqual(self.snapshots.call_count, 2)
        self.assertFalse(owner.failed)
        self.assertTrue(owner.finished)
