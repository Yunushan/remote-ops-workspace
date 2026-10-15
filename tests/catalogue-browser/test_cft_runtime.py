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
    return {'schema': 'row.cft-runtime-operation.v2', 'root': '/var/lib/row-cft-' + 'f' * 32,
        'binding': binding(), 'version': bundle.VERSION, 'policy_sha256': bundle.hashed(policy_raw()),
        'manifest_sha256': '2' * 64, 'complete': True, 'vendor_binary_executed': False,
        'sandbox_policy': 'default-browser-with-scoped-host-userns-profile', 'host_policy': synthetic_host_policy(), 'readiness_credit': 0}


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
             mock.patch.object(runtime, 'select_host_policy', return_value={'synthetic': True}), \
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
            patch(runtime, 'prepare_host_policy', return_value={'synthetic': True})
            patch(runtime, 'policy_evidence', return_value=synthetic_host_policy())
            patch(runtime, 'remove_host_policy')
            patch(runtime, 'late_failure_policy_removal')
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





def synthetic_host_policy():
    return {'scope': 'exact-pinned-chrome-userns', 'host_policy_changed': True,
        'default_browser_sandbox_requested': True, 'profile_loaded_preparation_observed': True,
        'task_label_initial_observed': False, 'initial_observed_chrome_tasks': 0,
        'task_label_final_observed': False, 'final_observed_chrome_tasks': 0,
        'profile_sha256': '3' * 64, 'abi_sha256': '4' * 64, 'tool_sha256': '5' * 64,
        'features_sha256': '6' * 64, 'intent_sha256': '7' * 64}


class HostPolicyPureTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        for name, value in (('Path', FixturePath), ('APPARMOR_TOOL', FixturePath('/usr/sbin/apparmor_parser')),
                            ('APPARMOR_ABI', FixturePath('/etc/apparmor.d/abi/4.0'))):
            patch = mock.patch.object(runtime, name, value)
            self.addCleanup(patch.stop)
            patch.start()
        for getter in ('getuid', 'geteuid', 'getgid', 'getegid'):
            patch = mock.patch.object(runtime.os, getter, return_value=0, create=True)
            self.addCleanup(patch.stop)
            patch.start()
        for name, value in (('O_NOFOLLOW', 131072), ('O_CLOEXEC', 524288), ('O_DIRECTORY', 65536)):
            patch = mock.patch.object(runtime.os, name, value, create=True)
            self.addCleanup(patch.stop)
            patch.start()

    def test_exact_profile_has_one_fixed_attachment_and_userns_rule(self):
        root = FixturePath('/var/lib/row-cft-' + 'f' * 32)
        with mock.patch.object(runtime, 'Path', FixturePath):
            raw = runtime.policy_profile(root)
        self.assertEqual(raw, ('profile row-cft-userns-' + 'f' * 32 + ' ' + str(root)
            + '/chrome-linux64/chrome flags=(unconfined) {\n  userns,\n}\n').encode())
        self.assertNotIn(b'include', raw)
        self.assertNotIn(b'*', raw)
        self.assertNotIn(b'--no-sandbox', raw)
        for value in ('/PRIVATE', '/var/lib/row-cft-' + 'f' * 32 + '/..', '/var/lib/row-cft-' + 'F' * 32):
            with self.subTest(value=value), mock.patch.object(runtime, 'Path', FixturePath):
                with self.assertRaises(bundle.BundleRefusal):
                    runtime.policy_profile(value)

    def test_fixed_parser_argv_config_abi_cache_and_single_profile(self):
        state = {'root': '/var/lib/row-cft-' + 'f' * 32, 'directory': '/var/lib/row-cft-userns-' + 'f' * 32}
        expected = ['/usr/sbin/apparmor_parser', '--config-file', state['directory'] + '/config',
            '--skip-cache', '--jobs=0', '--abort-on-error', '--Werror', '--policy-features',
            state['directory'] + '/abi', '--add', state['directory'] + '/profile']
        with mock.patch.object(runtime, 'Path', FixturePath):
            self.assertEqual(runtime.policy_argv(state, 'add'), expected)
            self.assertEqual(runtime.policy_argv(state, 'remove'), [*expected[:9], '--remove', expected[10]])
            for action in ('replace', '/PRIVATE', '', None):
                with self.subTest(action=action), self.assertRaises(bundle.BundleRefusal):
                    runtime.policy_argv(state, action)

    def test_only_supported_feature_literals_admitted_without_mutation(self):
        good = [b'Y\n', b'userns_create\n', b'1\n', b'1\n', b'123\n']
        with mock.patch.object(runtime, 'kernel_read', side_effect=good) as read:
            observed = runtime.host_features(30)
        self.assertEqual(len(observed), 64)
        self.assertEqual(read.call_count, 5)
        for index, raw in ((0, b'N\n'), (1, b'PRIVATE'), (2, b'0\n'), (3, b'0\n'),
                           (4, b'0\n'), (4, b'2147483648\n'), (4, b'1\v')):
            rows = good.copy()
            rows[index] = raw
            with self.subTest(index=index, raw=raw), mock.patch.object(runtime, 'kernel_read', side_effect=rows):
                with self.assertRaises(bundle.BundleRefusal):
                    runtime.host_features(30)

    def test_profile_membership_collision_mode_duplicates_and_bounds(self):
        name = 'row-cft-userns-' + 'f' * 32
        chrome = '/var/lib/row-cft-' + 'f' * 32 + '/chrome-linux64/chrome'
        for raw, expected in ((b'other (enforce)\n', False), ((name + ' (unconfined)\n').encode(), True),
                              ((name + ' (default_allow)\n').encode(), True)):
            with self.subTest(raw=raw), mock.patch.object(runtime, 'kernel_read', return_value=raw):
                self.assertIs(runtime.profile_membership(name, chrome, 30), expected)
        for raw in ((chrome + ' (enforce)\n').encode(), (name + ' (complain)\n').encode(),
                    ((name + ' (unconfined)\n') * 2).encode(), b'PRIVATE', b'other (enforce)\x00\n',
                    b'x' * 4097 + b' (enforce)\n', b'other (enforce)\n' * 4097):
            with self.subTest(length=len(raw)), mock.patch.object(runtime, 'kernel_read', return_value=raw):
                with self.assertRaises(bundle.BundleRefusal):
                    runtime.profile_membership(name, chrome, 30)

    def test_caller_context_requires_exact_unconfined_without_settings_writes(self):
        for raw in (b'unconfined', b'unconfined\n'):
            with mock.patch.object(runtime, 'kernel_read', return_value=raw), \
                    mock.patch.object(runtime.os, 'getuid', return_value=1001, create=True):
                runtime.caller_unconfined(30)
        for raw in (b'PRIVATE (enforce)\n', b'unconfined\v', b''):
            with self.subTest(raw=raw), mock.patch.object(runtime, 'kernel_read', return_value=raw), \
                    mock.patch.object(runtime.os, 'getuid', return_value=1001, create=True):
                with self.assertRaises(bundle.BundleRefusal):
                    runtime.caller_unconfined(30)

    def test_virtual_reader_zero_stat_size_one_owner_final_close_and_clock(self):
        info = SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o444,
            st_uid=0, st_gid=0, st_nlink=1, st_size=0)
        directory = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        path = FixturePath('/sys/kernel/security/apparmor/profiles')
        def sampled(value):
            return info if value == path else directory
        with mock.patch.object(runtime, 'Path', FixturePath), mock.patch.object(FixturePath, 'lstat', sampled), \
                mock.patch.object(runtime.os, 'open', return_value=7) as opened, \
                mock.patch.object(runtime.os, 'fstat', return_value=info), \
                mock.patch.object(runtime.os, 'read', side_effect=[b'a', b'b', b'']) as read, \
                mock.patch.object(runtime.os, 'close') as closed, \
                mock.patch.object(bundle, 'remaining', return_value=10) as clock:
            self.assertEqual(runtime.kernel_read(path, 2, 30), b'ab')
        opened.assert_called_once()
        closed.assert_called_once_with(7)
        self.assertEqual(read.call_count, 3)
        self.assertEqual(clock.call_count, 5)

    def test_virtual_reader_overflow_or_close_error_refuses(self):
        info = SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o444,
            st_uid=0, st_gid=0, st_nlink=1, st_size=0)
        directory = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        path = FixturePath('/sys/kernel/security/apparmor/profiles')
        def sampled(value):
            return info if value == path else directory
        for chunks, failure in (([b'abc'], None), ([b''], KeyboardInterrupt('PRIVATE'))):
            with self.subTest(length=len(chunks)), mock.patch.object(runtime, 'Path', FixturePath), \
                    mock.patch.object(FixturePath, 'lstat', sampled), mock.patch.object(runtime.os, 'open', return_value=7), \
                    mock.patch.object(runtime.os, 'fstat', return_value=info), \
                    mock.patch.object(runtime.os, 'read', side_effect=chunks), \
                    mock.patch.object(runtime.os, 'close', side_effect=failure) as closed, \
                    mock.patch.object(bundle, 'remaining', return_value=10):
                with self.assertRaises(bundle.BundleRefusal if failure is None else KeyboardInterrupt):
                    runtime.kernel_read(path, 2, 30)
            closed.assert_called_once_with(7)



    def test_policy_drain_close_fault_sets_failure_latch_without_raw_exception(self):
        for original in (RuntimeError('PRIVATE'), KeyboardInterrupt('PRIVATE'), SystemExit(9)):
            calls = []
            class Base:
                def __init__(self, registry, argv, cwd, env, deadline, calls=calls):
                    calls.append((argv, cwd, env, deadline))
                    self.overflow = mock.Mock()
                    registry.append(self)
                def drain(self, *args, error=original):
                    raise error
            registry = []
            with self.subTest(error=type(original)), mock.patch.dict(runtime.sys.modules, {'host_controller': SimpleNamespace(Owned=Base)}):
                owner = runtime.policy_owner(registry, ['/synthetic/parser'], 30)
                self.assertIsNone(owner.drain(None, bytearray(), False))
            self.assertEqual(registry, [owner])
            self.assertEqual(calls, [(['/synthetic/parser'], FixturePath('/var/lib'), {}, 30)])
            owner.overflow.set.assert_called_once()

    def test_unsupported_host_refuses_before_policy_write_or_parser_birth(self):
        original = bundle.BundleRefusal('synthetic-feature-refused')
        with mock.patch.object(runtime, 'root_bases'), mock.patch.object(runtime, 'caller_unconfined'), \
                mock.patch.object(runtime, 'host_features', side_effect=original), \
                mock.patch.object(runtime, 'policy_tool') as tool, mock.patch.object(runtime.os, 'mkdir') as mkdir, \
                mock.patch.object(runtime, 'publish_pointer') as publish, mock.patch.object(runtime, 'run_policy') as native:
            with self.assertRaises(bundle.BundleRefusal) as caught:
                runtime.prepare_host_policy(FixturePath('/var/lib/row-cft-' + 'f' * 32), binding(), 30, [], {})
        self.assertIs(caught.exception, original)
        tool.assert_not_called()
        mkdir.assert_not_called()
        publish.assert_not_called()
        native.assert_not_called()

    def test_remove_only_own_name_and_truthful_absence_sample(self):
        holder = policy_fixture_holder()
        for present in (True, False):
            with self.subTest(present=present), mock.patch.object(runtime, 'root_bases'), \
                    mock.patch.object(runtime, 'caller_unconfined'), mock.patch.object(runtime, 'policy_readback'), \
                    mock.patch.object(runtime, 'profile_membership', side_effect=[present, False]), \
                    mock.patch.object(runtime, 'run_policy') as remove, \
                    mock.patch.object(bundle, 'remaining', return_value=10):
                row = runtime.remove_host_policy(holder, 30, [])
            self.assertEqual(row['status'], 'removed' if present else 'already-absent')
            self.assertIs(row['profile_present_pre_remove_observed'], present)
            self.assertIs(row['remove_attempted'], present)
            self.assertTrue(row['profile_absent_observed'])
            self.assertTrue(row['host_disposal_required'])
            self.assertFalse(row['descendants_complete'])
            if present:
                remove.assert_called_once_with(holder['state'], 'remove', [], 30)
            else:
                remove.assert_not_called()

    def test_remove_failure_or_residual_profile_never_reports_success(self):
        holder = policy_fixture_holder()
        for failure in (None, RuntimeError('PRIVATE'), KeyboardInterrupt('PRIVATE'), SystemExit(9)):
            with self.subTest(failure=type(failure)), mock.patch.object(runtime, 'root_bases'), \
                    mock.patch.object(runtime, 'caller_unconfined'), mock.patch.object(runtime, 'policy_readback'), \
                    mock.patch.object(runtime, 'profile_membership', side_effect=[True, True]), \
                    mock.patch.object(runtime, 'run_policy', side_effect=failure):
                with self.assertRaises(bundle.BundleRefusal if failure is None else type(failure)) as caught:
                    runtime.remove_host_policy(holder, 30, [])
                if failure is not None:
                    self.assertIs(caught.exception, failure)


    def test_cleanup_main_no_intent_requires_no_completed_pointer_and_finishes_after_flush(self):
        source = {'head': binding()['source_head'], 'tree': binding()['source_tree'],
                  'bytes': binding()['source_bytes_sha256'], 'workflow': binding()['workflow_sha256']}
        repo = FixturePath('/synthetic-repo')
        publications = []
        stream = io.StringIO()
        host = SimpleNamespace(source_guard=mock.Mock(return_value=source))
        git = SimpleNamespace(RunnerGit=mock.Mock(side_effect=AssertionError('native-Git')))
        with mock.patch.object(runtime, 'root_context', return_value=(repo, 1001, 1001,
                {'source': binding()['source_head'], 'event': binding()['event_sha']})), \
                mock.patch.object(runtime, 'stage_readback', return_value={}), \
                mock.patch.object(FixturePath, 'exists', return_value=False), \
                mock.patch.object(FixturePath, 'is_symlink', return_value=False), \
                mock.patch.object(runtime, 'publish_pointer', side_effect=lambda path, record, deadline, **kw: publications.append(record)), \
                mock.patch.object(runtime.time, 'monotonic', return_value=10), \
                mock.patch.object(runtime.threading, 'Timer') as timer, \
                mock.patch.object(bundle, 'remaining', return_value=10), \
                mock.patch.object(runtime.sys, 'stdout', stream), \
                mock.patch.dict(runtime.os.environ, {'ROW_CFT_PREP_DEADLINE': '40', 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}), \
                mock.patch.dict(runtime.sys.modules, {'host_controller': host, 'cft_git_owner': git}):
            self.assertEqual(runtime.cleanup_main(), 0)
        self.assertEqual(len(publications), 1)
        self.assertEqual(publications[0]['binding'], binding())
        self.assertEqual(publications[0]['observation']['status'], 'not-needed')
        self.assertFalse(publications[0]['observation']['descendants_complete'])
        self.assertEqual(host.source_guard.call_count, 2)
        git.RunnerGit.assert_not_called()
        timer.return_value.cancel.assert_called_once()
        self.assertNotIn('PRIVATE', stream.getvalue())



