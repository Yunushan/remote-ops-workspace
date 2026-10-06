"""Pure synthetic contracts/mocks only: no host or browser evidence."""
import copy
import json
import unittest
from pathlib import PurePosixPath
from unittest.mock import Mock, patch

import browser_probe
import gate_contract as contract
import host_controller


def sample():
    binding = {'nonce': 'a' * 64, 'source_head': 'b' * 40, 'source_tree': 'c' * 40,
        'source_bytes_sha256': 'd' * 64, 'workflow_sha256': 'e' * 64, 'run_id': '12', 'run_attempt': '1',
        'event_sha': 'f' * 40, 'image_version': '20261006.1.0', 'image_os': 'ubuntu24'}
    runtime = {'chrome_version': '150.0.1.2', 'driver_version': '150.0.1.2', 'python_version': '3.14.7',
        'tool_inventory_sha256': '1' * 64, 'loaded_runtime_sha256': '2' * 64, 'loaded_runtime_files': 8}
    events = []
    for launch, case, method, status in ((1, 'api-read', 'GET', 200),
        (1, 'api-create-refresh', 'POST', 201), (1, 'api-create-refresh', 'GET', 200),
        (2, 'restart-persistence-auth-rotation', 'GET', 401),
        (2, 'restart-persistence-auth-rotation', 'GET', 200),
        (2, 'restart-persistence-auth-rotation', 'POST', 201),
        (2, 'service-worker-api-cache-boundary', 'GET', 200)):
        events.append({'launch': launch, 'ordinal': len(events) + 1, 'case': case, 'method': method,
            'route': 'catalogue', 'status': status, 'no_store': True, 'authorization_present': True})
    events.append({'launch': 2, 'ordinal': 8, 'case': 'service-worker-api-cache-boundary',
        'method': 'GET', 'route': 'policy', 'status': 200, 'no_store': True, 'authorization_present': True})
    record = {'schema': 'row.ubuntu-actual-catalogue-webdriver.v1', 'status': 'observations-complete-with-limits',
        'complete': True, 'binding': binding, 'runtime': runtime,
        'checks': [{'id': name, 'facts': copy.deepcopy(facts)} for name, facts in contract.CASES.items()],
        'inventories': [{'phase': phase, 'count': count, 'digest': digest * 64}
            for phase, count, digest in (('seed', 1, '3'), ('created', 2, '4'), ('restarted', 2, '4'), ('second-created', 3, '5'))],
        'events': events, 'cleanup': {'all_retained_zero': True, 'all_reaped': True, 'owned_groups_gone': True,
            'listeners_gone': True, 'forced_cleanup': False, 'descendants_complete': False},
        'elapsed_ms': 150000, 'server_down_ms': 100, 'source_unchanged': True, 'runtime_unchanged': True,
        'limits': list(contract.LIMITS), 'readiness_credit': 0}
    return record, {'binding': copy.deepcopy(binding), 'runtime': copy.deepcopy(runtime)}


