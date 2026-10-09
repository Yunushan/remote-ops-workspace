"""Pure result/frame contracts. Validation itself is never host evidence."""
import hashlib
import json
import re

MAX_PUBLIC = 65536
CASES = {
    'api-read': {'status': 200, 'dom_seed': True, 'input_cleared': True, 'no_store': True, 'public_only': True},
    'api-create-refresh': {'post_status': 201, 'get_status': 200, 'replace_false': True, 'disk_count': 2, 'disk_dom_agree': True},
    'restart-persistence-auth-rotation': {'first_zero_reaped': True, 'listener_gone': True, 'old_status': 401,
        'old_auth_cleared': True, 'new_status': 200, 'persisted_digest_equal': True, 'second_post_status': 201,
        'disk_count': 3, 'disk_dom_agree': True, 'token_digests_distinct': True},
    'disconnect-token-state': {'token_empty': True, 'rows_empty': True, 'input_empty': True, 'controls_disabled': True,
        'no_authenticated_request_after_disconnect': True, 'storage_private_absent': True},
    'pagehide-new-document': {'real_pagehide_clear_observed': True, 'new_document_requires_auth': True,
        'new_noopener_requires_auth': True, 'synthetic_lifecycle_event_used': False},
    'service-worker-api-cache-boundary': {'controlled': True, 'api_canary_bypassed': True, 'fresh_server_get': True,
        'health_policy_not_cached': True, 'auth_static_canary_bypassed': True, 'no_store_static_canary_bypassed': True,
        'canaries_removed': True, 'final_cache_public_exact': True, 'storage_private_absent': True},
    'owned-server-down': {'second_zero_reaped': True, 'listener_gone': True, 'visible_refusal': True,
        'token_rows_cleared': True, 'api_mode_retained': True, 'stale_or_demo_returned': False},
}
LIMITS = [
    'Observed hosted Linux Chrome/ChromeDriver catalogue metadata only; no reproduced release browser artifact',
    'No Android/iOS/installed-PWA/browser-matrix/native-session/installer/signing claim',
    'No complete OS descendant or physical network isolation proof; disposable-host destruction remains required',
    'Runtime mapping inventory covers observed executable mappings only, not writable browser resources or every OS input',
]

class GateRefusal(ValueError):
    pass

def need(condition):
    if not condition:
        raise GateRefusal('catalogue-gate-contract-refused')

def exact(value, fields):
    need(type(value) is dict and set(value) == set(fields))

def digest(value):
    need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None)

def integer(value, maximum, minimum=0):
    need(type(value) is int and minimum <= value <= maximum)

def pairs(items):
    result = {}
    for key, value in items:
        need(key not in result)
        result[key] = value
    return result

def decode(raw, maximum=MAX_PUBLIC):
    need(type(raw) is bytes and len(raw) <= maximum)
    try:
        return json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(GateRefusal('catalogue-gate-contract-refused')))
    except (ValueError, RecursionError) as exc:
        raise GateRefusal('catalogue-gate-contract-refused') from exc

def check_case(name, facts):
    need(type(name) is str and name in CASES)
    exact(facts, CASES[name])
    for key, expected in CASES[name].items():
        if type(expected) is bool:
            need(facts[key] is expected)
        else:
            need(type(facts[key]) is int and facts[key] == expected)