class PolicyMemory:
    """Mock every syscall/provider beneath the actual prepare/remove/PolicyOwned bodies."""
    def __init__(self):
        self.data = {'/usr/sbin/apparmor_parser': b'\x7fELFsynthetic-parser',
            '/etc/apparmor.d/abi/4.0': b'userns_create synthetic-ABI\n'}
        self.modes = {name: stat.S_IFREG | (0o755 if name.endswith('apparmor_parser') else 0o444)
            for name in self.data}
        self.fds, self.positions, self.inodes = {}, {}, {}
        self.next_fd = 50
        self.loaded = False
        self.events, self.births = [], []
        self.stderr = b''
        self.returncode = 0
        self.clock = 10.0
        self.identity = {'pid': 123, 'group': 123, 'session': 123, 'start': 99, 'state': 'S'}
        self.stack = ExitStack()

    def raw(self, name):
        if name == '/sys/kernel/security/apparmor/profiles':
            return (('row-cft-userns-' + 'f' * 32 + ' (unconfined)\n').encode()
                if self.loaded else b'other (enforce)\n')
        values = dict(zip(runtime.KERNEL_SCALARS, [b'Y\n', b'userns_create\n', b'1\n', b'1\n', b'123\n'], strict=True))
        if name in values:
            return values[name]
        if name.endswith('/attr/apparmor/current'):
            return b'unconfined\n'
        return self.data[name]

    def info(self, path):
        name = str(path)
        is_file = name in self.data or name in runtime.KERNEL_SCALARS or name.endswith('/attr/apparmor/current') or name.endswith('/apparmor/profiles')
        mode = self.modes.get(name, stat.S_IFREG | 0o444 if is_file else stat.S_IFDIR | 0o755)
        inode = self.inodes.setdefault(name, len(self.inodes) + 1)
        size = len(self.data[name]) if name in self.data else 0
        return SimpleNamespace(st_dev=1, st_ino=inode, st_mode=mode, st_uid=0, st_gid=0,
            st_nlink=1, st_mtime_ns=0, st_ctime_ns=0, st_size=size)

    def open(self, path, flags, *, dir_fd=None):
        name = str(path)
        if dir_fd is not None:
            name = str(FixturePath(self.fds[dir_fd]) / name)
        self.next_fd += 1
        self.fds[self.next_fd] = name
        self.positions[self.next_fd] = 0
        self.events.append(('open', name, flags))
        return self.next_fd

    def read(self, fd, maximum):
        raw = self.raw(self.fds[fd])
        start = self.positions[fd]
        answer = raw[start:start + maximum]
        self.positions[fd] += len(answer)
        return answer

    def mkdir(self, name, mode, *, dir_fd):
        path = str(FixturePath(self.fds[dir_fd]) / name)
        self.modes[path] = stat.S_IFDIR | mode
        self.events.append(('mkdir', path, mode))

    def chmod(self, fd, mode):
        name = self.fds[fd]
        self.modes[name] = stat.S_IFMT(self.info(name).st_mode) | mode
        self.events.append(('chmod', name, mode))

    def stable(self, path, maximum, deadline, *, raw=False, **kwargs):
        value = self.raw(str(path))
        bundle.remaining(deadline)
        self.case.assertLessEqual(len(value), maximum)
        answer = {'bytes': len(value), 'sha256': bundle.hashed(value),
            'identity': list(bundle.identity(self.info(path)))}
        return (answer, value) if raw else answer

    def writer(self, path, access_mode, flags, deadline, *, mode=None):
        memory = self
        self.case.assertEqual(access_mode, 'wb')
        self.case.assertEqual(mode, 0o600)
        self.case.assertFalse(str(path) in self.data)
        name = str(path)
        memory.data[name] = b''
        memory.modes[name] = stat.S_IFREG | 0o600
        fd = self.open(path, flags)
        class Writer:
            def __enter__(self):
                self.stream = io.BytesIO()
                self.stream.fileno = lambda: fd
                return self.stream
            def __exit__(self, *_args):
                memory.data[name] = self.stream.getvalue()
                self.stream.close()
                return False
        return Writer()

    def process(self, argv, **kwargs):
        memory = self
        self.case.assertEqual(kwargs['cwd'], FixturePath('/var/lib'))
        self.case.assertEqual(kwargs['env'], {})
        self.case.assertIs(kwargs['start_new_session'], True)
        self.case.assertIs(kwargs['close_fds'], True)
        class Pipe(io.BytesIO):
            def __init__(self, label, raw):
                super().__init__(raw)
                self.fd = memory.open(label, 0)
                memory.data[label] = raw
            def fileno(self):
                return self.fd
        class Process:
            pid = 123
            returncode = None
            def __init__(self):
                self.stdin = Pipe('/synthetic-pipe-in', b'')
                self.stdout = Pipe('/synthetic-pipe-out', b'')
                self.stderr = Pipe('/synthetic-pipe-error', memory.stderr)
            def poll(self):
                return self.returncode
            def wait(self, timeout):
                memory.case.assertGreater(timeout, 0)
                self.returncode = memory.returncode
                if self.returncode == 0:
                    memory.loaded = '--add' in argv
                memory.events.append(('wait', list(argv), timeout))
                return self.returncode
        value = Process()
        self.births.append((list(argv), kwargs, value))
        return value

    def __enter__(self):
        import host_controller as host
        memory = self
        class Thread:
            def __init__(self, *, target, args):
                self.target, self.args = target, args
            def start(self):
                self.target(*self.args)
            def join(self, timeout):
                memory.case.assertGreaterEqual(timeout, 0)
            def is_alive(self):
                return False
        patch = self.stack.enter_context
        patch(mock.patch.object(runtime, 'Path', FixturePath))
        patch(mock.patch.object(runtime, 'APPARMOR_TOOL', FixturePath('/usr/sbin/apparmor_parser')))
        patch(mock.patch.object(runtime, 'APPARMOR_ABI', FixturePath('/etc/apparmor.d/abi/4.0')))
        for getter in ('getuid', 'geteuid', 'getgid', 'getegid'):
            patch(mock.patch.object(runtime.os, getter, return_value=0, create=True))
        for name, value in (('O_NOFOLLOW', 131072), ('O_CLOEXEC', 524288), ('O_DIRECTORY', 65536)):
            patch(mock.patch.object(runtime.os, name, value, create=True))
        patch(mock.patch.object(FixturePath, 'lstat', lambda path: memory.info(path)))
        patch(mock.patch.object(FixturePath, 'exists', lambda path: str(path) in memory.data or str(path) in memory.modes))
        patch(mock.patch.object(FixturePath, 'is_symlink', return_value=False))
        patch(mock.patch.object(FixturePath, 'iterdir', lambda path: [FixturePath(name) for name in memory.data if FixturePath(name).parent == path]))
        patch(mock.patch.object(runtime.os, 'getpid', return_value=123))
        patch(mock.patch.object(runtime.os, 'open', side_effect=self.open))
        patch(mock.patch.object(runtime.os, 'fstat', side_effect=lambda fd: self.info(self.fds[fd])))
        patch(mock.patch.object(runtime.os, 'read', side_effect=self.read))
        patch(mock.patch.object(runtime.os, 'close', side_effect=lambda fd: self.events.append(('close', fd))))
        patch(mock.patch.object(runtime.os, 'mkdir', side_effect=self.mkdir))
        patch(mock.patch.object(runtime.os, 'fchmod', side_effect=self.chmod))
        patch(mock.patch.object(runtime.os, 'fsync'))
        patch(mock.patch.object(runtime.time, 'monotonic', side_effect=lambda: self.clock))
        patch(mock.patch.object(bundle, 'stable_file', side_effect=self.stable))
        patch(mock.patch.object(bundle, 'owned_binary', side_effect=self.writer))
        patch(mock.patch.object(host.subprocess, 'Popen', side_effect=self.process))
        patch(mock.patch.object(host, 'proc_identity', return_value=self.identity))
        patch(mock.patch.object(host, 'group_members', return_value=[]))
        patch(mock.patch.object(host.threading, 'Thread', Thread))
        patch(mock.patch.object(host.select, 'select', side_effect=lambda reads, _writes, _errors, _timeout: (reads, [], [])))
        return self

    def __exit__(self, *_args):
        self.stack.close()
        return False