class ContractTests(unittest.TestCase):
    def refused(self, alter):
        record, expected = sample()
        alter(record)
        with self.assertRaises(contract.GateRefusal) as error:
            contract.validate(json.dumps(record).encode(), expected)
        self.assertEqual(str(error.exception), 'catalogue-gate-contract-refused')

    def test_valid_synthetic_result_has_no_host_authority(self):
        record, expected = sample()
        result = contract.validate(json.dumps(record).encode(), expected)
        self.assertEqual(result['status'], 'result-contract-valid-only')
        self.assertFalse(result['genuine_host_authority'])
        self.assertEqual(result['readiness_credit'], 0)

    def test_same_major_different_observed_patch_refused(self):
        record, expected = sample()
        record['runtime']['driver_version'] = '150.0.1.3'
        expected['runtime']['driver_version'] = '150.0.1.3'
        with self.assertRaises(contract.GateRefusal):
            contract.validate(json.dumps(record).encode(), expected)

    def test_wrong_run_binding_refused(self):
        self.refused(lambda row: row['binding'].__setitem__('run_id', '13'))

    def test_boolean_count_is_not_integer(self):
        self.refused(lambda row: row['inventories'][0].__setitem__('count', True))

    def test_missing_genuine_case_refused(self):
        self.refused(lambda row: row['checks'].pop())

    def test_duplicate_ordered_case_refused(self):
        self.refused(lambda row: row['checks'].__setitem__(1, row['checks'][0]))

    def test_rotated_token_status_requires_actual_401(self):
        self.refused(lambda row: row['events'][3].__setitem__('status', 200))

    def test_restart_disk_digest_must_match_prior_write(self):
        self.refused(lambda row: row['inventories'][2].__setitem__('digest', '6' * 64))

    def test_api_cache_canary_failure_refused(self):
        self.refused(lambda row: row['checks'][5]['facts'].__setitem__('api_canary_bypassed', False))

    def test_storage_private_failure_refused(self):
        self.refused(lambda row: row['checks'][3]['facts'].__setitem__('storage_private_absent', False))

    def test_synthetic_pagehide_claim_refused(self):
        self.refused(lambda row: row['checks'][4]['facts'].__setitem__('synthetic_lifecycle_event_used', True))

    def test_forced_cleanup_cannot_pass(self):
        self.refused(lambda row: row['cleanup'].__setitem__('forced_cleanup', True))

    def test_missing_reaped_handle_refused(self):
        self.refused(lambda row: row['cleanup'].__setitem__('all_reaped', False))

    def test_deadline_overrun_refused(self):
        self.refused(lambda row: row.__setitem__('elapsed_ms', 300000))

    def test_changed_runtime_refused(self):
        self.refused(lambda row: row.__setitem__('runtime_unchanged', False))

    def test_boolean_score_is_not_zero(self):
        self.refused(lambda row: row.__setitem__('readiness_credit', False))

    def test_raw_private_field_rejected(self):
        self.refused(lambda row: row.__setitem__('token', 'synthetic-private-token'))

    def test_duplicate_json_key_fixed_refusal(self):
        with self.assertRaises(contract.GateRefusal):
            contract.decode(b'{"a":1,"a":2}')

    def test_nonfinite_and_invalid_utf8_fixed_refusal(self):
        for raw in (b'{"a":NaN}', b'{"a":"\xff"}'):
            with self.subTest(raw_digest=contract.hashlib.sha256(raw).hexdigest()):
                with self.assertRaises(contract.GateRefusal):
                    contract.decode(raw)

    def test_valid_oversized_json_hits_byte_bound(self):
        raw = json.dumps({'padding': 'x' * 65536}).encode()
        self.assertIsInstance(json.loads(raw), dict)
        with self.assertRaises(contract.GateRefusal):
            contract.decode(raw)

    def test_no_store_response_fact_required(self):
        self.refused(lambda row: row['events'][0].__setitem__('no_store', False))

    def test_duplicate_request_receipt_refused(self):
        self.refused(lambda row: row['events'].__setitem__(7, row['events'][0]))

    def test_untyped_event_shape_fixed_refusal(self):
        self.refused(lambda row: row['events'][0].__setitem__('method', ['GET']))

    def test_public_refusal_accepts_only_digest_count_enum_facts(self):
        record = {'schema': 'row.ubuntu-actual-catalogue-webdriver.v1', 'status': 'refused', 'complete': False,
            'phase': 'api-read', 'readiness_credit': 0, 'limits': contract.LIMITS,
            'private_streams': [{'stdout_bytes': 5, 'stdout_sha256': '1' * 64,
                'stderr_bytes': 9, 'stderr_sha256': '2' * 64, 'overflow': False}],
            'forced_cleanup_attempted': True, 'cleanup_complete': False}
        raw = json.dumps(record).encode()
        self.assertEqual(contract.public_bytes(raw), raw)
        record['private_streams'][0]['stderr_text'] = 'private-path-example'
        with self.assertRaises(contract.GateRefusal):
            contract.public_bytes(json.dumps(record).encode())

    def test_public_refusal_rejects_arbitrary_exception_or_path_phase(self):
        record = {'schema': 'row.ubuntu-actual-catalogue-webdriver.v1', 'status': 'refused', 'complete': False,
            'phase': '/private/path/error', 'readiness_credit': 0, 'limits': contract.LIMITS}
        with self.assertRaises(contract.GateRefusal):
            contract.public_bytes(json.dumps(record).encode())


