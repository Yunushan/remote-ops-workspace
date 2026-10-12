"""Future hosted parser cases only; none are executed during local authoring."""
import importlib.util
import os
import stat
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

BASE = (b'[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n'
        b'\tbare = false\n\tlogallrefupdates = true\n'
        b'[remote "origin"]\n\turl = https://github.com/Yunushan/remote-ops-workspace\n'
        b'\tfetch = +refs/heads/*:refs/remotes/origin/*\n')


class ConfigParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('reviewed_cft_git_config',
            Path(__file__).with_name('cft_git_config.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_exact_checkout_config(self):
        result = self.module.config_values(BASE)
        self.assertEqual(result[('core', 'bare')], 'false')
        self.assertEqual(result[('remote "origin"', 'url')],
                         'https://github.com/Yunushan/remote-ops-workspace')
        self.assertEqual(len(result), 6)

    def test_optional_safe_checkout_values(self):
        raw = BASE.replace(b'\tfilemode = true\n',
                           b'\tfilemode = true\n\tignorecase = false\n\tautocrlf = false\n')
        raw += b'[branch "main"]\n\tremote = origin\n\tmerge = refs/heads/main\n'
        result = self.module.config_values(raw)
        self.assertEqual(len(result), 10)
        self.assertEqual(result[('branch "main"', 'merge')], 'refs/heads/main')

    def test_helper_and_credential_configuration_refused(self):
        extras = (
            b'[include]\n\tpath = /tmp/other-config\n',
            b'[includeIf "gitdir:*"]\n\tpath = /tmp/other-config\n',
            b'[filter "anything"]\n\tclean = unexpected-command\n',
            b'[core]\n\tfsmonitor = unexpected-command\n',
            b'[credential]\n\thelper = unexpected-command\n',
            b'[extensions]\n\tworktreeconfig = true\n',
            b'[http "https://github.com/"]\n\textraheader = AUTHORIZATION: anything\n',
            b'[diff "anything"]\n\ttextconv = unexpected-command\n',
            b'[pager]\n\tdiff = unexpected-command\n',
        )
        for extra in extras:
            with self.subTest(extra=extra):
                with self.assertRaises(self.module.ConfigRefusal):
                    self.module.config_values(BASE + extra)

    def test_syntax_and_identity_mutations_refused(self):
        mutated = (
            BASE + b'[core]\n\tbare = false\n',
            BASE.replace(b'\tbare = false\n', b'\tbare = false\n\tbare = false\n'),
            BASE.replace(b'\tbare = false', b'\tbare = true'),
            BASE.replace(b'repositoryformatversion = 0', b'repositoryformatversion = 1'),
            BASE.replace(b'https://github.com/Yunushan/remote-ops-workspace', b'file:///tmp/other'),
            BASE.replace(b'\tbare = false', b'\tbare = "false"'),
            BASE.replace(b'\tbare = false', b'\tbare = false # comment'),
            BASE.replace(b'\n', b'\r\n'),
            BASE + b'\x00',
            BASE + b'\xff',
            BASE + b'\tunknown = value\n',
            BASE.replace(b'\tbare = false', b'\tbare = fal\\\nse'),
        )
        for raw in mutated:
            with self.subTest(raw=raw):
                with self.assertRaises(self.module.ConfigRefusal):
                    self.module.config_values(raw)

    def test_input_bounds_and_type_refused(self):
        for raw in (BASE.decode('ascii'), bytearray(BASE), b' ' * 16385):
            with self.subTest(raw=type(raw)):
                with self.assertRaises(self.module.ConfigRefusal):
                    self.module.config_values(raw)

    def test_parser_refusal_attributes_identify_fixed_predicate_with_original_message(self):
        cases = ((BASE.decode(), 'config-values-1'), (b'\xff', 'config-encoding'),
            (BASE.replace(b'\n', b'\r\n'), 'config-values-2'),
            (BASE + b'[include]\n\tpath = /PRIVATE\n', 'config-values-3'),
            (BASE + b'not a key line\n', 'config-values-4'),
            (BASE.replace(b'bare = false', b'bare = true'), 'config-values-5'),
            (BASE.replace(b'bare = false', b'bare = false\n\tbare = false'), 'config-values-6'),
            (BASE.replace(b'\tbare = false\n', b''), 'config-values-7'))
        for raw, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(self.module.ConfigRefusal) as caught:
                    self.module.config_values(raw)
                self.assertEqual(caught.exception.args, ('cft-git-config-refused',))
                self.assertEqual(caught.exception.fixed_refusal_code, code)
                self.assertIn(code, self.module.CONFIG_REFUSAL_CODES)
                self.assertNotIn('PRIVATE', str(caught.exception))

    def test_every_declared_config_predicate_has_fixed_diagnostic_without_admission(self):
        for code in self.module.CONFIG_REFUSAL_CODES:
            if code in ('config-encoding', 'raw-close-unproved', 'required-absent'):
                continue
            with self.subTest(code=code):
                self.assertIsNone(self.module.need(True, code))
                with self.assertRaises(self.module.ConfigRefusal) as caught:
                    self.module.need(False, code)
                self.assertEqual(caught.exception.args, ('cft-git-config-refused',))
                self.assertEqual(caught.exception.fixed_refusal_code, code)

    def test_fixed_absence_codes_keep_missing_targets_accepted_without_other_IO(self):
        expected = {'commondir': 'required-absent-commondir',
                    'config.worktree': 'required-absent-worktree-config',
                    'info-attributes': 'required-absent-info-attributes'}
        self.assertEqual(self.module.ABSENCE_CODES, expected)
        for code in ('required-absent', *expected.values()):
            path = SimpleNamespace(lstat=mock.Mock(side_effect=FileNotFoundError('/PRIVATE')))
            with self.subTest(code=code), mock.patch.object(self.module.os, 'open') as opened, \
                 mock.patch.object(self.module.os, 'unlink') as deleted:
                if code == 'required-absent':
                    self.assertIsNone(self.module.absent(path))
                else:
                    self.assertIsNone(self.module.absent(path, code=code))
                path.lstat.assert_called_once_with()
                opened.assert_not_called()
                deleted.assert_not_called()

    def test_present_target_keeps_original_refusal_and_only_fixed_absence_code(self):
        for code in ('required-absent', *self.module.ABSENCE_CODES.values()):
            path = SimpleNamespace(lstat=mock.Mock(return_value=object()))
            with self.subTest(code=code), mock.patch.object(self.module.os, 'open') as opened, \
                 mock.patch.object(self.module.os, 'unlink') as deleted:
                with self.assertRaises(self.module.ConfigRefusal) as caught:
                    if code == 'required-absent':
                        self.module.absent(path)
                    else:
                        self.module.absent(path, code=code)
                self.assertEqual(caught.exception.args, ('cft-git-config-refused',))
                self.assertEqual(caught.exception.fixed_refusal_code, code)
                self.assertIn(code, self.module.CONFIG_REFUSAL_CODES)
                self.assertNotIn('PRIVATE', str(caught.exception))
                path.lstat.assert_called_once_with()
                opened.assert_not_called()
                deleted.assert_not_called()

    def test_access_error_identity_is_not_converted_to_target_presence(self):
        for code in ('required-absent', *self.module.ABSENCE_CODES.values()):
            original = PermissionError('/PRIVATE/access')
            path = SimpleNamespace(lstat=mock.Mock(side_effect=original))
            with self.subTest(code=code), mock.patch.object(self.module.os, 'open') as opened, \
                 mock.patch.object(self.module.os, 'unlink') as deleted:
                with self.assertRaises(PermissionError) as caught:
                    if code == 'required-absent':
                        self.module.absent(path)
                    else:
                        self.module.absent(path, code=code)
                self.assertIs(caught.exception, original)
                self.assertNotIn('fixed_refusal_code', original.__dict__)
                path.lstat.assert_called_once_with()
                opened.assert_not_called()
                deleted.assert_not_called()


@unittest.skipUnless(os.name == 'posix', 'Future POSIX raw descriptor fixture only')
class RawDescriptorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('reviewed_cft_git_config_raw',
            Path(__file__).with_name('cft_git_config.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_one_owner_read_and_fault_boundaries(self):
        info = SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o644,
            st_uid=3, st_gid=4, st_nlink=1, st_size=4, st_mtime_ns=5, st_ctime_ns=6)
        path = SimpleNamespace(lstat=lambda: info)
        for case in ('success', 'first-fstat', 'last-fstat', 'read', 'overflow',
                     'short', 'close', 'final-clock'):
            with self.subTest(case=case):
                fault = OSError('synthetic read or fstat refusal')
                fstats = [fault] if case == 'first-fstat' else [info, fault if case == 'last-fstat' else info]
                reads = [fault] if case == 'read' else [b'ab', b'cd', b'']
                if case == 'overflow':
                    reads = [b'abcde']
                if case == 'short':
                    reads = [b'ab', b'']
                clocks = [None] * 4 + [self.module.ConfigRefusal('synthetic expiry')] if case == 'final-clock' else None
                close_fault = OSError('synthetic close refusal') if case == 'close' else None
                with mock.patch.object(self.module, 'clock', side_effect=clocks), \
                     mock.patch.object(self.module.os, 'open', return_value=37) as opened, \
                     mock.patch.object(self.module.os, 'fstat', side_effect=fstats), \
                     mock.patch.object(self.module.os, 'read', side_effect=reads) as read, \
                     mock.patch.object(self.module.os, 'close', side_effect=close_fault) as closed, \
                     mock.patch.object(self.module.os, 'fdopen') as wrapped:
                    if case == 'success':
                        result = self.module.stable_bytes(path, 3, 4, 4, 10)
                        self.assertEqual(result[0], b'abcd')
                        self.assertEqual(result[1], (1, 2, stat.S_IFREG | 0o644, 3, 4, 1, 4, 5, 6))
                        self.assertEqual(read.call_args_list,
                            [mock.call(37, 5), mock.call(37, 3), mock.call(37, 1)])
                    else:
                        expected = OSError if case in ('first-fstat', 'last-fstat', 'read') else self.module.ConfigRefusal
                        with self.assertRaises(expected) as observed:
                            self.module.stable_bytes(path, 3, 4, 4, 10)
                        if case in ('first-fstat', 'last-fstat', 'read'):
                            self.assertIs(observed.exception, fault)
                        if case == 'close':
                            self.assertEqual(str(observed.exception), 'cft-git-config-close-unproved')
                    opened.assert_called_once_with(path, os.O_RDONLY | os.O_NOFOLLOW)
                    closed.assert_called_once_with(37)
                    wrapped.assert_not_called()


class InactiveWorktreeConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('reviewed_inactive_worktree_config',
            Path(__file__).with_name('cft_git_config.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_closed_sparse_false_literals_and_present_empty_are_harmless(self):
        cases = (
            (b'', {}),
            (b' \t\n\n', {}),
            (b'[core]\n', {}),
            (b'[core]\n\tsparseCheckout = false\n', {'sparsecheckout': 'false'}),
            (b'[core]\n SPARSECHECKOUTCONE\t=\tfalse\n sparseCheckout=false\n',
             {'sparsecheckoutcone': 'false', 'sparsecheckout': 'false'}),
        )
        for raw, expected in cases:
            with self.subTest(raw_size=len(raw)):
                self.assertEqual(self.module.inactive_worktree_config_values(raw), expected)

    def test_harmful_or_ambiguous_worktree_syntax_keeps_fixed_refusal(self):
        raw_cases = (
            '[core]\n', bytearray(b'[core]\n'), b' ' * 16385, b'\x00', b'\xff',
            b'[core]\r\n', b'[core]\n\tsparseCheckout = fal\\se\n',
            b'[core]\n\tsparseCheckout\v= false\n', b'[core]\n\tsparseCheckout = false\x1f\n',
            b'[core]\n\tsparseCheckout = false\x7f\n',
            b'[include]\n path = /PRIVATE\n',
            b'[includeIf "gitdir:*"]\n path = /PRIVATE\n',
            b'[extensions]\n worktreeConfig = true\n',
            b'[credential]\n helper = PRIVATE\n', b'[filter "PRIVATE"]\n clean = PRIVATE\n',
            b'[core "PRIVATE"]\n sparseCheckout = false\n', b'[Core]\n',
            b'[core]\n[core]\n', b'sparseCheckout = false\n',
            b'[core]\n sparseCheckout = false\n SPARSECHECKOUT = false\n',
            b'[core]\n sparseCheckout = true\n', b'[core]\n sparseCheckoutCone = 0\n',
            b'[core]\n sparseCheckout = "false"\n',
            b'[core]\n sparseCheckout = false # PRIVATE\n', b'# PRIVATE\n',
            b'[core]\n bare = false\n', b'[core]\n fsmonitor = PRIVATE\n',
        )
        for index, raw in enumerate(raw_cases):
            with self.subTest(index=index):
                with self.assertRaises(self.module.ConfigRefusal) as caught:
                    self.module.inactive_worktree_config_values(raw)
                self.assertEqual(caught.exception.args, ('cft-git-config-refused',))
                self.assertIn(caught.exception.fixed_refusal_code, self.module.CONFIG_REFUSAL_CODES)
                self.assertNotIn('PRIVATE', str(caught.exception))

    def test_absent_and_access_refusal_never_read_or_mutate(self):
        for error_type in (FileNotFoundError, PermissionError):
            original = error_type('/PRIVATE')
            path = SimpleNamespace(lstat=mock.Mock(side_effect=original))
            with self.subTest(error=error_type.__name__), \
                 mock.patch.object(self.module, 'clock'), \
                 mock.patch.object(self.module, 'stable_bytes') as read, \
                 mock.patch.object(self.module.os, 'unlink') as deleted, \
                 mock.patch.object(self.module.os, 'chmod') as changed:
                if error_type is FileNotFoundError:
                    self.assertEqual(self.module.optional_worktree_config(path, 3, 4, 10), (None, None))
                else:
                    with self.assertRaises(PermissionError) as caught:
                        self.module.optional_worktree_config(path, 3, 4, 10)
                    self.assertIs(caught.exception, original)
                path.lstat.assert_called_once_with()
                read.assert_not_called()
                deleted.assert_not_called()
                changed.assert_not_called()

    def test_present_reader_validates_closed_grammar_before_return(self):
        identity = (1, 8, stat.S_IFREG | 0o644, 3, 4, 1, 0, 5, 6)
        for raw in (b'', b'[core]\n sparseCheckout = false\n', b'[include]\n path = /PRIVATE\n'):
            path = SimpleNamespace(lstat=mock.Mock(return_value=object()))
            with self.subTest(size=len(raw)), mock.patch.object(self.module, 'clock'), \
                 mock.patch.object(self.module, 'stable_bytes', return_value=(raw, identity)) as read:
                if b'PRIVATE' in raw:
                    with self.assertRaises(self.module.ConfigRefusal) as caught:
                        self.module.optional_worktree_config(path, 3, 4, 10)
                    self.assertEqual(caught.exception.fixed_refusal_code, 'worktree-values-3')
                else:
                    self.assertEqual(self.module.optional_worktree_config(path, 3, 4, 10), (raw, identity))
                read.assert_called_once_with(path, 3, 4, self.module.MAX_CONFIG, 10)

    def snapshot_fixture(self, common=BASE):
        directory = SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFDIR | 0o755,
            st_uid=3, st_gid=4, st_nlink=2, st_size=0, st_mtime_ns=5, st_ctime_ns=6)
        config = SimpleNamespace(**{**directory.__dict__, 'st_ino': 3,
            'st_mode': stat.S_IFREG | 0o644, 'st_nlink': 1, 'st_size': len(common)})
        attributes = ('\n'.join(self.module.ATTRIBUTES) + '\n').encode('ascii')
        attrs = SimpleNamespace(**{**config.__dict__, 'st_ino': 4, 'st_size': len(attributes)})
        ordinary = SimpleNamespace(**{**config.__dict__, 'st_ino': 5, 'st_size': 1})
        states = {'/fixture/checkout': directory, '/fixture/checkout/.git': directory,
            '/fixture/checkout/.git/info': directory, '/fixture/checkout/.git/config': config,
            '/fixture/checkout/.gitattributes': attrs, '/fixture/checkout/source.py': ordinary}
        nodes = {}

        class Node:
            def __init__(self, name):
                self.value = name
                self.parts = tuple(name.split('/'))

            def is_absolute(self):
                return self.value.startswith('/')

            def __truediv__(self, name):
                return path(self.value + '/' + name)

            def lstat(self):
                if self.value not in states:
                    raise FileNotFoundError('/PRIVATE')
                return states[self.value]

            def relative_to(self, root):
                relative = self.value[len(root.value) + 1:]
                return SimpleNamespace(as_posix=lambda: relative)

        def path(value):
            if isinstance(value, Node):
                return value
            if value not in nodes:
                nodes[value] = Node(value)
            return nodes[value]

        entries = []
        for value in ('/fixture/checkout/.git', '/fixture/checkout/.gitattributes', '/fixture/checkout/source.py'):
            info = states[value]
            entries.append(SimpleNamespace(path=value, name=value.rsplit('/', 1)[1],
                stat=lambda *, follow_symlinks, info=info: info))
        scan = mock.MagicMock()
        scan.__enter__.return_value = entries

        def stable(node, uid, gid, maximum, deadline):
            self.assertEqual((uid, gid, deadline), (3, 4, 10))
            if node.value == '/fixture/checkout/.git/config':
                self.assertEqual(maximum, self.module.MAX_CONFIG)
                return common, self.module.identity(config)
            self.assertEqual(node.value, '/fixture/checkout/.gitattributes')
            self.assertEqual(maximum, 4096)
            return attributes, self.module.identity(attrs)

        return path, path('/fixture/checkout'), stable, scan

    def test_snapshot_absent_and_present_empty_states_are_distinct(self):
        observed_states = []
        for state in ((None, None), (b'', (1, 8, stat.S_IFREG | 0o644, 3, 4, 1, 0, 5, 6))):
            path, root, stable, scan = self.snapshot_fixture()
            with self.subTest(present=state[0] is not None), \
                 mock.patch.object(self.module, 'Path', side_effect=path), \
                 mock.patch.object(self.module, 'clock'), \
                 mock.patch.object(self.module, 'stable_bytes', side_effect=stable), \
                 mock.patch.object(self.module, 'optional_worktree_config', side_effect=[state, state]) as optional, \
                 mock.patch.object(self.module.os, 'scandir', return_value=scan):
                result = self.module.snapshot(root, 3, 4, 10)
            self.assertEqual(optional.call_count, 2)
            self.assertEqual(result['worktree_config_present'], state[0] is not None)
            self.assertEqual(result['worktree_config_identity'], state[1])
            self.assertEqual(result['worktree_config_sha256'],
                             None if state[0] is None else self.module.hashlib.sha256(state[0]).hexdigest())
            observed_states.append(result)
        self.assertNotEqual(observed_states[0], observed_states[1])

    def test_snapshot_refuses_presence_byte_and_identity_drift(self):
        absent_state = (None, None)
        empty = (b'', (1, 8, stat.S_IFREG | 0o644, 3, 4, 1, 0, 5, 6))
        changed = (b'[core]\n', (1, 8, stat.S_IFREG | 0o644, 3, 4, 1, 7, 5, 6))
        replacement = (b'', (1, 9, stat.S_IFREG | 0o644, 3, 4, 1, 0, 5, 6))
        for first, last in ((absent_state, empty), (empty, absent_state),
                            (empty, changed), (empty, replacement)):
            path, root, stable, scan = self.snapshot_fixture()
            with self.subTest(first_present=first[0] is not None, last_present=last[0] is not None), \
                 mock.patch.object(self.module, 'Path', side_effect=path), \
                 mock.patch.object(self.module, 'clock'), \
                 mock.patch.object(self.module, 'stable_bytes', side_effect=stable), \
                 mock.patch.object(self.module, 'optional_worktree_config', side_effect=[first, last]), \
                 mock.patch.object(self.module.os, 'scandir', return_value=scan):
                with self.assertRaises(self.module.ConfigRefusal) as caught:
                    self.module.snapshot(root, 3, 4, 10)
            self.assertEqual(caught.exception.fixed_refusal_code, 'snapshot-17')

    def test_common_activation_still_refuses_before_active_git_birth_mock(self):
        import sys

        spec = importlib.util.spec_from_file_location('reviewed_inactive_config_owner',
            Path(__file__).with_name('cft_git_owner.py'))
        owner = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {'cft_git_config': self.module}):
            spec.loader.exec_module(owner)
        path, root, stable, scan = self.snapshot_fixture(BASE + b'[extensions]\n worktreeConfig = true\n')
        with mock.patch.object(self.module, 'Path', side_effect=path), \
             mock.patch.object(self.module, 'clock'), \
             mock.patch.object(self.module, 'stable_bytes', side_effect=stable), \
             mock.patch.object(self.module, 'optional_worktree_config', return_value=(b'', (1,))), \
             mock.patch.object(self.module.os, 'scandir', return_value=scan), \
             mock.patch.object(owner.os, 'getuid', return_value=0, create=True), \
             mock.patch.object(owner.os, 'geteuid', return_value=0, create=True), \
             mock.patch.object(owner.time, 'monotonic', return_value=0), \
             mock.patch.object(owner.subprocess, 'Popen') as birth:
            with self.assertRaises(self.module.ConfigRefusal) as caught:
                owner.RunnerGit([], ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', 'rev-parse', 'HEAD'],
                                root, 10, uid=3, gid=4)
            self.assertEqual(caught.exception.fixed_refusal_code, 'config-values-3')
            birth.assert_not_called()

    def test_index_false_and_mixed_sections_keep_closed_return_values(self):
        cases = (
            (b'[index]\n sparse=false\n', {'sparse': 'false'}),
            (b' \t[index]\n\tSPARSE\t=\tfalse\n', {'sparse': 'false'}),
            (b'[core]\n sparseCheckout=false\n sparseCheckoutCone=false\n'
             b'[index]\n sparse=false\n',
             {'sparsecheckout': 'false', 'sparsecheckoutcone': 'false', 'sparse': 'false'}),
            (b'[index]\n sparse=false\n[core]\n sparseCheckout=false\n',
             {'sparse': 'false', 'sparsecheckout': 'false'}),
            (b'[core]\n[index]\n sparse=false\n', {'sparse': 'false'}),
        )
        for raw, expected in cases:
            with self.subTest(size=len(raw)):
                self.assertEqual(self.module.inactive_worktree_config_values(raw), expected)

    def test_index_wrong_sections_values_duplicates_and_executable_syntax_refuse(self):
        cases = (
            (b'[index]\n', 'worktree-values-5'),
            (b'[index]\n sparse=true\n', 'worktree-values-5'),
            (b'[index]\n sparse=0\n', 'worktree-values-5'),
            (b'[index]\n sparse=1\n', 'worktree-values-5'),
            (b'[index]\n sparse=FALSE\n', 'worktree-values-5'),
            (b'[index]\n sparse="false"\n', 'worktree-values-5'),
            (b'[index]\n sparse=false # PRIVATE\n', 'worktree-values-5'),
            (b'[index]\n sparse=PRIVATE-command\n', 'worktree-values-5'),
            (b'[index]\n sparseCheckout=false\n', 'worktree-values-5'),
            (b'[index]\n sparseCheckoutCone=false\n', 'worktree-values-5'),
            (b'[core]\n sparse=false\n', 'worktree-values-5'),
            (b'[index]\n sparse=false\n SPARSE=false\n', 'worktree-values-6'),
            (b'[index]\n sparse=false\n[index]\n sparse=false\n', 'worktree-values-3'),
            (b'[core]\n[index]\n sparse=false\n[core]\n', 'worktree-values-3'),
            (b'[Index]\n sparse=false\n', 'worktree-values-3'),
            (b'[index "PRIVATE"]\n sparse=false\n', 'worktree-values-3'),
            (b'[index]\n sparse=false\n[include]\n path=/PRIVATE\n', 'worktree-values-3'),
            (b'[index]\n sparse=false\n[includeIf "gitdir:*"]\n path=/PRIVATE\n', 'worktree-values-3'),
            (b'[index]\n sparse=false\n[extensions]\n worktreeConfig=true\n', 'worktree-values-3'),
            (b'[index]\n sparse=false\n[filter "PRIVATE"]\n clean=PRIVATE\n', 'worktree-values-3'),
            (b'[index]\n sparse=false\n[credential]\n helper=PRIVATE\n', 'worktree-values-3'),
            (b'sparse=false\n', 'worktree-values-4'),
            (b'[index]\n # PRIVATE\n', 'worktree-values-4'),
            (b'[index]\n sparse=\n', 'worktree-values-4'),
            (b'[index]\r\n sparse=false\n', 'worktree-values-2'),
            (b'[index]\n sparse=fal\\se\n', 'worktree-values-2'),
            (b'[index]\n sparse\v=false\n', 'worktree-values-2'),
            (b'[index]\n sparse=false\x7f\n', 'worktree-values-2'),
        )
        for raw, code in cases:
            with self.subTest(code=code, size=len(raw)):
                with self.assertRaises(self.module.ConfigRefusal) as caught:
                    self.module.inactive_worktree_config_values(raw)
                self.assertEqual(caught.exception.args, ('cft-git-config-refused',))
                self.assertEqual(caught.exception.fixed_refusal_code, code)
                self.assertIn(code, self.module.CONFIG_REFUSAL_CODES)
                self.assertNotIn('PRIVATE', str(caught.exception))

    def test_optional_reader_applies_index_parser_without_other_operations(self):
        cases = (b'[index]\n sparse=false\n',
                 b'[core]\n sparseCheckout=false\n[index]\n sparse=false\n',
                 b'[index]\n sparse=true\n', b'[index]\n sparse=false\n[include]\n path=/PRIVATE\n')
        for raw in cases:
            identity = (1, 8, stat.S_IFREG | 0o644, 3, 4, 1, len(raw), 5, 6)
            path = SimpleNamespace(lstat=mock.Mock(return_value=object()))
            with self.subTest(size=len(raw)), mock.patch.object(self.module, 'clock'), \
                 mock.patch.object(self.module, 'stable_bytes', return_value=(raw, identity)) as read, \
                 mock.patch.object(self.module.os, 'unlink') as deleted, \
                 mock.patch.object(self.module.os, 'chmod') as changed:
                if b'true' in raw or b'PRIVATE' in raw:
                    with self.assertRaises(self.module.ConfigRefusal):
                        self.module.optional_worktree_config(path, 3, 4, 10)
                else:
                    self.assertEqual(self.module.optional_worktree_config(path, 3, 4, 10), (raw, identity))
                read.assert_called_once_with(path, 3, 4, self.module.MAX_CONFIG, 10)
                path.lstat.assert_called_once_with()
                deleted.assert_not_called()
                changed.assert_not_called()

    def test_index_state_is_bound_by_full_snapshot_and_drift_refuses(self):
        raw = b'[index]\n sparse=false\n'
        self.assertEqual(self.module.inactive_worktree_config_values(raw), {'sparse': 'false'})
        identity = (1, 8, stat.S_IFREG | 0o644, 3, 4, 1, len(raw), 5, 6)
        first = (raw, identity)
        cases = (first, (None, None), (raw + b'\n', (*identity[:6], len(raw) + 1, 5, 6)),
                 (raw, (1, 9, *identity[2:])))
        for last in cases:
            path, root, stable, scan = self.snapshot_fixture()
            with self.subTest(same=last == first), \
                 mock.patch.object(self.module, 'Path', side_effect=path), \
                 mock.patch.object(self.module, 'clock'), \
                 mock.patch.object(self.module, 'stable_bytes', side_effect=stable), \
                 mock.patch.object(self.module, 'optional_worktree_config', side_effect=[first, last]) as optional, \
                 mock.patch.object(self.module.os, 'scandir', return_value=scan):
                if last == first:
                    result = self.module.snapshot(root, 3, 4, 10)
                    self.assertIs(result['worktree_config_present'], True)
                    self.assertEqual(result['worktree_config_sha256'], self.module.hashlib.sha256(raw).hexdigest())
                    self.assertEqual(result['worktree_config_identity'], identity)
                else:
                    with self.assertRaises(self.module.ConfigRefusal) as caught:
                        self.module.snapshot(root, 3, 4, 10)
                    self.assertEqual(caught.exception.fixed_refusal_code, 'snapshot-17')
                self.assertEqual(optional.call_count, 2)

    def test_valid_index_still_refuses_harmful_common_config_before_active_birth(self):
        import sys

        raw = b'[core]\n sparseCheckout=false\n[index]\n sparse=false\n'
        self.assertEqual(self.module.inactive_worktree_config_values(raw),
                         {'sparsecheckout': 'false', 'sparse': 'false'})
        spec = importlib.util.spec_from_file_location('reviewed_inactive_index_owner',
            Path(__file__).with_name('cft_git_owner.py'))
        owner = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {'cft_git_config': self.module}):
            spec.loader.exec_module(owner)
        extras = (b'[extensions]\n worktreeConfig=true\n', b'[include]\n path=/PRIVATE\n',
                  b'[filter "PRIVATE"]\n clean=PRIVATE\n', b'[credential]\n helper=PRIVATE\n')
        for extra in extras:
            path, root, stable, scan = self.snapshot_fixture(BASE + extra)
            identity = (1, 8, stat.S_IFREG | 0o644, 3, 4, 1, len(raw), 5, 6)
            with self.subTest(size=len(extra)), mock.patch.object(self.module, 'Path', side_effect=path), \
                 mock.patch.object(self.module, 'clock'), \
                 mock.patch.object(self.module, 'stable_bytes', side_effect=stable), \
                 mock.patch.object(self.module, 'optional_worktree_config', return_value=(raw, identity)) as optional, \
                 mock.patch.object(self.module.os, 'scandir', return_value=scan), \
                 mock.patch.object(owner.os, 'getuid', return_value=0, create=True), \
                 mock.patch.object(owner.os, 'geteuid', return_value=0, create=True), \
                 mock.patch.object(owner.time, 'monotonic', return_value=0), \
                 mock.patch.object(owner.subprocess, 'Popen') as birth:
                with self.assertRaises(self.module.ConfigRefusal) as caught:
                    owner.RunnerGit([], ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', 'rev-parse', 'HEAD'],
                                    root, 10, uid=3, gid=4)
                self.assertEqual(caught.exception.fixed_refusal_code, 'config-values-3')
                self.assertEqual(caught.exception.args, ('cft-git-config-refused',))
                self.assertNotIn('PRIVATE', str(caught.exception))
                optional.assert_called_once()
                birth.assert_not_called()


@unittest.skipUnless(os.name == 'posix', 'POSIX no-follow raw descriptor fixture only')
class InactiveWorktreeRawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('reviewed_inactive_worktree_raw',
            Path(__file__).with_name('cft_git_config.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_present_file_uses_original_raw_owner_and_refuses_unsafe_shape_before_open(self):
        raw = b'[core]\n sparseCheckout = false\n'
        base = dict(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o644,
            st_uid=3, st_gid=4, st_nlink=1, st_size=len(raw), st_mtime_ns=5, st_ctime_ns=6)
        changes = ({}, {'st_mode': stat.S_IFLNK | 0o644}, {'st_mode': stat.S_IFDIR | 0o755},
                   {'st_uid': 9}, {'st_gid': 9}, {'st_mode': stat.S_IFREG | 0o666},
                   {'st_nlink': 2}, {'st_size': self.module.MAX_CONFIG + 1})
        for index, changed in enumerate(changes):
            info = SimpleNamespace(**{**base, **changed})
            path = SimpleNamespace(lstat=mock.Mock(return_value=info))
            with self.subTest(index=index), mock.patch.object(self.module, 'clock'), \
                 mock.patch.object(self.module.os, 'open', return_value=37) as opened, \
                 mock.patch.object(self.module.os, 'fstat', return_value=info), \
                 mock.patch.object(self.module.os, 'read', side_effect=[raw, b'']) as read, \
                 mock.patch.object(self.module.os, 'close') as closed, \
                 mock.patch.object(self.module.os, 'fdopen') as wrapped:
                if index == 0:
                    self.assertEqual(self.module.optional_worktree_config(path, 3, 4, 10),
                                     (raw, self.module.identity(info)))
                    opened.assert_called_once_with(path, os.O_RDONLY | os.O_NOFOLLOW)
                    closed.assert_called_once_with(37)
                    self.assertEqual(read.call_count, 2)
                else:
                    with self.assertRaises(self.module.ConfigRefusal) as caught:
                        self.module.optional_worktree_config(path, 3, 4, 10)
                    self.assertEqual(caught.exception.fixed_refusal_code, 'stable-bytes-1')
                    opened.assert_not_called()
                    closed.assert_not_called()
                    read.assert_not_called()
                wrapped.assert_not_called()


if __name__ == '__main__':
    unittest.main()