def policy_fixture_holder():
    root = '/var/lib/row-cft-' + 'f' * 32
    def pin(size, value):
        return {'bytes': size, 'sha256': value * 64, 'identity': [1, 2, 0o100444, 0, 0, 1, 0, size]}
    state = {'schema': 'row.cft-userns-intent.v1', 'root': root, 'directory': '/var/lib/row-cft-userns-' + 'f' * 32,
        'name': 'row-cft-userns-' + 'f' * 32, 'binding': binding(),
        'input_pins': {'profile': pin(100, '3'), 'config': pin(0, '0'), 'abi': pin(100, '4')},
        'tool_pin': pin(100, '5'), 'features_sha256': '6' * 64, 'profile_sha256': '3' * 64,
        'abi_sha256': '4' * 64, 'host_policy_change_planned': True, 'readiness_credit': 0}
    return {'state': state, 'intent_pin': pin(100, '7'), 'preparation_loaded_observed': True,
        'samples': {'initial': {'observed': False, 'count': 0}, 'final': {'observed': False, 'count': 0}}}


class HostPolicyLifecycleTests(unittest.TestCase):
    def test_actual_prepare_and_remove_with_actual_registered_policy_owned(self):
        memory = PolicyMemory()
        memory.case = self
        registry = []
        with memory:
            holder = runtime.prepare_host_policy(FixturePath('/var/lib/row-cft-' + 'f' * 32), binding(), 30, registry, {})
            self.assertTrue(memory.loaded)
            self.assertEqual(len(registry), 1)
            self.assertEqual(len(memory.births), 1)
            self.assertEqual(memory.births[0][0], runtime.policy_argv(holder['state'], 'add'))
            evidence = runtime.policy_evidence(holder)
            self.assertTrue(evidence['profile_loaded_preparation_observed'])
            self.assertFalse(evidence['task_label_initial_observed'])
            self.assertFalse(evidence['task_label_final_observed'])
            self.assertIn(runtime.policy_record_path(binding(), 'intent').as_posix(), memory.data)
            observation = runtime.remove_host_policy(holder, 30, registry)
            self.assertEqual(observation['status'], 'removed')
            self.assertTrue(observation['profile_present_pre_remove_observed'])
            self.assertTrue(observation['remove_attempted'])
            self.assertFalse(memory.loaded)
            self.assertEqual(len(registry), 2)
            self.assertEqual(memory.births[1][0], runtime.policy_argv(holder['state'], 'remove'))
            self.assertTrue(all(owner.finished and owner.reaped and owner.cleanup_observed() for owner in registry))
            self.assertTrue(all(stream.closed for owner in registry for stream in (owner.process.stdin, owner.process.stdout, owner.process.stderr)))

    def test_real_parser_nonzero_private_stderr_and_overflow_never_mint_preparation(self):
        for code, errors in ((1, b''), (0, b'PRIVATE'), (0, b'x' * 65537)):
            with self.subTest(code=code, bytes=len(errors)):
                memory = PolicyMemory()
                memory.case, memory.returncode, memory.stderr = self, code, errors
                registry, holder = [], {}
                with memory:
                    with self.assertRaises((bundle.BundleRefusal, runtime.GateRefusal)):
                        runtime.prepare_host_policy(FixturePath('/var/lib/row-cft-' + 'f' * 32), binding(), 30, registry, holder)
                    self.assertNotIn('preparation_loaded_observed', holder)
                    self.assertEqual(len(registry), 1)
                    self.assertTrue(all(len(owner.errors) <= 65536 for owner in registry))
                    self.assertIn(runtime.policy_record_path(binding(), 'intent').as_posix(), memory.data)

    def test_nonroot_global_policy_view_refuses_before_read(self):
        for uid in (1, 1001):
            with self.subTest(uid=uid), mock.patch.object(runtime.os, 'getuid', return_value=uid, create=True), \
                    mock.patch.object(runtime.os, 'geteuid', return_value=uid, create=True), \
                    mock.patch.object(runtime.os, 'getgid', return_value=uid, create=True), \
                    mock.patch.object(runtime.os, 'getegid', return_value=uid, create=True), \
                    mock.patch.object(runtime, 'kernel_read', side_effect=PermissionError('PRIVATE')) as read:
                with self.assertRaises(bundle.BundleRefusal):
                    runtime.profile_membership('row-cft-userns-' + 'f' * 32, '/synthetic/chrome', 30)
            read.assert_not_called()

    def test_static_readback_retains_full_intent_and_never_views_global_policy(self):
        holder = policy_fixture_holder()
        with mock.patch.object(bundle, 'stable_file', return_value=(holder['intent_pin'], bundle.packed(holder['state']))), \
                mock.patch.object(runtime, 'policy_inputs') as inputs, \
                mock.patch.object(runtime, 'host_features', return_value='6' * 64), \
                mock.patch.object(runtime, 'profile_membership', side_effect=PermissionError('PRIVATE')) as membership, \
                mock.patch.object(bundle, 'remaining', return_value=10):
            runtime.policy_readback(holder, 30)
        inputs.assert_called_once_with(holder['state'], 30)
        membership.assert_not_called()

    def test_checkpoint_order_duplicate_and_fault_do_not_fabricate_task_samples(self):
        import host_controller as host
        row = {'pid': 123, 'group': 123, 'session': 123, 'start': 99, 'state': 'S'}
        owner = SimpleNamespace(identity=row, process=SimpleNamespace(pid=123, poll=lambda: None))
        holder = policy_fixture_holder()
        with mock.patch.object(runtime, 'policy_readback'), mock.patch.object(host, 'proc_identity', return_value=row), \
                mock.patch.object(host, 'group_members', return_value=[row]), \
                mock.patch.object(runtime.os, 'readlink', return_value=holder['state']['root'] + '/chrome-linux64/chrome'), \
                mock.patch.object(runtime.os, 'getuid', return_value=1001, create=True), \
                mock.patch.object(runtime, 'kernel_read', return_value=(holder['state']['name'] + ' (unconfined)\n').encode()), \
                mock.patch.object(runtime, 'profile_membership', side_effect=PermissionError('PRIVATE')) as membership, \
                mock.patch.object(bundle, 'remaining', return_value=10):
            with self.assertRaises(bundle.BundleRefusal):
                runtime.observe_policy_tasks(holder, owner, 30, checkpoint='final')
            first = runtime.observe_policy_tasks(holder, owner, 30, checkpoint='initial')
            self.assertTrue(first['task_label_initial_observed'])
            self.assertFalse(first['task_label_final_observed'])
            with self.assertRaises(bundle.BundleRefusal):
                runtime.observe_policy_tasks(holder, owner, 30, checkpoint='initial')
            final = runtime.observe_policy_tasks(holder, owner, 30, checkpoint='final')
            self.assertTrue(final['task_label_final_observed'])
            self.assertEqual(final['final_observed_chrome_tasks'], 1)
            with self.assertRaises(bundle.BundleRefusal):
                runtime.observe_policy_tasks(holder, owner, 30, checkpoint='final')
        membership.assert_not_called()

    def test_failed_checkpoint_and_late_clock_commit_no_observation(self):
        import host_controller as host
        row = {'pid': 123, 'group': 123, 'session': 123, 'start': 99, 'state': 'S'}
        owner = SimpleNamespace(identity=row, process=SimpleNamespace(pid=123, poll=lambda: None))
        for failure in ('label', 'clock', 'identity'):
            holder = policy_fixture_holder()
            with self.subTest(failure=failure), mock.patch.object(runtime, 'policy_readback'), \
                    mock.patch.object(host, 'proc_identity', return_value={**row, 'start': 1} if failure == 'identity' else row), \
                    mock.patch.object(host, 'group_members', return_value=[row]), \
                    mock.patch.object(runtime.os, 'readlink', return_value=holder['state']['root'] + '/chrome-linux64/chrome'), \
                    mock.patch.object(runtime.os, 'getuid', return_value=1001, create=True), \
                    mock.patch.object(runtime, 'kernel_read', return_value=b'PRIVATE' if failure == 'label' else (holder['state']['name'] + ' (unconfined)\n').encode()), \
                    mock.patch.object(bundle, 'remaining', side_effect=bundle.BundleRefusal('late') if failure == 'clock' else None, return_value=10):
                with self.assertRaises(bundle.BundleRefusal):
                    runtime.observe_policy_tasks(holder, owner, 30, checkpoint='initial')
            self.assertEqual(holder['samples'], {'initial': {'observed': False, 'count': 0}, 'final': {'observed': False, 'count': 0}})