class MockTransportTests(unittest.TestCase):
    def test_w3c_error_body_not_returned_or_printed(self):
        response = Mock(status=500)
        response.read.return_value = b'{"value":{"error":"unknown error","message":"private-example"}}'
        connection = Mock()
        connection.getresponse.return_value = response
        with patch.object(browser_probe.http.client, 'HTTPConnection', return_value=connection) as opener:
            driver = browser_probe.Driver(12345, 200)
            with patch.object(browser_probe.time, 'monotonic', return_value=100):
                with self.assertRaises(contract.GateRefusal) as error:
                    driver.call('GET', '/status')
            opener.assert_called_once_with('127.0.0.1', 12345, timeout=10)
        self.assertNotIn('private-example', str(error.exception))
        connection.close.assert_called_once()

    def test_deadline_refuses_before_http_creation(self):
        with patch.object(browser_probe.time, 'monotonic', return_value=201), patch.object(browser_probe.http.client, 'HTTPConnection') as opener:
            with self.assertRaises(contract.GateRefusal):
                browser_probe.Driver(12345, 200).call('GET', '/status')
            opener.assert_not_called()

    def test_external_navigation_refuses_before_transport(self):
        driver = browser_probe.Driver(12345, 200)
        driver.session, driver.origin = 'owned-session', 'http://127.0.0.1:12346'
        driver.call = Mock()
        with self.assertRaises(contract.GateRefusal):
            driver.command('/url', {'url': 'https://outside.example.invalid/'})
        driver.call.assert_not_called()

    def test_dom_form_actions_are_used_for_connect(self):
        driver = browser_probe.Driver(12345, 200)
        driver.fill, driver.click, driver.wait = Mock(), Mock(), Mock(return_value={'observed': True})
        self.assertEqual(driver.connect('synthetic-token', 1), {'observed': True})
        driver.fill.assert_called_once_with('#catalogue-token', 'synthetic-token')
        driver.click.assert_called_once_with('#catalogue-form button')

    def test_session_caps_select_owned_binary_profile_without_sandbox_bypass(self):
        driver = browser_probe.Driver(12345, 200)
        driver.call = Mock(return_value={'sessionId': 'owned-session', 'capabilities': {'observed': True}})
        driver.command = Mock()
        self.assertEqual(driver.start('/fixed/chrome', '/private/profile'), {'observed': True})
        caps = driver.call.call_args.args[2]['capabilities']['alwaysMatch']['goog:chromeOptions']
        self.assertEqual(caps['binary'], '/fixed/chrome')
        self.assertFalse(caps['detach'])
        self.assertIn('--user-data-dir=/private/profile', caps['args'])
        self.assertNotIn('--no-sandbox', caps['args'])

    def test_process_retained_before_birth_observation_failure(self):
        registry = []
        child = Mock(pid=12345)
        with patch.object(host_controller.subprocess, 'Popen', return_value=child), patch.object(host_controller, 'proc_identity', side_effect=contract.GateRefusal('fixed')), patch.object(host_controller.time, 'monotonic', return_value=100):
            with self.assertRaises(contract.GateRefusal):
                host_controller.Owned(registry, ['fixed'], '.', {}, 200)
        self.assertEqual(len(registry), 1)
        self.assertIs(registry[0].process, child)
        self.assertIsNone(registry[0].identity)

    def test_disk_dom_is_observation_not_constant_success(self):
        inventory = {'count': 1, 'profiles': [{'protocol': 'ssh', 'name': 'one', 'host': 'one.example.invalid', 'port': 22}]}
        self.assertTrue(host_controller.disk_dom({'texts': ['ssh • one • one.example.invalid:22'], 'rows': [{}]}, inventory))
        with self.assertRaises(contract.GateRefusal):
            host_controller.disk_dom({'texts': ['stale demo'], 'rows': [{}]}, inventory)

    def test_proc_birth_parser_keeps_stable_identity_fields(self):
        fields = ['S', '1', '123', '123'] + ['0'] * 15 + ['9876'] + ['0'] * 4
        path = Mock()
        path.read_text.return_value = '123 (driver with parentheses()) ' + ' '.join(fields)
        with patch.object(host_controller, 'Path', return_value=path):
            observed = host_controller.proc_identity(123)
        self.assertEqual(observed, {'pid': 123, 'group': 123, 'session': 123, 'start': 9876, 'state': 'S'})

    def test_listener_checks_birth_identity_not_changing_scheduler_state(self):
        owner = Mock()
        owner.process.poll.return_value = None
        owner.process.pid = 123
        owner.identity = {'pid': 123, 'group': 123, 'session': 123, 'start': 9876, 'state': 'R'}
        entry = Mock()
        directory = Mock()
        directory.iterdir.return_value = [entry]
        with patch.object(host_controller, 'proc_identity', return_value={**owner.identity, 'state': 'S'}), patch.object(host_controller, 'listener_inodes', return_value={'42': '0100007F'}), patch.object(host_controller, 'Path', return_value=directory), patch.object(host_controller.os, 'readlink', return_value='socket:[42]'):
            host_controller.owned_listener(owner, 12345)

    def test_child_environment_contains_no_inherited_authority(self):
        private = PurePosixPath('/synthetic-private')
        env = host_controller.child_env(private)
        self.assertNotIn('GITHUB_TOKEN', env)
        self.assertNotIn('HTTP_PROXY', env)
        self.assertNotIn('PYTHONPATH', env)
        self.assertEqual(env['ROW_HOME'], '/synthetic-private/state')


