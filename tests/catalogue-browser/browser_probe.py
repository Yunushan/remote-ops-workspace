"""W3C HTTP client and actual DOM/storage/SW observations, hosted only.

The transport must be an owned loopback ChromeDriver supplied by the controller.
No browser process, product import or network operation occurs at module import.
"""
import http.client
import json
import re
import sys
import time

from gate_contract import (
    DRIVER_START_ERRORS,
    GateRefusal,
    decode,
    driver_start_diagnostic,
    need,
)

ELEMENT = 'element-6066-11e4-a52e-4f735466cecf'
SNAPSHOT = """
return {mode: catalogueMode, tokenEmpty: catalogueTokenValue === '',
 inputEmpty: catalogueToken.value === '', rows: catalogueRows,
 texts: Array.from(document.querySelectorAll('#profiles li'), e => e.textContent),
 busy: catalogueBusy, refreshDisabled: catalogueRefresh.disabled,
 saveDisabled: profileSubmit.disabled,
 authRefused: catalogueStatus.textContent.includes('Authentication failed'),
 serverRefused: catalogueStatus.textContent.includes('Catalogue request failed'),
 saved: profileStatus.textContent.includes('Profile saved by the local catalogue')};
"""
STORAGE = """
const secrets = arguments[0], callback = arguments[arguments.length - 1];
(async () => {
  const clean = value => !secrets.some(secret => String(value).includes(secret));
  let entries = 0;
  for (const storage of [localStorage, sessionStorage]) {
    if (storage.length > 128) throw new Error('bound');
    for (let i = 0; i < storage.length; ++i) {
      const key = storage.key(i), value = storage.getItem(key);
      if (String(value).length > 262144 || !clean(key) || !clean(value)) throw new Error('private');
      ++entries;
    }
  }
  if (typeof indexedDB.databases !== 'function') throw new Error('unsupported');
  const databases = await indexedDB.databases();
  if (databases.length > 16) throw new Error('bound');
  for (const metadata of databases) {
    if (!clean(metadata.name)) throw new Error('private');
    const db = await new Promise((resolve, reject) => {
      const request = indexedDB.open(metadata.name);
      request.onsuccess = () => resolve(request.result); request.onerror = reject;
      request.onupgradeneeded = () => { request.transaction.abort(); reject(new Error('changed')); };
    });
    try {
      if (db.objectStoreNames.length > 16) throw new Error('bound');
      for (const name of db.objectStoreNames) {
        if (!clean(name)) throw new Error('private');
        const transaction = db.transaction(name, 'readonly'), store = transaction.objectStore(name);
        const values = await new Promise((resolve, reject) => {
          const request = store.getAll(undefined, 129);
          request.onsuccess = () => resolve(request.result); request.onerror = reject;
        });
        const keys = await new Promise((resolve, reject) => {
          const request = db.transaction(name, 'readonly').objectStore(name).getAllKeys(undefined, 129);
          request.onsuccess = () => resolve(request.result); request.onerror = reject;
        });
        if (values.length > 128 || keys.length > 128) throw new Error('bound');
        const encoded = JSON.stringify([keys, values]);
        if (encoded.length > 262144 || !clean(encoded)) throw new Error('private');
        entries += values.length;
      }
    } finally { db.close(); }
  }
  const names = await caches.keys();
  if (names.length > 16) throw new Error('bound');
  for (const name of names) {
    if (!clean(name)) throw new Error('private');
    const cache = await caches.open(name), keys = await cache.keys();
    if (keys.length > 32) throw new Error('bound');
    for (const request of keys) {
      if (!clean(request.url) || request.headers.has('Authorization')) throw new Error('private');
      const response = await cache.match(request), text = await response.text();
      if (text.length > 262144 || !clean(text)) throw new Error('private');
      ++entries;
    }
  }
  callback({clean: true, entries});
})().catch(() => callback({clean: false}));
"""
SW_PROBE = """
const token = arguments[0], expected = arguments[1], callback = arguments[arguments.length - 1];
(async () => {
  if (!navigator.serviceWorker.controller) throw new Error('uncontrolled');
  const names = await caches.keys();
  if (names.length !== 1 || names[0] !== 'remote-ops-workspace-static-v3') throw new Error('cache');
  const cache = await caches.open(names[0]), url = path => new URL(path, location.origin).href;
  const marker = 'qualification-cache-canary';
  await cache.put(url('/api/v1/profiles'), new Response(JSON.stringify({profiles: [{name: marker}]}),
    {headers: {'Content-Type': 'application/json'}}));
  // The controller clicks the real refresh button before removing this API canary.
  if (arguments[2] === 'seed-api') { callback({controlled: true, seeded: true}); return; }
  const api = await cache.match(url('/api/v1/profiles'));
  if (!api || !(await api.text()).includes(marker)) throw new Error('canary');
  await cache.delete(url('/api/v1/profiles'));
  for (const path of ['/healthz', '/api/v1/health', '/enterprise-policy.json']) {
    const response = await fetch(path, {cache: 'no-store', headers: {'Authorization': 'Bearer ' + token}});
    if (response.status !== 200 || response.headers.get('Cache-Control') !== 'no-store') throw new Error('response');
    if (await cache.match(url(path))) throw new Error('private-cache');
  }
  const hash = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    value => value.toString(16).padStart(2, '0')).join('');
  let authBypass = false, noStoreBypass = false;
  for (const mode of ['auth', 'no-store']) {
    await cache.put(url('/app.js'), new Response(marker));
    const response = await fetch('/app.js', mode === 'auth'
      ? {headers: {'Authorization': 'Bearer ' + token}} : {cache: 'no-store'});
    if (response.status !== 200 || await hash(await response.arrayBuffer()) !== expected['/app.js']) throw new Error('bypass');
    if (mode === 'auth') authBypass = true; else noStoreBypass = true;
  }
  await cache.delete(url('/app.js'));
  const publicResponse = await fetch('/app.js', {cache: 'no-store', credentials: 'omit'});
  if (publicResponse.status !== 200) throw new Error('static');
  await cache.put(url('/app.js'), publicResponse);
  const keys = await cache.keys();
  if (keys.length !== Object.keys(expected).length) throw new Error('inventory');
  for (const request of keys) {
    const parsed = new URL(request.url);
    if (parsed.origin !== location.origin || parsed.search || !Object.hasOwn(expected, parsed.pathname)) throw new Error('private');
    const response = await cache.match(request);
    if (response.headers.get('Cache-Control')?.includes('no-store') || request.headers.has('Authorization')) throw new Error('private');
    if (await hash(await response.arrayBuffer()) !== expected[parsed.pathname]) throw new Error('bytes');
  }
  callback({controlled: true, healthPolicyAbsent: true, authBypass, noStoreBypass, removed: true, exact: true});
})().catch(() => callback({controlled: false}));
"""