def validate(raw, expected):
    record = decode(raw)
    exact(record, {'schema', 'status', 'complete', 'binding', 'runtime', 'checks', 'inventories', 'events',
        'cleanup', 'elapsed_ms', 'server_down_ms', 'source_unchanged', 'runtime_unchanged', 'limits', 'readiness_credit'})
    need(record['schema'] == 'row.ubuntu-actual-catalogue-webdriver.v1')
    need(record['status'] == 'observations-complete-with-limits' and record['complete'] is True)
    exact(record['binding'], {'nonce', 'source_head', 'source_tree', 'source_bytes_sha256', 'workflow_sha256',
        'run_id', 'run_attempt', 'event_sha', 'image_version', 'image_os'})
    need(record['binding'] == expected['binding'])
    for key in ('nonce', 'source_bytes_sha256', 'workflow_sha256'):
        digest(record['binding'][key])
    for key in ('source_head', 'source_tree', 'event_sha'):
        need(type(record['binding'][key]) is str and re.fullmatch(r'[0-9a-f]{40}', record['binding'][key]))
    for key in ('run_id', 'run_attempt'):
        need(type(record['binding'][key]) is str and re.fullmatch(r'[1-9][0-9]{0,19}', record['binding'][key]))
    need(record['binding']['image_os'] == 'ubuntu24')
    need(type(record['binding']['image_version']) is str and re.fullmatch(r'[0-9.]{1,64}', record['binding']['image_version']))
    exact(record['runtime'], {'chrome_version', 'driver_version', 'python_version', 'tool_inventory_sha256', 'loaded_runtime_sha256', 'loaded_runtime_files'})
    need(record['runtime'] == expected['runtime'])
    need(type(record['runtime']['chrome_version']) is str and re.fullmatch(r'[0-9]+(?:\.[0-9]+){3}', record['runtime']['chrome_version']))
    need(record['runtime']['driver_version'] == record['runtime']['chrome_version'])
    need(record['runtime']['python_version'] == '3.14.7')
    digest(record['runtime']['tool_inventory_sha256'])
    digest(record['runtime']['loaded_runtime_sha256'])
    integer(record['runtime']['loaded_runtime_files'], 4096, 1)
    rows = record['checks']
    need(type(rows) is list and len(rows) == len(CASES))
    need([row.get('id') for row in rows if type(row) is dict] == list(CASES))
    for row in rows:
        exact(row, {'id', 'facts'})
        check_case(row['id'], row['facts'])
    inventories = record['inventories']
    need(type(inventories) is list and len(inventories) == 4)
    for row, (phase, count) in zip(inventories, (('seed', 1), ('created', 2), ('restarted', 2), ('second-created', 3)), strict=True):
        exact(row, {'phase', 'count', 'digest'})
        need(row['phase'] == phase and type(row['count']) is int and row['count'] == count)
        digest(row['digest'])
    need(inventories[1]['digest'] == inventories[2]['digest'])
    need(inventories[0]['digest'] != inventories[1]['digest'] != inventories[3]['digest'])
    events = record['events']
    need(type(events) is list and 8 <= len(events) <= 128)
    seen = set()
    for event in events:
        exact(event, {'launch', 'ordinal', 'case', 'method', 'route', 'status', 'no_store', 'authorization_present'})
        integer(event['launch'], 2, 1)
        integer(event['ordinal'], 128, 1)
        need((event['launch'], event['ordinal']) not in seen)
        seen.add((event['launch'], event['ordinal']))
        need(type(event['case']) is str and event['case'] in CASES)
        need(event['method'] in ('GET', 'POST') and event['route'] in ('catalogue', 'health', 'policy', 'static'))
        need(type(event['status']) is int and event['status'] in (200, 201, 401))
        need(type(event['authorization_present']) is bool and type(event['no_store']) is bool)
        if event['route'] != 'static':
            need(event['no_store'] is True)
    for case, method, status in (('api-read', 'GET', 200), ('api-create-refresh', 'POST', 201),
        ('api-create-refresh', 'GET', 200), ('restart-persistence-auth-rotation', 'GET', 401),
        ('restart-persistence-auth-rotation', 'GET', 200), ('restart-persistence-auth-rotation', 'POST', 201),
        ('service-worker-api-cache-boundary', 'GET', 200)):
        need(any(event['case'] == case and event['route'] == 'catalogue' and event['method'] == method
            and event['status'] == status and event['authorization_present'] is True for event in events))
    exact(record['cleanup'], {'all_retained_zero', 'all_reaped', 'owned_groups_gone', 'listeners_gone', 'forced_cleanup', 'descendants_complete'})
    for key in ('all_retained_zero', 'all_reaped', 'owned_groups_gone', 'listeners_gone'):
        need(record['cleanup'][key] is True)
    need(record['cleanup']['forced_cleanup'] is False and record['cleanup']['descendants_complete'] is False)
    integer(record['elapsed_ms'], 299999)
    integer(record['server_down_ms'], 5500)
    need(record['source_unchanged'] is True and record['runtime_unchanged'] is True)
    need(record['limits'] == LIMITS and type(record['readiness_credit']) is int and record['readiness_credit'] == 0)
    return {'status': 'result-contract-valid-only', 'record_sha256': hashlib.sha256(raw).hexdigest(),
        'genuine_host_authority': False, 'readiness_credit': 0}


PREPARATION_STEPS = ('source-checks', 'workflow-command', 'workflow-bytes', 'source-summary',
    'python-path', 'chrome-file-pin', 'driver-file-pin', 'python-file-pin', 'git-file-pin',
    'runtime-tool-owners', 'runtime-checkpoint')


CHROME_FILE_STAGES = ('lstat-before', 'regular-file', 'single-link', 'size-bound', 'nonempty',
    'write-mode', 'root-owner', 'trusted-owner', 'open', 'header-read', 'rewind', 'sha256-read',
    'elf-header', 'executable-mode', 'lstat-after', 'stable-identity')


def public_bytes(raw):
    """Privacy reader, not an authenticity/adoption or genuine-host decision."""
    record = decode(raw)
    need(type(record) is dict)
    if record.get('complete') is True:
        need('binding' in record and 'runtime' in record)
        validate(raw, {'binding': record['binding'], 'runtime': record['runtime']})
        return raw
    required = {'schema', 'status', 'complete', 'phase', 'readiness_credit', 'limits'}
    optional = {'private_streams', 'forced_cleanup_attempted', 'cleanup_complete', 'preparation_step', 'chrome_file_stage'}
    need(required.issubset(record) and set(record).issubset(required | optional))
    need(record['schema'] == 'row.ubuntu-actual-catalogue-webdriver.v1' and record['status'] == 'refused'
         and record['complete'] is False and type(record['readiness_credit']) is int and record['readiness_credit'] == 0
         and record['limits'] == LIMITS)
    need(type(record['phase']) is str and record['phase'] in ('preparation', 'host-runtime-observation', *CASES, 'cleanup'))
    if 'preparation_step' in record:
        step = record['preparation_step']
        need(type(step) is str and step in PREPARATION_STEPS)
        need(record['phase'] == 'preparation' or (record['phase'] == 'host-runtime-observation'
             and step == 'runtime-checkpoint'))
    if 'chrome_file_stage' in record:
        stage = record['chrome_file_stage']
        need(type(stage) is str and stage in CHROME_FILE_STAGES)
        need(record['phase'] == 'preparation' and record.get('preparation_step') == 'chrome-file-pin')
    for key in ('forced_cleanup_attempted', 'cleanup_complete'):
        if key in record:
            need(type(record[key]) is bool)
    if 'private_streams' in record:
        streams = record['private_streams']
        need(type(streams) is list and len(streams) <= 128)
        for stream in streams:
            exact(stream, {'stdout_bytes', 'stdout_sha256', 'stderr_bytes', 'stderr_sha256', 'overflow'})
            integer(stream['stdout_bytes'], 65536)
            integer(stream['stderr_bytes'], 65536)
            digest(stream['stdout_sha256'])
            digest(stream['stderr_sha256'])
            need(type(stream['overflow']) is bool)
    return raw