class FailureCleanupTests(unittest.TestCase):
    @staticmethod
    def owner(*, identity):
        owner = host_controller.Owned.__new__(host_controller.Owned)
        owner.process = Mock(pid=123)
        owner.process.poll.return_value = None
        owner.process.wait.return_value = -15
        owner.process.stdin.closed = False
        owner.identity = identity
        owner.reaped = False
        owner.finished = False
        owner.threads = []
        owner.stop_drains = host_controller.threading.Event()
        owner.overflow = host_controller.threading.Event()
        owner.queue = host_controller.queue.Queue(maxsize=128)
        owner.output = bytearray()
        owner.errors = bytearray()
        owner.deadline = 200
        return owner

    def test_unqualified_birth_still_terminates_and_reaps_retained_leader_only(self):
        owner = self.owner(identity=None)
        with patch.object(host_controller.os, 'killpg', create=True) as group_signal:
            owner.refuse_cleanup()
        owner.process.terminate.assert_called_once()
        owner.process.wait.assert_called_once_with(timeout=2)
        owner.process.kill.assert_not_called()
        group_signal.assert_not_called()
        self.assertTrue(owner.reaped)
        self.assertFalse(owner.finished)
        self.assertFalse(owner.cleanup_observed())
        self.assertTrue(owner.stop_drains.is_set())
        owner.process.stdout.close.assert_called_once()
        owner.process.stderr.close.assert_called_once()

    def test_unqualified_birth_timeout_kills_only_still_retained_child(self):
        owner = self.owner(identity=None)
        owner.process.wait.side_effect = [host_controller.subprocess.TimeoutExpired('fixed', 2), -9]
        with patch.object(host_controller.os, 'killpg', create=True) as group_signal:
            owner.refuse_cleanup()
        owner.process.terminate.assert_called_once()
        owner.process.kill.assert_called_once()
        self.assertEqual(owner.process.wait.call_count, 2)
        group_signal.assert_not_called()
        self.assertTrue(owner.reaped)
        self.assertFalse(owner.cleanup_observed())

    def test_reaped_leader_with_failed_drain_is_not_finished_or_cleanup_complete(self):
        identity = {'pid': 123, 'group': 123, 'session': 123, 'start': 9876, 'state': 'S'}
        owner = self.owner(identity=identity)
        owner.process.wait.return_value = 0
        owner.process.poll.return_value = 0
        thread = Mock()
        thread.is_alive.side_effect = [True, False]
        owner.threads = [thread]
        with patch.object(host_controller.time, 'monotonic', return_value=100), patch.object(host_controller, 'group_members', return_value=[{'pid': 124}]), patch.object(host_controller.os, 'killpg', create=True) as group_signal:
            with self.assertRaises(contract.GateRefusal):
                owner.finish()
            self.assertTrue(owner.reaped)
            self.assertFalse(owner.finished)
            owner.refuse_cleanup()
            self.assertTrue(owner.stop_drains.is_set())
            self.assertFalse(owner.cleanup_observed())
            group_signal.assert_not_called()  # Never signal a stale reaped leader's group ID.
        self.assertEqual(thread.join.call_count, 2)

    def test_framed_no_newline_overflow_stops_retention_and_never_enqueues(self):
        owner = self.owner(identity=None)
        stream = Mock()
        target = bytearray()
        chunks = [b'x' * 4096] * 20 + [b'']
        with patch.object(host_controller.time, 'monotonic', return_value=100), patch.object(host_controller.select, 'select', return_value=([stream], [], [])), patch.object(host_controller.os, 'read', side_effect=chunks) as reader:
            owner.drain(stream, target, True)
        self.assertTrue(owner.overflow.is_set())
        self.assertLessEqual(len(target), 65536)
        self.assertLess(len(target), sum(map(len, chunks)))
        self.assertTrue(owner.queue.empty())
        self.assertEqual(reader.call_count, 21)
        stream.close.assert_called_once()

    def test_stop_drain_flag_closes_stream_without_another_native_read(self):
        owner = self.owner(identity=None)
        owner.stop_drains.set()
        stream = Mock()
        with patch.object(host_controller.os, 'read') as reader, patch.object(host_controller.select, 'select') as waiter:
            owner.drain(stream, bytearray(), True)
        reader.assert_not_called()
        waiter.assert_not_called()
        stream.close.assert_called_once()