def prepare_driver_start(driver):
    context = None
    try:
        context = {'token': object(), 'active': False, 'call': None, 'attached': None}
        driver._row_driver_start_context = context
        if driver._row_driver_start_context is context:
            context['active'] = True
    except BaseException:
        pass
    return context


def _driver_context(driver):
    try:
        context = driver._row_driver_start_context
        if (type(context) is dict and set(context) == {'token', 'active', 'call', 'attached'}
                and type(context['token']) is object and context['active'] is True):
            return context
    except BaseException:
        pass
    return None


def _clear_driver_capture(context, *, start=False):
    try:
        if context is not None:
            context['call'] = None
            if start:
                context['attached'] = None
    except BaseException:
        pass


def _driver_exception_token(error):
    for kind, token in ((GateRefusal, 'gate-refusal'), (TimeoutError, 'timeout'),
                        (ConnectionRefusedError, 'connection-refused'),
                        (http.client.RemoteDisconnected, 'remote-disconnected'),
                        (ConnectionResetError, 'connection-reset'), (BrokenPipeError, 'broken-pipe'),
                        (http.client.HTTPException, 'http-error'), (http.client.BadStatusLine, 'http-error'),
                        (http.client.IncompleteRead, 'http-error'), (KeyError, 'key-error'),
                        (TypeError, 'type-error'), (ValueError, 'value-error'),
                        (KeyboardInterrupt, 'interrupted'), (SystemExit, 'interrupted')):
        if type(error) is kind:
            return token
    return 'other'


DRIVER_MESSAGE_PREFIX_CODEPOINTS = 4096
DRIVER_MESSAGE_MARKERS = (
    (1, ('Chrome instance exited.',)),
    (2, ('failed to start:',)),
    (4, ("DevToolsActivePort file doesn't exist",)),
    (8, ('Could not remove old devtools port file.',)),
    (16, ('This version of', 'only supports')),
)


def _driver_message_bits(message):
    """Positive literal presence in a partial message; never a causal finding."""
    try:
        if type(message) is not str:
            return None
        prefix = message[:DRIVER_MESSAGE_PREFIX_CODEPOINTS]
        bits = sum(bit for bit, literals in DRIVER_MESSAGE_MARKERS
                   if all(literal in prefix for literal in literals))
        return bits if 1 <= bits <= 31 else None
    except BaseException:
        return None


