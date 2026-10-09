"""W3C HTTP client and actual DOM/storage/SW observations, hosted only.

The transport must be an owned loopback ChromeDriver supplied by the controller.
No browser process, product import or network operation occurs at module import.
"""
import http.client
import json
import re
import time

from gate_contract import decode, need

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


class Driver:
    def __init__(self, port, deadline):
        need(type(port) is int and 1 <= port <= 65535)
        self.port = port
        self.deadline = deadline
        self.session = None
        self.origin = None

    def call(self, method, path, body=None, timeout=10):
        need(method in ('GET', 'POST', 'DELETE') and re.fullmatch(r'/[A-Za-z0-9/_-]*', path))
        remaining = min(timeout, self.deadline - time.monotonic())
        need(remaining > 0)
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=remaining)
        try:
            raw = None if body is None else json.dumps(body, separators=(',', ':')).encode('utf-8')
            need(raw is None or len(raw) <= 262144)
            connection.request(method, path, body=raw, headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            data = response.read(262145)
            need(response.status == 200 and len(data) <= 262144)
            value = decode(data, 262144)
            need(type(value) is dict and 'value' in value)
            return value['value']
        finally:
            connection.close()

    def command(self, suffix, body=None, method='POST', timeout=10):
        need(self.session is not None)
        if suffix == '/url':
            need(type(body) is dict and type(body.get('url')) is str and self.origin is not None
                 and body['url'].startswith(self.origin + '/'))
        return self.call(method, '/session/' + self.session + suffix, body, timeout)

    def start(self, binary, profile):
        value = self.call('POST', '/session', {'capabilities': {'alwaysMatch': {
            'browserName': 'chrome', 'pageLoadStrategy': 'normal', 'goog:chromeOptions': {
                'binary': str(binary), 'detach': False, 'args': ['--headless=new',
                    '--disable-background-networking', '--disable-component-update', '--disable-sync',
                    '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
                    '--no-first-run', '--no-default-browser-check', '--user-data-dir=' + str(profile)]}}}})
        need(type(value) is dict and type(value.get('sessionId')) is str
             and re.fullmatch(r'[a-zA-Z0-9-]{1,128}', value['sessionId']))
        self.session = value['sessionId']
        capabilities = value['capabilities']
        self.command('/timeouts', {'script': 10000, 'pageLoad': 10000, 'implicit': 0})
        return capabilities

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
        self.connect(token, 3)
        self.execute("window.addEventListener('pagehide', () => { window.name = catalogueTokenValue === '' && catalogueToken.value === '' && catalogueRows.length === 0 ? 'qualification-cleared' : 'qualification-refused'; }, {once: true});")
        self.command('/url', {'url': origin + '/index.html?qualification-away=' + nonce})
        marker = self.execute('return window.name;')
        fresh = self.snapshot()
        need(marker == 'qualification-cleared' and fresh['tokenEmpty'] and fresh['inputEmpty']
             and fresh['rows'] == [] and fresh['refreshDisabled'])
        original = self.command('/window', method='GET')
        tab = self.command('/window/new', {'type': 'tab'})
        self.command('/window', {'handle': tab['handle']})
        self.command('/url', {'url': origin + '/index.html'})
        need(self.execute('return window.opener === null;') is True)
        fresh = self.snapshot()
        need(fresh['tokenEmpty'] and fresh['inputEmpty'] and fresh['rows'] == [] and fresh['refreshDisabled'])
        self.command('/window', method='DELETE')
        self.command('/window', {'handle': original})
        return {'real_pagehide_clear_observed': True, 'new_document_requires_auth': True,
            'new_noopener_requires_auth': True, 'synthetic_lifecycle_event_used': False}

    def controlled(self):
        value = self.execute("const done = arguments[arguments.length-1]; navigator.serviceWorker.ready.then(() => { if (navigator.serviceWorker.controller) done(true); else navigator.serviceWorker.addEventListener('controllerchange', () => done(!!navigator.serviceWorker.controller), {once:true}); }).catch(() => done(false));", async_=True)
        need(value is True)

    def close(self):
        if self.session is not None:
            self.command('', method='DELETE')
            self.session = None