class QualificationMismatchTests(unittest.TestCase):
    def test_group_or_session_mismatch_never_grants_group_signal_authority(self):
        for group, session in ((999, 123), (123, 999)):
            with self.subTest(group=group, session=session):
                child = Mock(pid=123)
                child.poll.return_value = None
                child.wait.return_value = -15
                child.stdin.closed = False
                registry = []
                observed = {'pid': 123, 'group': group, 'session': session, 'start': 9876, 'state': 'S'}
                with patch.object(host_controller.subprocess, 'Popen', return_value=child), patch.object(host_controller, 'proc_identity', return_value=observed), patch.object(host_controller.time, 'monotonic', return_value=100), patch.object(host_controller.threading, 'Thread') as drain_thread, patch.object(host_controller.os, 'killpg', create=True) as group_signal:
                    with self.assertRaises(contract.GateRefusal):
                        host_controller.Owned(registry, ['fixed'], '.', {}, 200)
                    self.assertEqual(len(registry), 1)
                    owner = registry[0]
                    self.assertIs(owner.process, child)
                    self.assertIsNone(owner.identity)
                    owner.refuse_cleanup()
                    child.terminate.assert_called_once()
                    child.wait.assert_called_once_with(timeout=2)
                    child.kill.assert_not_called()
                    group_signal.assert_not_called()
                    drain_thread.assert_not_called()
                    self.assertTrue(owner.reaped)
                    self.assertFalse(owner.finished)
                    self.assertFalse(owner.cleanup_observed())


class PreparationDiagnosticTests(unittest.TestCase):
    @staticmethod
    def refused_record():
        return {'schema': 'row.ubuntu-actual-catalogue-webdriver.v1', 'status': 'refused',
            'complete': False, 'phase': 'preparation', 'readiness_credit': 0, 'limits': contract.LIMITS}

    def test_each_literal_preparation_step_is_privacy_valid(self):
        for step in contract.PREPARATION_STEPS:
            with self.subTest(step=step):
                record = self.refused_record()
                host_controller.preparation_note(record, step)
                raw = json.dumps(record).encode()
                self.assertEqual(contract.public_bytes(raw), raw)
                self.assertEqual(record['preparation_step'], step)
                self.assertFalse(record['complete'])
                self.assertEqual(record['readiness_credit'], 0)

    def test_unknown_private_or_wrong_type_step_is_refused(self):
        for step in ('private/path/example', 'exception-message-example', 'source-checks' * 100,
            '', True, 1, None, ['source-checks'], {'step': 'source-checks'}):
            with self.subTest(type_name=type(step).__name__):
                record = self.refused_record()
                record['preparation_step'] = step
                with self.assertRaises(contract.GateRefusal):
                    contract.public_bytes(json.dumps(record).encode())

    def test_marker_refuses_invalid_value_without_mutating_record(self):
        record = self.refused_record()
        original = copy.deepcopy(record)
        with self.assertRaises(contract.GateRefusal):
            host_controller.preparation_note(record, '/private/path')
        self.assertEqual(record, original)

    def test_marker_refuses_after_preparation_without_mutating_record(self):
        record = self.refused_record()
        record['phase'] = 'api-read'
        original = copy.deepcopy(record)
        with self.assertRaises(contract.GateRefusal):
            host_controller.preparation_note(record, 'source-checks')
        self.assertEqual(record, original)

    def test_only_runtime_transition_step_can_remain_at_runtime_phase(self):
        for step in contract.PREPARATION_STEPS:
            with self.subTest(step=step):
                record = self.refused_record()
                record.update(phase='host-runtime-observation', preparation_step=step)
                raw = json.dumps(record).encode()
                if step == 'runtime-checkpoint':
                    self.assertEqual(contract.public_bytes(raw), raw)
                else:
                    with self.assertRaises(contract.GateRefusal):
                        contract.public_bytes(raw)

    def test_preparation_step_is_refused_in_later_case(self):
        record = self.refused_record()
        record.update(phase='api-read', preparation_step='runtime-checkpoint')
        with self.assertRaises(contract.GateRefusal):
            contract.public_bytes(json.dumps(record).encode())

    def test_diagnostic_does_not_allow_private_exception_fields(self):
        record = self.refused_record()
        record.update(preparation_step='chrome-file-pin', exception='private-message')
        with self.assertRaises(contract.GateRefusal):
            contract.public_bytes(json.dumps(record).encode())

    def test_completed_result_cannot_carry_preparation_diagnostic(self):
        record, expected = sample()
        record['preparation_step'] = 'source-checks'
        with self.assertRaises(contract.GateRefusal):
            contract.validate(json.dumps(record).encode(), expected)