def _driver_error_token(data, *, message_observation=None):
    try:
        if type(message_observation) is dict:
            message_observation.pop('message_bits', None)
    except BaseException:
        pass
    try:
        if type(data) is not bytes or len(data) > 262144:
            return None
        value = decode(data, 262144)
        if type(value) is not dict or type(value.get('value')) is not dict:
            return None
        token = value['value'].get('error')
        if type(token) is not str:
            return None
        try:
            if token == 'session not created' and type(message_observation) is dict:
                bits = _driver_message_bits(value['value'].get('message'))
                if type(bits) is int and 1 <= bits <= 31:
                    message_observation['message_bits'] = bits
        except BaseException:
            pass  # New classification faults retain the existing valid error token.
        return token if token in DRIVER_START_ERRORS[:-1] else 'other'
    except BaseException:
        return None


def _note_driver_call_failure(context, error, step, status, data):
    try:
        if context is None:
            return
        context['call'] = None
        observed = status if type(status) is int and 100 <= status <= 599 else None
        token = None
        message_observation = None
        if step == 'connection-close':
            observed = None
        elif step == 'response-guard' and observed is not None and observed != 200:
            if observed == 500:
                try:
                    message_observation = {}
                except BaseException:
                    pass
            token = _driver_error_token(data, message_observation=message_observation)
        fields = {'step': step, 'exception': _driver_exception_token(error),
                  'http_status': observed, 'webdriver_error': token}
        try:
            if observed == 500 and token == 'session not created' and type(message_observation) is dict:
                bits = message_observation.get('message_bits')
                if type(bits) is int and 1 <= bits <= 31:
                    fields['message_bits'] = bits
        except BaseException:
            pass
        context['call'] = (error, fields)
    except BaseException:
        pass


def _note_driver_start_failure(context, error, operation):
    try:
        if context is None:
            return
        context['attached'] = None
        fields = {'operation': operation, 'step': 'start-control',
                  'exception': _driver_exception_token(error), 'http_status': None, 'webdriver_error': None}
        call = context['call']
        if (operation in ('session-create', 'session-timeouts') and type(call) is tuple
                and len(call) == 2 and call[0] is error and type(call[1]) is dict):
            fields.update(call[1])
        if (fields['operation'] != 'session-create' or fields['step'] != 'response-guard'
                or fields['exception'] != 'gate-refusal' or type(fields['http_status']) is not int
                or fields['http_status'] != 500 or fields['webdriver_error'] != 'session not created'):
            fields.pop('message_bits', None)
        fields = driver_start_diagnostic(fields)
        snapshot = (context['token'], fields)
        error._row_driver_start_diagnostic = snapshot
        if error._row_driver_start_diagnostic is snapshot:
            context['attached'] = (error, snapshot)
    except BaseException:
        pass


def driver_start_fields(context, error):
    try:
        if type(context) is not dict or context.get('active') is not True:
            return None
        attached = context['attached']
        if type(attached) is not tuple or len(attached) != 2 or attached[0] is not error:
            return None
        snapshot = attached[1]
        if (type(snapshot) is not tuple or len(snapshot) != 2 or snapshot[0] is not context['token']
                or error._row_driver_start_diagnostic is not snapshot):
            return None
        return driver_start_diagnostic(snapshot[1])
    except BaseException:
        return None


def emit_lifecycle_refusal(stage, error, marker=None, fresh=None):
    """Project only current caller-local fixed stage/category and optional typed mismatch bits."""
    try:
        need(type(stage) is str and stage in ('connect', 'pagehide-handler-install',
            'same-origin-navigation', 'pagehide-marker-read', 'pagehide-fresh-snapshot',
            'pagehide-state-guard', 'original-window-read', 'new-window-create',
            'new-window-switch', 'new-window-navigation', 'new-window-opener-guard',
            'new-window-snapshot', 'new-window-state-guard', 'new-window-close', 'original-window-restore'))
        categories = {GateRefusal: 'gate-refusal', KeyError: 'key-error', IndexError: 'index-error',
            TypeError: 'type-error', ValueError: 'value-error', TimeoutError: 'timeout-error', OSError: 'os-error'}
        diagnostic = {'schema': 'row.catalogue-lifecycle-refusal.v1', 'status': 'refused',
            'phase': 'pagehide-new-document', 'readiness_credit': 0, 'entered_stage': stage,
            'exception_category': categories.get(type(error), 'other-exact-type')}
        if (stage == 'pagehide-state-guard' and type(error) is GateRefusal
                and type(marker) is str and type(fresh) is dict
                and all(type(key) is str for key in fresh)
                and all(key in fresh for key in ('tokenEmpty', 'inputEmpty', 'rows', 'refreshDisabled'))
                and all(type(fresh[key]) is bool for key in ('tokenEmpty', 'inputEmpty', 'refreshDisabled'))
                and type(fresh['rows']) is list):
            failed = (marker != 'qualification-cleared', fresh['tokenEmpty'] is not True,
                fresh['inputEmpty'] is not True, len(fresh['rows']) != 0, fresh['refreshDisabled'] is not True)
            bits = sum(1 << index for index, value in enumerate(failed) if value)
            if bits:
                diagnostic['first_guard_failure_bits'] = bits
                if bits & 1:
                    kind = 'other-string'
                    if marker == '':
                        kind = 'empty'
                    elif marker == 'qualification-refused':
                        kind = 'refused-literal'
                    diagnostic['first_marker_kind'] = kind
        raw = json.dumps(diagnostic, sort_keys=True, separators=(',', ':')).encode('ascii')
        need(len(raw) + 1 <= 512)
        sys.stderr.write(raw.decode('ascii') + '\n')
    except BaseException:
        pass


