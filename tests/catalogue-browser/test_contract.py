"""Pure synthetic contracts/mocks only: no host or browser evidence."""
import copy
import io
import json
import sys
import unittest
from contextlib import ExitStack
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
    record = {'schema': 'row.ubuntu-actual-catalogue-webdriver.v2', 'status': 'observations-complete-with-limits',
        'complete': True, 'binding': binding, 'runtime': runtime,
        'checks': [{'id': name, 'facts': copy.deepcopy(facts)} for name, facts in contract.CASES.items()],
        'inventories': [{'phase': phase, 'count': count, 'digest': digest * 64}
            for phase, count, digest in (('seed', 1, '3'), ('created', 2, '4'), ('restarted', 2, '4'), ('second-created', 3, '5'))],
        'events': events, 'cleanup': {'all_retained_zero': True, 'all_reaped': True, 'owned_groups_gone': True,
            'listeners_gone': True, 'forced_cleanup': False, 'descendants_complete': False},
        'elapsed_ms': 150000, 'server_down_ms': 100, 'source_unchanged': True, 'runtime_unchanged': True,
        'limits': list(contract.LIMITS), 'readiness_credit': 0}
    record['host_policy'] = synthetic_policy_evidence()
    record['host_policy_cleanup'] = synthetic_policy_cleanup()
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
        record = {'schema': 'row.ubuntu-actual-catalogue-webdriver.v2', 'status': 'refused', 'complete': False,
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
        record = {'schema': 'row.ubuntu-actual-catalogue-webdriver.v2', 'status': 'refused', 'complete': False,
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


class RuntimeDiagnosticTests(unittest.TestCase):
    @staticmethod
    def refused_record():
        return {'schema': 'row.ubuntu-actual-catalogue-webdriver.v2', 'status': 'refused',
            'complete': False, 'phase': 'host-runtime-observation', 'readiness_credit': 0,
            'limits': contract.LIMITS}

    def test_fixed_stages_and_mismatched_versions_are_only_refusal_metadata(self):
        for stage in contract.RUNTIME_STAGES:
            record = self.refused_record()
            host_controller.runtime_note(record, stage)
            raw = json.dumps(record).encode()
            self.assertEqual(contract.public_bytes(raw), raw)
            self.assertFalse(record['complete'])
            self.assertEqual(record['readiness_credit'], 0)
        record = self.refused_record()
        pair = {'chrome': '142.0.7444.175', 'driver': '142.0.7444.176'}
        host_controller.runtime_note(record, 'version-equality', pair)
        pair['chrome'] = '0.0.0.0'
        self.assertEqual(record['runtime_versions']['chrome'], '142.0.7444.175')
        raw = json.dumps(record).encode()
        self.assertEqual(contract.public_bytes(raw), raw)
        # The existing complete-result same-patch predicate is still strict.
        complete, expected = sample()
        complete['runtime']['driver_version'] = '142.0.7444.176'
        with self.assertRaises(contract.GateRefusal):
            contract.validate(json.dumps(complete).encode(), expected)

    def test_unknown_private_types_bounds_and_wrong_phase_refuse(self):
        for stage in ('/private/example', '', True, None, ['version-equality']):
            record = self.refused_record()
            record['runtime_stage'] = stage
            with self.subTest(stage=stage), self.assertRaises(contract.GateRefusal):
                contract.public_bytes(json.dumps(record).encode())
        for pair in ({'chrome': '/private/example', 'driver': '1.2.3.4'},
                     {'chrome': '1' * 65 + '.2.3.4', 'driver': '1.2.3.4'},
                     {'chrome': '1.2.3.4\n', 'driver': '1.2.3.4'},
                     {'chrome': True, 'driver': '1.2.3.4'},
                     {'chrome': '1.2.3.4', 'driver': '1.2.3.4', 'token': 'private'},
                     None):
            record = self.refused_record()
            record.update(runtime_stage='version-equality', runtime_versions=pair)
            with self.subTest(pair=pair), self.assertRaises(contract.GateRefusal):
                contract.public_bytes(json.dumps(record).encode())
        for phase in ('preparation', 'api-read', 'cleanup'):
            record = self.refused_record()
            record.update(phase=phase, runtime_stage='chrome-version-command')
            with self.subTest(phase=phase), self.assertRaises(contract.GateRefusal):
                contract.public_bytes(json.dumps(record).encode())
        record = self.refused_record()
        record.update(runtime_versions={'chrome': '1.2.3.4', 'driver': '1.2.3.4'})
        with self.assertRaises(contract.GateRefusal):
            contract.public_bytes(json.dumps(record).encode())
        record['runtime_stage'] = 'driver-version-command'
        with self.assertRaises(contract.GateRefusal):
            contract.public_bytes(json.dumps(record).encode())

    def test_marker_refuses_without_mutating_and_clears_stale_pair(self):
        record = self.refused_record()
        original = copy.deepcopy(record)
        with self.assertRaises(contract.GateRefusal):
            host_controller.runtime_note(record, '/private/example')
        self.assertEqual(record, original)
        record['phase'] = 'api-read'
        original = copy.deepcopy(record)
        with self.assertRaises(contract.GateRefusal):
            host_controller.runtime_note(record, 'chrome-version-command')
        self.assertEqual(record, original)
        record = self.refused_record()
        host_controller.runtime_note(record, 'version-equality', {'chrome': '1.2.3.4', 'driver': '1.2.3.4'})
        host_controller.runtime_note(record, 'chrome-version-command')
        self.assertNotIn('runtime_versions', record)

    def test_log_is_bounded_and_writer_failure_is_inert(self):
        record = self.refused_record()
        host_controller.runtime_note(record, 'version-equality', {'chrome': '1.2.3.4', 'driver': '1.2.3.5'})
        stream = io.StringIO()
        with patch.object(sys, 'stderr', stream):
            host_controller.emit_runtime_refusal(record)
        raw = stream.getvalue()
        self.assertTrue(raw.isascii())
        self.assertLessEqual(len(raw), 513)
        diagnostic = json.loads(raw)
        self.assertEqual(diagnostic['readiness_credit'], 0)
        self.assertEqual(diagnostic['runtime_versions'], record['runtime_versions'])
        class BrokenStream:
            def write(self, value):
                raise RuntimeError('/private/example')
        with patch.object(sys, 'stderr', BrokenStream()):
            self.assertIsNone(host_controller.emit_runtime_refusal(record))
        record['complete'] = True
        stream = io.StringIO()
        with patch.object(sys, 'stderr', stream):
            host_controller.emit_runtime_refusal(record)
        self.assertEqual(stream.getvalue(), '')


class PreparationDiagnosticTests(unittest.TestCase):
    @staticmethod
    def refused_record():
        return {'schema': 'row.ubuntu-actual-catalogue-webdriver.v2', 'status': 'refused',
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
        return {'schema': 'row.ubuntu-actual-catalogue-webdriver.v2', 'status': 'refused',
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


class RuntimeStartupDiagnosticTests(unittest.TestCase):
    STAGES = (
        'session-setup', 'initial-fixture-startup', 'initial-fixture-inventory',
        'driver-service-birth', 'driver-port-wait', 'driver-port-validation',
        'driver-listener', 'browser-client', 'browser-session-start',
        'browser-capabilities', 'loaded-runtime-inventory', 'loaded-runtime-tools',
    )

    def run_mock_main(self, failure_stage, *, note_failure=None, emission_failure=None,
                      write_failure=False):
        files, owners, labels, operations = {}, [], [], []
        error = contract.GateRefusal('synthetic-private-operation-refused')
        case = self

        class Sink:
            def __init__(self, path):
                self.path = path

            def __enter__(self):
                return self

            def write(self, raw):
                files[str(self.path)] = raw
                return len(raw)

            def __exit__(self, _kind, _error, _traceback):
                return False

        class MemoryPath(PurePosixPath):
            def resolve(self, strict=False):
                return self

            def exists(self):
                return str(self) in files

            def mkdir(self, mode=0o777, parents=False):
                pass

            def open(self, mode):
                case.assertEqual(mode, 'wb')
                return Sink(self)

            def replace(self, target):
                files[str(target)] = files.pop(str(self))
                return target

            def write_bytes(self, raw):
                files[str(self)] = raw
                return len(raw)

        def entered(stage):
            operations.append(stage)
            if failure_stage == stage:
                raise error

        def owned(registry, argv, cwd, env, deadline, *, frames=False):
            owner = Mock(finished=False, reaped=False, output=bytearray(), errors=bytearray())
            owner.overflow.is_set.return_value = False
            owner.cleanup_observed.return_value = True
            owner.process.poll.return_value = None
            owner.process.returncode = None
            registry.append(owner)
            owners.append(owner)
            entered('initial-fixture-startup' if frames else 'driver-service-birth')
            if frames:
                count = 0 if failure_stage == 'initial-fixture-inventory' else 1
                owner.receive.return_value = {'ready': True, 'nonce': 'a' * 64, 'port': 12345,
                    'inventory': {'count': count, 'profiles': [{}] * count, 'digest': '1' * 64}}
            else:
                case.assertEqual(argv, ['/synthetic/driver', '--port=0', '--enable-chrome-logs'])
                port = 0 if failure_stage == 'driver-port-validation' else 12346
                owner.output.extend(('ChromeDriver was started successfully on port ' + str(port)).encode())
                owner.process.poll.side_effect = lambda: entered('driver-port-wait')
            return owner

        def listener(owner, port):
            if owner is owners[-1] and len(owners) == 2:
                entered('driver-listener')

        driver = Mock()
        def start(binary, profile):
            entered('browser-session-start')
            return {'browserVersion': '9.9.9.9' if failure_stage == 'browser-capabilities' else '1.2.3.4',
                'chrome': {'chromedriverVersion': '1.2.3.4 synthetic', 'userDataDir': str(profile)}}
        driver.start.side_effect = start
        driver.command.side_effect = error

        def make_driver(port, deadline):
            entered('browser-client')
            return driver

        def loaded(owner):
            entered('loaded-runtime-inventory')
            return {} if failure_stage == 'loaded-runtime-tools' else {
                '/synthetic/chrome': {}, '/synthetic/driver': {}}

        tokens = iter(('a' * 64, 'b' * 64, 'c' * 64))
        def token(size):
            case.assertEqual(size, 32)
            entered('session-setup')
            return next(tokens)

        original_note = host_controller.runtime_note
        original_inert = host_controller.inert_runtime_note
        original_packed = host_controller.packed
        def note(public, stage, versions=None):
            if note_failure is not None and stage in self.STAGES:
                raise note_failure
            return original_note(public, stage, versions)

        def inert(public, stage):
            labels.append(stage)
            return original_inert(public, stage)

        def packed(value):
            if emission_failure is not None and not write_failure and value.get('schema') == 'row.catalogue-runtime-refusal.v1':
                raise emission_failure
            return original_packed(value)

        stream = io.StringIO()
        if write_failure:
            stream = Mock()
            stream.write.side_effect = emission_failure
        timer = Mock()
        patches = {
            'context': patch.object(host_controller, 'host_context', return_value={'source': 'a' * 40, 'event': 'b' * 40, 'image_version': '1.2'}),
            'paths': patch.object(host_controller, 'Path', MemoryPath),
            'directory': patch.object(host_controller, 'DIRECTORY', MemoryPath('/synthetic-repo/tests/catalogue-browser')),
            'temp': patch.object(host_controller.tempfile, 'TemporaryDirectory'),
            'chmod': patch.object(host_controller.os, 'chmod'),
            'env': patch.dict(host_controller.os.environ, {'GITHUB_WORKSPACE': '/synthetic-repo', 'RUNNER_TEMP': '/synthetic-temp'}),
            'clock': patch.object(host_controller.time, 'monotonic', return_value=100),
            'timer': patch.object(host_controller.threading, 'Timer', return_value=timer),
            'source': patch.object(host_controller, 'source_guard', return_value={'head': 'a' * 40, 'tree': 'b' * 40, 'bytes': 'c' * 64, 'workflow': 'd' * 64}),
            'selection': patch.object(host_controller, 'selected_runtime', return_value=(MemoryPath('/synthetic/chrome'), MemoryPath('/synthetic/driver'), {'provider': 'pinned-cft', 'installed': {'version': '1.2.3.4'}, 'host_policy': {}})),
            'policy_evidence': patch.object(host_controller, 'policy_evidence', return_value=synthetic_policy_evidence(observed=False)),
            'policy_tasks': patch.object(host_controller, 'observe_policy_tasks', side_effect=lambda holder, owner, deadline, *, checkpoint: synthetic_policy_evidence(initial_only=checkpoint == 'initial')),
            'pins': patch.object(host_controller, 'file_pin', return_value={'uid': 0}),
            'version_argv': patch.object(host_controller, 'chrome_version_argv', return_value=['/synthetic/chrome', '--product-version']),
            'version_match': patch.object(host_controller, 'chrome_version_match', return_value=(b'1.2.3.4', b'1.2.3.4')),
            'commands': patch.object(host_controller, 'command', side_effect=[b'1.2.3.4\n', b'ChromeDriver 1.2.3.4\n']),
            'owned': patch.object(host_controller, 'Owned', side_effect=owned),
            'listener': patch.object(host_controller, 'owned_listener', side_effect=listener),
            'driver': patch.object(host_controller, 'Driver', side_effect=make_driver),
            'loaded': patch.object(host_controller, 'loaded_runtime', side_effect=loaded),
            'tokens': patch.object(host_controller.secrets, 'token_hex', side_effect=token),
            'note': patch.object(host_controller, 'runtime_note', side_effect=note),
            'inert': patch.object(host_controller, 'inert_runtime_note', side_effect=inert),
            'packed': patch.object(host_controller, 'packed', side_effect=packed),
            'stderr': patch.object(host_controller.sys, 'stderr', stream),
            'birth': patch.object(host_controller.subprocess, 'Popen'),
            'transport': patch.object(host_controller.http.client, 'HTTPConnection'),
            'thread': patch.object(host_controller.threading, 'Thread'),
        }
        with ExitStack() as stack:
            mocks = {name: stack.enter_context(context) for name, context in patches.items()}
            mocks['temp'].return_value.__enter__.return_value = '/synthetic-private'
            code = host_controller.main()
            version_calls = [call.args[1] for call in mocks['note'].call_args_list if call.args[1] in contract.RUNTIME_STAGES[:3]]
            policy_calls = mocks['policy_tasks'].call_args_list
            expected_checkpoints = ['initial'] if 'loaded-runtime-inventory' in operations else []
            case.assertEqual([call.kwargs['checkpoint'] for call in policy_calls], expected_checkpoints)
            for call in policy_calls:
                case.assertIs(call.args[0], mocks['selection'].return_value[2]['host_policy'])
                case.assertIs(call.args[1], owners[1])
                case.assertEqual(len(call.args), 3)
                case.assertEqual(set(call.kwargs), {'checkpoint'})
            for name in ('birth', 'transport', 'thread'):
                mocks[name].assert_not_called()
        timer.start.assert_called_once()
        timer.cancel.assert_called_once()
        for owner in owners:
            owner.refuse_cleanup.assert_called_once()
            owner.cleanup_observed.assert_called_once()
        record = json.loads(files['/synthetic-repo/.tmp/catalogue-browser-public/result.json'])
        return code, record, labels, operations, driver, owners, version_calls

    def test_all_new_stages_are_bounded_fixed_refusal_projection(self):
        for stage in self.STAGES:
            with self.subTest(stage=stage):
                record = RuntimeDiagnosticTests.refused_record()
                host_controller.runtime_note(record, 'version-equality', {'chrome': '1.2.3.4', 'driver': '1.2.3.4'})
                host_controller.inert_runtime_note(record, stage)
                self.assertEqual(record['runtime_stage'], stage)
                self.assertNotIn('runtime_versions', record)
                raw = json.dumps(record).encode()
                self.assertEqual(contract.public_bytes(raw), raw)
                stream = io.StringIO()
                with patch.object(host_controller.sys, 'stderr', stream):
                    host_controller.emit_runtime_refusal(record)
                line = stream.getvalue()
                self.assertTrue(line.isascii())
                self.assertLessEqual(len(line.encode('ascii')), 512)
                self.assertEqual(set(json.loads(line)), {'schema', 'status', 'phase', 'readiness_credit', 'runtime_stage'})
                self.assertFalse(record['complete'])
                self.assertEqual(record['readiness_credit'], 0)

    def test_new_stages_cannot_carry_versions_or_cross_case_phase(self):
        for stage in self.STAGES:
            with self.subTest(stage=stage):
                record = RuntimeDiagnosticTests.refused_record()
                record.update(runtime_stage=stage, runtime_versions={'chrome': '1.2.3.4', 'driver': '1.2.3.4'})
                with self.assertRaises(contract.GateRefusal):
                    contract.public_bytes(json.dumps(record).encode())
                record.pop('runtime_versions')
                record['phase'] = 'api-read'
                with self.assertRaises(contract.GateRefusal):
                    contract.public_bytes(json.dumps(record).encode())

    def test_note_failures_are_inert_but_original_helper_remains_strict(self):
        for error in (RuntimeError('synthetic-private'), KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(kind=type(error).__name__):
                record = RuntimeDiagnosticTests.refused_record()
                original = copy.deepcopy(record)
                with patch.object(host_controller, 'runtime_note', side_effect=error) as reporter:
                    self.assertIsNone(host_controller.inert_runtime_note(record, 'session-setup'))
                    reporter.assert_called_once_with(record, 'session-setup')
                self.assertEqual(record, original)
        with self.assertRaises(contract.GateRefusal):
            host_controller.runtime_note(RuntimeDiagnosticTests.refused_record(), '/synthetic-private')

    def test_each_initial_failure_keeps_entered_stage_and_original_cleanup(self):
        for stage in self.STAGES:
            with self.subTest(stage=stage):
                code, record, labels, _, driver, owners, version_calls = self.run_mock_main(stage)
                self.assertEqual(code, 1)
                self.assertEqual(record['runtime_stage'], stage)
                self.assertEqual(labels, list(self.STAGES[:self.STAGES.index(stage) + 1]))
                self.assertEqual(record['phase'], 'host-runtime-observation')
                self.assertFalse(record['complete'])
                self.assertTrue(record['cleanup_complete'])
                self.assertEqual(record['forced_cleanup_attempted'], bool(owners))
                self.assertEqual(len(record['private_streams']), len(owners))
                self.assertNotIn('runtime_versions', record)
                self.assertEqual(record['readiness_credit'], 0)
                raw = json.dumps(record).encode()
                self.assertEqual(contract.public_bytes(raw), raw)
                self.assertNotIn(b'synthetic-private-operation-refused', raw)
                driver.command.assert_not_called()
                self.assertEqual(version_calls, ['chrome-version-command', 'driver-version-command', 'version-equality', 'version-equality'])

    def test_api_read_transition_clears_both_fields_and_retains_four_version_calls(self):
        code, record, labels, _, driver, owners, version_calls = self.run_mock_main('after-api')
        self.assertEqual(code, 1)
        self.assertEqual(record['phase'], 'api-read')
        self.assertNotIn('runtime_stage', record)
        self.assertNotIn('runtime_versions', record)
        self.assertEqual(labels, list(self.STAGES))
        self.assertEqual(len(owners), 2)
        driver.command.assert_called_once_with('/url', {'url': 'http://127.0.0.1:12345/index.html'})
        self.assertEqual(version_calls, ['chrome-version-command', 'driver-version-command', 'version-equality', 'version-equality'])
        raw = json.dumps(record).encode()
        self.assertEqual(contract.public_bytes(raw), raw)

    def test_interrupted_new_notes_do_not_replace_actual_operation_refusal(self):
        for error in (RuntimeError('synthetic-private'), KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(kind=type(error).__name__):
                code, record, labels, operations, driver, owners, _ = self.run_mock_main('browser-session-start', note_failure=error)
                self.assertEqual(code, 1)
                self.assertEqual(operations[-1], 'browser-session-start')
                self.assertEqual(labels[-1], 'browser-session-start')
                self.assertEqual(record['runtime_stage'], 'version-equality')
                self.assertEqual(len(owners), 2)
                self.assertTrue(record['cleanup_complete'])
                driver.command.assert_not_called()
                self.assertEqual(contract.public_bytes(json.dumps(record).encode()), json.dumps(record).encode())

    def test_emitter_interruptions_keep_main_refusal_cleanup_and_result_write(self):
        for error in (RuntimeError('synthetic-private'), KeyboardInterrupt(), SystemExit(9)):
            for write in (False, True):
                with self.subTest(kind=type(error).__name__, write=write):
                    code, record, _, operations, driver, _, _ = self.run_mock_main('browser-session-start', emission_failure=error, write_failure=write)
                    self.assertEqual(code, 1)
                    self.assertEqual(operations[-1], 'browser-session-start')
                    self.assertEqual(record['runtime_stage'], 'browser-session-start')
                    self.assertTrue(record['cleanup_complete'])
                    self.assertFalse(record['complete'])
                    self.assertEqual(record['readiness_credit'], 0)
                    driver.command.assert_not_called()
                    raw = json.dumps(record).encode()
                    self.assertEqual(contract.public_bytes(raw), raw)


class DriverStartDiagnosticTests(unittest.TestCase):
    GOOD = b'{"value":{"sessionId":"owned-session","capabilities":{"observed":true}}}'
    OK = b'{"value":null}'
    ERROR = b'{"value":{"error":"session not created","message":"PRIVATE-path-and-token","stacktrace":"PRIVATE-stack","data":{"path":"PRIVATE"}}}'

    def invoke(self, responses, *, request_error=None, close_error=None, deadline=200):
        connections = []
        for status, raw in responses:
            response = Mock(status=status)
            response.read.return_value = raw
            connection = Mock()
            connection.getresponse.return_value = response
            connections.append(connection)
        if request_error is not None:
            connections[0].request.side_effect = request_error
        if close_error is not None:
            connections[0].close.side_effect = close_error
        driver = browser_probe.Driver(12345, deadline)
        context = browser_probe.prepare_driver_start(driver)
        with patch.object(browser_probe.time, 'monotonic', return_value=100) as clock, \
             patch.object(browser_probe.http.client, 'HTTPConnection', side_effect=connections) as provider:
            try:
                value = driver.start('/fixed/chrome', '/PRIVATE/profile')
            except BaseException as error:
                value, selected = None, error
            else:
                selected = None
        return value, selected, driver, context, connections, provider, clock

    def test_success_retains_exact_two_requests_clock_and_close(self):
        value, error, driver, context, connections, provider, clock = self.invoke([(200, self.GOOD), (200, self.OK)])
        self.assertEqual(value, {'observed': True})
        self.assertIsNone(error)
        self.assertIsNone(context['attached'])
        self.assertEqual(driver.session, 'owned-session')
        self.assertEqual(clock.call_count, 2)
        self.assertEqual(provider.call_args_list, [unittest.mock.call('127.0.0.1', 12345, timeout=10)] * 2)
        first, second = (connection.request.call_args for connection in connections)
        self.assertEqual(first.args[:2], ('POST', '/session'))
        self.assertEqual(second.args[:2], ('POST', '/session/owned-session/timeouts'))
        caps = json.loads(first.kwargs['body'])['capabilities']['alwaysMatch']
        self.assertEqual(caps['goog:chromeOptions']['binary'], '/fixed/chrome')
        self.assertFalse(caps['goog:chromeOptions']['detach'])
        self.assertNotIn('--no-sandbox', caps['goog:chromeOptions']['args'])
        self.assertEqual(json.loads(second.kwargs['body']), {'script': 10000, 'pageLoad': 10000, 'implicit': 0})
        for connection in connections:
            connection.close.assert_called_once()
            connection.getresponse.return_value.read.assert_called_once_with(262145)

    def test_non200_boundaries_preserve_original_refusal_and_private_body(self):
        for responses, operation, count in (([(500, self.ERROR)], 'session-create', 1),
                                           ([(200, self.GOOD), (500, self.ERROR)], 'session-timeouts', 2)):
            with self.subTest(operation=operation):
                _value, error, driver, context, connections, provider, clock = self.invoke(responses)
                self.assertIs(type(error), contract.GateRefusal)
                self.assertEqual(error.args, ('catalogue-gate-contract-refused',))
                fields = browser_probe.driver_start_fields(context, error)
                self.assertEqual(fields, {'operation': operation, 'step': 'response-guard', 'exception': 'gate-refusal',
                                          'http_status': 500, 'webdriver_error': 'session not created'})
                self.assertNotIn('PRIVATE', json.dumps(fields))
                self.assertEqual(provider.call_count, count)
                self.assertEqual(clock.call_count, count)
                self.assertEqual(driver.session, None if count == 1 else 'owned-session')
                for connection in connections:
                    connection.close.assert_called_once()

    def test_decode_envelope_result_and_capability_failures(self):
        cases = ((b'{', 'response-decode', 'session-create'), (b'\xff', 'response-decode', 'session-create'),
                 (b'{"value":{},"value":{}}', 'response-decode', 'session-create'),
                 (b'{"value":NaN}', 'response-decode', 'session-create'),
                 (b'{}', 'value-envelope', 'session-create'),
                 (b'{"value":{"sessionId":"PRIVATE/id"}}', 'start-control', 'session-result'),
                 (b'{"value":{"sessionId":"owned-session"}}', 'start-control', 'session-capabilities'))
        for raw, step, operation in cases:
            with self.subTest(step=step, operation=operation, raw=raw[:20]):
                _value, error, _driver, context, connections, provider, _clock = self.invoke([(200, raw)])
                self.assertIsNotNone(error)
                fields = browser_probe.driver_start_fields(context, error)
                self.assertEqual((fields['step'], fields['operation']), (step, operation))
                if step == 'start-control':
                    self.assertIsNone(fields['http_status'])
                self.assertIsNone(fields['webdriver_error'])
                self.assertEqual(provider.call_count, 1)
                connections[0].close.assert_called_once()

    def test_body_bound_and_exact_status_types_remain_refusal(self):
        class Status(int):
            pass

        for status, raw in ((200, b'x' * 262145), (True, self.ERROR), (None, self.ERROR),
                            (500.0, self.ERROR), (99, self.ERROR), (600, self.ERROR), (Status(500), self.ERROR)):
            with self.subTest(status=status, length=len(raw)):
                _value, error, _driver, context, connections, _provider, _clock = self.invoke([(status, raw)])
                self.assertIs(type(error), contract.GateRefusal)
                fields = browser_probe.driver_start_fields(context, error)
                self.assertEqual(fields['step'], 'response-guard')
                self.assertIsNone(fields['webdriver_error'])
                self.assertEqual(fields['http_status'], 200 if status == 200 else None)
                connections[0].getresponse.return_value.read.assert_called_once_with(262145)
                connections[0].close.assert_called_once()

    def test_original_status_property_is_sampled_once(self):
        class Response:
            reads = 0

            @property
            def status(self):
                self.reads += 1
                return 500

            def read(self, maximum):
                self.maximum = maximum
                return DriverStartDiagnosticTests.ERROR

        response, connection = Response(), Mock()
        connection.getresponse.return_value = response
        driver = browser_probe.Driver(12345, 200)
        context = browser_probe.prepare_driver_start(driver)
        with patch.object(browser_probe.time, 'monotonic', return_value=100), \
             patch.object(browser_probe.http.client, 'HTTPConnection', return_value=connection):
            with self.assertRaises(contract.GateRefusal) as caught:
                driver.start('/fixed/chrome', '/PRIVATE/profile')
        self.assertEqual(response.reads, 1)
        self.assertEqual(response.maximum, 262145)
        self.assertEqual(browser_probe.driver_start_fields(context, caught.exception)['http_status'], 500)
        connection.close.assert_called_once()

    def test_deadline_transport_and_unknown_exception_identity(self):
        _value, error, _driver, context, connections, provider, _clock = self.invoke([(200, self.GOOD)], deadline=99)
        self.assertIs(type(error), contract.GateRefusal)
        self.assertEqual(browser_probe.driver_start_fields(context, error)['step'], 'call-preflight')
        provider.assert_not_called()
        connections[0].close.assert_not_called()
        for original, token in ((TimeoutError('PRIVATE'), 'timeout'), (ConnectionRefusedError('PRIVATE'), 'connection-refused'),
                                (ConnectionResetError('PRIVATE'), 'connection-reset'),
                                (browser_probe.http.client.RemoteDisconnected('PRIVATE'), 'remote-disconnected'),
                                (KeyboardInterrupt('PRIVATE'), 'interrupted'), (SystemExit(7), 'interrupted')):
            with self.subTest(token=token):
                _value, selected, _driver, context, connections, provider, _clock = self.invoke([(200, self.GOOD)], request_error=original)
                self.assertIs(selected, original)
                fields = browser_probe.driver_start_fields(context, selected)
                self.assertEqual((fields['step'], fields['exception']), ('request-send', token))
                self.assertNotIn('PRIVATE', json.dumps(fields))
                provider.assert_called_once()
                connections[0].close.assert_called_once()

    def test_finally_selected_close_error_wins_without_body_observations(self):
        for status, raw in ((200, self.GOOD), (500, self.ERROR)):
            original = RuntimeError('PRIVATE-close')
            with self.subTest(raw=raw[:20]):
                _value, selected, _driver, context, connections, _provider, _clock = self.invoke([(status, raw)], close_error=original)
                self.assertIs(selected, original)
                self.assertEqual(selected.args, ('PRIVATE-close',))
                if status == 200:
                    self.assertIsNone(selected.__context__)
                else:
                    self.assertIs(type(selected.__context__), contract.GateRefusal)
                fields = browser_probe.driver_start_fields(context, selected)
                self.assertEqual(fields['step'], 'connection-close')
                self.assertIsNone(fields['http_status'])
                self.assertIsNone(fields['webdriver_error'])
                connections[0].close.assert_called_once()

    def test_unknown_malformed_and_interrupted_error_inspection_is_inert(self):
        for raw, token in ((b'{"value":{"error":"PRIVATE-other"}}', 'other'),
                           (b'{"value":{"error":7}}', None), (b'{', None),
                           (b'{"value":{"error":"unknown error","error":"PRIVATE"}}', None),
                           (b'x' * 262145, None)):
            with self.subTest(token=token, length=len(raw)):
                _value, error, _driver, context, _connections, _provider, _clock = self.invoke([(500, raw)])
                self.assertIs(type(error), contract.GateRefusal)
                self.assertEqual(browser_probe.driver_start_fields(context, error)['webdriver_error'], token)
        for interruption in (KeyboardInterrupt(), SystemExit(9)):
            with patch.object(browser_probe, 'decode', side_effect=interruption):
                _value, error, _driver, context, connections, _provider, _clock = self.invoke([(500, self.ERROR)])
            self.assertIs(type(error), contract.GateRefusal)
            self.assertIsNone(browser_probe.driver_start_fields(context, error)['webdriver_error'])
            connections[0].close.assert_called_once()

    def test_reused_exception_failed_or_partial_annotation_never_projects_stale(self):
        class Poison(ValueError):
            armed = False
            partial = False

            def __setattr__(self, name, value):
                if name == '_row_driver_start_diagnostic' and self.armed:
                    if self.partial:
                        super().__setattr__(name, value)
                    raise KeyboardInterrupt('PRIVATE-poison')
                super().__setattr__(name, value)

        for partial in (False, True):
            original = Poison('PRIVATE-original')
            old_context = {'token': object(), 'active': True, 'call': None, 'attached': None}
            browser_probe._note_driver_start_failure(old_context, original, 'session-create')
            self.assertIsNotNone(browser_probe.driver_start_fields(old_context, original))
            original.partial, original.armed = partial, True
            _value, selected, _driver, context, connections, _provider, _clock = self.invoke([(200, self.GOOD)], request_error=original)
            self.assertIs(selected, original)
            self.assertEqual(selected.args, ('PRIVATE-original',))
            self.assertIsNone(context['attached'])
            self.assertIsNone(browser_probe.driver_start_fields(context, selected))
            connections[0].close.assert_called_once()

    def test_poisoned_read_or_context_setup_omits_diagnostic(self):
        class Poison(ValueError):
            armed = False

            def __getattribute__(self, name):
                if name == '_row_driver_start_diagnostic' and self.armed:
                    raise SystemExit(9)
                return super().__getattribute__(name)

        original = Poison('PRIVATE')
        _value, selected, _driver, context, _connections, _provider, _clock = self.invoke([(200, self.GOOD)], request_error=original)
        self.assertIsNotNone(browser_probe.driver_start_fields(context, selected))
        original.armed = True
        self.assertIsNone(browser_probe.driver_start_fields(context, selected))

        class BadDriver:
            def __setattr__(self, _name, _value):
                raise KeyboardInterrupt()

        bad_context = browser_probe.prepare_driver_start(BadDriver())
        self.assertFalse(bad_context['active'])
        self.assertIsNone(browser_probe.driver_start_fields(bad_context, selected))

    def test_new_collector_create_reset_and_annotation_faults_are_inert(self):
        for name in ('_driver_context', '_clear_driver_capture', '_note_driver_call_failure',
                     '_note_driver_start_failure', '_driver_error_token', '_driver_exception_token'):
            with self.subTest(helper=name), patch.object(browser_probe, name, side_effect=KeyboardInterrupt('PRIVATE')):
                _value, selected, _driver, context, connections, provider, _clock = self.invoke([(500, self.ERROR)])
            self.assertIs(type(selected), contract.GateRefusal)
            self.assertEqual(selected.args, ('catalogue-gate-contract-refused',))
            provider.assert_called_once()
            connections[0].close.assert_called_once()
            fields = browser_probe.driver_start_fields(context, selected)
            self.assertTrue(fields is None or fields['step'] == 'start-control')
        with patch.object(browser_probe, 'object', side_effect=SystemExit(9), create=True):
            _value, selected, _driver, context, connections, provider, _clock = self.invoke([(500, self.ERROR)])
        self.assertIsNone(context)
        self.assertIs(type(selected), contract.GateRefusal)
        provider.assert_called_once()
        connections[0].close.assert_called_once()

    def test_closed_public_projection_context_and_bound(self):
        fields = {'operation': 'session-create', 'step': 'response-guard', 'exception': 'gate-refusal',
                  'http_status': 500, 'webdriver_error': 'session not created'}
        record = RuntimeDiagnosticTests.refused_record()
        record['runtime_stage'] = 'browser-session-start'
        record['driver_start'] = fields
        raw = json.dumps(record).encode()
        self.assertEqual(contract.public_bytes(raw), raw)
        stream = io.StringIO()
        with patch.object(host_controller.sys, 'stderr', stream):
            host_controller.emit_runtime_refusal(record)
        self.assertTrue(stream.getvalue().isascii())
        self.assertLessEqual(len(stream.getvalue().encode('ascii')), 512)
        self.assertEqual(json.loads(stream.getvalue())['driver_start'], fields)
        for key, value in (('operation', 'PRIVATE'), ('step', 'PRIVATE'), ('exception', 'PRIVATE'),
                           ('http_status', True), ('http_status', 600), ('webdriver_error', 'PRIVATE')):
            wrong = copy.deepcopy(record)
            wrong['driver_start'][key] = value
            with self.assertRaises(contract.GateRefusal):
                contract.public_bytes(json.dumps(wrong).encode())
        for phase in ('api-read', 'preparation'):
            wrong = copy.deepcopy(record)
            wrong['phase'] = phase
            with self.assertRaises(contract.GateRefusal):
                contract.public_bytes(json.dumps(wrong).encode())
        for interruption in (KeyboardInterrupt(), SystemExit(9)):
            with patch.object(host_controller, 'packed', side_effect=interruption):
                host_controller.emit_runtime_refusal(record)

    def test_actual_main_projection_keeps_original_failure_cleanup(self):
        original_note = host_controller.driver_start_note

        def annotate(public, error, context):
            context['call'] = (error, {'step': 'response-guard', 'exception': 'gate-refusal',
                                      'http_status': 500, 'webdriver_error': 'session not created'})
            browser_probe._note_driver_start_failure(context, error, 'session-create')
            original_note(public, error, context)

        fixture = RuntimeStartupDiagnosticTests('test_all_new_stages_are_bounded_fixed_refusal_projection')
        with patch.object(host_controller, 'driver_start_note', side_effect=annotate):
            code, record, _labels, _operations, _driver, owners, _versions = fixture.run_mock_main('browser-session-start')
        self.assertEqual(code, 1)
        self.assertFalse(record['complete'])
        self.assertEqual(record['driver_start']['operation'], 'session-create')
        self.assertEqual(contract.public_bytes(json.dumps(record).encode()), json.dumps(record).encode())
        for owner in owners:
            owner.refuse_cleanup.assert_called_once()
            owner.cleanup_observed.assert_called_once()


class DriverMessageMarkerTests(unittest.TestCase):
    def invoke_message(self, message, *, status=500, token='session not created', timeouts=False, close_error=None):
        raw = json.dumps({'value': {'error': token, 'message': message,
                                   'stacktrace': '/PRIVATE/stack', 'data': {'token': '/PRIVATE/token'}}}).encode()
        fixture = DriverStartDiagnosticTests('test_success_retains_exact_two_requests_clock_and_close')
        responses = [(status, raw)]
        if timeouts:
            responses.insert(0, (200, fixture.GOOD))
        result = fixture.invoke(responses, close_error=close_error)
        return result, raw

    def test_each_fixed_marker_is_partial_positive_only(self):
        for bit, literals in browser_probe.DRIVER_MESSAGE_MARKERS:
            with self.subTest(bit=bit):
                (value, error, _driver, context, connections, provider, clock), _raw = self.invoke_message('\n'.join(literals))
                self.assertIsNone(value)
                self.assertIs(type(error), contract.GateRefusal)
                self.assertEqual(error.args, ('catalogue-gate-contract-refused',))
                fields = browser_probe.driver_start_fields(context, error)
                self.assertEqual(fields['message_bits'], bit)
                self.assertEqual(fields['http_status'], 500)
                self.assertEqual(fields['webdriver_error'], 'session not created')
                self.assertEqual(clock.call_count, 1)
                provider.assert_called_once()
                connections[0].close.assert_called_once()

    def test_multiple_markers_and_private_suffix_never_leave_bits(self):
        message = '\n'.join(literal for _bit, literals in browser_probe.DRIVER_MESSAGE_MARKERS for literal in literals)
        message += '\n/PRIVATE/profile TOKEN-VALUE PRIVATE-stack-data'
        (_value, error, _driver, context, _connections, _provider, _clock), _raw = self.invoke_message(message)
        fields = browser_probe.driver_start_fields(context, error)
        self.assertEqual(fields['message_bits'], 31)
        self.assertEqual(set(fields), {'operation', 'step', 'exception', 'http_status', 'webdriver_error', 'message_bits'})
        self.assertNotIn('PRIVATE', json.dumps(fields))
        for _bit, literals in browser_probe.DRIVER_MESSAGE_MARKERS:
            for literal in literals:
                self.assertNotIn(literal, json.dumps(fields))

    def test_unicode_codepoint_prefix_edge_and_partial_marker(self):
        literal = browser_probe.DRIVER_MESSAGE_MARKERS[0][1][0]
        at_edge = '\u2603' * (4096 - len(literal)) + literal
        self.assertGreater(len(at_edge.encode()), 4096)
        self.assertEqual(browser_probe._driver_message_bits(at_edge + '/PRIVATE/suffix'), 1)
        self.assertIsNone(browser_probe._driver_message_bits('\u2603' + at_edge))
        self.assertIsNone(browser_probe._driver_message_bits('x' * 4096 + literal))
        self.assertIsNone(browser_probe._driver_message_bits(literal[:-1]))
        (_value, error, _driver, context, _connections, _provider, _clock), _raw = self.invoke_message(at_edge)
        self.assertEqual(browser_probe.driver_start_fields(context, error)['message_bits'], 1)

    def test_unknown_missing_nonstring_and_subclass_omit_new_key(self):
        class Text(str):
            pass

        for message in (None, False, 1, [], {}, '', '/PRIVATE/unknown', Text(browser_probe.DRIVER_MESSAGE_MARKERS[0][1][0])):
            with self.subTest(message_type=type(message).__name__):
                self.assertIsNone(browser_probe._driver_message_bits(message))
        for value in ({'error': 'session not created'}, {'error': 'session not created', 'message': 7},
                      {'error': 'session not created', 'message': '/PRIVATE/unknown'}):
            raw = json.dumps({'value': value}).encode()
            fixture = DriverStartDiagnosticTests('test_success_retains_exact_two_requests_clock_and_close')
            _value, error, _driver, context, connections, _provider, _clock = fixture.invoke([(500, raw)])
            self.assertNotIn('message_bits', browser_probe.driver_start_fields(context, error))
            connections[0].close.assert_called_once()

    def test_old_token_return_seam_and_one_strict_decode_are_retained(self):
        literal = browser_probe.DRIVER_MESSAGE_MARKERS[0][1][0]
        raw = json.dumps({'value': {'error': 'session not created', 'message': literal}}).encode()
        with patch.object(browser_probe, 'decode', wraps=browser_probe.decode) as decoded:
            self.assertEqual(browser_probe._driver_error_token(raw), 'session not created')
            decoded.assert_called_once_with(raw, 262144)
        observation = {'message_bits': 31}
        with patch.object(browser_probe, 'decode', wraps=browser_probe.decode) as decoded:
            self.assertEqual(browser_probe._driver_error_token(raw, message_observation=observation), 'session not created')
            self.assertEqual(observation, {'message_bits': 1})
            decoded.assert_called_once_with(raw, 262144)
        with patch.object(browser_probe, '_driver_error_token', wraps=browser_probe._driver_error_token) as seam, \
             patch.object(browser_probe, 'decode', wraps=browser_probe.decode) as decoded:
            (_value, error, _driver, context, _connections, _provider, _clock), _raw = self.invoke_message(literal)
        self.assertEqual(seam.call_count, 1)
        self.assertEqual(decoded.call_count, 1)
        self.assertEqual(browser_probe.driver_start_fields(context, error)['message_bits'], 1)
        self.assertEqual(seam.call_args.args, (_raw,))

    def test_classifier_faults_and_malformed_returns_retain_five_fields(self):
        literal = browser_probe.DRIVER_MESSAGE_MARKERS[0][1][0]
        expected = {'operation': 'session-create', 'step': 'response-guard', 'exception': 'gate-refusal',
                    'http_status': 500, 'webdriver_error': 'session not created'}
        for interruption in (KeyboardInterrupt('/PRIVATE'), SystemExit(9), MemoryError('/PRIVATE'), RuntimeError('/PRIVATE')):
            with self.subTest(error_type=type(interruption).__name__), \
                 patch.object(browser_probe, '_driver_message_bits', side_effect=interruption):
                (_value, selected, _driver, context, connections, _provider, _clock), _raw = self.invoke_message(literal)
            self.assertIs(type(selected), contract.GateRefusal)
            self.assertEqual(selected.args, ('catalogue-gate-contract-refused',))
            self.assertEqual(browser_probe.driver_start_fields(context, selected), expected)
            connections[0].close.assert_called_once()
        class Integer(int):
            pass
        for bits in (None, False, True, 0, 32, 1.0, Integer(1), '/PRIVATE'):
            with self.subTest(bits_type=type(bits).__name__), patch.object(browser_probe, '_driver_message_bits', return_value=bits):
                (_value, selected, _driver, context, _connections, _provider, _clock), _raw = self.invoke_message(literal)
            self.assertEqual(browser_probe.driver_start_fields(context, selected), expected)

    def test_wrong_operation_status_and_error_token_drop_only_bits(self):
        literal = browser_probe.DRIVER_MESSAGE_MARKERS[0][1][0]
        with patch.object(browser_probe, '_driver_message_bits', wraps=browser_probe._driver_message_bits) as classifier:
            self.invoke_message(literal, status=501)
        classifier.assert_not_called()
        for status, token, timeouts in ((501, 'session not created', False),
                                       (500, 'unknown error', False), (500, 'session not created', True)):
            with self.subTest(status=status, token=token, timeouts=timeouts):
                (_value, error, _driver, context, _connections, provider, _clock), _raw = self.invoke_message(
                    literal, status=status, token=token, timeouts=timeouts)
                fields = browser_probe.driver_start_fields(context, error)
                self.assertNotIn('message_bits', fields)
                self.assertEqual(fields['http_status'], status)
                self.assertEqual(fields['webdriver_error'], token)
                self.assertEqual(fields['operation'], 'session-timeouts' if timeouts else 'session-create')
                self.assertEqual(provider.call_count, 2 if timeouts else 1)
        error = contract.GateRefusal('catalogue-gate-contract-refused')
        context = browser_probe.prepare_driver_start(Mock())
        context['call'] = (error, {'step': 'response-guard', 'exception': 'other', 'http_status': 500,
                                 'webdriver_error': 'session not created', 'message_bits': 31})
        browser_probe._note_driver_start_failure(context, error, 'session-create')
        fields = browser_probe.driver_start_fields(context, error)
        self.assertNotIn('message_bits', fields)
        self.assertEqual(fields['exception'], 'other')

    def test_close_winner_never_inspects_message_or_retains_response_bits(self):
        selected = RuntimeError('/PRIVATE/close')
        literal = browser_probe.DRIVER_MESSAGE_MARKERS[0][1][0]
        with patch.object(browser_probe, '_driver_message_bits', wraps=browser_probe._driver_message_bits) as classifier, \
             patch.object(browser_probe, 'decode', wraps=browser_probe.decode) as decoded:
            (_value, error, _driver, context, connections, _provider, _clock), _raw = self.invoke_message(
                literal, close_error=selected)
        self.assertIs(error, selected)
        self.assertEqual(error.args, ('/PRIVATE/close',))
        self.assertIs(type(error.__context__), contract.GateRefusal)
        fields = browser_probe.driver_start_fields(context, error)
        self.assertEqual(fields['step'], 'connection-close')
        self.assertIsNone(fields['http_status'])
        self.assertIsNone(fields['webdriver_error'])
        self.assertNotIn('message_bits', fields)
        classifier.assert_not_called()
        decoded.assert_not_called()
        connections[0].close.assert_called_once()

    def test_validator_closed_positive_types_and_eligible_context(self):
        fields = {'operation': 'session-create', 'step': 'response-guard', 'exception': 'gate-refusal',
                  'http_status': 500, 'webdriver_error': 'session not created'}
        self.assertEqual(contract.driver_start_diagnostic(fields), fields)
        for bits in range(1, 32):
            value = {**fields, 'message_bits': bits}
            self.assertEqual(contract.driver_start_diagnostic(value), value)
        class Integer(int):
            pass
        for bits in (False, True, 0, 32, -1, 1.0, None, Integer(1), '/PRIVATE'):
            with self.subTest(bits_type=type(bits).__name__), self.assertRaises(contract.GateRefusal):
                contract.driver_start_diagnostic({**fields, 'message_bits': bits})
        for key, value in (('operation', 'session-timeouts'), ('step', 'connection-close'),
                           ('exception', 'other'), ('http_status', 501), ('webdriver_error', 'unknown error')):
            wrong = {**fields, 'message_bits': 1, key: value}
            with self.subTest(key=key), self.assertRaises(contract.GateRefusal):
                contract.driver_start_diagnostic(wrong)
        with self.assertRaises(contract.GateRefusal):
            contract.driver_start_diagnostic({**fields, 'message_bits': 1, 'PRIVATE': 1})

    def test_fresh_attachment_roundtrip_reuse_and_poisoned_getter(self):
        class Poison(ValueError):
            armed = False
            partial = False
            unreadable = False
            def __setattr__(self, name, value):
                if name == '_row_driver_start_diagnostic' and self.armed:
                    if self.partial:
                        super().__setattr__(name, value)
                    raise KeyboardInterrupt('/PRIVATE')
                super().__setattr__(name, value)
            def __getattribute__(self, name):
                if name == '_row_driver_start_diagnostic' and self.unreadable:
                    raise SystemExit(9)
                return super().__getattribute__(name)
        fields = {'step': 'response-guard', 'exception': 'gate-refusal', 'http_status': 500,
                  'webdriver_error': 'session not created', 'message_bits': 31}
        for partial in (False, True):
            original = Poison('/PRIVATE-original')
            old = browser_probe.prepare_driver_start(Mock())
            old['call'] = (original, fields)
            browser_probe._note_driver_start_failure(old, original, 'session-create')
            self.assertEqual(browser_probe.driver_start_fields(old, original)['message_bits'], 31)
            current = browser_probe.prepare_driver_start(Mock())
            current['call'] = (original, fields)
            original.armed, original.partial = True, partial
            browser_probe._note_driver_start_failure(current, original, 'session-create')
            self.assertIsNone(current['attached'])
            self.assertIsNone(browser_probe.driver_start_fields(current, original))
            self.assertEqual(original.args, ('/PRIVATE-original',))
        original = Poison('/PRIVATE-original')
        current = browser_probe.prepare_driver_start(Mock())
        current['call'] = (original, fields)
        browser_probe._note_driver_start_failure(current, original, 'session-create')
        original.unreadable = True
        self.assertIsNone(browser_probe.driver_start_fields(current, original))

    def test_public_projection_bound_and_publication_interruptions(self):
        fields = {'operation': 'session-create', 'step': 'response-guard', 'exception': 'gate-refusal',
                  'http_status': 500, 'webdriver_error': 'session not created', 'message_bits': 31}
        record = RuntimeDiagnosticTests.refused_record()
        record['runtime_stage'], record['driver_start'] = 'browser-session-start', fields
        raw = json.dumps(record).encode()
        self.assertEqual(contract.public_bytes(raw), raw)
        output = io.StringIO()
        with patch.object(host_controller.sys, 'stderr', output):
            host_controller.emit_runtime_refusal(record)
        self.assertTrue(output.getvalue().isascii())
        self.assertLessEqual(len(output.getvalue().encode()), 351)
        self.assertEqual(json.loads(output.getvalue())['driver_start']['message_bits'], 31)
        for phase in ('preparation', 'api-read'):
            wrong = copy.deepcopy(record)
            wrong['phase'] = phase
            with self.assertRaises(contract.GateRefusal):
                contract.public_bytes(json.dumps(wrong).encode())
        for interruption in (KeyboardInterrupt(), SystemExit(9)):
            with patch.object(host_controller, 'packed', side_effect=interruption):
                host_controller.emit_runtime_refusal(record)
            stream = Mock()
            stream.write.side_effect = interruption
            with patch.object(host_controller.sys, 'stderr', stream):
                host_controller.emit_runtime_refusal(record)

    def test_malformed_decode_and_old_sink_reset_never_expose_stale_bits(self):
        for raw in (b'{', b'{"value":NaN}', b'{"value":{"error":"session not created","error":"PRIVATE"}}',
                    b'x' * 262145, b'\xff'):
            sink = {'message_bits': 31}
            self.assertIsNone(browser_probe._driver_error_token(raw, message_observation=sink))
            self.assertNotIn('message_bits', sink)
        class Sink(dict):
            def __setitem__(self, _key, _value):
                raise KeyboardInterrupt('/PRIVATE')
        literal = browser_probe.DRIVER_MESSAGE_MARKERS[0][1][0]
        raw = json.dumps({'value': {'error': 'session not created', 'message': literal}}).encode()
        with patch.object(browser_probe, 'decode', wraps=browser_probe.decode) as decoded:
            self.assertEqual(browser_probe._driver_error_token(raw, message_observation=Sink()), 'session not created')
            decoded.assert_called_once_with(raw, 262144)
        for interruption in (KeyboardInterrupt(), SystemExit(9)):
            sink = {'message_bits': 31}
            with patch.object(browser_probe, 'decode', side_effect=interruption):
                self.assertIsNone(browser_probe._driver_error_token(raw, message_observation=sink))
            self.assertNotIn('message_bits', sink)


class DriverPrivateStderrTests(unittest.TestCase):
    def captured(self, *, close_error=None, timeouts=False):
        fixture = DriverStartDiagnosticTests('test_success_retains_exact_two_requests_clock_and_close')
        responses = [(500, fixture.ERROR)]
        if timeouts:
            responses.insert(0, (200, fixture.GOOD))
        value, error, driver, context, connections, provider, clock = fixture.invoke(responses, close_error=close_error)
        record = RuntimeDiagnosticTests.refused_record()
        record['runtime_stage'] = 'browser-session-start'
        host_controller.driver_start_note(record, error, context)
        owner = object.__new__(host_controller.Owned)
        owner.errors = bytearray()
        return record, error, driver, context, owner, [owner], connections, provider, clock, value

    def test_each_fixed_literal_uses_current_owner_and_same_error(self):
        for bit, literals in host_controller.DRIVER_STDERR_MARKERS:
            with self.subTest(bit=bit):
                record, error, _driver, context, owner, registry, connections, provider, clock, value = self.captured()
                owner.errors.extend(b'\xff /PRIVATE/path TOKEN\n' + b'\n'.join(literals))
                old = copy.deepcopy(record['driver_start'])
                host_controller.driver_stderr_note(record, error, context, owner, registry)
                self.assertEqual(record['driver_start'], {**old, 'stderr_bits': bit})
                self.assertIsNone(value)
                self.assertEqual(error.args, ('catalogue-gate-contract-refused',))
                self.assertEqual(clock.call_count, 1)
                provider.assert_called_once()
                connections[0].close.assert_called_once()
                self.assertNotIn('PRIVATE', json.dumps(record))

    def test_combined_bits_bounded_public_projection_and_private_canaries(self):
        record, error, _driver, context, owner, registry, _connections, _provider, _clock, _value = self.captured()
        owner.errors.extend(b'\n'.join(literal for _bit, fragments in host_controller.DRIVER_STDERR_MARKERS for literal in fragments))
        owner.errors.extend(b'\n/PRIVATE/secret credential=TOKEN-VALUE')
        host_controller.driver_stderr_note(record, error, context, owner, registry)
        self.assertEqual(record['driver_start']['stderr_bits'], 63)
        raw = json.dumps(record).encode()
        self.assertEqual(contract.public_bytes(raw), raw)
        stream = io.StringIO()
        with patch.object(host_controller.sys, 'stderr', stream):
            host_controller.emit_runtime_refusal(record)
        line = stream.getvalue()
        self.assertTrue(line.isascii())
        self.assertLessEqual(len(line.encode('ascii')), 512)
        self.assertEqual(json.loads(line)['driver_start']['stderr_bits'], 63)
        self.assertNotIn('PRIVATE', line)
        self.assertNotIn('TOKEN-VALUE', line)
        for _bit, fragments in host_controller.DRIVER_STDERR_MARKERS:
            for literal in fragments:
                self.assertNotIn(literal.decode('ascii'), line)

    def test_single_immutable_prefix_boundary_and_exact_buffer_types(self):
        owner = object.__new__(host_controller.Owned)
        literal = host_controller.DRIVER_STDERR_MARKERS[1][1][0]
        owner.errors = bytearray(b'x' * (65536 - len(literal)) + literal)
        self.assertEqual(host_controller._driver_stderr_bits(owner, [owner]), 2)
        owner.errors = bytearray(b'x' + owner.errors)
        self.assertIsNone(host_controller._driver_stderr_bits(owner, [owner]))
        class Buffer(bytearray):
            pass
        for raw in (b'', b'No usable sandbox!', None, [], Buffer(literal), bytearray(), bytearray(literal[:-1])):
            owner.errors = raw
            self.assertIsNone(host_controller._driver_stderr_bits(owner, [owner]))
        original_bytes = bytes
        def copied(raw):
            snapshot = original_bytes(raw)
            owner.errors.clear()
            return snapshot
        owner.errors = bytearray(literal)
        with patch.object(host_controller, 'bytes', side_effect=copied, create=True) as snapshot:
            self.assertEqual(host_controller._driver_stderr_bits(owner, [owner]), 2)
            snapshot.assert_called_once()
        self.assertEqual(owner.errors, bytearray())

    def test_identity_membership_bounds_and_poisoned_owner_are_inert(self):
        owner = object.__new__(host_controller.Owned)
        owner.errors = bytearray(b'No usable sandbox!')
        class Wrong(host_controller.Owned):
            pass
        class Registry(list):
            pass
        class Equality:
            def __eq__(self, _other):
                raise AssertionError('equality-must-not-be-called')
        for candidate, registry in ((None, [owner]), (Mock(), [owner]), (object.__new__(Wrong), [owner]),
                                    (owner, []), (owner, [object()]), (owner, Registry([owner])),
                                    (owner, [owner] * 129)):
            self.assertIsNone(host_controller._driver_stderr_bits(candidate, registry))
        self.assertEqual(host_controller._driver_stderr_bits(owner, [Equality(), owner]), 2)
        original = host_controller.Owned.__getattribute__
        def poisoned(current, name):
            if name == 'errors':
                raise KeyboardInterrupt('/PRIVATE')
            return original(current, name)
        with patch.object(host_controller.Owned, '__getattribute__', poisoned):
            self.assertIsNone(host_controller._driver_stderr_bits(owner, [owner]))

    def test_new_faults_and_bad_returns_keep_old_fields_and_clear_stale_bits(self):
        for failure in (ValueError('/PRIVATE'), KeyboardInterrupt('/PRIVATE'), SystemExit('/PRIVATE')):
            record, error, _driver, context, owner, registry, _connections, _provider, _clock, _value = self.captured()
            old = copy.deepcopy(record['driver_start'])
            record['driver_start']['stderr_bits'] = 63
            with patch.object(host_controller, '_driver_stderr_bits', side_effect=failure):
                host_controller.driver_stderr_note(record, error, context, owner, registry)
            self.assertEqual(record['driver_start'], old)
            self.assertEqual(error.args, ('catalogue-gate-contract-refused',))
        for bits in (None, False, True, 0, 64, -1, 1.0, '1', {}, []):
            record, error, _driver, context, owner, registry, _connections, _provider, _clock, _value = self.captured()
            old = copy.deepcopy(record['driver_start'])
            with patch.object(host_controller, '_driver_stderr_bits', return_value=bits):
                host_controller.driver_stderr_note(record, error, context, owner, registry)
            self.assertEqual(record['driver_start'], old)
        record, error, _driver, context, owner, registry, _connections, _provider, _clock, _value = self.captured()
        old = copy.deepcopy(record['driver_start'])
        owner.errors.extend(b'No usable sandbox!')
        with patch.object(host_controller, 'driver_start_diagnostic', return_value={'PRIVATE': 'path'}):
            host_controller.driver_stderr_note(record, error, context, owner, registry)
        self.assertEqual(record['driver_start'], old)

    def test_reuse_wrong_context_and_poisoned_capture_do_not_use_old_bits(self):
        record, error, _driver, context, owner, registry, _connections, _provider, _clock, _value = self.captured()
        owner.errors.extend(b'No usable sandbox!')
        host_controller.driver_stderr_note(record, error, context, owner, registry)
        self.assertEqual(record['driver_start']['stderr_bits'], 2)
        context['attached'] = None
        host_controller.driver_stderr_note(record, error, context, owner, registry)
        self.assertNotIn('stderr_bits', record['driver_start'])
        for phase, stage in (('preparation', 'browser-session-start'), ('host-runtime-observation', 'driver-listener')):
            record, error, _driver, context, owner, registry, _connections, _provider, _clock, _value = self.captured()
            record.update(phase=phase, runtime_stage=stage)
            record['driver_start']['stderr_bits'] = 63
            host_controller.driver_stderr_note(record, error, context, owner, registry)
            self.assertNotIn('stderr_bits', record['driver_start'])
        record, error, _driver, context, owner, registry, _connections, _provider, _clock, _value = self.captured()
        record['driver_start']['stderr_bits'] = 63
        with patch.object(host_controller, 'driver_start_fields', side_effect=SystemExit('/PRIVATE')):
            host_controller.driver_stderr_note(record, error, context, owner, registry)
        self.assertNotIn('stderr_bits', record['driver_start'])

    def test_close_winner_and_timeouts_are_not_startup_stderr_context(self):
        winner = RuntimeError('/PRIVATE-close')
        for close_error, timeouts in ((winner, False), (None, True)):
            record, error, _driver, context, owner, registry, connections, provider, clock, _value = self.captured(close_error=close_error, timeouts=timeouts)
            owner.errors.extend(b'No usable sandbox!')
            host_controller.driver_stderr_note(record, error, context, owner, registry)
            self.assertNotIn('stderr_bits', record['driver_start'])
            if close_error is not None:
                self.assertIs(error, winner)
                self.assertEqual(record['driver_start']['step'], 'connection-close')
                self.assertIsNone(record['driver_start']['http_status'])
                self.assertIsNone(record['driver_start']['webdriver_error'])
                self.assertEqual(error.args, ('/PRIVATE-close',))
            self.assertEqual(provider.call_count, 2 if timeouts else 1)
            self.assertEqual(clock.call_count, provider.call_count)
            for connection in connections:
                connection.close.assert_called_once()

    def test_independent_validator_closes_types_ranges_keys_and_context(self):
        record, _error, _driver, _context, _owner, _registry, _connections, _provider, _clock, _value = self.captured()
        good = {**record['driver_start'], 'stderr_bits': 63}
        self.assertEqual(contract.driver_start_diagnostic(good), good)
        self.assertEqual(contract.driver_start_diagnostic({**good, 'message_bits': 31}), {**good, 'message_bits': 31})
        for key, value in (('stderr_bits', 0), ('stderr_bits', 64), ('stderr_bits', True), ('stderr_bits', 1.0),
                           ('stderr_bits', '2'), ('operation', 'session-timeouts'), ('http_status', 200),
                           ('http_status', True), ('webdriver_error', 'other'), ('step', 'response-decode'),
                           ('exception', 'other')):
            with self.subTest(key=key, value=value):
                with self.assertRaises(contract.GateRefusal):
                    contract.driver_start_diagnostic({**good, key: value})
        with self.assertRaises(contract.GateRefusal):
            contract.driver_start_diagnostic({**good, 'PRIVATE': 'path'})

    def test_actual_main_call_faults_preserve_original_refusal_and_cleanup(self):
        fixture = RuntimeStartupDiagnosticTests('test_all_new_stages_are_bounded_fixed_refusal_projection')
        for failure in (KeyboardInterrupt('/PRIVATE'), SystemExit('/PRIVATE')):
            with patch.object(host_controller, 'driver_stderr_note', side_effect=failure) as note:
                code, record, _labels, _operations, _driver, owners, _versions = fixture.run_mock_main('browser-session-start')
            self.assertEqual(code, 1)
            self.assertFalse(record['complete'])
            self.assertTrue(record['cleanup_complete'])
            self.assertTrue(record['forced_cleanup_attempted'])
            self.assertNotIn('PRIVATE', json.dumps(record))
            note.assert_called_once()
            self.assertEqual(len(owners), 2)

    def test_publication_interruptions_retain_selected_record(self):
        record, error, _driver, context, owner, registry, _connections, _provider, _clock, _value = self.captured()
        owner.errors.extend(b'No usable sandbox!')
        host_controller.driver_stderr_note(record, error, context, owner, registry)
        retained = copy.deepcopy(record)
        for failure in (KeyboardInterrupt('/PRIVATE'), SystemExit('/PRIVATE')):
            stream = Mock()
            stream.write.side_effect = failure
            with patch.object(host_controller.sys, 'stderr', stream):
                host_controller.emit_runtime_refusal(record)
            self.assertEqual(record, retained)
            self.assertEqual(error.args, ('catalogue-gate-contract-refused',))





def synthetic_policy_evidence(*, observed=True, initial_only=False):
    return {'scope': 'exact-pinned-chrome-userns', 'host_policy_changed': True,
        'default_browser_sandbox_requested': True, 'profile_loaded_preparation_observed': True,
        'task_label_initial_observed': observed, 'initial_observed_chrome_tasks': 2 if observed else 0,
        'task_label_final_observed': observed and not initial_only, 'final_observed_chrome_tasks': 2 if observed and not initial_only else 0,
        'profile_sha256': '3' * 64, 'abi_sha256': '4' * 64, 'tool_sha256': '5' * 64,
        'features_sha256': '6' * 64, 'intent_sha256': '7' * 64}


def synthetic_policy_cleanup(*, present=True):
    return {'status': 'removed' if present else 'already-absent',
        'profile_present_pre_remove_observed': present, 'remove_attempted': present,
        'profile_absent_observed': True, 'scalar_state_unchanged': True,
        'host_disposal_required': True, 'descendants_complete': False,
        **{key: synthetic_policy_evidence()[key] for key in contract.HOST_POLICY_DIGESTS}}


class HostPolicyContractTests(unittest.TestCase):
    def test_complete_publication_requires_present_removed_matching_cleanup(self):
        record, expected = sample()
        self.assertEqual(contract.validate(json.dumps(record).encode(), expected)['readiness_credit'], 0)
        for value in (None, {}, {'status': 'pending'}, synthetic_policy_cleanup(present=False),
                      {**synthetic_policy_cleanup(), 'profile_present_pre_remove_observed': False},
                      {**synthetic_policy_cleanup(), 'remove_attempted': 1},
                      {**synthetic_policy_cleanup(), 'profile_absent_observed': False},
                      {**synthetic_policy_cleanup(), 'intent_sha256': '0' * 64}):
            changed = copy.deepcopy(record)
            changed['host_policy_cleanup'] = value
            with self.subTest(value=value), self.assertRaises(contract.GateRefusal):
                contract.public_bytes(json.dumps(changed).encode())

    def test_pending_is_only_internal_and_never_public(self):
        record, expected = sample()
        record['host_policy_cleanup'] = {'status': 'pending'}
        self.assertEqual(contract.validate(json.dumps(record).encode(), expected,
            policy_cleanup_pending=True)['readiness_credit'], 0)
        with self.assertRaises(contract.GateRefusal):
            contract.public_bytes(json.dumps(record).encode())
        for flag in (1, None, 'true'):
            with self.subTest(flag=flag), self.assertRaises(contract.GateRefusal):
                contract.validate(json.dumps(record).encode(), expected, policy_cleanup_pending=flag)

    def test_both_task_samples_and_exact_count_types_required(self):
        record, expected = sample()
        for value in (synthetic_policy_evidence(observed=False),
                      {**synthetic_policy_evidence(), 'task_label_final_observed': False, 'final_observed_chrome_tasks': 0},
                      {**synthetic_policy_evidence(), 'task_label_initial_observed': False, 'initial_observed_chrome_tasks': 0},
                      {**synthetic_policy_evidence(), 'initial_observed_chrome_tasks': True},
                      {**synthetic_policy_evidence(), 'final_observed_chrome_tasks': 257},
                      {**synthetic_policy_evidence(), 'effective_sandbox': True},
                      {**synthetic_policy_evidence(), 'scope': '/PRIVATE'}):
            record['host_policy'] = value
            with self.subTest(keys=list(value)), self.assertRaises(contract.GateRefusal):
                contract.validate(json.dumps(record).encode(), expected)

    def test_partial_initial_only_is_private_refusal_evidence_never_complete(self):
        value = {**synthetic_policy_evidence(), 'task_label_final_observed': False, 'final_observed_chrome_tasks': 0}
        self.assertEqual(contract.host_policy_evidence(value), value)
        with self.assertRaises(contract.GateRefusal):
            contract.host_policy_evidence(value, complete=True)
        value['task_label_initial_observed'] = False
        value['initial_observed_chrome_tasks'] = 0
        value['task_label_final_observed'] = True
        value['final_observed_chrome_tasks'] = 1
        with self.assertRaises(contract.GateRefusal):
            contract.host_policy_evidence(value)

    def test_cleanup_exact_fields_and_status_relations(self):
        for key, value in (('tool_sha256', '/PRIVATE'), ('descendants_complete', True),
                           ('scalar_state_unchanged', False), ('profile', 'PRIVATE'),
                           ('host_disposal_required', False), ('profile_present_pre_remove_observed', 1)):
            row = {**synthetic_policy_cleanup(), key: value}
            with self.subTest(key=key), self.assertRaises(contract.GateRefusal):
                contract.host_policy_cleanup(row, synthetic_policy_evidence())
        row = synthetic_policy_cleanup(present=False)
        self.assertEqual(contract.host_policy_cleanup(row), row)
        with self.assertRaises(contract.GateRefusal):
            contract.host_policy_cleanup(row, synthetic_policy_evidence(), complete=True)

    def test_not_needed_and_already_absent_can_clean_only_refused_runs(self):
        not_needed = {'status': 'not-needed', 'intent_absent_observed': True,
            'host_disposal_required': True, 'descendants_complete': False}
        for cleanup in (not_needed, synthetic_policy_cleanup(present=False), synthetic_policy_cleanup()):
            record = {'schema': 'row.ubuntu-actual-catalogue-webdriver.v2', 'status': 'refused',
                'complete': False, 'phase': 'preparation', 'readiness_credit': 0,
                'limits': contract.LIMITS, 'host_policy_cleanup': cleanup}
            raw = json.dumps(record).encode()
            self.assertEqual(contract.public_bytes(raw), raw)
            self.assertNotIn(b'PRIVATE', raw)
            self.assertFalse(record['complete'])
        with self.assertRaises(contract.GateRefusal):
            contract.host_policy_cleanup(not_needed, synthetic_policy_evidence())

    def test_closed_public_serialization_retains_caps_and_no_private_names(self):
        record, expected = sample()
        raw = json.dumps(record).encode()
        self.assertLessEqual(len(raw), 65536)
        self.assertEqual(contract.public_bytes(raw), raw)
        self.assertEqual(contract.validate(raw, expected)['readiness_credit'], 0)
        for secret in (b'row-cft-userns-', b'/var/lib', b'PRIVATE', b'pid', b'policy_text'):
            self.assertNotIn(secret, raw)


class PolicyPublisherFixture:
    def __init__(self, case, failure='none'):
        from types import SimpleNamespace

        import cft_runtime as runtime
        self.runtime, self.case, self.failure = runtime, case, failure
        self.stack = ExitStack()
        self.clock = 100.0
        self.error = RuntimeError('PRIVATE-selected-publication-error')
        self.events = []
        self.record, _expected = sample()
        self.record['host_policy_cleanup'] = {'status': 'pending'}
        self.binding = {key: self.record['binding'][key] for key in ('source_head', 'source_tree',
            'source_bytes_sha256', 'workflow_sha256', 'event_sha', 'run_id', 'run_attempt')}
        root = '/var/lib/row-cft-' + 'f' * 32
        def pin(size, value):
            return {'bytes': size, 'sha256': value * 64, 'identity': [1, 2, 0o100444, 0, 0, 1, 0, size]}
        self.intent = {'schema': 'row.cft-userns-intent.v1', 'root': root,
            'directory': '/var/lib/row-cft-userns-' + 'f' * 32, 'name': 'row-cft-userns-' + 'f' * 32,
            'binding': self.binding.copy(), 'input_pins': {'profile': pin(100, '3'), 'config': pin(0, '0'), 'abi': pin(100, '4')},
            'tool_pin': pin(100, '5'), 'features_sha256': '6' * 64, 'profile_sha256': '3' * 64,
            'abi_sha256': '4' * 64, 'host_policy_change_planned': True, 'readiness_credit': 0}
        if failure == 'intent-binding':
            self.intent['binding']['source_tree'] = '0' * 40
        self.intent_raw = json.dumps(self.intent, sort_keys=True, separators=(',', ':')).encode()
        intent_sha = runtime.bundle.hashed(self.intent_raw)
        self.record['host_policy']['intent_sha256'] = intent_sha
        cleanup_observation = {**synthetic_policy_cleanup(present=failure != 'already-absent'), 'intent_sha256': intent_sha}
        self.cleanup = {'schema': 'row.cft-userns-cleanup.v1', 'binding': self.binding.copy(),
            'observation': cleanup_observation, 'readiness_credit': 0}
        if failure == 'run':
            self.cleanup['binding']['run_attempt'] = '2'
        if failure == 'digest':
            self.cleanup['observation']['profile_sha256'] = '0' * 64
        self.policy_raw = b'synthetic-enabled-policy'
        prep_evidence = {**synthetic_policy_evidence(observed=False), 'intent_sha256': intent_sha}
        self.pointer = {'schema': 'row.cft-runtime-operation.v2', 'root': root, 'binding': self.binding,
            'version': runtime.bundle.VERSION, 'policy_sha256': runtime.bundle.hashed(self.policy_raw),
            'manifest_sha256': '9' * 64, 'complete': True, 'vendor_binary_executed': False,
            'sandbox_policy': 'default-browser-with-scoped-host-userns-profile', 'host_policy': prep_evidence,
            'readiness_credit': 0}
        if failure == 'pointer-root':
            self.pointer['root'] = '/var/lib/row-cft-' + 'e' * 32
        self.source = '/synthetic-repo/.tmp/catalogue-browser-public/result.json'
        self.temporary = '/synthetic-repo/.tmp/catalogue-browser-public/host-policy-result.tmp'
        self.data = {self.source: json.dumps(self.record).encode()}
        self.counts = {}
        fixture = self
        class MemoryPath(PurePosixPath):
            def resolve(self, *args, **kwargs):
                return self
            def lstat(self):
                return SimpleNamespace(st_mode=(0o40700 if self.name == 'catalogue-browser-public' else 0o100600),
                    st_uid=1001, st_nlink=1)
            def exists(self):
                return str(self) in fixture.data or self.name.startswith('row-cft-operation-')
            def is_symlink(self):
                return False
            def replace(self, destination):
                if fixture.failure == 'replace':
                    raise fixture.error
                fixture.data[str(destination)] = fixture.data.pop(str(self))
                fixture.events.append('replace')
                return destination
        self.Path = MemoryPath

    def read(self, path, maximum, deadline, *, raw=False, **kwargs):
        self.events.append(('read', path.name, raw))
        self.counts[path.name] = self.counts.get(path.name, 0) + 1
        if path.name == 'result.json':
            data = self.data[self.source]
            if self.failure == 'source-readback' and self.counts[path.name] > 1:
                data += b' '
            if 'replace' in self.events and self.failure == 'final-readback':
                raise self.error
            if 'replace' in self.events and self.failure == 'final-clock':
                self.clock = 121.0
        elif path.name.startswith('row-cft-policy-cleanup-'):
            data = json.dumps(self.cleanup).encode()
        elif path.name.startswith('row-cft-policy-intent-'):
            data = self.intent_raw
        elif path.name.startswith('row-cft-operation-'):
            data = json.dumps(self.pointer).encode()
        elif path.name == 'cft-runtime-policy.json':
            data = self.policy_raw
        else:
            self.case.fail('unmocked-publisher-file')
        self.case.assertLessEqual(len(data), maximum)
        result = {'bytes': len(data), 'sha256': self.runtime.bundle.hashed(data),
            'identity': [1, 2, 0o100444, 0, 0, 1, 0, len(data)]}
        return (result, data) if raw else result

    def writer(self, path, access_mode, flags, deadline, *, mode):
        fixture = self
        self.case.assertEqual(str(path), self.temporary)
        self.case.assertEqual((access_mode, mode), ('wb', 0o600))
        self.events.append('writer')
        class Stream(io.BytesIO):
            def write(self, raw):
                if fixture.failure == 'write':
                    raise fixture.error
                return super().write(raw)
            def flush(self):
                if fixture.failure == 'flush':
                    raise fixture.error
                if fixture.failure == 'late-flush':
                    fixture.clock = 121.0
                return super().flush()
            def fileno(self):
                return 7
        class Writer:
            def __enter__(self):
                self.stream = Stream()
                return self.stream
            def __exit__(self, *_args):
                fixture.data[fixture.temporary] = self.stream.getvalue()
                self.stream.close()
                if fixture.failure == 'close':
                    raise fixture.error
                return False
        return Writer()

    def __enter__(self):
        enter = self.stack.enter_context
        enter(patch.object(host_controller, 'Path', self.Path))
        enter(patch.object(self.runtime, 'Path', self.Path))
        enter(patch.object(host_controller, 'DIRECTORY', self.Path('/synthetic-repo/tests/catalogue-browser')))
        enter(patch.object(host_controller, 'host_context', return_value={'source': self.binding['source_head'], 'event': self.binding['event_sha']}))
        for getter in ('getuid', 'geteuid', 'getgid', 'getegid'):
            enter(patch.object(host_controller.os, getter, return_value=1001, create=True))
        for name, value in (('O_NOFOLLOW', 131072),):
            enter(patch.object(host_controller.os, name, value, create=True))
        enter(patch.dict(host_controller.os.environ, {'GITHUB_WORKSPACE': '/synthetic-repo', 'GITHUB_RUN_ID': '12',
            'GITHUB_RUN_ATTEMPT': '1', 'ROW_CFT_CLEANUP_OUTCOME': 'success'}))
        enter(patch.object(host_controller.time, 'monotonic', side_effect=lambda: self.clock))
        enter(patch.object(host_controller, 'file_pin', return_value={'sha256': self.binding['workflow_sha256']}))
        enter(patch.object(self.runtime.bundle, 'stable_file', side_effect=self.read))
        enter(patch.object(self.runtime.bundle, 'policy', return_value={}))
        enter(patch.object(self.runtime, 'policy_inputs'))
        enter(patch.object(self.runtime, 'host_features', return_value='6' * 64))
        enter(patch.object(self.runtime, 'profile_membership', side_effect=PermissionError('PRIVATE')))
        enter(patch.object(self.runtime.bundle, 'owned_binary', side_effect=self.writer))
        enter(patch.object(host_controller.os, 'fsync', side_effect=self.error if self.failure == 'fsync' else None))
        self.native = enter(patch.object(host_controller.subprocess, 'Popen', side_effect=AssertionError('unexpected-native-provider')))
        self.transport = enter(patch.object(host_controller.http.client, 'HTTPConnection', side_effect=AssertionError('unexpected-network')))
        return self

    def __exit__(self, *_args):
        self.native.assert_not_called()
        self.transport.assert_not_called()
        self.stack.close()
        return False


class HostPolicyPublisherTests(unittest.TestCase):
    def test_cleanup_outcome_refuses_before_any_file_IO(self):
        import cft_runtime as runtime
        for outcome in ('failure', 'skipped', 'cancelled', '', None):
            env = {} if outcome is None else {'ROW_CFT_CLEANUP_OUTCOME': outcome}
            with self.subTest(outcome=outcome), patch.object(host_controller, 'host_context', return_value={}), \
                    patch.object(host_controller.os, 'getuid', return_value=1001, create=True), \
                    patch.object(host_controller.os, 'geteuid', return_value=1001, create=True), \
                    patch.object(host_controller.os, 'getgid', return_value=1001, create=True), \
                    patch.object(host_controller.os, 'getegid', return_value=1001, create=True), \
                    patch.dict(host_controller.os.environ, env, clear=True), \
                    patch.object(runtime.bundle, 'stable_file') as read:
                with self.assertRaises(contract.GateRefusal):
                    host_controller.bind_host_policy_cleanup()
            read.assert_not_called()

    def test_actual_publisher_accepts_one_fully_bound_removed_capsule(self):
        with PolicyPublisherFixture(self) as fixture:
            host_controller.bind_host_policy_cleanup()
            final = json.loads(fixture.data[fixture.source])
            self.assertTrue(final['complete'])
            self.assertTrue(final['host_policy_cleanup']['profile_present_pre_remove_observed'])
            self.assertEqual(final['host_policy_cleanup']['status'], 'removed')
            self.assertEqual(contract.public_bytes(fixture.data[fixture.source]), fixture.data[fixture.source])
            self.assertEqual(fixture.events.count('writer'), 1)
            self.assertEqual(fixture.events.count('replace'), 1)

    def test_source_run_profile_and_absence_mismatches_never_write(self):
        for failure in ('run', 'digest', 'intent-binding', 'pointer-root', 'already-absent', 'source-readback'):
            with self.subTest(failure=failure), PolicyPublisherFixture(self, failure) as fixture:
                with self.assertRaises((contract.GateRefusal, fixture.runtime.bundle.BundleRefusal)):
                    host_controller.bind_host_policy_cleanup()
                self.assertNotIn('writer', fixture.events)
                self.assertEqual(json.loads(fixture.data[fixture.source])['host_policy_cleanup'], {'status': 'pending'})

    def test_write_flush_close_replace_and_readback_errors_remain_refusals(self):
        for failure in ('write', 'flush', 'close', 'fsync', 'replace', 'final-readback'):
            with self.subTest(failure=failure), PolicyPublisherFixture(self, failure) as fixture:
                with self.assertRaises(RuntimeError) as caught:
                    host_controller.bind_host_policy_cleanup()
                self.assertIs(caught.exception, fixture.error)
                self.assertNotIn(b'PRIVATE', fixture.data[fixture.source])

    def test_late_flush_and_final_clock_never_return_positive(self):
        for failure in ('late-flush', 'final-clock'):
            with self.subTest(failure=failure), PolicyPublisherFixture(self, failure) as fixture:
                with self.assertRaises(fixture.runtime.bundle.BundleRefusal):
                    host_controller.bind_host_policy_cleanup()
                if failure == 'late-flush':
                    self.assertNotIn('replace', fixture.events)


class ActualPolicyCheckpointMainTests(unittest.TestCase):
    def run_actual_main(self, *, final_label_failure, failure_phase=None, failure_error=None, diagnostic_stream=None, service_worker_result=None):
        import hashlib
        import stat
        import threading

        import cft_bundle as bundle
        import cft_runtime as policy_runtime
        from test_cft_runtime import FixturePath, PolicyMemory, binding, policy_raw

        case = self
        memory = PolicyMemory()
        memory.case = self
        memory.data['/synthetic-repo/tests/catalogue-browser/cft-runtime-policy.json'] = policy_raw()
        memory.modes['/synthetic-repo/tests/catalogue-browser/cft-runtime-policy.json'] = stat.S_IFREG | 0o444
        holder, policy_registry, files, owners, task_calls, native_calls = {}, [], {}, [], [], []
        source_binding = binding()
        source = {'head': source_binding['source_head'], 'tree': source_binding['source_tree'],
            'bytes': source_binding['source_bytes_sha256'], 'workflow': source_binding['workflow_sha256']}
        context = {'source': source_binding['source_head'], 'event': source_binding['event_sha'],
            'image_version': '20261006.1.0'}
        root = FixturePath('/var/lib/row-cft-' + 'f' * 32)
        chrome = root / bundle.EXECUTABLES['chrome']
        chrome_driver = root / bundle.EXECUTABLES['chromedriver']
        profiles = [{'protocol': 'ssh', 'name': 'catalogue seed', 'host': 'seed.example.invalid', 'port': 22}]
        events, replace_false = [], []
        state = {'launch': 0, 'case': 'api-read', 'alive': False, 'connected': False,
            'old_rejected': False, 'down': False, 'pending': None}
        def event(method, status, *, route='catalogue'):
            events.append({'launch': state['launch'], 'ordinal': len(events) + 1,
                'case': state['case'], 'method': method, 'route': route, 'status': status,
                'no_store': True, 'authorization_present': True})
        def inventory():
            digest = hashlib.sha256(json.dumps(profiles, sort_keys=True).encode()).hexdigest()
            return {'count': len(profiles), 'profiles': copy.deepcopy(profiles), 'digest': digest,
                'disk_digest': digest, 'events': copy.deepcopy(events), 'posts_replace_false': list(replace_false)}
        def snapshot():
            visible = state['connected'] and state['alive']
            texts = [row['protocol'] + ' \u2022 ' + row['name'] + ' \u2022 ' + row['host'] + ':' + str(row['port'])
                for row in profiles] if visible else []
            return {'busy': False, 'texts': texts, 'rows': [dict(row) for row in profiles] if visible else [],
                'inputEmpty': True, 'tokenEmpty': not visible, 'refreshDisabled': not visible,
                'saveDisabled': not visible, 'authRefused': state['old_rejected'],
                'serverRefused': state['down'], 'mode': 'api'}
        class Sink:
            def __init__(self, path): self.path = path
            def __enter__(self): return self
            def write(self, raw):
                files[str(self.path)] = raw
                return len(raw)
            def __exit__(self, *_args): return False
        class MemoryPath(PurePosixPath):
            def resolve(self, strict=False): return self
            def exists(self): return str(self) in files
            def mkdir(self, mode=0o777, parents=False): pass
            def open(self, mode):
                case.assertEqual(mode, 'wb')
                return Sink(self)
            def replace(self, target):
                files[str(target)] = files.pop(str(self))
                return target
            def write_bytes(self, raw):
                files[str(self)] = raw
                return len(raw)
            def read_bytes(self): return ('synthetic-asset-' + self.name).encode()
        class FakeOwner:
            def __init__(self, registry, argv, cwd, env, deadline, *, frames=False):
                native_calls.append(('owned', list(argv), frames))
                self.frames, self.finished, self.reaped = frames, False, False
                self.output, self.errors = bytearray(), bytearray()
                self.overflow = threading.Event()
                self.pid = 300 + len(owners) * 100
                self.identity = {'pid': self.pid, 'group': self.pid, 'session': self.pid, 'start': 99, 'state': 'S'}
                self.process = Mock(pid=self.pid, returncode=None)
                self.process.poll.side_effect = lambda: self.process.returncode
                registry.append(self)
                owners.append(self)
                if not frames:
                    case.assertEqual(argv, [str(chrome_driver), '--port=0', '--enable-chrome-logs'])
                    self.output.extend(b'ChromeDriver was started successfully on port 12346')
            def send(self, value):
                if 'launch' in value:
                    state.update(launch=value['launch'], case='api-read', alive=True, connected=False,
                        old_rejected=False, down=False)
                    events.clear()
                    state['pending'] = {'ready': True, 'nonce': 'a' * 64, 'port': 12345, 'inventory': inventory()}
                else:
                    state['case'] = value['case']
                    if value['case'] == failure_phase:
                        raise failure_error
                    if value['op'] == 'stop':
                        state['alive'] = False
                    state['pending'] = {'nonce': 'a' * 64, 'inventory': inventory()}
            def receive(self): return state['pending']
            def finish(self, timeout=10):
                self.finished = self.reaped = True
                self.process.returncode = 0
                return bytes(self.output)
            def refuse_cleanup(self):
                self.finished = self.reaped = True
                self.process.returncode = 0
            def cleanup_observed(self): return self.reaped
        class FakeDriver:
            def __init__(self, port, deadline):
                native_calls.append(('driver', port, deadline))
                self.origin = None
            def start(self, binary, profile):
                case.assertEqual(binary, chrome)
                return {'browserVersion': bundle.VERSION, 'chrome': {
                    'chromedriverVersion': bundle.VERSION + ' synthetic', 'userDataDir': str(profile)}}
            def command(self, route, payload):
                case.assertEqual(route, '/url')
                case.assertEqual(payload, {'url': 'http://127.0.0.1:12345/index.html'})
            def connect(self, token, count):
                case.assertIn(token, ('b' * 64, 'c' * 64))
                case.assertEqual(count, len(profiles))
                state.update(connected=True, old_rejected=False, down=False)
                event('GET', 200)
                return snapshot()
            def create(self, name, address, count):
                host, port = address.rsplit(':', 1)
                profiles.append({'protocol': 'ssh', 'name': name, 'host': host, 'port': int(port)})
                case.assertEqual(count, len(profiles))
                replace_false.append(True)
                event('POST', 201)
            def refresh(self, count):
                case.assertEqual(count, len(profiles))
                event('GET', 200)
                return snapshot()
            def click(self, selector):
                if selector == '#catalogue-disconnect':
                    state['connected'] = False
                elif selector == '#catalogue-refresh' and not state['alive']:
                    state.update(connected=False, down=True)
                elif selector == '#catalogue-refresh' and state['launch'] == 2 and state['case'] == 'restart-persistence-auth-rotation':
                    state.update(connected=False, old_rejected=True)
                    event('GET', 401)
                else:
                    case.assertIn(selector, ('#catalogue-refresh', '#profile-submit'))
            def wait(self, predicate, timeout=None):
                answer = snapshot()
                case.assertTrue(predicate(answer))
                return answer
            def private_storage_absent(self, tokens, names): return True
            def lifecycle(self, origin, token, nonce):
                case.assertEqual(nonce, 'a' * 64)
                return copy.deepcopy(contract.CASES['pagehide-new-document'])
            def controlled(self): pass
            def execute(self, script, token, assets, action, *, async_):
                case.assertIs(async_, True)
                if action == 'seed-api':
                    if service_worker_result is not None and service_worker_result[0] == action:
                        return copy.deepcopy(service_worker_result[1])
                    return {'controlled': True, 'seeded': True}
                case.assertEqual(action, 'finish')
                for _ in range(3):
                    event('GET', 200, route='static')
                if service_worker_result is not None and service_worker_result[0] == action:
                    return copy.deepcopy(service_worker_result[1])
                return {'controlled': True, 'healthPolicyAbsent': True, 'authBypass': True,
                    'noStoreBypass': True, 'removed': True, 'exact': True}
            def close(self): pass
        def proc(pid):
            if pid in (400, 401):
                return {'pid': pid, 'group': 400, 'session': 400, 'start': 99, 'state': 'S'}
            return {'pid': pid, 'group': pid, 'session': pid, 'start': 99, 'state': 'S'}
        def groups(group):
            if group == 400 and owners[1].process.returncode is None:
                return [proc(400), proc(401)]
            return []
        original_raw = memory.raw
        def raw(name):
            if name == '/proc/401/attr/apparmor/current':
                if final_label_failure and holder['samples']['initial']['observed']:
                    return b'wrong-fixed-profile (unconfined)\n'
                return (holder['state']['name'] + ' (unconfined)\n').encode()
            return original_raw(name)
        original_observe = policy_runtime.observe_policy_tasks
        def tasks(selected, owner, deadline, *, checkpoint):
            case.assertIs(selected, holder)
            case.assertIs(owner, owners[1])
            task_calls.append(checkpoint)
            if checkpoint == 'final' and failure_phase == 'cleanup':
                raise failure_error
            return original_observe(selected, owner, deadline, checkpoint=checkpoint)
        with memory:
            memory.raw = raw
            policy_runtime.prepare_host_policy(root, source_binding, 30, policy_registry, holder)
            self.assertTrue(holder['preparation_loaded_observed'])
            with ExitStack() as stack:
                enter = stack.enter_context
                for getter in ('getuid', 'geteuid', 'getgid', 'getegid'):
                    enter(patch.object(policy_runtime.os, getter, return_value=1001, create=True))
                enter(patch.object(host_controller, 'host_context', return_value=context))
                enter(patch.object(host_controller, 'Path', MemoryPath))
                enter(patch.object(host_controller, 'DIRECTORY', MemoryPath('/synthetic-repo/tests/catalogue-browser')))
                temp = enter(patch.object(host_controller.tempfile, 'TemporaryDirectory'))
                temp.return_value.__enter__.return_value = '/synthetic-private'
                enter(patch.object(host_controller.os, 'chmod'))
                enter(patch.dict(host_controller.os.environ, {'GITHUB_WORKSPACE': '/synthetic-repo',
                    'RUNNER_TEMP': '/synthetic-temp', 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}))
                timer = enter(patch.object(host_controller.threading, 'Timer'))
                enter(patch.object(host_controller, 'source_guard', return_value=source))
                enter(patch.object(host_controller, 'selected_runtime', return_value=(chrome, chrome_driver,
                    {'provider': 'pinned-cft', 'installed': {'version': bundle.VERSION}, 'host_policy': holder})))
                pin = {'uid': 0}
                enter(patch.object(host_controller, 'file_pin', return_value=pin))
                commands = enter(patch.object(host_controller, 'command', side_effect=[
                    bundle.VERSION.encode() + b'\n', ('ChromeDriver ' + bundle.VERSION + '\n').encode()]))
                enter(patch.object(host_controller, 'Owned', FakeOwner))
                enter(patch.object(host_controller, 'owned_listener'))
                enter(patch.object(host_controller, 'listener_inodes', return_value=set()))
                enter(patch.object(host_controller, 'Driver', FakeDriver))
                enter(patch.object(host_controller, 'loaded_runtime', return_value={str(chrome): pin, str(chrome_driver): pin}))
                enter(patch.object(host_controller, 'runtime_readback'))
                enter(patch.object(host_controller, 'observe_policy_tasks', side_effect=tasks))
                enter(patch.object(host_controller, 'proc_identity', side_effect=proc))
                enter(patch.object(host_controller, 'group_members', side_effect=groups))
                enter(patch.object(policy_runtime.os, 'readlink', side_effect=lambda path:
                    str(chrome) if str(path) == '/proc/401/exe' else str(chrome_driver)))
                enter(patch.object(host_controller.secrets, 'token_hex', side_effect=['a' * 64, 'b' * 64, 'c' * 64]))
                enter(patch.object(host_controller.platform, 'python_version', return_value='3.14.7'))
                connection = enter(patch.object(host_controller.http.client, 'HTTPConnection'))
                connection.return_value.getresponse.return_value.status = 200
                connection.return_value.getresponse.return_value.read.return_value = b''
                enter(patch.object(host_controller.sys, 'stderr', io.StringIO() if diagnostic_stream is None else diagnostic_stream))
                code = host_controller.main()
                self.assertEqual(commands.call_count, 2)
                self.assertEqual([call.args[1] for call in commands.call_args_list],
                    [[str(chrome), '--product-version'], [str(chrome_driver), '--version']])
                timer.return_value.start.assert_called_once()
                timer.return_value.cancel.assert_called_once()
        record = json.loads(files['/synthetic-repo/.tmp/catalogue-browser-public/result.json'])
        self.assertEqual(task_calls, ['initial', 'final'] if failure_phase in (None, 'cleanup')
            and (service_worker_result is None or record['phase'] == 'cleanup') else ['initial'])
        self.assertEqual([row[0] for row in native_calls], ['owned', 'owned', 'driver']
            if failure_phase in ('api-create-refresh', 'restart-persistence-auth-rotation') else ['owned', 'owned', 'driver', 'owned'])
        self.assertTrue(holder['samples']['initial']['observed'])
        self.assertEqual(holder['samples']['initial']['count'], 1)
        return code, record, holder

    def test_actual_H_main_normal_commits_both_samples_in_order_before_pending_result(self):
        code, record, holder = self.run_actual_main(final_label_failure=False)
        self.assertEqual(code, 0)
        self.assertTrue(record['complete'])
        self.assertTrue(holder['samples']['final']['observed'])
        self.assertEqual(holder['samples']['final']['count'], 1)
        self.assertEqual(record['host_policy_cleanup'], {'status': 'pending'})
        self.assertTrue(record['host_policy']['task_label_initial_observed'])
        self.assertTrue(record['host_policy']['task_label_final_observed'])
        with self.assertRaises(contract.GateRefusal):
            contract.public_bytes(json.dumps(record).encode())

    def test_actual_H_main_final_label_fault_commits_initial_only_and_refuses(self):
        code, record, holder = self.run_actual_main(final_label_failure=True)
        self.assertEqual(code, 1)
        self.assertFalse(record['complete'])
        self.assertEqual(holder['samples']['final'], {'observed': False, 'count': 0})
        self.assertTrue(record['host_policy']['task_label_initial_observed'])
        self.assertFalse(record['host_policy']['task_label_final_observed'])
        self.assertTrue(record['forced_cleanup_attempted'])
        self.assertTrue(record['cleanup_complete'])
        self.assertEqual(record['phase'], 'cleanup')


class ApiReadDiagnosticTests(unittest.TestCase):
    STAGES = RuntimeStartupDiagnosticTests.STAGES

    def run_api_read_main(self, stage, *, fact_mask=0, projection_failure=None, emission_failure=None,
                          invalid_projection=None, emitter_entry_failure=None):
        failure_stage, note_failure, write_failure = '__none__', None, False
        files, owners, labels, operations, selected = {}, [], [], [], []
        name = 'different seed' if fact_mask & 2 else 'catalogue seed'
        profiles = [{'protocol': 'ssh', 'name': name, 'host': 'seed.example.invalid', 'port': 22}]
        if fact_mask & 16:
            profiles[0]['credential_ref'] = 'synthetic-private-canary'
        event = {'route': 'catalogue', 'status': 401 if fact_mask & 1 else 200, 'no_store': not bool(fact_mask & 8)}
        if stage == 'case-contract':
            event['status'] = 401
        inventory = {'count': 1, 'profiles': profiles, 'digest': '1' * 64,
            'events': [] if stage == 'catalogue-event-selection' else [event]}
        snapshot = {'texts': ['ssh \u2022 ' + name + ' \u2022 seed.example.invalid:22'],
            'rows': [{}], 'inputEmpty': not bool(fact_mask & 4)}
        if stage == 'disk-dom-inventory':
            snapshot['texts'] = ['synthetic mismatched DOM']
        error = contract.GateRefusal('synthetic-private-operation-refused')
        case = self

        class Sink:
            def __init__(self, path):
                self.path = path

            def __enter__(self):
                return self

            def write(self, raw):
                files[str(self.path)] = raw
                return len(raw)

            def __exit__(self, _kind, _error, _traceback):
                return False

        class MemoryPath(PurePosixPath):
            def resolve(self, strict=False):
                return self

            def exists(self):
                return str(self) in files

            def mkdir(self, mode=0o777, parents=False):
                pass

            def open(self, mode):
                case.assertEqual(mode, 'wb')
                return Sink(self)

            def replace(self, target):
                files[str(target)] = files.pop(str(self))
                return target

            def write_bytes(self, raw):
                files[str(self)] = raw
                return len(raw)

        def entered(stage):
            operations.append(stage)
            if failure_stage == stage:
                raise error

        def owned(registry, argv, cwd, env, deadline, *, frames=False):
            owner = Mock(finished=False, reaped=False, output=bytearray(), errors=bytearray())
            owner.overflow.is_set.return_value = False
            owner.cleanup_observed.return_value = True
            owner.process.poll.return_value = None
            owner.process.returncode = None
            registry.append(owner)
            owners.append(owner)
            entered('initial-fixture-startup' if frames else 'driver-service-birth')
            if frames:
                count = 0 if failure_stage == 'initial-fixture-inventory' else 1
                ready = {'ready': True, 'nonce': 'a' * 64, 'port': 12345,
                    'inventory': {'count': count, 'profiles': [{}] * count, 'digest': '1' * 64}}
                inspected = {'nonce': 'a' * 64, 'inventory': inventory}
                owner.receive.side_effect = [ready, error if stage == 'fixture-inspection' else inspected, inspected]
            else:
                case.assertEqual(argv, ['/synthetic/driver', '--port=0', '--enable-chrome-logs'])
                port = 0 if failure_stage == 'driver-port-validation' else 12346
                owner.output.extend(('ChromeDriver was started successfully on port ' + str(port)).encode())
                owner.process.poll.side_effect = lambda: entered('driver-port-wait')
            return owner

        def listener(owner, port):
            if owner is owners[-1] and len(owners) == 2:
                entered('driver-listener')

        driver = Mock()
        def start(binary, profile):
            entered('browser-session-start')
            return {'browserVersion': '9.9.9.9' if failure_stage == 'browser-capabilities' else '1.2.3.4',
                'chrome': {'chromedriverVersion': '1.2.3.4 synthetic', 'userDataDir': str(profile)}}
        driver.start.side_effect = start
        driver.command.side_effect = error if stage == 'navigation-command' else None
        driver.connect.side_effect = error if stage == 'browser-connect' else None
        driver.connect.return_value = snapshot
        driver.create.side_effect = error

        def make_driver(port, deadline):
            entered('browser-client')
            return driver

        def loaded(owner):
            entered('loaded-runtime-inventory')
            return {} if failure_stage == 'loaded-runtime-tools' else {
                '/synthetic/chrome': {}, '/synthetic/driver': {}}

        tokens = iter(('a' * 64, 'b' * 64, 'c' * 64))
        def token(size):
            case.assertEqual(size, 32)
            entered('session-setup')
            return next(tokens)

        original_note = host_controller.runtime_note
        original_inert = host_controller.inert_runtime_note
        original_packed = host_controller.packed
        def note(public, stage, versions=None):
            if note_failure is not None and stage in self.STAGES:
                raise note_failure
            return original_note(public, stage, versions)

        def inert(public, stage):
            labels.append(stage)
            return original_inert(public, stage)

        def packed(value):
            if emission_failure is not None and not write_failure and value.get('schema') == 'row.catalogue-api-read-refusal.v1':
                raise emission_failure
            return original_packed(value)

        original_projection = host_controller.api_read_refusal
        def projection(public, error, entered_stage, facts):
            selected.append((entered_stage, error, facts))
            if projection_failure is not None:
                raise projection_failure
            if invalid_projection is not None:
                return invalid_projection
            return original_projection(public, error, entered_stage, facts)
        stream = io.StringIO()
        if write_failure:
            stream = Mock()
            stream.write.side_effect = emission_failure
        timer = Mock()
        patches = {
            'context': patch.object(host_controller, 'host_context', return_value={'source': 'a' * 40, 'event': 'b' * 40, 'image_version': '1.2'}),
            'paths': patch.object(host_controller, 'Path', MemoryPath),
            'directory': patch.object(host_controller, 'DIRECTORY', MemoryPath('/synthetic-repo/tests/catalogue-browser')),
            'temp': patch.object(host_controller.tempfile, 'TemporaryDirectory'),
            'chmod': patch.object(host_controller.os, 'chmod'),
            'env': patch.dict(host_controller.os.environ, {'GITHUB_WORKSPACE': '/synthetic-repo', 'RUNNER_TEMP': '/synthetic-temp'}),
            'clock': patch.object(host_controller.time, 'monotonic', return_value=100),
            'timer': patch.object(host_controller.threading, 'Timer', return_value=timer),
            'source': patch.object(host_controller, 'source_guard', return_value={'head': 'a' * 40, 'tree': 'b' * 40, 'bytes': 'c' * 64, 'workflow': 'd' * 64}),
            'selection': patch.object(host_controller, 'selected_runtime', return_value=(MemoryPath('/synthetic/chrome'), MemoryPath('/synthetic/driver'), {'provider': 'pinned-cft', 'installed': {'version': '1.2.3.4'}, 'host_policy': {}})),
            'policy_evidence': patch.object(host_controller, 'policy_evidence', return_value=synthetic_policy_evidence(observed=False)),
            'policy_tasks': patch.object(host_controller, 'observe_policy_tasks', side_effect=lambda holder, owner, deadline, *, checkpoint: synthetic_policy_evidence(initial_only=checkpoint == 'initial')),
            'pins': patch.object(host_controller, 'file_pin', return_value={'uid': 0}),
            'version_argv': patch.object(host_controller, 'chrome_version_argv', return_value=['/synthetic/chrome', '--product-version']),
            'version_match': patch.object(host_controller, 'chrome_version_match', return_value=(b'1.2.3.4', b'1.2.3.4')),
            'commands': patch.object(host_controller, 'command', side_effect=[b'1.2.3.4\n', b'ChromeDriver 1.2.3.4\n']),
            'owned': patch.object(host_controller, 'Owned', side_effect=owned),
            'listener': patch.object(host_controller, 'owned_listener', side_effect=listener),
            'driver': patch.object(host_controller, 'Driver', side_effect=make_driver),
            'loaded': patch.object(host_controller, 'loaded_runtime', side_effect=loaded),
            'tokens': patch.object(host_controller.secrets, 'token_hex', side_effect=token),
            'note': patch.object(host_controller, 'runtime_note', side_effect=note),
            'inert': patch.object(host_controller, 'inert_runtime_note', side_effect=inert),
            'packed': patch.object(host_controller, 'packed', side_effect=packed),
            'stderr': patch.object(host_controller.sys, 'stderr', stream),
            'projection': patch.object(host_controller, 'api_read_refusal', side_effect=projection),
            'api_emitter': patch.object(host_controller, 'emit_api_read_refusal', side_effect=emitter_entry_failure, wraps=host_controller.emit_api_read_refusal),
            'birth': patch.object(host_controller.subprocess, 'Popen'),
            'transport': patch.object(host_controller.http.client, 'HTTPConnection'),
            'thread': patch.object(host_controller.threading, 'Thread'),
        }
        with ExitStack() as stack:
            mocks = {name: stack.enter_context(context) for name, context in patches.items()}
            mocks['temp'].return_value.__enter__.return_value = '/synthetic-private'
            code = host_controller.main()
            version_calls = [call.args[1] for call in mocks['note'].call_args_list if call.args[1] in contract.RUNTIME_STAGES[:3]]
            policy_calls = mocks['policy_tasks'].call_args_list
            expected_checkpoints = ['initial'] if 'loaded-runtime-inventory' in operations else []
            case.assertEqual([call.kwargs['checkpoint'] for call in policy_calls], expected_checkpoints)
            for call in policy_calls:
                case.assertIs(call.args[0], mocks['selection'].return_value[2]['host_policy'])
                case.assertIs(call.args[1], owners[1])
                case.assertEqual(len(call.args), 3)
                case.assertEqual(set(call.kwargs), {'checkpoint'})
            for name in ('birth', 'transport', 'thread'):
                mocks[name].assert_not_called()
        timer.start.assert_called_once()
        timer.cancel.assert_called_once()
        for owner in owners:
            owner.refuse_cleanup.assert_called_once()
            owner.cleanup_observed.assert_called_once()
        record = json.loads(files['/synthetic-repo/.tmp/catalogue-browser-public/result.json'])
        return code, record, labels, operations, driver, owners, version_calls, stream.getvalue(), selected

    def test_actual_main_six_boundaries_keep_original_calls_and_cleanup(self):
        for stage in contract.API_READ_STAGES:
            with self.subTest(stage=stage):
                code, record, _labels, _operations, driver, owners, versions, line, selected = self.run_api_read_main(stage)
                self.assertEqual(code, 1)
                self.assertEqual(record['phase'], 'api-read')
                self.assertFalse(record['complete'])
                self.assertTrue(record['cleanup_complete'])
                self.assertTrue(record['forced_cleanup_attempted'])
                diagnostic = json.loads(line)
                self.assertEqual(diagnostic['entered_stage'], stage)
                self.assertEqual(diagnostic['exception_category'], 'index-error' if stage == 'catalogue-event-selection' else 'gate-refusal')
                self.assertEqual(diagnostic['readiness_credit'], 0)
                self.assertNotIn('synthetic-private', line)
                self.assertTrue(line.isascii())
                self.assertLessEqual(len(line.encode('ascii')), 512)
                self.assertEqual(len(selected), 1)
                self.assertEqual(selected[0][0], stage)
                driver.command.assert_called_once_with('/url', {'url': 'http://127.0.0.1:12345/index.html'})
                self.assertEqual(driver.connect.call_count, 0 if stage == 'navigation-command' else 1)
                driver.create.assert_not_called()
                self.assertEqual(len(owners), 2)
                self.assertEqual(versions, ['chrome-version-command', 'driver-version-command',
                    'version-equality', 'version-equality'])

    def test_actual_main_each_fact_bit_and_combination_remain_refused(self):
        for bits in (1, 2, 4, 8, 16, 31):
            with self.subTest(bits=bits):
                code, record, _labels, _operations, driver, _owners, _versions, line, selected = self.run_api_read_main('__none__', fact_mask=bits)
                self.assertEqual(code, 1)
                self.assertEqual(record['phase'], 'api-read')
                self.assertEqual(json.loads(line)['case_failure_bits'], bits)
                self.assertIs(type(selected[0][1]), contract.GateRefusal)
                driver.create.assert_not_called()

    def test_successful_api_read_has_no_stale_diagnostic_in_next_phase(self):
        code, record, _labels, _operations, driver, _owners, _versions, line, selected = self.run_api_read_main('__none__')
        self.assertEqual(code, 1)
        self.assertEqual(record['phase'], 'api-create-refresh')
        self.assertEqual(line, '{"phase":"api-create-refresh","readiness_credit":0,'
            '"schema":"row.catalogue-case-refusal.v1","status":"refused"}\n')
        self.assertIsNone(host_controller.api_read_refusal(record, selected[0][1], selected[0][0], selected[0][2]))
        driver.create.assert_called_once_with('catalogue created one', 'one.example.invalid:2222', 2)
        self.assertNotIn('entered_stage', record)
        self.assertNotIn('api_read', record)

    def test_projection_and_publication_interruptions_are_inert(self):
        for error in (RuntimeError('synthetic-private'), KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(kind=type(error).__name__, path='projection'):
                code, record, *_rest, line, selected = self.run_api_read_main('navigation-command', projection_failure=error)
                self.assertEqual(code, 1)
                self.assertTrue(record['cleanup_complete'])
                self.assertEqual(line, '')
                self.assertIs(type(selected[0][1]), contract.GateRefusal)
            with self.subTest(kind=type(error).__name__, path='publication'):
                code, record, *_rest, line, _selected = self.run_api_read_main('navigation-command', emission_failure=error)
                self.assertEqual(code, 1)
                self.assertTrue(record['cleanup_complete'])
                self.assertEqual(line, '')

        for error in (KeyboardInterrupt(), SystemExit(9), MemoryError('synthetic-private')):
            with self.subTest(kind=type(error).__name__, path='emitter-entry'):
                code, record, *_rest, line, selected = self.run_api_read_main('navigation-command', emitter_entry_failure=error)
                self.assertEqual(code, 1)
                self.assertTrue(record['cleanup_complete'])
                self.assertTrue(record['forced_cleanup_attempted'])
                self.assertEqual(line, '')
                self.assertIs(type(selected[0][1]), contract.GateRefusal)

    def test_independent_emitter_drops_bad_projection_returns(self):
        for value in ({'entered_stage': '/synthetic-private', 'exception_category': 'gate-refusal'},
                      {'entered_stage': 'navigation-command', 'exception_category': 'gate-refusal', 'path': '/synthetic-private'},
                      {'entered_stage': 'navigation-command', 'exception_category': 'gate-refusal', 'case_failure_bits': 1}):
            with self.subTest(value=value):
                code, record, *_rest, line, _selected = self.run_api_read_main('navigation-command', invalid_projection=value)
                self.assertEqual(code, 1)
                self.assertTrue(record['cleanup_complete'])
                self.assertEqual(line, '')

    def test_closed_validator_types_keys_positive_bits_and_context(self):
        class Text(str):
            pass
        valid = {'entered_stage': 'case-contract', 'exception_category': 'gate-refusal', 'case_failure_bits': 31}
        self.assertEqual(contract.api_read_diagnostic(valid), valid)
        for key, value in (('entered_stage', Text('case-contract')), ('exception_category', Text('gate-refusal')),
                           ('case_failure_bits', True), ('case_failure_bits', 0), ('case_failure_bits', 32),
                           ('entered_stage', 'navigation-command'), ('exception_category', 'other-exact-type')):
            with self.subTest(key=key, value=value):
                changed = dict(valid, **{key: value})
                with self.assertRaises(contract.GateRefusal):
                    contract.api_read_diagnostic(changed)
        changed = {Text('entered_stage'): 'case-contract', 'exception_category': 'gate-refusal'}
        with self.assertRaises(contract.GateRefusal):
            contract.api_read_diagnostic(changed)

    def test_exact_error_types_and_reused_poisoned_exception_never_read_attributes(self):
        class PoisonError(Exception):
            def __getattribute__(self, name):
                raise AssertionError('private exception attribute read')
        public = {'status': 'refused', 'complete': False, 'phase': 'api-read'}
        error = PoisonError('synthetic-private')
        for _ in range(2):
            self.assertEqual(host_controller.api_read_refusal(public, error, 'browser-connect'),
                {'entered_stage': 'browser-connect', 'exception_category': 'other-exact-type'})
        class Refusal(contract.GateRefusal):
            pass
        self.assertEqual(host_controller.api_read_refusal(public, Refusal('synthetic-private'), 'case-contract',
            {'status': 401, 'dom_seed': True, 'input_cleared': True, 'no_store': True, 'public_only': True}),
            {'entered_stage': 'case-contract', 'exception_category': 'other-exact-type'})

    def test_bad_facts_and_wrong_context_omit_without_private_serialization(self):
        public = {'status': 'refused', 'complete': False, 'phase': 'api-read'}
        error = contract.GateRefusal('synthetic-private')
        expected = {'entered_stage': 'case-contract', 'exception_category': 'gate-refusal'}
        class Text(str):
            pass
        for facts in (None, {}, {'private': 'canary'}, {Text('status'): 401, 'dom_seed': True,
                'input_cleared': True, 'no_store': True, 'public_only': True},
                {'status': True, 'dom_seed': True, 'input_cleared': True, 'no_store': True, 'public_only': True}):
            self.assertEqual(host_controller.api_read_refusal(public, error, 'case-contract', facts), expected)
        for key, value in (('phase', 'cleanup'), ('status', 'observations-complete-with-limits'), ('complete', True)):
            self.assertIsNone(host_controller.api_read_refusal(dict(public, **{key: value}), error, 'case-contract'))

    def test_all_closed_records_bounded_with_LF_and_public_unchanged(self):
        public = {'status': 'refused', 'complete': False, 'phase': 'api-read'}
        original = copy.deepcopy(public)
        for stage in contract.API_READ_STAGES:
            for category in contract.API_READ_EXCEPTIONS:
                value = {'entered_stage': stage, 'exception_category': category}
                if stage == 'case-contract' and category == 'gate-refusal':
                    value['case_failure_bits'] = 31
                stream = io.StringIO()
                with patch.object(host_controller.sys, 'stderr', stream):
                    host_controller.emit_api_read_refusal(public, value)
                line = stream.getvalue()
                self.assertTrue(line.isascii())
                self.assertLessEqual(len(line.encode('ascii')), 512)
                self.assertEqual(json.loads(line)['entered_stage'], stage)
                self.assertEqual(public, original)



class DriverElementPathTests(unittest.TestCase):
    def response_connections(self, values):
        connections = []
        for value in values:
            response = Mock(status=200)
            response.read.return_value = json.dumps({'value': value}, separators=(',', ':')).encode('utf-8')
            connection = Mock()
            connection.getresponse.return_value = response
            connections.append(connection)
        return connections

    def assert_requests_and_closes(self, connections, requests):
        self.assertEqual(len(connections), len(requests))
        for connection, (path, body) in zip(connections, requests, strict=True):
            connection.request.assert_called_once_with('POST', path,
                body=json.dumps(body, separators=(',', ':')).encode('utf-8'),
                headers={'Content-Type': 'application/json'})
            connection.getresponse.assert_called_once_with()
            connection.getresponse.return_value.read.assert_called_once_with(262145)
            connection.close.assert_called_once_with()

    def test_real_element_fill_and_click_transport_dotted_opaque_ids(self):
        for identifier in ('f.1.d.2.e.3', 'opaque._-9', '..opaque..', '.' + 'a' * 254 + '.'):
            for action in ('fill', 'click'):
                with self.subTest(identifier=identifier, action=action):
                    values = [{browser_probe.ELEMENT: identifier}, None]
                    requests = [('/session/owned-session/element', {'using': 'css selector', 'value': '#synthetic'})]
                    path = '/session/owned-session/element/' + identifier
                    if action == 'fill':
                        values.append(None)
                        requests.extend([(path + '/clear', {}), (path + '/value', {'text': 'synthetic-token'})])
                    else:
                        requests.append((path + '/click', {}))
                    connections = self.response_connections(values)
                    driver = browser_probe.Driver(12345, 200)
                    driver.session = 'owned-session'
                    with patch.object(browser_probe.time, 'monotonic', return_value=100) as clock, \
                            patch.object(browser_probe.http.client, 'HTTPConnection', side_effect=connections) as provider:
                        if action == 'fill':
                            self.assertIsNone(driver.fill('#synthetic', 'synthetic-token'))
                        else:
                            self.assertIsNone(driver.click('#synthetic'))
                    self.assertEqual(provider.call_count, len(requests))
                    self.assertEqual(clock.call_count, len(requests))
                    for call in provider.call_args_list:
                        self.assertEqual(call.args, ('127.0.0.1', 12345))
                        self.assertEqual(call.kwargs, {'timeout': 10})
                    self.assert_requests_and_closes(connections, requests)

    def test_whole_dot_element_ids_refuse_action_after_the_existing_lookup(self):
        for identifier in ('.', '..'):
            for action in ('fill', 'click'):
                with self.subTest(identifier=identifier, action=action):
                    connections = self.response_connections([{browser_probe.ELEMENT: identifier}])
                    driver = browser_probe.Driver(12345, 200)
                    driver.session = 'owned-session'
                    with patch.object(browser_probe.time, 'monotonic', return_value=100) as clock, \
                            patch.object(browser_probe.http.client, 'HTTPConnection', side_effect=connections) as provider:
                        with self.assertRaises(contract.GateRefusal):
                            if action == 'fill':
                                driver.fill('#synthetic', 'synthetic-token')
                            else:
                                driver.click('#synthetic')
                    provider.assert_called_once_with('127.0.0.1', 12345, timeout=10)
                    self.assertEqual(clock.call_count, 1)
                    self.assert_requests_and_closes(connections,
                        [('/session/owned-session/element', {'using': 'css selector', 'value': '#synthetic'})])

    def test_invalid_paths_and_whole_dot_segments_refuse_before_clock_or_connection(self):
        paths = ('/.', '/..', '/./', '/../', '/session/owned/./click', '/session/owned/../click',
            '/session/owned/element/./value', '/session/owned/element/../click',
            '/session/owned/element/%2e/click', '/session/owned/element/%2E%2E/click',
            '/session/owned/element/a?b/click', '/session/owned/element/a#b/click',
            '/session/owned/element/a\\b/click', '/session/owned/element/a:b/click',
            'https://outside.invalid/status', 'status', '/a b', '/a\n', '/a\x00', '/caf\u00e9')
        for path in paths:
            with self.subTest(path=path), patch.object(browser_probe.time, 'monotonic') as clock, \
                    patch.object(browser_probe.http.client, 'HTTPConnection') as provider:
                with self.assertRaises(contract.GateRefusal):
                    browser_probe.Driver(12345, 200).call('POST', path, {})
                provider.assert_not_called()
                clock.assert_not_called()

    def test_element_invalid_ids_still_refuse_after_lookup_without_action_transport(self):
        for identifier in ('', 'a/b', 'a%b', 'a?b', 'a b', 'caf\u00e9', 'a\n', 'a' * 257, None, True):
            with self.subTest(identifier=identifier):
                connections = self.response_connections([{browser_probe.ELEMENT: identifier}])
                driver = browser_probe.Driver(12345, 200)
                driver.session = 'owned-session'
                with patch.object(browser_probe.time, 'monotonic', return_value=100) as clock, \
                        patch.object(browser_probe.http.client, 'HTTPConnection', side_effect=connections) as provider:
                    with self.assertRaises(contract.GateRefusal):
                        driver.fill('#synthetic', 'synthetic-token')
                provider.assert_called_once_with('127.0.0.1', 12345, timeout=10)
                self.assertEqual(clock.call_count, 1)
                self.assert_requests_and_closes(connections,
                    [('/session/owned-session/element', {'using': 'css selector', 'value': '#synthetic'})])


class CatalogueCaseRefusalTests(unittest.TestCase):
    PHASES = ('api-create-refresh', 'restart-persistence-auth-rotation', 'disconnect-token-state',
        'pagehide-new-document', 'service-worker-api-cache-boundary', 'owned-server-down', 'cleanup')

    def run_failure(self, phase, *, entry_fault=None, packed_fault=None, stream_fault=None):
        selected = contract.GateRefusal('synthetic-private-case-failure')
        stream = io.StringIO()
        if stream_fault is not None:
            stream = Mock()
            stream.write.side_effect = stream_fault
        original_packed = host_controller.packed
        def packed(value):
            if type(value) is dict and value.get('schema') == 'row.catalogue-case-refusal.v1' and packed_fault is not None:
                raise packed_fault
            return original_packed(value)
        fixture = ActualPolicyCheckpointMainTests('test_actual_H_main_normal_commits_both_samples_in_order_before_pending_result')
        with patch.object(host_controller, 'emit_case_refusal', side_effect=entry_fault, wraps=host_controller.emit_case_refusal) as emit, \
                patch.object(host_controller, 'packed', side_effect=packed), \
                patch.object(host_controller, 'api_read_refusal', wraps=host_controller.api_read_refusal) as original_failure:
            code, record, holder = fixture.run_actual_main(final_label_failure=False,
                failure_phase=phase, failure_error=selected, diagnostic_stream=stream)
        emit.assert_called_once()
        self.assertIs(original_failure.call_args.args[1], selected)
        return code, record, holder, stream

    def test_actual_main_each_remaining_case_and_cleanup_emits_only_fixed_phase(self):
        for phase in self.PHASES:
            with self.subTest(phase=phase):
                code, record, holder, stream = self.run_failure(phase)
                self.assertEqual(code, 1)
                self.assertEqual(record['phase'], phase)
                self.assertFalse(record['complete'])
                self.assertTrue(record['forced_cleanup_attempted'])
                self.assertTrue(record['cleanup_complete'])
                self.assertTrue(holder['samples']['initial']['observed'])
                self.assertFalse(holder['samples']['final']['observed'])
                expected = [{'schema': 'row.catalogue-case-refusal.v1',
                    'status': 'refused', 'phase': phase, 'readiness_credit': 0}]
                if phase == 'service-worker-api-cache-boundary':
                    expected.insert(0, {'schema': 'row.catalogue-service-worker-refusal.v1', 'status': 'refused',
                        'phase': phase, 'readiness_credit': 0, 'entered_stage': 'case-mark', 'exception_category': 'gate-refusal'})
                self.assertEqual([json.loads(line) for line in stream.getvalue().splitlines()], expected)
                self.assertNotIn('synthetic-private', stream.getvalue())
                self.assertLessEqual(len(stream.getvalue().encode('ascii')), 512)
                self.assertEqual(stream.getvalue().count('\n'), 2 if phase == 'service-worker-api-cache-boundary' else 1)
                self.assertNotIn('case_diagnostic', record)

    def test_default_full_main_success_retains_original_result_and_emits_nothing(self):
        fixture = ActualPolicyCheckpointMainTests('test_actual_H_main_normal_commits_both_samples_in_order_before_pending_result')
        stream = io.StringIO()
        with patch.object(host_controller, 'emit_case_refusal', wraps=host_controller.emit_case_refusal) as emit:
            code, record, holder = fixture.run_actual_main(final_label_failure=False, diagnostic_stream=stream)
        self.assertEqual(code, 0)
        self.assertTrue(record['complete'])
        self.assertTrue(holder['samples']['final']['observed'])
        self.assertEqual(record['host_policy_cleanup'], {'status': 'pending'})
        self.assertEqual(stream.getvalue(), '')
        emit.assert_not_called()

    def test_emitter_entry_serialization_and_stream_faults_preserve_result_and_cleanup(self):
        for fault in (KeyboardInterrupt(), SystemExit(9), MemoryError('synthetic-private')):
            for location in ('entry_fault', 'packed_fault', 'stream_fault'):
                with self.subTest(fault=type(fault).__name__, location=location):
                    code, record, holder, stream = self.run_failure('api-create-refresh', **{location: fault})
                    self.assertEqual(code, 1)
                    self.assertEqual(record['phase'], 'api-create-refresh')
                    self.assertFalse(record['complete'])
                    self.assertTrue(record['cleanup_complete'])
                    self.assertTrue(record['forced_cleanup_attempted'])
                    self.assertFalse(holder['samples']['final']['observed'])
                    if location != 'stream_fault':
                        self.assertEqual(stream.getvalue(), '')

    def test_closed_phase_record_never_serializes_other_public_fields(self):
        for phase in self.PHASES:
            with self.subTest(phase=phase), patch.object(host_controller.sys, 'stderr', io.StringIO()) as stream:
                public = {'phase': phase, 'status': 'refused', 'complete': False,
                    'private_example': '/synthetic-private/path?token=PRIVATE', 'private_streams': [object()]}
                before = public.copy()
                host_controller.emit_case_refusal(public)
                self.assertEqual(public, before)
                self.assertEqual(json.loads(stream.getvalue()), {'schema': 'row.catalogue-case-refusal.v1',
                    'phase': phase, 'status': 'refused', 'readiness_credit': 0})
                self.assertTrue(stream.getvalue().isascii())
                self.assertLessEqual(len(stream.getvalue().encode('ascii')), 512)
                self.assertNotIn('PRIVATE', stream.getvalue())
                self.assertNotIn('synthetic-private', stream.getvalue())

    def test_wrong_phases_types_and_success_records_are_omitted_without_mutation(self):
        class Text(str):
            pass
        class Mapping(dict):
            pass
        invalid = [None, [], Mapping(phase='cleanup', status='refused', complete=False)]
        for phase in ('api-read', 'host-runtime-observation', 'preparation', 'unknown', '/PRIVATE',
                      '', None, True, ['cleanup'], Text('cleanup')):
            invalid.append({'phase': phase, 'status': 'refused', 'complete': False})
        invalid.extend([{'phase': 'cleanup', 'status': status, 'complete': False}
            for status in ('observations-complete-with-limits', None, Text('refused'))])
        invalid.extend([{'phase': 'cleanup', 'status': 'refused', 'complete': complete}
            for complete in (True, 0, None)])
        for public in invalid:
            before = repr(public)
            with self.subTest(public=before), patch.object(host_controller.sys, 'stderr', io.StringIO()) as stream:
                host_controller.emit_case_refusal(public)
                self.assertEqual(stream.getvalue(), '')
                self.assertEqual(repr(public), before)


class DriverLifecycleDiagnosticTests(unittest.TestCase):
    STAGES = ('connect', 'pagehide-handler-install', 'same-origin-navigation', 'pagehide-marker-read',
        'pagehide-fresh-snapshot', 'pagehide-state-guard', 'original-window-read', 'new-window-create',
        'new-window-switch', 'new-window-navigation', 'new-window-opener-guard', 'new-window-snapshot',
        'new-window-state-guard', 'new-window-close', 'original-window-restore')
    FIRST = {'tokenEmpty': True, 'inputEmpty': True, 'rows': [], 'refreshDisabled': True}
    HANDLER = "\nconst key = arguments[0], storage = sessionStorage;\nif (storage.length >= 128 || storage.getItem(key) !== null) return false;\nwindow.addEventListener('pagehide', event => {\n  if (event.isTrusted !== true) return;\n  storage.setItem(key, catalogueTokenValue === '' && catalogueToken.value === '' && catalogueRows.length === 0 ? '1' : '0');\n}, {once: true});\nreturn true;\n"
    CONSUME = "\nconst key = arguments[0], storage = sessionStorage;\nlet value;\ntry { value = storage.getItem(key); }\nfinally { storage.removeItem(key); }\nif (storage.getItem(key) !== null) return '';\nreturn value === '1' ? 'qualification-cleared' : value === '0' ? 'qualification-refused' : '';\n"
    NONCE = 'a' * 64
    KEY = 'row-qualification-pagehide-' + NONCE

    def run_lifecycle(self, failure=None, *, bits=0, primary=None, fresh_override=None, marker_override=...,
                      entry_fault=None, serialization_fault=None, stream_fault=None):
        driver = browser_probe.Driver(12345, 200)
        events = []
        selected = contract.GateRefusal('synthetic-private-primary') if primary is None else primary
        first, second = copy.deepcopy(self.FIRST), copy.deepcopy(self.FIRST)
        marker = 'synthetic-private-marker' if bits & 1 or failure == 'pagehide-state-guard' and not bits else 'qualification-cleared'
        if marker_override is not Ellipsis:
            marker = marker_override
        for bit, key, value in ((2, 'tokenEmpty', False), (4, 'inputEmpty', False),
                                (8, 'rows', [{'private': 'synthetic-private-row'}]), (16, 'refreshDisabled', False)):
            if bits & bit:
                first[key] = value
        if fresh_override is not None:
            first = fresh_override
        if failure == 'new-window-state-guard':
            second['tokenEmpty'] = False
        snapshots = iter((first, second))
        def entered(stage, value=None):
            events.append(stage)
            if stage == failure and stage not in ('pagehide-state-guard', 'new-window-state-guard'):
                raise selected
            return value
        def execute(script, *args):
            if script == self.HANDLER:
                self.assertEqual(args, (self.KEY,))
                return entered('pagehide-handler-install', True)
            if script == self.CONSUME:
                self.assertEqual(args, (self.KEY,))
                return entered('pagehide-marker-read', marker)
            self.assertEqual(args, ())
            self.assertEqual(script, 'return window.opener === null;')
            return entered('new-window-opener-guard', True)
        def command(path, body=None, method='POST'):
            if path == '/url':
                if body['url'] == 'http://127.0.0.1:12346/index.html?qualification-away=' + self.NONCE:
                    return entered('same-origin-navigation')
                self.assertEqual(body, {'url': 'http://127.0.0.1:12346/index.html'})
                return entered('new-window-navigation')
            if path == '/window/new':
                self.assertEqual(body, {'type': 'tab'})
                return entered('new-window-create', {'handle': 'new-window'})
            self.assertEqual(path, '/window')
            if method == 'GET':
                return entered('original-window-read', 'original-window')
            if method == 'DELETE':
                return entered('new-window-close')
            self.assertEqual(method, 'POST')
            if body == {'handle': 'new-window'}:
                return entered('new-window-switch')
            self.assertEqual(body, {'handle': 'original-window'})
            return entered('original-window-restore')
        def snapshot():
            stage = 'new-window-snapshot' if 'new-window-opener-guard' in events else 'pagehide-fresh-snapshot'
            return entered(stage, next(snapshots))
        driver.connect = Mock(side_effect=lambda token, count: entered('connect'))
        driver.execute = Mock(side_effect=execute)
        driver.command = Mock(side_effect=command)
        driver.snapshot = Mock(side_effect=snapshot)
        stream = io.StringIO()
        if stream_fault is not None:
            stream = Mock()
            stream.write.side_effect = stream_fault
        original_dumps = browser_probe.json.dumps
        def dumps(value, *args, **kwargs):
            if type(value) is dict and value.get('schema') == 'row.catalogue-lifecycle-refusal.v1' and serialization_fault is not None:
                raise serialization_fault
            return original_dumps(value, *args, **kwargs)
        result, error = None, None
        with patch.object(browser_probe, 'emit_lifecycle_refusal', side_effect=entry_fault, wraps=browser_probe.emit_lifecycle_refusal) as emit, \
                patch.object(browser_probe.sys, 'stderr', stream), patch.object(browser_probe.json, 'dumps', side_effect=dumps), \
                patch.object(browser_probe.http.client, 'HTTPConnection') as transport:
            try:
                result = driver.lifecycle('http://127.0.0.1:12346', 'synthetic-private-token', self.NONCE)
            except BaseException as caught:
                error = caught
            transport.assert_not_called()
        if error is not None:
            emit.assert_called_once()
            self.assertIs(emit.call_args.args[1], error)
            if failure not in ('pagehide-state-guard', 'new-window-state-guard'):
                self.assertIs(error, selected)
        else:
            emit.assert_not_called()
        return result, error, events, stream, driver

    def test_success_retains_exact_native_operation_order_and_return(self):
        result, error, events, stream, driver = self.run_lifecycle()
        self.assertIsNone(error)
        self.assertEqual(result, dict(contract.CASES['pagehide-new-document']))
        self.assertEqual(stream.getvalue(), '')
        self.assertEqual(events, [stage for stage in self.STAGES if stage not in ('pagehide-state-guard', 'new-window-state-guard')])
        driver.connect.assert_called_once_with('synthetic-private-token', 3)
        self.assertEqual([call.args for call in driver.execute.call_args_list],
            [(self.HANDLER, self.KEY), (self.CONSUME, self.KEY), ('return window.opener === null;',)])
        self.assertEqual(driver.snapshot.call_count, 2)
        self.assertEqual([(call.args, call.kwargs) for call in driver.command.call_args_list], [
            (('/url', {'url': 'http://127.0.0.1:12346/index.html?qualification-away=' + self.NONCE}), {}),
            (('/window',), {'method': 'GET'}), (('/window/new', {'type': 'tab'}), {}),
            (('/window', {'handle': 'new-window'}), {}), (('/url', {'url': 'http://127.0.0.1:12346/index.html'}), {}),
            (('/window',), {'method': 'DELETE'}), (('/window', {'handle': 'original-window'}), {})])

    def test_each_actual_lifecycle_boundary_reports_fixed_stage_and_preserves_error(self):
        for index, stage in enumerate(self.STAGES):
            with self.subTest(stage=stage):
                result, error, events, stream, _driver = self.run_lifecycle(stage)
                self.assertIsNone(result)
                self.assertIs(type(error), contract.GateRefusal)
                self.assertEqual(events, [item for item in self.STAGES[:index + 1]
                    if item not in ('pagehide-state-guard', 'new-window-state-guard')])
                record = json.loads(stream.getvalue())
                self.assertEqual(record['entered_stage'], stage)
                self.assertEqual(record['exception_category'], 'gate-refusal')
                self.assertEqual(record['phase'], 'pagehide-new-document')
                self.assertEqual(record['readiness_credit'], 0)
                self.assertEqual(record.get('first_guard_failure_bits'), 1 if stage == 'pagehide-state-guard' else None)
                self.assertTrue(stream.getvalue().isascii())
                self.assertLessEqual(len(stream.getvalue().encode('ascii')), 512)
                self.assertNotIn('synthetic-private', stream.getvalue())

    def test_first_guard_positive_bits_and_combination_do_not_relax_predicate(self):
        for bits in (1, 2, 4, 8, 16, 31):
            with self.subTest(bits=bits):
                result, error, _events, stream, _driver = self.run_lifecycle('pagehide-state-guard', bits=bits)
                self.assertIsNone(result)
                self.assertIs(type(error), contract.GateRefusal)
                self.assertEqual(json.loads(stream.getvalue())['first_guard_failure_bits'], bits)

    def test_exact_exception_categories_and_primary_chain_are_preserved(self):
        class RefusalSubclass(contract.GateRefusal):
            pass
        cases = ((KeyError, 'key-error'), (IndexError, 'index-error'), (TypeError, 'type-error'),
            (ValueError, 'value-error'), (TimeoutError, 'timeout-error'), (OSError, 'os-error'),
            (RuntimeError, 'other-exact-type'), (RefusalSubclass, 'other-exact-type'))
        for kind, category in cases:
            selected = kind('synthetic-private-primary')
            selected.__cause__ = RuntimeError('synthetic-private-cause')
            original_chain = (selected.args, selected.__cause__, selected.__context__, selected.__suppress_context__)
            with self.subTest(kind=kind):
                _result, error, _events, stream, _driver = self.run_lifecycle('pagehide-marker-read', primary=selected)
                self.assertIs(error, selected)
                self.assertEqual((error.args, error.__cause__, error.__context__, error.__suppress_context__), original_chain)
                self.assertEqual(json.loads(stream.getvalue())['exception_category'], category)

    def test_diagnostic_entry_serialization_and_write_interruptions_preserve_original_error(self):
        for fault in (KeyboardInterrupt(), SystemExit(9), MemoryError('synthetic-private')):
            for key in ('entry_fault', 'serialization_fault', 'stream_fault'):
                primary = TimeoutError('synthetic-private-selected')
                with self.subTest(fault=type(fault).__name__, key=key):
                    result, error, _events, stream, _driver = self.run_lifecycle('same-origin-navigation', primary=primary, **{key: fault})
                    self.assertIsNone(result)
                    self.assertIs(error, primary)
                    if key != 'stream_fault':
                        self.assertEqual(stream.getvalue(), '')

    def test_malformed_first_snapshot_omits_bits_but_keeps_selected_failure_and_closed_fields(self):
        class Text(str):
            pass
        class Mapping(dict):
            pass
        class Rows(list):
            pass
        invalid = [[], Mapping(self.FIRST), {**self.FIRST, 'tokenEmpty': 1},
            {**self.FIRST, 'rows': Rows()}, {**self.FIRST, 'rows': 'synthetic-private'},
            {Text('tokenEmpty'): True, 'inputEmpty': True, 'rows': [], 'refreshDisabled': True}]
        for fresh in invalid:
            with self.subTest(kind=type(fresh).__name__):
                _result, error, _events, stream, _driver = self.run_lifecycle('pagehide-state-guard', fresh_override=fresh)
                self.assertIs(type(error), contract.GateRefusal)
                record = json.loads(stream.getvalue())
                self.assertNotIn('first_guard_failure_bits', record)
                self.assertEqual(set(record), {'schema', 'status', 'phase', 'readiness_credit', 'entered_stage', 'exception_category'})
                self.assertNotIn('synthetic-private', stream.getvalue())


class LifecycleMarkerKindTests(unittest.TestCase):
    def observed_marker(self, marker, *, bits=0):
        fixture = DriverLifecycleDiagnosticTests('test_success_retains_exact_native_operation_order_and_return')
        result, error, _events, stream, _driver = fixture.run_lifecycle('pagehide-state-guard',
            bits=bits, marker_override=marker)
        self.assertIsNone(result)
        self.assertIs(type(error), contract.GateRefusal)
        self.assertTrue(stream.getvalue().isascii())
        self.assertLessEqual(len(stream.getvalue().encode('ascii')), 512)
        return json.loads(stream.getvalue()), stream.getvalue()

    def test_three_exact_marker_classes_from_real_selected_guard_never_publish_marker(self):
        cases = (('', 'empty'), ('qualification-refused', 'refused-literal'),
            ('synthetic-private-marker', 'other-string'), ('qualification-refused-extra', 'other-string'),
            ('qualification-cleared-extra', 'other-string'))
        for marker, kind in cases:
            with self.subTest(kind=kind, marker=marker):
                record, line = self.observed_marker(marker)
                self.assertEqual(record['first_marker_kind'], kind)
                self.assertEqual(record['first_guard_failure_bits'], 1)
                self.assertEqual(record['entered_stage'], 'pagehide-state-guard')
                self.assertEqual(record['exception_category'], 'gate-refusal')
                self.assertEqual(set(record), {'schema', 'status', 'phase', 'readiness_credit',
                    'entered_stage', 'exception_category', 'first_guard_failure_bits', 'first_marker_kind'})
                self.assertNotIn('synthetic-private', line)
                self.assertNotIn('qualification-refused-extra', line)
                self.assertNotIn('qualification-cleared-extra', line)

    def test_cleared_marker_other_failed_facts_have_bits_without_marker_category(self):
        for bits in (2, 4, 8, 16, 30):
            with self.subTest(bits=bits):
                record, _line = self.observed_marker('qualification-cleared', bits=bits)
                self.assertEqual(record['first_guard_failure_bits'], bits)
                self.assertNotIn('first_marker_kind', record)

    def test_wrong_marker_types_context_error_and_snapshot_omit_new_field(self):
        class Text(str):
            pass
        class RefusalSubclass(contract.GateRefusal):
            pass
        fresh = DriverLifecycleDiagnosticTests.FIRST
        rows = [('pagehide-state-guard', contract.GateRefusal(), marker, fresh)
            for marker in (None, True, 1, [], Text(''), Text('qualification-refused'))]
        rows.extend([('new-window-state-guard', contract.GateRefusal(), '', fresh),
            ('pagehide-state-guard', ValueError(), '', fresh),
            ('pagehide-state-guard', RefusalSubclass(), '', fresh),
            ('pagehide-state-guard', contract.GateRefusal(), '', []),
            ('pagehide-state-guard', contract.GateRefusal(), '', {**fresh, 'tokenEmpty': 1})])
        for stage, error, marker, snapshot in rows:
            with self.subTest(stage=stage, error=type(error).__name__, marker=type(marker).__name__), \
                    patch.object(browser_probe.sys, 'stderr', io.StringIO()) as stream:
                browser_probe.emit_lifecycle_refusal(stage, error, marker, snapshot)
                record = json.loads(stream.getvalue())
                self.assertNotIn('first_marker_kind', record)
                self.assertNotIn('first_guard_failure_bits', record)
                self.assertEqual(set(record), {'schema', 'status', 'phase', 'readiness_credit',
                    'entered_stage', 'exception_category'})


class PagehideSessionProofTests(unittest.TestCase):
    def test_scripts_require_trusted_pagehide_and_consume_only_one_fixed_byte(self):
        install = browser_probe.PAGEHIDE_PROOF_INSTALL
        consume = browser_probe.PAGEHIDE_PROOF_CONSUME
        self.assertEqual(install, DriverLifecycleDiagnosticTests.HANDLER)
        self.assertEqual(consume, DriverLifecycleDiagnosticTests.CONSUME)
        self.assertIn("storage.length >= 128 || storage.getItem(key) !== null", install)
        self.assertLess(install.index('event.isTrusted !== true'), install.index('storage.setItem('))
        self.assertEqual(install.count('storage.setItem('), 1)
        self.assertIn("catalogueTokenValue === '' && catalogueToken.value === '' && catalogueRows.length === 0 ? '1' : '0'", install)
        self.assertIn("}, {once: true});", install)
        self.assertLess(consume.index('value = storage.getItem(key)'), consume.index('storage.removeItem(key)'))
        self.assertLess(consume.index('storage.removeItem(key)'), consume.index("storage.getItem(key) !== null"))
        self.assertLess(consume.index("storage.getItem(key) !== null"), consume.index("value === '1'"))
        self.assertIn("value === '1' ? 'qualification-cleared' : value === '0' ? 'qualification-refused' : ''", consume)
        self.assertEqual(consume.count('storage.removeItem(key)'), 1)
        for forbidden in ('window.name', 'dispatchEvent', 'resetCatalogue', 'localStorage', 'catalogueToken.value = '):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, install + consume)

    def test_nonce_must_have_exact_real_producer_shape_before_any_install_or_navigation(self):
        class Text(str):
            pass
        cases = (None, True, 1, [], Text('a' * 64), '', 'a' * 63, 'a' * 65, 'A' * 64,
            'g' * 64, 'a' * 63 + '\n', 'synthetic-nonce')
        for nonce in cases:
            driver = browser_probe.Driver(12345, 200)
            driver.connect, driver.execute, driver.command, driver.snapshot = Mock(), Mock(), Mock(), Mock()
            with self.subTest(kind=type(nonce).__name__), patch.object(browser_probe.sys, 'stderr', io.StringIO()) as stream:
                with self.assertRaises(contract.GateRefusal):
                    driver.lifecycle('http://127.0.0.1:12346', 'synthetic-private-token', nonce)
                driver.connect.assert_called_once_with('synthetic-private-token', 3)
                driver.execute.assert_not_called()
                driver.command.assert_not_called()
                driver.snapshot.assert_not_called()
                record = json.loads(stream.getvalue())
                self.assertEqual(record['entered_stage'], 'pagehide-handler-install')
                self.assertNotIn('synthetic-private', stream.getvalue())

    def test_install_requires_exact_true_ack_so_collision_bound_or_missing_setup_cannot_pass(self):
        for ack in (None, False, 0, 1, 'true', [], {}):
            driver = browser_probe.Driver(12345, 200)
            driver.connect = Mock()
            driver.execute = Mock(return_value=ack)
            driver.command, driver.snapshot = Mock(), Mock()
            with self.subTest(kind=type(ack).__name__), patch.object(browser_probe.sys, 'stderr', io.StringIO()) as stream:
                with self.assertRaises(contract.GateRefusal):
                    driver.lifecycle('http://127.0.0.1:12346', 'synthetic-private-token', 'a' * 64)
                driver.execute.assert_called_once_with(browser_probe.PAGEHIDE_PROOF_INSTALL,
                    'row-qualification-pagehide-' + 'a' * 64)
                driver.command.assert_not_called()
                driver.snapshot.assert_not_called()
                self.assertEqual(json.loads(stream.getvalue())['entered_stage'], 'pagehide-handler-install')

    def test_each_fresh_nonce_binds_install_and_consumption_in_the_same_original_positions(self):
        fixture = DriverLifecycleDiagnosticTests('test_success_retains_exact_native_operation_order_and_return')
        for nonce in ('a' * 64, 'b' * 64):
            key = 'row-qualification-pagehide-' + nonce
            with self.subTest(nonce=nonce), patch.object(fixture, 'NONCE', nonce), patch.object(fixture, 'KEY', key):
                result, error, events, stream, driver = fixture.run_lifecycle()
                self.assertIsNone(error)
                self.assertEqual(result, dict(contract.CASES['pagehide-new-document']))
                self.assertEqual(stream.getvalue(), '')
                self.assertEqual([call.args for call in driver.execute.call_args_list], [
                    (fixture.HANDLER, key), (fixture.CONSUME, key), ('return window.opener === null;',)])
                self.assertEqual(driver.execute.call_count, 3)
                self.assertEqual(driver.command.call_count, 7)
                self.assertEqual(driver.snapshot.call_count, 2)
                self.assertLess(events.index('pagehide-marker-read'), events.index('pagehide-fresh-snapshot'))
                self.assertLess(events.index('pagehide-marker-read'), events.index('new-window-create'))
                self.assertEqual(driver.deadline, 200)

    def test_missing_refused_or_unrecognized_consumed_proof_never_accepts_fresh_defaults(self):
        fixture = DriverLifecycleDiagnosticTests('test_success_retains_exact_native_operation_order_and_return')
        for marker in ('', 'qualification-refused', 'synthetic-private-marker'):
            with self.subTest(marker=marker):
                result, error, events, stream, driver = fixture.run_lifecycle('pagehide-state-guard', marker_override=marker)
                self.assertIsNone(result)
                self.assertIs(type(error), contract.GateRefusal)
                self.assertEqual(driver.snapshot.call_count, 1)
                self.assertEqual(driver.command.call_count, 1)
                self.assertNotIn('new-window-create', events)
                self.assertEqual(json.loads(stream.getvalue())['first_guard_failure_bits'], 1)
                self.assertNotIn('synthetic-private', stream.getvalue())

    def test_install_and_consumption_faults_preserve_selected_error_chain_without_cleanup_queries(self):
        fixture = DriverLifecycleDiagnosticTests('test_success_retains_exact_native_operation_order_and_return')
        for stage in ('pagehide-handler-install', 'pagehide-marker-read'):
            for kind in (KeyboardInterrupt, SystemExit, MemoryError, TimeoutError, OSError):
                selected = kind('synthetic-private-selected')
                selected.__cause__ = RuntimeError('synthetic-private-cause')
                before = (selected.args, selected.__cause__, selected.__context__, selected.__suppress_context__)
                with self.subTest(stage=stage, kind=kind.__name__):
                    result, error, _events, stream, driver = fixture.run_lifecycle(stage, primary=selected)
                    self.assertIsNone(result)
                    self.assertIs(error, selected)
                    self.assertEqual((error.args, error.__cause__, error.__context__, error.__suppress_context__), before)
                    self.assertEqual(driver.execute.call_count, 1 if stage == 'pagehide-handler-install' else 2)
                    self.assertEqual(driver.command.call_count, 0 if stage == 'pagehide-handler-install' else 1)
                    self.assertEqual(driver.snapshot.call_count, 0)
                    self.assertEqual(json.loads(stream.getvalue())['entered_stage'], stage)
                    self.assertNotIn('synthetic-private', stream.getvalue())


class ServiceWorkerBoundaryDiagnosticTests(unittest.TestCase):
    PUBLIC = {'phase': 'service-worker-api-cache-boundary', 'status': 'refused', 'complete': False}

    def actual_failure(self, *, result=None, entry_fault=None, packed_fault=None, stream_fault=None):
        fixture = ActualPolicyCheckpointMainTests('test_actual_H_main_normal_commits_both_samples_in_order_before_pending_result')
        selected = contract.GateRefusal('synthetic-private-primary')
        stream = io.StringIO() if stream_fault is None else Mock()
        if stream_fault is not None:
            stream.write.side_effect = stream_fault
        original_packed = host_controller.packed
        def packed(value):
            if type(value) is dict and value.get('schema') == 'row.catalogue-service-worker-refusal.v1' and packed_fault is not None:
                raise packed_fault
            return original_packed(value)
        with patch.object(host_controller, 'emit_service_worker_refusal', side_effect=entry_fault,
                wraps=host_controller.emit_service_worker_refusal) as emit, \
                patch.object(host_controller, 'packed', side_effect=packed), \
                patch.object(host_controller, 'api_read_refusal', wraps=host_controller.api_read_refusal) as captured:
            code, record, holder = fixture.run_actual_main(final_label_failure=False,
                failure_phase='service-worker-api-cache-boundary' if result is None else None,
                failure_error=selected if result is None else None, service_worker_result=result, diagnostic_stream=stream)
        emit.assert_called_once()
        self.assertIs(emit.call_args.args[1], captured.call_args.args[1])
        if result is None:
            self.assertIs(captured.call_args.args[1], selected)
            self.assertEqual(selected.args, ('synthetic-private-primary',))
        self.assertEqual(code, 1)
        self.assertEqual(record['phase'], 'service-worker-api-cache-boundary')
        self.assertFalse(record['complete'])
        self.assertTrue(record['forced_cleanup_attempted'])
        self.assertTrue(record['cleanup_complete'])
        self.assertTrue(holder['samples']['initial']['observed'])
        self.assertFalse(holder['samples']['final']['observed'])
        return stream

    def test_actual_mark_failure_preserves_selected_error_cleanup_and_exact_two_lines(self):
        stream = self.actual_failure()
        lines = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(lines, [{'schema': 'row.catalogue-service-worker-refusal.v1', 'status': 'refused',
            'phase': 'service-worker-api-cache-boundary', 'readiness_credit': 0,
            'entered_stage': 'case-mark', 'exception_category': 'gate-refusal'},
            {'schema': 'row.catalogue-case-refusal.v1', 'status': 'refused',
                'phase': 'service-worker-api-cache-boundary', 'readiness_credit': 0}])
        self.assertNotIn('synthetic-private', stream.getvalue())

    def test_actual_seed_and_finish_guards_project_every_closed_JS_stage(self):
        for action in ('seed-api', 'finish'):
            eligible = host_controller.SW_PROBE_STAGES[:4] if action == 'seed-api' else tuple(
                stage for stage in host_controller.SW_PROBE_STAGES if stage != 'api-canary-seed')
            for stage in eligible:
                with self.subTest(action=action, stage=stage):
                    stream = self.actual_failure(result=(action, {'controlled': False, 'entered_stage': stage}))
                    diagnostic = json.loads(stream.getvalue().splitlines()[0])
                    self.assertEqual(diagnostic['entered_stage'], 'seed-result-guard' if action == 'seed-api' else 'finish-result-guard')
                    self.assertEqual(diagnostic['probe_stage'], stage)
                    self.assertEqual(diagnostic['exception_category'], 'gate-refusal')
                    self.assertNotIn('case_failure_bits', diagnostic)
                    self.assertLessEqual(len(stream.getvalue().splitlines()[0].encode('ascii')) + 1, 512)

    def test_actual_case_contract_false_fact_bits_remain_refused_after_real_static_event_guards(self):
        result = {'controlled': True, 'healthPolicyAbsent': True, 'authBypass': True,
            'noStoreBypass': True, 'removed': True, 'exact': True}
        for key, bit in (('healthPolicyAbsent', 8), ('authBypass', 16), ('noStoreBypass', 32),
                         ('removed', 64), ('exact', 128)):
            with self.subTest(key=key):
                stream = self.actual_failure(result=('finish', {**result, key: False}))
                diagnostic = json.loads(stream.getvalue().splitlines()[0])
                self.assertEqual(diagnostic['entered_stage'], 'case-record')
                self.assertEqual(diagnostic['case_failure_bits'], bit)
                self.assertNotIn('probe_stage', diagnostic)

    def test_all_operation_categories_and_primitive_masks_are_closed_and_private_free(self):
        class RefusalSubclass(contract.GateRefusal):
            pass
        cases = ((contract.GateRefusal, 'gate-refusal'), (KeyError, 'key-error'), (IndexError, 'index-error'),
            (TypeError, 'type-error'), (ValueError, 'value-error'), (TimeoutError, 'timeout-error'),
            (OSError, 'os-error'), (RefusalSubclass, 'other-exact-type'), (KeyboardInterrupt, 'other-exact-type'))
        for stage in host_controller.SW_HOST_STAGES:
            for kind, category in cases:
                with self.subTest(stage=stage, kind=kind.__name__), patch.object(host_controller.sys, 'stderr', io.StringIO()) as stream:
                    host_controller.emit_service_worker_refusal(self.PUBLIC, kind('synthetic-private'), stage)
                    diagnostic = json.loads(stream.getvalue())
                    self.assertEqual(diagnostic['exception_category'], category)
                    self.assertEqual(set(diagnostic), {'schema', 'status', 'phase', 'readiness_credit', 'entered_stage', 'exception_category'})
                    self.assertNotIn('synthetic-private', stream.getvalue())
        for bits in (1, 2, 4, 8, 16, 32, 64, 128, 256, 511):
            facts = {key: not bool(bits & (1 << index)) for index, key in enumerate(host_controller.SW_CASE_FACTS)}
            with self.subTest(bits=bits), patch.object(host_controller.sys, 'stderr', io.StringIO()) as stream:
                host_controller.emit_service_worker_refusal(self.PUBLIC, contract.GateRefusal(), 'case-record', facts=facts)
                self.assertEqual(json.loads(stream.getvalue())['case_failure_bits'], bits)
                self.assertLessEqual(len(stream.getvalue().encode('ascii')), 512)

    def test_malformed_private_wrong_context_and_subclass_optional_values_are_omitted(self):
        class Text(str):
            pass
        class Mapping(dict):
            pass
        probes = (None, [], Mapping(controlled=False, entered_stage='controller'),
            {'controlled': 0, 'entered_stage': 'controller'}, {'controlled': False, 'entered_stage': Text('controller')},
            {'controlled': False, 'entered_stage': 'synthetic-private-stage'},
            {'controlled': False, 'entered_stage': 'final-entry-bytes'},
            {Text('controlled'): False, 'entered_stage': 'controller'},
            {'controlled': False, 'entered_stage': 'controller', 'private': '/synthetic-private/path'})
        for probe in probes:
            with self.subTest(kind=type(probe).__name__), patch.object(host_controller.sys, 'stderr', io.StringIO()) as stream:
                host_controller.emit_service_worker_refusal(self.PUBLIC, contract.GateRefusal(), 'seed-result-guard', probe)
                self.assertNotIn('probe_stage', json.loads(stream.getvalue()))
                self.assertNotIn('synthetic-private', stream.getvalue())
        facts = dict.fromkeys(host_controller.SW_CASE_FACTS, True)
        for bad in ([], Mapping(facts), {**facts, 'controlled': 0}, {**facts, 'controlled': False, 'private': True},
                    {Text(key): value for key, value in facts.items()}):
            with self.subTest(kind=type(bad).__name__), patch.object(host_controller.sys, 'stderr', io.StringIO()) as stream:
                host_controller.emit_service_worker_refusal(self.PUBLIC, contract.GateRefusal(), 'case-record', facts=bad)
                self.assertNotIn('case_failure_bits', json.loads(stream.getvalue()))
        for public, stage in (({**self.PUBLIC, 'phase': 'api-read'}, 'case-record'),
                ({**self.PUBLIC, 'complete': True}, 'case-record'), ({**self.PUBLIC, 'status': 'complete'}, 'case-record'),
                (Mapping(self.PUBLIC), 'case-record'), (self.PUBLIC, Text('case-record')), (self.PUBLIC, '/synthetic-private')):
            with self.subTest(stage=stage), patch.object(host_controller.sys, 'stderr', io.StringIO()) as stream:
                host_controller.emit_service_worker_refusal(public, contract.GateRefusal(), stage)
                self.assertEqual(stream.getvalue(), '')

    def test_entry_serialization_and_stream_interruptions_never_replace_result_or_cleanup(self):
        for fault in (KeyboardInterrupt(), SystemExit(9), MemoryError('synthetic-private')):
            for location in ('entry_fault', 'packed_fault', 'stream_fault'):
                with self.subTest(fault=type(fault).__name__, location=location):
                    stream = self.actual_failure(**{location: fault})
                    if location != 'stream_fault':
                        self.assertEqual(json.loads(stream.getvalue()), {'schema': 'row.catalogue-case-refusal.v1',
                            'status': 'refused', 'phase': 'service-worker-api-cache-boundary', 'readiness_credit': 0})

    def test_seed_is_only_before_real_refresh_and_finish_checks_retained_canary_without_reseeding(self):
        source = browser_probe.SW_PROBE
        seed = source.index("if (arguments[2] === 'seed-api') {")
        write = source.index("await cache.put(url('/api/v1/profiles')")
        done = source.index('callback({controlled: true, seeded: true}); return;')
        read = source.index("const api = await cache.match(url('/api/v1/profiles'))")
        remove = source.index("await cache.delete(url('/api/v1/profiles'))")
        self.assertLess(seed, write)
        self.assertLess(write, done)
        self.assertLess(done, read)
        self.assertLess(read, remove)
        self.assertEqual(source.count("cache.put(url('/api/v1/profiles')"), 1)
        self.assertIn("if (!api || !(await api.text()).includes(marker)) throw new Error('canary');", source)
        self.assertIn("})().catch(() => callback({controlled: false, entered_stage: stage}));", source)
        self.assertNotIn('error.message', source)
        self.assertNotIn('error.stack', source)


class ServiceWorkerAuthNetworkTests(unittest.TestCase):
    def test_auth_probe_uses_reload_to_distinguish_HTTP_cache_from_worker_authorization_bypass(self):
        source = browser_probe.SW_PROBE
        start = "const response = await fetch('/app.js', mode === 'auth'\n      ? "
        auth = source.split(start, 1)[1].split(" : {cache: 'no-store'});", 1)[0]
        self.assertEqual(auth, "{cache: 'reload', headers: {'Authorization': 'Bearer ' + token}}")
        cache_mode = auth.split("cache: '", 1)[1].split("'", 1)[0]
        has_authorization = "headers: {'Authorization': 'Bearer ' + token}" in auth
        self.assertEqual(cache_mode, 'reload')
        self.assertNotEqual(cache_mode, 'no-store')
        self.assertTrue(has_authorization)
        # Counterfactual model: the SW cache contains the existing poisoned canary;
        # the HTTP cache contains a fresh real asset. This models the two distinct stores.
        def observations(mode, authorization, worker_honors_auth):
            worker_bypassed = mode == 'no-store' or authorization and worker_honors_auth
            correct_asset_bytes = worker_bypassed
            fresh_server_event = worker_bypassed and mode in ('reload', 'no-store')
            return correct_asset_bytes, fresh_server_event
        self.assertEqual(observations(cache_mode, has_authorization, True), (True, True))
        self.assertEqual(observations(cache_mode, has_authorization, False), (False, False))
        self.assertEqual(observations(cache_mode, False, True), (False, False))
        self.assertEqual(observations('default', True, True), (True, False))
        self.assertEqual(observations('no-store', True, False), (True, True))
        self.assertEqual(source.count("? {cache: 'reload', headers: {'Authorization': 'Bearer ' + token}} : {cache: 'no-store'});"), 1)

    def test_real_Driver_execute_emits_same_single_async_command_with_full_probe_and_arguments(self):
        driver = browser_probe.Driver(12345, 200)
        expected = {'/app.js': 'a' * 64}
        answer = {'controlled': True, 'healthPolicyAbsent': True, 'authBypass': True,
            'noStoreBypass': True, 'removed': True, 'exact': True}
        driver.command = Mock(return_value=answer)
        with patch.object(browser_probe.http.client, 'HTTPConnection') as connection:
            result = driver.execute(browser_probe.SW_PROBE, 'synthetic-private-token', expected, 'finish', async_=True)
            connection.assert_not_called()
        self.assertIs(result, answer)
        driver.command.assert_called_once_with('/execute/async', {'script': browser_probe.SW_PROBE,
            'args': ['synthetic-private-token', expected, 'finish']})
        self.assertEqual(driver.deadline, 200)
        self.assertIn("if (response.status !== 200 || await hash(await response.arrayBuffer()) !== expected['/app.js']) throw new Error('bypass');", browser_probe.SW_PROBE)


if __name__ == '__main__':
    unittest.main(verbosity=2)