class ChromeFileDiagnosticTests(unittest.TestCase):
    @staticmethod
    def record():
        return {'schema': 'row.ubuntu-actual-catalogue-webdriver.v1', 'status': 'refused',
            'complete': False, 'phase': 'preparation', 'preparation_step': 'chrome-file-pin',
            'readiness_credit': 0, 'limits': contract.LIMITS}

    @staticmethod
    def fixture():
        before = Mock(st_mode=0o100755, st_nlink=1, st_size=50, st_uid=0,
            st_dev=1, st_ino=2, st_mtime_ns=3, st_ctime_ns=4)
        path = Mock()
        path.lstat.side_effect = [before, before]
        stream = Mock()
        stream.read.return_value = b'\x7fELF'
        path.open.return_value = Mock(__enter__=Mock(return_value=stream), __exit__=Mock(return_value=False))
        hasher = Mock()
        hasher.hexdigest.return_value = '1' * 64
        return path, before, stream, hasher

    @staticmethod
    def pin(path, hasher, diagnostic=None):
        with patch.object(host_controller, 'Path', return_value=path), patch.object(host_controller.os, 'getuid', return_value=1000, create=True), patch.object(host_controller.hashlib, 'file_digest', return_value=hasher, create=True):
            return host_controller.file_pin('/synthetic/not-accessed', trusted_owner=True, elf=True, diagnostic=diagnostic)

    def test_every_fixed_stage_is_privacy_valid_without_values_or_authority(self):
        self.assertEqual(len(contract.CHROME_FILE_STAGES), 16)
        for stage in contract.CHROME_FILE_STAGES:
            with self.subTest(stage=stage):
                record = self.record()
                host_controller.chrome_file_note(record, stage)
                raw = json.dumps(record).encode()
                self.assertEqual(contract.public_bytes(raw), raw)
                self.assertEqual(record['chrome_file_stage'], stage)
                self.assertFalse(record['complete'])
                self.assertEqual(record['readiness_credit'], 0)

    def test_unknown_private_or_untyped_stage_refuses_before_record_mutation(self):
        for stage in ('/private/file', 'error-message', '', 'lstat-before' * 100,
            True, 1, None, ['lstat-before'], {'stage': 'lstat-before'}):
            with self.subTest(type_name=type(stage).__name__):
                record = self.record()
                original = copy.deepcopy(record)
                with self.assertRaises(contract.GateRefusal):
                    host_controller.chrome_file_note(record, stage)
                self.assertEqual(record, original)
                record['chrome_file_stage'] = stage
                with self.assertRaises(contract.GateRefusal):
                    contract.public_bytes(json.dumps(record).encode())

    def test_stage_requires_exact_chrome_preparation_context(self):
        for phase, step in (('api-read', 'chrome-file-pin'), ('preparation', 'driver-file-pin'),
            ('host-runtime-observation', 'runtime-checkpoint'), ('preparation', None)):
            with self.subTest(phase=phase, step=step):
                record = self.record()
                record.update(phase=phase)
                if step is None:
                    record.pop('preparation_step')
                else:
                    record['preparation_step'] = step
                original = copy.deepcopy(record)
                with self.assertRaises(contract.GateRefusal):
                    host_controller.chrome_file_note(record, 'lstat-before')
                self.assertEqual(record, original)
                record['chrome_file_stage'] = 'lstat-before'
                with self.assertRaises(contract.GateRefusal):
                    contract.public_bytes(json.dumps(record).encode())

    def test_private_extra_and_completed_record_cannot_carry_stage(self):
        for field in ('path', 'exception', 'stat_uid', 'header'):
            with self.subTest(field=field):
                record = self.record()
                record.update(chrome_file_stage='regular-file')
                record[field] = 'private-detail'
                with self.assertRaises(contract.GateRefusal):
                    contract.public_bytes(json.dumps(record).encode())
        record, expected = sample()
        record['chrome_file_stage'] = 'stable-identity'
        with self.assertRaises(contract.GateRefusal):
            contract.validate(json.dumps(record).encode(), expected)

    def test_success_retains_pin_and_order_and_none_callback_contract(self):
        path, _, stream, hasher = self.fixture()
        stages = []
        pin = self.pin(path, hasher, stages.append)
        expected = {'sha256': '1' * 64, 'size': 50, 'device': 1, 'inode': 2,
            'mtime_ns': 3, 'ctime_ns': 4, 'mode': 0o755, 'uid': 0}
        self.assertEqual(pin, expected)
        self.assertEqual(stages, [stage for stage in contract.CHROME_FILE_STAGES if stage != 'root-owner'])
        stream.read.assert_called_once_with(4)
        stream.seek.assert_called_once_with(0)
        path, _, _, hasher = self.fixture()
        self.assertEqual(self.pin(path, hasher), expected)

    def test_metadata_guards_keep_exact_entered_stage_and_refusal(self):
        for field, value, stage in (('st_mode', 0o040755, 'regular-file'), ('st_nlink', 2, 'single-link'),
            ('st_size', 536870913, 'size-bound'), ('st_size', 0, 'nonempty'),
            ('st_mode', 0o100777, 'write-mode'), ('st_uid', 42, 'trusted-owner')):
            with self.subTest(stage=stage):
                record = self.record()
                path, before, _, hasher = self.fixture()
                setattr(before, field, value)
                with self.assertRaises(contract.GateRefusal) as error:
                    self.pin(path, hasher, lambda note, record=record: host_controller.chrome_file_note(record, note))
                self.assertEqual(str(error.exception), 'catalogue-gate-contract-refused')
                self.assertEqual(record['chrome_file_stage'], stage)
                self.assertEqual(contract.public_bytes(json.dumps(record).encode()), json.dumps(record).encode())
                path.open.assert_not_called()

    def test_io_failures_keep_only_entered_operation_without_exception_details(self):
        for stage in ('lstat-before', 'open', 'header-read', 'rewind', 'sha256-read', 'lstat-after'):
            with self.subTest(stage=stage):
                record = self.record()
                path, before, stream, hasher = self.fixture()
                error = OSError('private-detail-not-projected')
                if stage == 'lstat-before':
                    path.lstat.side_effect = error
                elif stage == 'open':
                    path.open.side_effect = error
                elif stage == 'header-read':
                    stream.read.side_effect = error
                elif stage == 'rewind':
                    stream.seek.side_effect = error
                elif stage == 'sha256-read':
                    hasher.hexdigest.side_effect = error
                else:
                    path.lstat.side_effect = [before, error]
                with self.assertRaises(OSError):
                    self.pin(path, hasher, lambda note, record=record: host_controller.chrome_file_note(record, note))
                self.assertEqual(record['chrome_file_stage'], stage)
                raw = json.dumps(record).encode()
                self.assertEqual(contract.public_bytes(raw), raw)
                self.assertNotIn(b'private-detail', raw)

    def test_elf_executable_and_identity_guards_remain_strict(self):
        for stage in ('elf-header', 'executable-mode', 'stable-identity'):
            with self.subTest(stage=stage):
                record = self.record()
                path, before, stream, hasher = self.fixture()
                if stage == 'elf-header':
                    stream.read.return_value = b'#!sh'
                elif stage == 'executable-mode':
                    before.st_mode = 0o100644
                else:
                    after = Mock(st_dev=1, st_ino=9, st_size=50, st_mtime_ns=3, st_ctime_ns=4)
                    path.lstat.side_effect = [before, after]
                with self.assertRaises(contract.GateRefusal):
                    self.pin(path, hasher, lambda note, record=record: host_controller.chrome_file_note(record, note))
                self.assertEqual(record['chrome_file_stage'], stage)
                raw = json.dumps(record).encode()
                self.assertEqual(contract.public_bytes(raw), raw)


if __name__ == '__main__':
    unittest.main(verbosity=2)