class Driver:
    def __init__(self, port, deadline):
        need(type(port) is int and 1 <= port <= 65535)
        self.port = port
        self.deadline = deadline
        self.session = None
        self.origin = None

    def call(self, method, path, body=None, timeout=10):
        context = None
        try:
            context = _driver_context(self)
            _clear_driver_capture(context)
        except BaseException:
            context = None
        step = 'call-preflight'
        status = None
        data = None
        try:
            need(method in ('GET', 'POST', 'DELETE') and re.fullmatch(r'/[A-Za-z0-9/_.-]*', path)
                 and all(segment not in ('.', '..') for segment in path.split('/')))
            remaining = min(timeout, self.deadline - time.monotonic())
            need(remaining > 0)
            step = 'connection-create'
            connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=remaining)
            try:
                step = 'request-encode'
                raw = None if body is None else json.dumps(body, separators=(',', ':')).encode('utf-8')
                need(raw is None or len(raw) <= 262144)
                step = 'request-send'
                connection.request(method, path, body=raw, headers={'Content-Type': 'application/json'})
                step = 'response-open'
                response = connection.getresponse()
                step = 'response-read'
                data = response.read(262145)
                step = 'response-guard'
                need((status := response.status) == 200 and len(data) <= 262144)
                step = 'response-decode'
                value = decode(data, 262144)
                step = 'value-envelope'
                need(type(value) is dict and 'value' in value)
                return value['value']
            finally:
                try:
                    connection.close()
                except BaseException:
                    step = 'connection-close'
                    raise
        except BaseException as error:
            try:
                _note_driver_call_failure(context, error, step, status, data)
            except BaseException:
                pass
            raise

    def command(self, suffix, body=None, method='POST', timeout=10):
        need(self.session is not None)
        if suffix == '/url':
            need(type(body) is dict and type(body.get('url')) is str and self.origin is not None
                 and body['url'].startswith(self.origin + '/'))
        return self.call(method, '/session/' + self.session + suffix, body, timeout)

    def start(self, binary, profile):
        context = None
        try:
            context = _driver_context(self)
            _clear_driver_capture(context, start=True)
        except BaseException:
            context = None
        operation = 'session-create'
        try:
            try:
                _clear_driver_capture(context)
            except BaseException:
                pass
            value = self.call('POST', '/session', {'capabilities': {'alwaysMatch': {
                'browserName': 'chrome', 'pageLoadStrategy': 'normal', 'goog:chromeOptions': {
                    'binary': str(binary), 'detach': False, 'args': ['--headless=new',
                        '--disable-background-networking', '--disable-component-update', '--disable-sync',
                        '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
                        '--no-first-run', '--no-default-browser-check', '--user-data-dir=' + str(profile)]}}}})
            operation = 'session-result'
            need(type(value) is dict and type(value.get('sessionId')) is str
                 and re.fullmatch(r'[a-zA-Z0-9-]{1,128}', value['sessionId']))
            self.session = value['sessionId']
            operation = 'session-capabilities'
            capabilities = value['capabilities']
            operation = 'session-timeouts'
            try:
                _clear_driver_capture(context)
            except BaseException:
                pass
            self.command('/timeouts', {'script': 10000, 'pageLoad': 10000, 'implicit': 0})
            return capabilities
        except BaseException as error:
            try:
                _note_driver_start_failure(context, error, operation)
            except BaseException:
                pass
            raise

    def execute(self, script, *args, async_=False):
        return self.command('/execute/' + ('async' if async_ else 'sync'), {'script': script, 'args': list(args)})

    def element(self, selector):
        value = self.command('/element', {'using': 'css selector', 'value': selector})
        need(type(value) is dict and type(value.get(ELEMENT)) is str
             and re.fullmatch(r'[a-zA-Z0-9._-]{1,256}', value[ELEMENT]))
        return '/element/' + value[ELEMENT]

    def click(self, selector):
        self.command(self.element(selector) + '/click', {})

    def fill(self, selector, text):
        suffix = self.element(selector)
        self.command(suffix + '/clear', {})
        self.command(suffix + '/value', {'text': text})

    def snapshot(self):
        return self.execute(SNAPSHOT)

    def wait(self, predicate, timeout=10):
        limit = min(self.deadline, time.monotonic() + timeout)
        while time.monotonic() < limit:
            value = self.snapshot()
            if predicate(value):
                return value
            time.sleep(0.05)
        need(False)

    def connect(self, token, count):
        self.fill('#catalogue-token', token)
        self.click('#catalogue-form button')
        # Read only; the actual DOM form handler owns request/credential behavior.
        return self.wait(lambda row: not row['busy'] and not row['tokenEmpty'] and len(row['rows']) == count)

    def create(self, name, target, count):
        self.fill('#profile-form input[name=name]', name)
        self.fill('#profile-form input[name=target]', target)
        self.click('#profile-submit')
        return self.wait(lambda row: not row['busy'] and row['saved'] and len(row['rows']) == count)

    def refresh(self, count):
        self.click('#catalogue-refresh')
        return self.wait(lambda row: not row['busy'] and len(row['rows']) == count)

    def private_storage_absent(self, tokens, names):
        value = self.execute(STORAGE, tokens + names + ['catalogue-private-reference', 'catalogue-private-key'], async_=True)
        need(type(value) is dict and value.get('clean') is True)
        return True

    def lifecycle(self, origin, token, nonce):
        stage = None
        marker = fresh = None
        try:
            stage = 'connect'
            self.connect(token, 3)
            stage = 'pagehide-handler-install'
            self.execute("window.addEventListener('pagehide', () => { window.name = catalogueTokenValue === '' && catalogueToken.value === '' && catalogueRows.length === 0 ? 'qualification-cleared' : 'qualification-refused'; }, {once: true});")
            stage = 'same-origin-navigation'
            self.command('/url', {'url': origin + '/index.html?qualification-away=' + nonce})
            stage = 'pagehide-marker-read'
            marker = self.execute('return window.name;')
            stage = 'pagehide-fresh-snapshot'
            fresh = self.snapshot()
            stage = 'pagehide-state-guard'
            need(marker == 'qualification-cleared' and fresh['tokenEmpty'] and fresh['inputEmpty']
                 and fresh['rows'] == [] and fresh['refreshDisabled'])
            stage = 'original-window-read'
            original = self.command('/window', method='GET')
            stage = 'new-window-create'
            tab = self.command('/window/new', {'type': 'tab'})
            stage = 'new-window-switch'
            self.command('/window', {'handle': tab['handle']})
            stage = 'new-window-navigation'
            self.command('/url', {'url': origin + '/index.html'})
            stage = 'new-window-opener-guard'
            need(self.execute('return window.opener === null;') is True)
            stage = 'new-window-snapshot'
            fresh = self.snapshot()
            stage = 'new-window-state-guard'
            need(fresh['tokenEmpty'] and fresh['inputEmpty'] and fresh['rows'] == [] and fresh['refreshDisabled'])
            stage = 'new-window-close'
            self.command('/window', method='DELETE')
            stage = 'original-window-restore'
            self.command('/window', {'handle': original})
            return {'real_pagehide_clear_observed': True, 'new_document_requires_auth': True,
                'new_noopener_requires_auth': True, 'synthetic_lifecycle_event_used': False}
        except BaseException as error:
            try:
                emit_lifecycle_refusal(stage, error, marker, fresh)
            except BaseException:
                pass
            raise

    def controlled(self):
        value = self.execute("const done = arguments[arguments.length-1]; navigator.serviceWorker.ready.then(() => { if (navigator.serviceWorker.controller) done(true); else navigator.serviceWorker.addEventListener('controllerchange', () => done(!!navigator.serviceWorker.controller), {once:true}); }).catch(() => done(false));", async_=True)
        need(value is True)

    def close(self):
        if self.session is not None:
            self.command('', method='DELETE')
            self.session = None