class HostPolicyFinalizationTests(unittest.TestCase):
    def cleanup_fixture(self, *, fault='none', primary=None):
        clock = [10.0]
        source = {'head': binding()['source_head'], 'tree': binding()['source_tree'],
            'bytes': binding()['source_bytes_sha256'], 'workflow': binding()['workflow_sha256']}
        context = {'source': binding()['source_head'], 'event': binding()['event_sha']}
        repo = FixturePath('/synthetic-repo')
        events, publications = [], []
        pending = mock.Mock(finished=False)
        pending.refuse_cleanup.side_effect = KeyboardInterrupt('PRIVATE-secondary')
        def source_guard(*args, **kwargs):
            events.append('source')
            if primary is not None:
                args[2].append(pending)
                raise primary
            return source
        def cancel():
            events.append('cancel')
            if fault == 'late-cancel':
                clock[0] = 41.0
            if fault == 'cancel-error':
                raise SystemExit(9)
        def emit(raw, **kwargs):
            events.append(('emit', kwargs))
            self.assertIs(kwargs.get('flush'), True)
            if fault == 'late-print':
                clock[0] = 41.0
            if fault == 'print-error':
                raise KeyboardInterrupt('PRIVATE-print')
        class LateFlush(io.StringIO):
            def flush(self):
                events.append('flush')
                clock[0] = 41.0
                return super().flush()
        host = SimpleNamespace(source_guard=mock.Mock(side_effect=source_guard))
        git = SimpleNamespace(RunnerGit=mock.Mock(side_effect=AssertionError('unexpected-Git')))
        with ExitStack() as stack:
            enter = stack.enter_context
            enter(mock.patch.object(runtime, 'Path', FixturePath))
            enter(mock.patch.object(runtime, 'root_context', return_value=(repo, 1001, 1001, context)))
            enter(mock.patch.object(runtime, 'stage_readback', return_value={}))
            enter(mock.patch.object(FixturePath, 'exists', return_value=False))
            enter(mock.patch.object(FixturePath, 'is_symlink', return_value=False))
            publish = enter(mock.patch.object(runtime, 'publish_pointer', side_effect=lambda path, record, deadline, **kw: publications.append((path, record, kw))))
            enter(mock.patch.object(runtime.time, 'monotonic', side_effect=lambda: clock[0]))
            timer = enter(mock.patch.object(runtime.threading, 'Timer'))
            timer.return_value.cancel.side_effect = cancel
            enter(mock.patch.dict(runtime.os.environ, {'ROW_CFT_PREP_DEADLINE': '40', 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}))
            enter(mock.patch.dict(runtime.sys.modules, {'host_controller': host, 'cft_git_owner': git}))
            if fault == 'late-flush':
                enter(mock.patch.object(runtime.sys, 'stdout', LateFlush()))
            else:
                enter(mock.patch.object(runtime, 'print', side_effect=emit, create=True))
            try:
                answer = runtime.cleanup_main()
            except BaseException as error:
                answer = error
            git.RunnerGit.assert_not_called()
        timer.return_value.start.assert_called_once()
        timer.return_value.cancel.assert_called_once()
        return answer, events, publications, pending, publish

    def test_cleanup_success_requires_finalization_and_final_clock(self):
        answer, events, publications, _pending, _publish = self.cleanup_fixture()
        self.assertEqual(answer, 0)
        self.assertEqual(len(publications), 1)
        self.assertEqual(publications[0][1]['observation']['status'], 'not-needed')
        self.assertFalse(publications[0][1]['observation']['descendants_complete'])
        self.assertEqual(publications[0][2], {'maximum': runtime.POLICY_MAX})
        self.assertLess(events.index(next(x for x in events if type(x) is tuple)), events.index('cancel'))
        self.assertEqual(events.count('source'), 2)

    def test_late_print_flush_cancel_or_cancel_error_never_return_zero(self):
        for fault in ('late-print', 'late-flush', 'late-cancel', 'cancel-error', 'print-error'):
            with self.subTest(fault=fault):
                answer, _events, publications, _pending, _publish = self.cleanup_fixture(fault=fault)
                self.assertIsInstance(answer, BaseException)
                self.assertNotEqual(answer, 0)
                self.assertEqual(len(publications), 1)
                self.assertEqual(publications[0][1]['readiness_credit'], 0)

    def test_selected_source_error_wins_cleanup_and_cancel_interruptions(self):
        for primary in (RuntimeError('PRIVATE-primary'), KeyboardInterrupt('PRIVATE-primary'), SystemExit(7)):
            with self.subTest(kind=type(primary)):
                answer, _events, publications, pending, publish = self.cleanup_fixture(primary=primary, fault='cancel-error')
                self.assertIs(answer, primary)
                self.assertEqual(answer.args, primary.args)
                self.assertEqual(publications, [])
                publish.assert_not_called()
                pending.refuse_cleanup.assert_called_once()

    def test_root_collision_and_unsafe_parent_refuse_before_birth(self):
        for cause in ('collision', 'parent-mode'):
            with self.subTest(cause=cause):
                memory = PolicyMemory()
                memory.case = self
                memory.loaded = cause == 'collision'
                if cause == 'parent-mode':
                    memory.modes['/var/lib'] = stat.S_IFDIR | 0o777
                with memory:
                    with self.assertRaises(bundle.BundleRefusal):
                        runtime.prepare_host_policy(FixturePath('/var/lib/row-cft-' + 'f' * 32), binding(), 30, [], {})
                self.assertEqual(memory.births, [])
                self.assertFalse(any(row[0] == 'mkdir' for row in memory.events))

    def test_private_holder_types_and_order_cannot_fabricate_public_evidence(self):
        for field, value in (('preparation_loaded_observed', False), ('samples', {}),
                            ('samples', {'initial': {'observed': True, 'count': True}, 'final': {'observed': False, 'count': 0}}),
                            ('samples', {'initial': {'observed': False, 'count': 0}, 'final': {'observed': True, 'count': 1}})):
            holder = policy_fixture_holder()
            holder[field] = value
            with self.subTest(field=field), self.assertRaises(bundle.BundleRefusal):
                runtime.policy_evidence(holder)


