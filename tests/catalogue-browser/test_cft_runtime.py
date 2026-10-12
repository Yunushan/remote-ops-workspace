"""Synthetic pinned-runtime selection/preparation guards; no vendor operation."""
import ast
import io
import json
import stat
import unittest
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest import mock

import cft_bundle as bundle
import cft_git_owner
import cft_runtime as runtime


def path_io_refused(*_args, **_kwargs):
    raise AssertionError('unmocked-cft-runtime-path-IO')


class FixturePath(PurePosixPath):
    lstat = stat = exists = is_symlink = resolve = iterdir = path_io_refused


def binding():
    return {'source_head': 'a' * 40, 'source_tree': 'b' * 40, 'source_bytes_sha256': 'c' * 64,
        'workflow_sha256': 'd' * 64, 'event_sha': 'e' * 40, 'run_id': '123', 'run_attempt': '1'}


def policy_raw():
    value = {'schema': 'row.cft-provider-policy.v1', 'enabled': True, 'version': bundle.VERSION,
        'platform': bundle.PLATFORM, 'metadata_url': bundle.METADATA_URL,
        'metadata': {'bytes': 1, 'sha256': '0' * 64}, 'archives': {},
        'origin_evidence': 'certificate-and-hostname-verified-official-HTTPS',
        'independent_vendor_signature': False, 'publisher_license_approval': False,
        'sandbox_policy': 'unchanged-default-no-fallback'}
    for asset in bundle.ASSETS:
        value['archives'][asset] = {'url': bundle.asset_url(bundle.VERSION, asset),
            'bytes': 22, 'sha256': '0' * 64, 'inventory_sha256': '1' * 64,
            'entries': 1, 'files': 1, 'unpacked_bytes': 1}
    return bundle.packed(value)


def pointer():
    return {'schema': 'row.cft-runtime-operation.v1', 'root': '/var/lib/row-cft-' + 'f' * 32,
        'binding': binding(), 'version': bundle.VERSION, 'policy_sha256': bundle.hashed(policy_raw()),
        'manifest_sha256': '2' * 64, 'complete': True, 'vendor_binary_executed': False,
        'sandbox_policy': 'unchanged-default-no-fallback', 'readiness_credit': 0}


class RuntimeSelectionTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        path_patch = mock.patch.object(runtime, 'Path', FixturePath)
        self.addCleanup(path_patch.stop)
        path_patch.start()

    def test_version_command_and_grammar_are_bound_to_exact_provider(self):
        version = b'154.0.8037.92'
        image = b'Google Chrome ' + version + b'\n'
        cft = version + b'\n'
        binary = FixturePath('/var/lib/row-cft-' + 'f' * 32 + '/chrome-linux64/chrome')
        self.assertEqual(runtime.chrome_version_argv(binary, 'image'), [str(binary), '--version'])
        self.assertEqual(runtime.chrome_version_argv(binary, 'pinned-cft'), [str(binary), '--product-version'])
        self.assertEqual(runtime.chrome_version_match(image, 'image')[1], version)
        self.assertEqual(runtime.chrome_version_match(cft, 'pinned-cft')[1], version)
        self.assertIsNone(runtime.chrome_version_match(cft, 'image'))
        self.assertIsNone(runtime.chrome_version_match(image, 'pinned-cft'))
        for raw in (b'Chromium ' + version, cft + b'PRIVATE', b'154.0.8037', b'154.0.8037.92.1',
                    b'Google Chrome for Testing ' + version):
            with self.subTest(raw=raw):
                self.assertIsNone(runtime.chrome_version_match(raw, 'pinned-cft'))
        for provider in ('/PRIVATE', '', None):
            with self.subTest(provider=provider):
                with self.assertRaises(bundle.BundleRefusal):
                    runtime.chrome_version_match(cft, provider)
                with self.assertRaises(bundle.BundleRefusal):
                    runtime.chrome_version_argv(binary, provider)

    def test_binding_and_pointer_are_fixed_same_operation(self):
        expected = binding()
        source = {'head': expected['source_head'], 'tree': expected['source_tree'],
            'bytes': expected['source_bytes_sha256'], 'workflow': expected['workflow_sha256']}
        context = {'source': expected['source_head'], 'event': expected['event_sha']}
        env = {'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}
        self.assertEqual(runtime.operation_binding(source, context, env), expected)
        self.assertEqual(runtime.pointer_path(expected), FixturePath('/var/lib/row-cft-operation-123-1.json'))
        source['head'] = '0' * 40
        with self.assertRaises(bundle.BundleRefusal):
            runtime.operation_binding(source, context, env)
        for value in ('../private', '0', True):
            with self.subTest(value=value):
                invalid = {**expected, 'run_id': value}
                with self.assertRaises(bundle.BundleRefusal):
                    runtime.pointer_path(invalid)

    def test_pointer_refuses_old_binding_policy_and_false_completion(self):
        changes = [('binding', {**binding(), 'run_attempt': '2'}), ('policy_sha256', '0' * 64),
            ('version', '154.0.8037.97'), ('complete', False), ('complete', 1),
            ('vendor_binary_executed', True), ('readiness_credit', True),
            ('sandbox_policy', 'no-sandbox'), ('root', '/opt/google/chrome'),
            ('root', '/var/lib/row-cft-' + 'f' * 32 + '/..'),
            ('root', '/opt/row-cft-' + 'f' * 32), ('manifest_sha256', '/PRIVATE')]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                record = {**pointer(), key: value}
                with self.assertRaises(bundle.BundleRefusal):
                    runtime.pointer_contract(bundle.packed(record), binding(), policy_raw())
        with self.assertRaises(bundle.BundleRefusal):
            runtime.pointer_contract(bundle.packed({**pointer(), 'extra': 'PRIVATE'}), binding(), policy_raw())

    def test_only_verified_exact_pair_is_selected(self):
        pin = {'bytes': 1, 'sha256': '0' * 64, 'identity': [1]}
        installed = {'version': bundle.VERSION, 'root_owned': True, 'manifest_sha256': '2' * 64}
        with mock.patch.object(runtime, 'runner_account', return_value=(1001, 1001)), \
             mock.patch.object(runtime.os, 'getuid', return_value=1001, create=True), \
             mock.patch.object(runtime.os, 'geteuid', return_value=1001, create=True), \
             mock.patch.object(runtime.os, 'getgid', return_value=1001, create=True), \
             mock.patch.object(runtime.os, 'getegid', return_value=1001, create=True), \
             mock.patch.object(runtime, 'root_bases') as bases, \
             mock.patch.object(runtime, 'operation_binding', return_value=binding()), \
             mock.patch.object(bundle, 'stable_file', side_effect=[(pin, policy_raw()), (pin, bundle.packed(pointer()))]) as reads, \
             mock.patch.object(bundle, 'verify_installed', return_value=installed) as verify:
            chrome, driver, state = runtime.selected_runtime(FixturePath('/frozen'), {}, {}, 30)
        root = FixturePath(pointer()['root'])
        self.assertEqual(chrome, root / 'chrome-linux64/chrome')
        self.assertEqual(driver, root / 'chromedriver-linux64/chromedriver')
        self.assertEqual(state['installed'], installed)
        self.assertEqual(state['provider'], 'pinned-cft')
        self.assertEqual(state['binding'], binding())
        self.assertEqual(state['pointer'], FixturePath('/var/lib/row-cft-operation-123-1.json'))
        bases.assert_called_once_with()
        reads.assert_has_calls([
            mock.call(FixturePath('/frozen/cft-runtime-policy.json'), bundle.MAX_METADATA, 30, raw=True),
            mock.call(state['pointer'], runtime.MAX_POINTER, 30, root_owned=True, raw=True)])
        verify.assert_called_once_with(policy_raw(), root, 30, binding())

    def test_wrong_effective_identity_refuses_before_files(self):
        with mock.patch.object(runtime, 'runner_account', return_value=(1001, 1001)), \
             mock.patch.object(runtime.os, 'getuid', return_value=0, create=True), \
             mock.patch.object(runtime.os, 'geteuid', return_value=0, create=True), \
             mock.patch.object(runtime.os, 'getgid', return_value=0, create=True), \
             mock.patch.object(runtime.os, 'getegid', return_value=0, create=True), \
             mock.patch.object(runtime, 'root_bases') as bases, \
             mock.patch.object(bundle, 'stable_file') as reads:
            with self.assertRaises(bundle.BundleRefusal):
                runtime.selected_runtime(FixturePath('/frozen'), {}, {}, 30)
        bases.assert_not_called()
        reads.assert_not_called()

    def test_installed_manifest_mismatch_refuses(self):
        pin = {'bytes': 1, 'sha256': '0' * 64, 'identity': [1]}
        with mock.patch.object(runtime, 'runner_account', return_value=(1001, 1001)), \
             mock.patch.object(runtime.os, 'getuid', return_value=1001, create=True), \
             mock.patch.object(runtime.os, 'geteuid', return_value=1001, create=True), \
             mock.patch.object(runtime.os, 'getgid', return_value=1001, create=True), \
             mock.patch.object(runtime.os, 'getegid', return_value=1001, create=True), \
             mock.patch.object(runtime, 'root_bases'), \
             mock.patch.object(runtime, 'operation_binding', return_value=binding()), \
             mock.patch.object(bundle, 'stable_file', side_effect=[(pin, policy_raw()), (pin, bundle.packed(pointer()))]), \
             mock.patch.object(bundle, 'verify_installed', return_value={'manifest_sha256': '3' * 64}) as verify:
            with self.assertRaises(bundle.BundleRefusal):
                runtime.selected_runtime(FixturePath('/frozen'), {}, {}, 30)
        verify.assert_called_once()

    def test_final_policy_pointer_and_inventory_drift_refuse(self):
        state = {'policy_file': FixturePath('/policy'), 'policy_pin': {'bytes': 1},
            'pointer': FixturePath('/pointer'), 'pointer_pin': {'bytes': 2},
            'policy_raw': policy_raw(), 'root': FixturePath(pointer()['root']),
            'binding': binding(), 'installed': {'manifest_sha256': '2' * 64}}
        rows = [([{'bytes': 9}], None),
            ([{'bytes': 1}, {'bytes': 9}], None),
            ([{'bytes': 1}, {'bytes': 2}], {'manifest_sha256': '3' * 64})]
        for reads, installed in rows:
            with self.subTest(reads=reads), mock.patch.object(runtime, 'root_bases'), \
                 mock.patch.object(bundle, 'stable_file', side_effect=reads), \
                 mock.patch.object(bundle, 'verify_installed', return_value=installed):
                with self.assertRaises(bundle.BundleRefusal):
                    runtime.runtime_readback(state, 30)

    def test_fixed_git_workflow_route_and_unknown_route_refusal(self):
        argv = ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', 'show', 'a' * 40 + ':' + runtime.WORKFLOW]
        self.assertEqual(cft_git_owner.checked_argv(argv)[-2:], argv[-2:])
        argv[-1] = 'a' * 40 + ':.github/workflows/unknown.yml'
        with self.assertRaises(cft_git_owner.GitObservationRefusal):
            cft_git_owner.checked_argv(argv)

    def test_root_context_failure_cannot_create_private_or_launch_git(self):
        with mock.patch.object(runtime.threading, 'Timer') as timer, \
             mock.patch.object(runtime.time, 'monotonic', return_value=10), \
             mock.patch.dict(runtime.os.environ, {'ROW_CFT_PREP_DEADLINE': '160'}), \
             mock.patch.object(runtime, 'root_context', side_effect=RuntimeError('PRIVATE')), \
             mock.patch.object(runtime.tempfile, 'TemporaryDirectory') as private, \
             mock.patch.object(runtime, 'stage_readback') as stage, \
             mock.patch.object(runtime.sys, 'stderr', io.StringIO()) as errors:
            self.assertEqual(runtime.main(), 1)
            diagnostic = bundle.decode(errors.getvalue().encode(), 512)
        self.assertEqual(diagnostic['phase'], 'context')
        self.assertEqual(diagnostic['readiness_credit'], 0)
        self.assertNotIn('PRIVATE', errors.getvalue())
        private.assert_not_called()
        stage.assert_not_called()
        timer.return_value.cancel.assert_called_once_with()

    def main_fixture(self, state, *, late_print=False, late_cancel=False, late_flush=False, print_failure=False, source_failure=None):
        clock = [10.0]
        events = []
        state['events'] = events
        source = {'head': binding()['source_head'], 'tree': binding()['source_tree'],
            'bytes': binding()['source_bytes_sha256'], 'workflow': binding()['workflow_sha256']}
        context = {'source': binding()['source_head'], 'event': binding()['event_sha']}
        repo = FixturePath('/home/runner/work/remote-ops-workspace/remote-ops-workspace')
        policy = policy_raw()
        installed = {'manifest_sha256': '2' * 64}
        stage_file = '/var/lib/row-cft-source-' + 'e' * 32 + '/cft_runtime.py'

        def observe_clock():
            events.append('clock')
            return clock[0]

        def cancel():
            events.append('cancel')
            if late_cancel:
                clock[0] = 161.0

        def emit(raw, **kwargs):
            events.append('print')
            state.setdefault('printed', []).append((raw, kwargs))
            if 'file' not in kwargs:
                if late_print:
                    clock[0] = 161.0
                if print_failure:
                    raise RuntimeError('PRIVATE')

        with ExitStack() as stack:
            def patch(*args, **kwargs):
                return stack.enter_context(mock.patch.object(*args, **kwargs))

            timer = patch(runtime.threading, 'Timer')
            timer.return_value.cancel.side_effect = cancel
            state['cancel'] = timer.return_value.cancel
            patch(runtime.time, 'monotonic', side_effect=observe_clock)
            stack.enter_context(mock.patch.dict(runtime.os.environ,
                {'ROW_CFT_PREP_DEADLINE': '160', 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}))
            patch(runtime, '__file__', stage_file)
            patch(runtime, 'root_context', return_value=(repo, 1001, 1001, context))
            patch(runtime, 'stage_readback', return_value={'bytes': 1})
            patch(FixturePath, 'exists', return_value=False)
            patch(FixturePath, 'is_symlink', return_value=False)
            private = patch(runtime.tempfile, 'TemporaryDirectory')
            private.return_value.__enter__.return_value = '/var/lib/row-cft-private-fixture'
            patch(runtime.secrets, 'token_hex', return_value='f' * 32)
            patch(bundle, 'stable_file', return_value=({'bytes': len(policy)}, policy))
            state['acquire'] = patch(bundle, 'acquire')
            state['install'] = patch(bundle, 'install_pinned', return_value=installed)
            state['publish'] = patch(runtime, 'publish_pointer')
            if late_flush:
                stdout = patch(runtime.sys, 'stdout')

                def write(raw):
                    state.setdefault('stream_writes', []).append(raw)

                def flush():
                    events.append('flush')
                    clock[0] = 161.0

                stdout.write.side_effect = write
                stdout.flush.side_effect = flush
                state['stdout_flush'] = stdout.flush
            else:
                patch(runtime, 'print', side_effect=emit, create=True)
            git = mock.Mock(side_effect=AssertionError('unmocked-Git-birth'))
            def source_result(*args, **kwargs):
                if source_failure is not None:
                    kwargs['source_diagnostic']('git-head')
                    raise source_failure
                return source
            source_guard = mock.Mock(side_effect=source_result)
            stack.enter_context(mock.patch.dict(runtime.sys.modules, {
                'cft_git_owner': SimpleNamespace(RunnerGit=git),
                'host_controller': SimpleNamespace(source_guard=source_guard)}))
            result = runtime.main()
            git.assert_not_called()
            self.assertEqual(source_guard.call_count, 2 if source_failure is None else 1)
        return result

    def test_success_is_decided_after_fixed_stdout_and_finalization(self):
        state = {}
        self.assertEqual(self.main_fixture(state), 0)
        self.assertEqual(state['events'], ['clock', 'clock', 'print', 'cancel', 'clock'])
        state['cancel'].assert_called_once_with()
        diagnostic = bundle.decode(state['printed'][0][0].encode(), 512)
        self.assertEqual(diagnostic, {'schema': 'row.cft-preparation.v1',
            'status': 'prepared-unqualified-pending-finalization', 'provisional': True, 'readiness_credit': 0})
        self.assertEqual(state['printed'][0][1], {'flush': True})
        state['acquire'].assert_called_once_with(policy_raw(), FixturePath('/var/lib/row-cft-private-fixture'),
            160.0, require_pins=True)
        state['install'].assert_called_once_with(policy_raw(), FixturePath('/var/lib/row-cft-private-fixture'),
            FixturePath(pointer()['root']), 160.0, binding())
        state['publish'].assert_called_once()

    def test_late_stdout_cannot_return_success_after_finalization(self):
        state = {}
        with self.assertRaisesRegex(bundle.BundleRefusal, 'cft-deadline-refused'):
            self.main_fixture(state, late_print=True)
        state['cancel'].assert_called_once_with()
        self.assertEqual(state['events'][-3:], ['print', 'cancel', 'clock'])
        self.assertEqual(len(state['printed']), 1)
        state['publish'].assert_called_once()

    def test_late_watchdog_finalization_cannot_return_success(self):
        state = {}
        with self.assertRaisesRegex(bundle.BundleRefusal, 'cft-deadline-refused'):
            self.main_fixture(state, late_cancel=True)
        state['cancel'].assert_called_once_with()
        self.assertEqual(state['events'][-3:], ['print', 'cancel', 'clock'])
        self.assertEqual(len(state['printed']), 1)

    def test_late_stdout_flush_cannot_return_success(self):
        state = {}
        with self.assertRaisesRegex(bundle.BundleRefusal, 'cft-deadline-refused'):
            self.main_fixture(state, late_flush=True)
        state['stdout_flush'].assert_called_once_with()
        state['cancel'].assert_called_once_with()
        self.assertEqual(state['events'][-3:], ['flush', 'cancel', 'clock'])
        diagnostic = bundle.decode(''.join(state['stream_writes']).encode(), 512)
        self.assertEqual(diagnostic['status'], 'prepared-unqualified-pending-finalization')
        self.assertIs(diagnostic['provisional'], True)

    def test_stdout_exception_keeps_refusal_and_runs_finalization(self):
        state = {}
        self.assertEqual(self.main_fixture(state, print_failure=True), 1)
        state['cancel'].assert_called_once_with()
        self.assertEqual(state['events'][-1], 'cancel')
        self.assertEqual(len(state['printed']), 2)
        diagnostic = bundle.decode(state['printed'][1][0].encode(), 512)
        self.assertEqual(diagnostic['status'], 'refused')
        self.assertEqual(diagnostic['phase'], 'publication')
        self.assertNotIn('PRIVATE', state['printed'][1][0])

    def test_all_three_runtime_bases_remain_strict_root_nonwritable_directories(self):
        good = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        with mock.patch.object(FixturePath, 'lstat', return_value=good) as sampled:
            runtime.root_bases()
        self.assertEqual(sampled.call_count, 3)
        for ancestor_index in range(3):
            for mode, uid in ((stat.S_IFDIR | 0o777, 0), (stat.S_IFLNK | 0o755, 0),
                              (stat.S_IFDIR | 0o755, 1000)):
                rows = [good] * ancestor_index + [SimpleNamespace(st_mode=mode, st_uid=uid)]
                with self.subTest(ancestor_index=ancestor_index, mode=mode, uid=uid), \
                     mock.patch.object(FixturePath, 'lstat', side_effect=rows) as sampled:
                    with self.assertRaises(bundle.BundleRefusal):
                        runtime.root_bases()
                self.assertEqual(sampled.call_count, ancestor_index + 1)


def bootstrap_diagnostic_units():
    workflow = (Path(__file__).resolve().parents[2] / runtime.WORKFLOW).read_text(encoding='utf-8')
    marker = "/usr/bin/python3 -I -S -B - <<'ROW_CFT_ROOT_PY'\n"
    source = workflow.partition(marker)[2].partition('          ROW_CFT_ROOT_PY\n')[0]
    assert source and len(source.encode()) <= 32768
    source = '\n'.join(line[10:] if line else '' for line in source.splitlines())
    tree = ast.parse(source)
    names = {'BOOTSTRAP_CODES', 'BOOTSTRAP_PHASES', 'BootstrapRefusal', 'need',
        'bootstrap_diagnostic', 'emit_bootstrap_diagnostic'}
    units = []
    found = set()
    for node in tree.body:
        name = None
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        if name in names:
            assert name not in found
            found.add(name)
            units.append(node)
    assert found == names
    # Only the actual pure serializer/refusal units are loaded, never the bootstrap body or native providers.
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for unit in units for node in ast.walk(unit))
    assert not any(isinstance(node, ast.Name) and node.id in
        {'os', 'sys', 'Path', 'pwd', 'platform', 'main', 'raw_read', 'write_source'}
        for unit in units for node in ast.walk(unit))
    namespace = {'json': json}
    exec(compile(ast.Module(body=units, type_ignores=[]), '<pure-bootstrap-diagnostics>', 'exec'), namespace)
    return namespace


