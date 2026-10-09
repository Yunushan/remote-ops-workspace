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


if __name__ == '__main__':
    unittest.main()