class RepairPolicyMemory(PolicyMemory):
    """Lower-layer faults under actual root main/prepare/remove/PolicyOwned."""
    def __init__(self, case, fault='none'):
        super().__init__()
        self.case, self.fault = case, fault
        self.selected = RuntimeError('PRIVATE-selected-provider')
        self.secondary = KeyboardInterrupt('PRIVATE-secondary-provider')
        self.processes, self.counts, self.timers = {}, {}, []
        self.rollback = False
        self.after_cancel = False
        self.source_calls = 0
        self.diagnostics = []
        self.fixture_phase = None
        self.primary = None
        self.primary_injected = False
        self.metadata_fault_fired = False
        self.fault_hits = 0
        self.close_faults = []
        self.data[str(FixturePath(runtime.__file__).parent / runtime.POLICY_NAME)] = policy_raw()
        self.modes[str(FixturePath(runtime.__file__).parent / runtime.POLICY_NAME)] = stat.S_IFREG | 0o444
        if fault == 'parser-first4bytes-not-ELF':
            self.hit()
            self.data['/usr/sbin/apparmor_parser'] = b'BAD!synthetic-parser'
        if fault == 'parser-mode-not-executable':
            self.hit()
            self.modes['/usr/sbin/apparmor_parser'] = stat.S_IFREG | 0o644
        for tag, raw in (('ABI-empty', b''), ('ABI-missing-userns_create', b'absent\n'),
                         ('ABI-control-byte', b'userns_create\x00\n')):
            if fault == tag:
                self.hit()
                self.data['/etc/apparmor.d/abi/4.0'] = raw
        if fault == 'ABI-owner-or-mode-refused':
            self.hit()
            self.modes['/etc/apparmor.d/abi/4.0'] = stat.S_IFREG | 0o666

    def hit(self):
        self.fault_hits += 1

    def count(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def info(self, path):
        value = super().info(path)
        name = str(path)
        if self.fault == 'parser-owner-or-parent-mode-refused' and name == '/usr/sbin':
            self.hit()
            value.st_mode |= 0o022
        if self.fault == 'ABI-owner-or-mode-refused' and name == '/etc/apparmor.d/abi/4.0':
            self.hit()
            value.st_uid = 1001
        if self.metadata_fault_fired and self.fault == 'parser-path-readback-identity-drift' and name == '/usr/sbin/apparmor_parser':
            self.hit()
            value.st_ino += 1
        if self.fault == 'sealed-directory-not555-or-extra-member' and name.startswith('/var/lib/row-cft-userns-') and name in self.modes and stat.S_ISDIR(value.st_mode):
            self.hit()
            if stat.S_IMODE(value.st_mode) == 0o555:
                value.st_mode = stat.S_IFDIR | 0o755
        if self.fault == 'child-fchmod-seal-or-parent-readback-fault' and name == '/var/lib' and any(row[0] == 'chmod' and row[2] == 0o555 for row in self.events):
            self.hit()
            value.st_ino += 1
        return value

    def fd_info(self, fd):
        name = self.fds[fd]
        value = super().info(name)
        number = self.count(('fstat', fd))
        if name == '/usr/sbin/apparmor_parser':
            if self.fault == 'parser-descriptor-before-identity-drift' and number == 1:
                self.hit()
                value.st_ino += 1
            if self.fault == 'parser-descriptor-after-identity-drift' and number >= 2:
                self.hit()
                value.st_mode &= ~0o111  # Executability is sampled again after the ELF read.
        if name == '/var/lib' and self.fault == 'parent-descriptor-vs-path-drift':
            self.hit()
            value.st_ino += 1
        if name.startswith('/var/lib/row-cft-userns-') and self.fault == 'child-descriptor-vs-path-drift' and stat.S_ISDIR(value.st_mode):
            self.hit()
            value.st_ino += 1
        return value

    def open(self, path, flags, *, dir_fd=None):
        if self.fault == 'parent-open-fault' and str(path) == '/var/lib':
            self.hit()
            raise self.selected
        if self.fault == 'child-open-after-mkdir-fault' and dir_fd is not None and str(path).startswith('row-cft-userns-'):
            self.hit()
            raise self.selected
        return super().open(path, flags, dir_fd=dir_fd)

    def close(self, fd):
        name = self.fds[fd]
        self.events.append(('close', fd))
        child = name.startswith('/var/lib/row-cft-userns-') and stat.S_ISDIR(self.modes.get(name, 0))
        fail = (self.fault == 'child-close-fault' and child
            or self.fault == 'parent-close-fault' and name == '/var/lib'
            or self.fault == 'both-close-faults-first-selected-close-preserved' and (child or name == '/var/lib'))
        if fail:
            self.close_faults.append(name)
            raise self.selected if child or self.fault != 'both-close-faults-first-selected-close-preserved' else self.secondary

    def read(self, fd, maximum):
        answer = super().read(fd, maximum)
        if self.fault == 'parser-path-readback-identity-drift' and self.fds[fd] == '/usr/sbin/apparmor_parser':
            self.hit()
            self.metadata_fault_fired = True
        return answer

    def stable(self, path, maximum, deadline, *, raw=False, **kwargs):
        name = str(path)
        number = self.count(('stable', name))
        if self.rollback and self.fault == 'pre-provider-static-readback-fault':
            self.hit()
            raise self.secondary
        if name == '/usr/sbin/apparmor_parser' and self.fault == 'parser-metadata-size-bound-no-large-allocation':
            self.hit()
            raise bundle.BundleRefusal('synthetic-stable-file-bound')
        if name == '/etc/apparmor.d/abi/4.0' and number >= 2 and self.fault == 'ABI-stable-raw-pin-drift':
            self.hit()
            self.data[name] += b'changed\n'
        is_sealed = '/row-cft-userns-' in name and path.name in ('profile', 'config', 'abi')
        if is_sealed and number >= 3:
            if self.fault == 'sealed-profile-bytes-wrong-root-or-rule' and path.name == 'profile':
                self.hit()
                self.data[name] += b'userns,\n'
            if self.fault == 'sealed-config-nonempty' and path.name == 'config':
                self.hit()
                self.data[name] = b'PRIVATE-config\n'
            if self.fault == 'sealed-ABI-bytes-drift' and path.name == 'abi':
                self.hit()
                self.data[name] += b'changed\n'
            if self.fault == 'sealed-' + {'profile': 'profile', 'config': 'config', 'abi': 'ABI'}[path.name] + '-mode-not444':
                self.hit()
                self.modes[name] = stat.S_IFREG | 0o600
        if name.startswith('/var/lib/row-cft-policy-intent-') and number >= 3 and self.fault == 'intent-raw-binding-or-pin-drift':
            self.hit()
            self.data[name] += b' '
        if self.loaded and self.fault == 'after-policy-load-before-static-readback-interruption':
            self.hit()
            raise self.selected
        if self.rollback and self.fault == 'post-finish-input-drift' and any(row[0] == 'wait' and '--remove' in row[1] for row in self.events):
            self.hit()
            if path.name == 'profile':
                self.data[name] += b'changed\n'
        value = self.raw(name)
        bundle.remaining(deadline)
        if len(value) > maximum:
            raise bundle.BundleRefusal('synthetic-stable-file-bound')
        info = self.info(path)
        if kwargs.get('root_owned') and (info.st_uid != 0 or info.st_mode & 0o022):
            raise bundle.BundleRefusal('synthetic-stable-file-owner')
        result = {'bytes': len(value), 'sha256': bundle.hashed(value), 'identity': list(bundle.identity(self.info(path)))}
        return (result, value) if raw else result

    def process(self, argv, **kwargs):
        removing = '--remove' in argv
        if removing:
            self.rollback = True
            if self.fault == 'Popen-no-handle-fault':
                self.hit()
                raise self.secondary
            if self.fault == 'private-stderr-present':
                self.hit()
                self.stderr = b'PRIVATE-stderr'
            if self.fault == 'real-65537-byte-drain-overflow':
                self.hit()
                self.stderr = b'x' * 65537
        elif self.fault == 'before-parser-birth-interruption':
            self.hit()
            raise self.selected
        value = super().process(argv, **kwargs)
        value.pid = 123 + len(self.births)
        value.argv = list(argv)
        self.processes[value.pid] = value
        value.identity = {'pid': value.pid, 'group': value.pid, 'session': value.pid,
            'start': 99 + len(self.births), 'state': 'S'}
        original_wait = value.wait
        memory = self
        def terminal(signal):
            value.returncode = -signal
        value.terminate = lambda: terminal(15)
        value.kill = lambda: terminal(9)
        def wait(timeout):
            if removing and self.fault in ('wait-interruption', 'wait-timeout') and self.count(('wait-fault', value.pid)) == 1:
                self.hit()
                if self.fault == 'wait-timeout':
                    self.hit()
                    import subprocess
                    raise subprocess.TimeoutExpired(argv, timeout)
                raise self.secondary
            if removing and self.fault in ('refuse-terminate-or-group-signal-fault', 'refuse-wait-fault', 'refuse-stdin-close-fault', 'refuse-drain-join-fault'):
                self.hit()
                if self.count(('wait-first', value.pid)) == 1:
                    raise self.secondary
                if self.fault == 'refuse-wait-fault':
                    self.hit()
                    raise self.secondary
            if value.returncode is not None:
                return value.returncode
            if removing and self.fault == 'nonzero-returncode':
                self.hit()
                self.returncode = 1
            answer = original_wait(timeout)
            if not removing and self.fault == 'late-clock-after-policy-load-before-latch':
                self.hit()
                self.clock = 31.0
            return answer
        value.wait = wait
        for name in ('stdin', 'stdout', 'stderr'):
            stream = getattr(value, name)
            original_close = stream.close
            def close(close=original_close, label=name):
                if removing and self.fault == 'refuse-stdin-close-fault' and label == 'stdin':
                    self.hit()
                    raise self.secondary
                close()
                if removing and self.fault == 'drain-close-fault' and label == 'stderr':
                    self.hit()
                    raise self.secondary
            stream.close = close
        if removing and self.fault == 'retained-pipe-open':
            self.hit()
            stream = value.stdin
            class PipeView:
                closed = False
                def close(self):
                    stream.close()
                def fileno(self):
                    return stream.fileno()
            value.stdin = PipeView()
        if removing and self.fault == 'poll-or-reap-contradiction':
            self.hit()
            value.poll = lambda: None
        if removing and self.fault == 'refuse-proc-inspection-fault':
            self.hit()
            value.poll = lambda: (_ for _ in ()).throw(memory.secondary)
        original_poll = value.poll
        def poll():
            self.count(('poll', value.pid))
            return original_poll()
        value.poll = poll
        return value

    def proc(self, pid):
        value = self.processes[pid]
        removing = '--remove' in value.argv
        if removing and self.fault == 'after-Popen-before-proc-identity-fault':
            self.hit()
            raise self.secondary
        if not removing and self.fault == 'after-parser-birth-before-identity-interruption':
            self.hit()
            raise self.selected
        row = value.identity.copy()
        if removing and self.fault == 'proc-identity-mismatch':
            self.hit()
            row['group'] = 999
        return row

    def groups(self, group):
        value = self.processes[group]
        if '--remove' in value.argv:
            if self.fault == 'cleanup_observed-interruption':
                self.hit()
                raise self.secondary
            if self.fault in ('cleanup_observed-false', 'drain-still-live'):
                self.hit()
                return [value.identity.copy()]
        return []

    def signal(self, group, signal):
        value = self.processes[group]
        if '--remove' in value.argv and self.fault == 'refuse-terminate-or-group-signal-fault':
            self.hit()
            raise self.secondary
        value.returncode = -signal

    def __enter__(self):
        import host_controller as host
        super().__enter__()
        memory = self
        enter = self.stack.enter_context
        enter(mock.patch.object(runtime.os, 'fstat', side_effect=self.fd_info))
        enter(mock.patch.object(runtime.os, 'close', side_effect=self.close))
        enter(mock.patch.object(runtime.os, 'killpg', side_effect=self.signal, create=True))
        enter(mock.patch.object(host, 'proc_identity', side_effect=self.proc))
        enter(mock.patch.object(host, 'group_members', side_effect=self.groups))
        original_reversed = reversed
        def reverse(registry):
            if self.rollback and self.fault == 'whole-fence-allocation-fault' and registry:
                self.hit()
                raise MemoryError('PRIVATE-iteration-allocation')
            return original_reversed(registry)
        enter(mock.patch.object(runtime, 'reversed', side_effect=reverse, create=True))
        class Thread:
            def __init__(self, *, target, args):
                removing = memory.rollback
                if removing and memory.fault == 'thread-construction-fault':
                    memory.hit()
                    raise memory.secondary
                self.target, self.args, self.started = target, args, False
            def start(self):
                if memory.rollback and memory.fault == 'thread-start-after-one-drain-fault' and self.args[0] is memory.births[-1][2].stderr:
                    memory.hit()
                    raise memory.secondary
                self.started = True
                self.target(*self.args)
            def join(self, timeout):
                memory.case.assertGreaterEqual(timeout, 0)
                if memory.rollback and memory.fault == 'refuse-drain-join-fault':
                    memory.hit()
                    raise memory.secondary
                if not self.started:
                    raise RuntimeError('synthetic-unstarted-thread')
            def is_alive(self):
                return memory.rollback and memory.fault == 'drain-still-live'
        enter(mock.patch.object(host.threading, 'Thread', Thread))
        original_read = self.read
        def read(fd, maximum):
            if self.rollback and self.fault == 'drain-read-fault' and self.fds[fd] == '/synthetic-pipe-error':
                self.hit()
                raise self.secondary
            return original_read(fd, maximum)
        enter(mock.patch.object(runtime.os, 'read', side_effect=read))
        return self

    def root_main(self, phase, primary):
        import host_controller as host
        self.fixture_phase, self.primary = phase, primary
        repo = FixturePath('/synthetic-repo')
        source = {'head': binding()['source_head'], 'tree': binding()['source_tree'],
            'bytes': binding()['source_bytes_sha256'], 'workflow': binding()['workflow_sha256']}
        context = {'source': binding()['source_head'], 'event': binding()['event_sha']}
        memory = self
        class Timer:
            def __init__(self, interval, function):
                self.late = bool(memory.timers)
                if self.late and memory.fault.startswith('guard-constructor-'):
                    memory.hit()
                    fault = {'MemoryError': MemoryError, 'KeyboardInterrupt': KeyboardInterrupt,
                        'SystemExit': SystemExit}[memory.fault.rsplit('-', 1)[1]]
                    raise fault('PRIVATE-guard')
                self.interval, self.function = interval, function
                self.started = self.cancelled = False
                self.cancel_calls = 0
                self._daemon = False
                memory.timers.append(self)
            @property
            def daemon(self):
                return self._daemon
            @daemon.setter
            def daemon(self, value):
                if self.late and memory.fault == 'guard-daemon-assignment-fault':
                    memory.hit()
                    raise memory.secondary
                self._daemon = value
            def start(self):
                if self.late and memory.fault == 'guard-start-fault':
                    memory.hit()
                    raise memory.secondary
                self.started = True
            def cancel(self):
                self.cancel_calls += 1
                if self.late and memory.fault == 'proved-fence-guard-cancel-fault':
                    memory.hit()
                    raise memory.secondary
                self.cancelled = True
                if not self.late:
                    memory.after_cancel = True
                    if memory.fault == 'allowance-expired':
                        memory.hit()
                        memory.clock = 41.0
        real_remaining = bundle.remaining
        def remaining(deadline):
            if deadline == 40:
                memory.rollback = True
            if phase == 'late' and memory.after_cancel and deadline == 30 and not memory.primary_injected:
                memory.primary_injected = True
                memory.clock = max(memory.clock, 31.0)
                raise primary
            return real_remaining(deadline)
        def source_guard(*args, **kwargs):
            memory.source_calls += 1
            if memory.source_calls == 2:
                if phase == 'early' or memory.fault == 'after-latch-handoff-before-pointer-publication-fault':
                    memory.hit()
                    if memory.fault == 'allowance-expired':
                        memory.hit()
                        memory.clock = 41.0
                    raise primary
            return source
        original_publish = runtime.publish_pointer
        def publish(path, record, deadline, **kwargs):
            if path.name.startswith('row-cft-operation-') and memory.fault == 'pointer-publication-fault':
                memory.hit()
                raise primary
            return original_publish(path, record, deadline, **kwargs)
        original_diagnostic = runtime.preparation_diagnostic
        def diagnostic(error, *args):
            memory.diagnostics.append(error)
            return original_diagnostic(error, *args)
        def emit(*args, **kwargs):
            if 'file' not in kwargs:
                memory.case.assertIs(kwargs.get('flush'), True)
            if memory.fault in ('late-flushed-output-after-handoff', 'late-main-final-clock-after-original-cancel'):
                memory.hit()
                memory.clock = 31.0
        with ExitStack() as stack:
            enter = stack.enter_context
            enter(mock.patch.object(runtime, 'root_context', return_value=(repo, 1001, 1001, context)))
            enter(mock.patch.object(runtime, 'stage_readback', return_value={}))
            enter(mock.patch.object(host, 'source_guard', side_effect=source_guard))
            enter(mock.patch.object(runtime.bundle, 'acquire'))
            enter(mock.patch.object(runtime.bundle, 'install_pinned', return_value={'manifest_sha256': '9' * 64}))
            temp = enter(mock.patch.object(runtime.tempfile, 'TemporaryDirectory'))
            temp.return_value.__enter__.return_value = '/var/lib/synthetic-private'
            enter(mock.patch.object(runtime.secrets, 'token_hex', return_value='f' * 32))
            enter(mock.patch.object(runtime.threading, 'Timer', Timer))
            enter(mock.patch.object(bundle, 'remaining', side_effect=remaining))
            enter(mock.patch.object(runtime, 'publish_pointer', side_effect=publish))
            enter(mock.patch.object(runtime, 'preparation_diagnostic', side_effect=diagnostic))
            enter(mock.patch.object(runtime, 'print', side_effect=emit, create=True))
            enter(mock.patch.dict(runtime.os.environ, {'ROW_CFT_PREP_DEADLINE': '30', 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}))
            try:
                result = runtime.main()
            except BaseException as error:
                result = error
        return result


class RepairedRootMainFaultTests(unittest.TestCase):
    OWNER_FAULTS = ('allowance-expired', 'guard-constructor-MemoryError', 'guard-constructor-KeyboardInterrupt', 'guard-constructor-SystemExit', 'guard-daemon-assignment-fault', 'guard-start-fault', 'pre-provider-static-readback-fault', 'Popen-no-handle-fault', 'after-Popen-before-proc-identity-fault', 'proc-identity-mismatch', 'thread-construction-fault', 'thread-start-after-one-drain-fault', 'wait-interruption', 'wait-timeout', 'nonzero-returncode', 'private-stderr-present', 'real-65537-byte-drain-overflow', 'drain-read-fault', 'drain-close-fault', 'post-finish-input-drift', 'refuse-proc-inspection-fault', 'refuse-terminate-or-group-signal-fault', 'refuse-wait-fault', 'refuse-stdin-close-fault', 'refuse-drain-join-fault', 'cleanup_observed-false', 'cleanup_observed-interruption', 'retained-pipe-open', 'drain-still-live', 'poll-or-reap-contradiction', 'whole-fence-allocation-fault', 'proved-fence-guard-cancel-fault')
    PREPARE_FAULTS = ('parser-first4bytes-not-ELF', 'parser-mode-not-executable', 'parser-owner-or-parent-mode-refused', 'parser-descriptor-before-identity-drift', 'parser-descriptor-after-identity-drift', 'parser-path-readback-identity-drift', 'parser-metadata-size-bound-no-large-allocation', 'ABI-empty', 'ABI-missing-userns_create', 'ABI-control-byte', 'ABI-owner-or-mode-refused', 'ABI-stable-raw-pin-drift', 'sealed-profile-bytes-wrong-root-or-rule', 'sealed-profile-mode-not444', 'sealed-config-nonempty', 'sealed-config-mode-not444', 'sealed-ABI-bytes-drift', 'sealed-ABI-mode-not444', 'sealed-directory-not555-or-extra-member', 'intent-raw-binding-or-pin-drift', 'parent-open-fault', 'parent-descriptor-vs-path-drift', 'child-open-after-mkdir-fault', 'child-descriptor-vs-path-drift', 'child-fchmod-seal-or-parent-readback-fault', 'child-close-fault', 'parent-close-fault', 'both-close-faults-first-selected-close-preserved', 'before-parser-birth-interruption', 'after-parser-birth-before-identity-interruption', 'after-policy-load-before-static-readback-interruption', 'late-clock-after-policy-load-before-latch', 'after-latch-handoff-before-pointer-publication-fault', 'pointer-publication-fault', 'late-flushed-output-after-handoff', 'late-main-final-clock-after-original-cancel')

    def test_actual_main_early_and_late_rollback_fences_every_retained_owner(self):
        for phase in ('early', 'late'):
            for fault in self.OWNER_FAULTS:
                # Guard setup faults are possible only after original cancellation.
                if phase == 'early' and (fault.startswith('guard-') or fault == 'proved-fence-guard-cancel-fault'):
                    continue
                for primary in (RuntimeError('PRIVATE-primary'), KeyboardInterrupt('PRIVATE-primary'), SystemExit(7)):
                    with self.subTest(phase=phase, fault=fault, primary=type(primary)):
                        memory = RepairPolicyMemory(self, fault)
                        original_chain = (primary.__cause__, primary.__context__, primary.__suppress_context__)
                        with memory:
                            result = memory.root_main(phase, primary)
                            self.assertNotEqual(result, 0)
                            self.assertGreater(memory.fault_hits, 0, fault)
                            if phase == 'late':
                                self.assertIs(result, primary)
                                self.assertEqual(result.args, primary.args)
                                self.assertEqual((result.__cause__, result.__context__, result.__suppress_context__), original_chain)
                            else:
                                self.assertEqual(result, 1)
                                self.assertIs(memory.diagnostics[0], primary)
                            remove_births = [row for row in memory.births if '--remove' in row[0]]
                            if fault == 'allowance-expired' or fault.startswith('guard-'):
                                self.assertEqual(remove_births, [])
                            if remove_births:
                                self.assertTrue(all(row[2].pid in memory.processes for row in remove_births))
                                self.assertTrue(memory.timers[0].started)
                            if phase == 'late' and len(memory.timers) == 2:
                                late = memory.timers[1]
                                self.assertLessEqual(late.interval, 10)
                                self.assertIs(late.daemon, fault != 'guard-daemon-assignment-fault')
                                self.assertIs(late.started, fault not in ('guard-daemon-assignment-fault', 'guard-start-fault'))
                                self.assertLessEqual(late.cancel_calls, 1)
                                if late.cancelled:
                                    self.assertEqual(late.cancel_calls, 1)
                                    self.assertTrue(all(row[2].returncode is not None for row in remove_births))
                            self.assertLessEqual(memory.timers[0].cancel_calls, 1)
                            for _argv, _kwargs, process in memory.births:
                                self.assertTrue(process.stdin.closed or any(timer.started and not timer.cancelled for timer in memory.timers))
                                if fault != 'whole-fence-allocation-fault':
                                    self.assertGreater(memory.counts.get(('poll', process.pid), 0), 0)

    def test_actual_prepare_all36_reject_without_fabricating_handoff_or_completion(self):
        for fault in self.PREPARE_FAULTS:
            with self.subTest(fault=fault):
                memory = RepairPolicyMemory(self, fault)
                primary = memory.selected
                with memory:
                    result = memory.root_main('prepare', primary)
                    self.assertNotEqual(result, 0)
                    self.assertGreater(memory.fault_hits, 0, fault)
                    self.assertTrue(any(timer.started for timer in memory.timers))
                    pointer = runtime.pointer_path(binding())
                    if str(pointer) in memory.data:
                        self.assertIn(fault, ('pointer-publication-fault', 'late-flushed-output-after-handoff', 'late-main-final-clock-after-original-cancel'))
                    if fault.startswith(('parser-', 'ABI-', 'parent-', 'child-')) or fault.startswith('sealed-'):
                        self.assertEqual([row for row in memory.births if '--add' in row[0]], [])
                    if memory.close_faults:
                        self.assertTrue(memory.diagnostics)
                        self.assertIs(memory.diagnostics[0], memory.selected)

    def test_guard_normal_exit_limit_is_not_misreported_as_hard_cleanup(self):
        memory = RepairPolicyMemory(self, 'cleanup_observed-false')
        primary = RuntimeError('PRIVATE-primary')
        with memory:
            result = memory.root_main('late', primary)
            self.assertIs(result, primary)
            self.assertFalse(memory.timers[-1].cancelled)
            self.assertTrue(memory.timers[-1].daemon)
            self.assertEqual(memory.timers[-1].function.__name__, '<lambda>')
            # The fixture never invokes the os._exit callback or claims its scheduling.


if __name__ == '__main__':
    unittest.main()