class BootstrapDiagnosticTests(unittest.TestCase):
    def test_each_fixed_reason_and_stage_is_bounded_and_refused(self):
        units = bootstrap_diagnostic_units()
        refusal = units['BootstrapRefusal']
        for code in units['BOOTSTRAP_CODES']:
            with self.subTest(code=code):
                with self.assertRaises(refusal) as caught:
                    units['need'](False, code)
                self.assertEqual(caught.exception.args, (code,))
                raw = units['bootstrap_diagnostic'](caught.exception, 'source-checks')
                self.assertLessEqual(len(raw), 512)
                raw.decode('ascii')
                value = json.loads(raw)
                self.assertEqual(value, {'schema': 'row.cft-root-bootstrap-diagnostic.v1', 'status': 'refused',
                    'phase': 'source-checks', 'code': code, 'readiness_credit': 0})
        for phase in units['BOOTSTRAP_PHASES']:
            with self.subTest(phase=phase):
                self.assertEqual(json.loads(units['bootstrap_diagnostic'](refusal('check-refused'), phase))['phase'], phase)
        self.assertIsNone(units['need'](True, 'PRIVATE'))

    def test_unknown_errors_values_and_string_subclasses_never_disclose(self):
        units = bootstrap_diagnostic_units()
        refusal = units['BootstrapRefusal']

        class PrivateText(str):
            def __str__(self):
                raise AssertionError('private stringification')

            def __eq__(self, _other):
                raise AssertionError('private comparison')

        class PrivateValue:
            def __str__(self):
                raise AssertionError('private object stringification')

        errors = [RuntimeError('PRIVATE /secret\n' + 'x' * 65536), KeyboardInterrupt('PRIVATE'),
            refusal('PRIVATE'), refusal(PrivateText('check-refused')), refusal(PrivateValue()),
            refusal('check-refused', 'PRIVATE')]
        for error in errors:
            with self.subTest(error_type=type(error).__name__):
                raw = units['bootstrap_diagnostic'](error, PrivateValue())
                value = json.loads(raw)
                self.assertEqual(value['code'], 'operation-exception')
                self.assertEqual(value['phase'], 'bootstrap')
                self.assertNotIn(b'PRIVATE', raw)
                self.assertNotIn(b'/secret', raw)
        raw = units['bootstrap_diagnostic'](refusal('check-refused'), PrivateText('source-checks'))
        self.assertEqual(json.loads(raw)['phase'], 'bootstrap')
        with mock.patch.object(json, 'dumps', return_value='x' * 513):
            raw = units['bootstrap_diagnostic'](refusal('check-refused'), 'source-checks')
        self.assertLessEqual(len(raw), 512)
        self.assertEqual(json.loads(raw)['code'], 'diagnostic-bound')

    def test_public_emission_is_ascii_one_line_and_flushed(self):
        units = bootstrap_diagnostic_units()
        stream = mock.Mock()
        self.assertIsNone(units['emit_bootstrap_diagnostic'](units['BootstrapRefusal']('source-bytes-pin'),
            'source-checks', stream))
        stream.write.assert_called_once()
        stream.flush.assert_called_once_with()
        raw = stream.write.call_args.args[0]
        self.assertLessEqual(len(raw.encode('ascii')), 512 + len('cft-root-bootstrap-diagnostic \n'))
        self.assertEqual(raw.count('\n'), 1)
        prefix, value = raw.rstrip('\n').split(' ', 1)
        self.assertEqual(prefix, 'cft-root-bootstrap-diagnostic')
        self.assertEqual(json.loads(value)['code'], 'source-bytes-pin')

    def test_write_flush_and_serializer_failures_are_suppressed(self):
        units = bootstrap_diagnostic_units()
        for point in ('write', 'flush', 'serialize'):
            stream = mock.Mock()
            with self.subTest(point=point), ExitStack() as stack:
                if point == 'serialize':
                    stack.enter_context(mock.patch.object(json, 'dumps', side_effect=RuntimeError('PRIVATE')))
                else:
                    getattr(stream, point).side_effect = RuntimeError('PRIVATE')
                self.assertIsNone(units['emit_bootstrap_diagnostic'](units['BootstrapRefusal']('check-refused'),
                    'bootstrap', stream))
                if point == 'serialize':
                    stream.write.assert_not_called()
                    stream.flush.assert_not_called()
                elif point == 'write':
                    stream.flush.assert_not_called()
                else:
                    stream.write.assert_called_once()


class SourceRefusalDiagnosticTests(unittest.TestCase):
    def test_exact_families_and_fixed_predicates_never_disclose_exception_text(self):
        families = ((runtime.ConfigRefusal, 'git-config', runtime.CONFIG_REFUSAL_CODES),
            (runtime.GitObservationRefusal, 'git-owner', runtime.GIT_REFUSAL_CODES))
        for error_type, family, codes in families:
            for code in codes:
                error = error_type('/PRIVATE/config-or-stderr')
                error.fixed_refusal_code = code
                with self.subTest(family=family, code=code):
                    raw = runtime.preparation_diagnostic(error, 'source-checks', 'git-head')
                    value = bundle.decode(raw, 512)
                    self.assertEqual(value['refusal_family'], family)
                    self.assertEqual(value['refusal_code'], code)
                    self.assertEqual(value['source_step'], 'git-head')
                    self.assertEqual(value['readiness_credit'], 0)
                    self.assertEqual(value['status'], 'refused')
                    self.assertNotIn(b'PRIVATE', raw)
                    self.assertTrue(raw.isascii())
                    self.assertLessEqual(len(raw), 512)

    def test_unknown_or_hostile_code_and_substage_are_not_stringified(self):
        class Hostile(str):
            def __hash__(self):
                raise AssertionError('private hash')
            def __str__(self):
                raise AssertionError('private text')
        for value in ('/PRIVATE/' * 10000, Hostile('config-values-1'), None, True, {}, b'PRIVATE'):
            error = runtime.ConfigRefusal('PRIVATE')
            error.fixed_refusal_code = value
            raw = runtime.preparation_diagnostic(error, value, value)
            record = bundle.decode(raw, 512)
            self.assertEqual(record['refusal_code'], 'unobserved')
            self.assertEqual(record['source_step'], 'unobserved')
            self.assertEqual(record['phase'], 'context')
            self.assertNotIn(b'PRIVATE', raw)

    def test_subclasses_and_standard_failures_remain_fixed_unqualified_families(self):
        class OtherConfig(runtime.ConfigRefusal):
            pass
        for error, family in ((OtherConfig('PRIVATE'), 'operation-exception'),
            (RuntimeError('PRIVATE'), 'operation-exception'), (KeyboardInterrupt('PRIVATE'), 'operation-exception'),
            (FileNotFoundError('/PRIVATE'), 'missing-input'), (PermissionError('/PRIVATE'), 'input-access'),
            (runtime.GateRefusal('PRIVATE'), 'source-contract'), (bundle.BundleRefusal('PRIVATE'), 'bundle')):
            error.fixed_refusal_code = runtime.CONFIG_REFUSAL_CODES[0]
            raw = runtime.preparation_diagnostic(error, 'installation', 'git-head')
            record = bundle.decode(raw, 512)
            self.assertEqual(record['refusal_family'], family)
            self.assertEqual(record['refusal_code'], 'unobserved')
            self.assertEqual(record['source_step'], 'unobserved')
            self.assertNotIn(b'PRIVATE', raw)

    def test_source_failure_stays_nonzero_without_acquisition_and_finalizes(self):
        for error in (runtime.ConfigRefusal('PRIVATE'), runtime.GitObservationRefusal('PRIVATE'),
                      runtime.GateRefusal('PRIVATE')):
            state = {}
            error.fixed_refusal_code = 'snapshot-4'
            helper = RuntimeSelectionTests()
            with mock.patch.object(runtime, 'Path', FixturePath):
                self.assertEqual(helper.main_fixture(state, source_failure=error), 1)
            state['acquire'].assert_not_called()
            state['install'].assert_not_called()
            state['publish'].assert_not_called()
            state['cancel'].assert_called_once_with()
            record = bundle.decode(state['printed'][0][0].encode(), 512)
            self.assertEqual(record['phase'], 'source-checks')
            self.assertEqual(record['source_step'], 'git-head')
            self.assertEqual(record['status'], 'refused')
            self.assertNotIn('PRIVATE', state['printed'][0][0])

    def test_optional_source_reporter_preserves_exact_guards_and_command_order(self):
        import host_controller as host
        repo = FixturePath('/mock-repo')
        directory = repo / 'tests/catalogue-browser'
        workflow = b'synthetic-workflow'
        product = 'src/remote_ops_workspace/state_lock.py'
        manifest = {'product_inputs': [{'path': product, 'size': 4, 'sha256': 'a' * 64}],
            'gate_inputs': ['host_controller.py', 'source-inputs.json']}
        for mismatch in (False, True):
            calls, steps = [], []

            def git(argv, calls=calls):
                calls.append(argv[3:])
                return {'rev-parse': ('e' * 40 if argv[-1] == 'HEAD' else 'f' * 40).encode(),
                    'diff': b'', 'show': workflow}[argv[3]]

            def pin(path, mismatch=mismatch, **kwargs):
                if kwargs.get('diagnostic') is not None:
                    kwargs['diagnostic']('write-mode')
                if path == repo / product:
                    return {'size': 4, 'sha256': ('b' if mismatch else 'a') * 64}
                return {'size': len(workflow), 'sha256': host.hashed(workflow)}

            with mock.patch.object(host, 'Path', FixturePath), \
                 mock.patch.object(host, 'file_pin', side_effect=pin), \
                 mock.patch.object(FixturePath, 'read_bytes', return_value=bundle.packed(manifest), create=True), \
                 mock.patch.object(FixturePath, 'iterdir', return_value=[directory / name for name in manifest['gate_inputs']]), \
                 mock.patch.object(host.os, 'getuid', return_value=0, create=True), \
                 mock.patch.object(host.os, 'geteuid', return_value=0, create=True), \
                 mock.patch.dict(host.os.environ, {'GITHUB_WORKFLOW_SHA': 'd' * 40,
                    'GITHUB_WORKFLOW_REF': 'Yunushan/remote-ops-workspace/' + host.WORKFLOW + '@fixed'}, clear=True), \
                 mock.patch.object(host.subprocess, 'Popen', side_effect=AssertionError('native')) as native:
                if mismatch:
                    with self.assertRaises(runtime.GateRefusal):
                        host.source_guard(repo, {'source': 'e' * 40}, [], {}, 30,
                            source_directory=directory, git_command=git, source_diagnostic=steps.append)
                    self.assertEqual(steps[-1], 'product-bytes')
                    self.assertEqual(len(calls), 3)
                else:
                    result = host.source_guard(repo, {'source': 'e' * 40}, [], {}, 30,
                        source_directory=directory, git_command=git, source_diagnostic=steps.append)
                    self.assertEqual(result['head'], 'e' * 40)
                    self.assertEqual(result['tree'], 'f' * 40)
                    self.assertEqual(result['workflow'], host.hashed(workflow))
                    self.assertEqual(steps[-1], 'source-summary')
                    self.assertEqual(calls, [['rev-parse', 'HEAD'], ['rev-parse', 'HEAD^{tree}'],
                        ['diff', '--no-ext-diff', '--exit-code', 'HEAD'],
                        ['show', 'd' * 40 + ':' + host.WORKFLOW]])
                native.assert_not_called()
            self.assertIn('git-file-write-mode', steps)
            self.assertTrue(all(step in runtime.SOURCE_STEPS for step in steps))


if __name__ == '__main__':
    unittest.main()
