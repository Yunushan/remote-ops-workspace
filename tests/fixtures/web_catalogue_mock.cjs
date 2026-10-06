'use strict';
// Pure fake-DOM/fake-fetch fixtures: no browser, listener, product process or network.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const [appPath, swPath, scenario, outputPath, nonce, progressPath] = process.argv.slice(2);
const started = Date.now();
const milestones = [];
function milestone(stage) {
  milestones.push({stage, elapsed_ms: Date.now() - started});
  fs.writeFileSync(progressPath, JSON.stringify(milestones));
}
process.on('exit', () => milestone('exit-event'));
milestone('harness-start');
const token = 'fixture-transient-token-123456789';
const policy = {active: false, allow_user_profiles: true, has_restricted_locks: false, locked_settings: []};
const row = (name, protocol = 'ssh', host = 'edge.example.invalid', port = null) => ({
  name, protocol, host, port, username: null, group: 'default', tags: [],
  description: '', url: null, tunnels: [], options: {},
});

function response(value, status = 200, options = {}) {
  const bytes = Buffer.from(typeof value === 'string' ? value : JSON.stringify(value));
  let consumed = false;
  return {
    ok: status >= 200 && status < 300, status,
    headers: new Headers({'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...options.headers}),
    json: async () => value,
    body: {getReader: () => ({
      read: async () => {
        if (options.pending) return new Promise(() => {});
        if (consumed) return {done: true};
        consumed = true;
        return {done: false, value: new Uint8Array(bytes)};
      },
      releaseLock: () => {},
    })},
  };
}

function node() {
  return {
    children: [], listeners: {}, dataset: {}, style: {}, value: '', disabled: false,
    textContent: '', className: '',
    addEventListener(name, listener) { this.listeners[name] = listener; },
    appendChild(child) { this.children.push(child); },
    replaceChildren(...children) { this.children = children; },
    querySelector() { return this.button; },
    reset() {},
    set innerHTML(value) { assert.equal(value, ''); this.children = []; },
  };
}

async function frontendCase() {
  const ids = Object.fromEntries(['profiles', 'profile-form', 'terminal-grid', 'feature-tags',
    'catalogue-form', 'catalogue-token', 'catalogue-refresh', 'catalogue-disconnect',
    'catalogue-demo', 'catalogue-status', 'profile-status', 'profile-submit'].map(id => [id, node()]));
  ids['catalogue-form'].button = node();
  const records = new Map();
  records.set('remote-ops-workspace-demo-profiles', JSON.stringify([{name: 'kept demo', protocol: 'ssh', target: 'demo.invalid'}]));
  const requests = [];
  const windowListeners = {};
  let formData = {name: 'new edge', protocol: 'ssh', target: 'edge.example.invalid:2222'};
  let apiReads = 0;
  let releaseStale;
  const context = vm.createContext({
    document: {querySelector: selector => ids[selector.slice(1)], querySelectorAll: () => [],
      createElement: node, documentElement: {dataset: {}}},
    navigator: {}, location: {protocol: 'http:', hostname: scenario === 'origin-refusal' ? 'public.example.invalid' : '127.0.0.1'},
    window: {addEventListener: (name, listener) => { windowListeners[name] = listener; }},
    sessionStorage: {getItem: key => records.get(key), setItem: (key, value) => records.set(key, value), removeItem: key => records.delete(key)},
    FormData: class { entries() { return Object.entries(formData); } },
    URL, Headers, AbortController, TextDecoder, clearTimeout,
    setTimeout: (callback, delay) => setTimeout(callback, scenario.includes('deadline') && delay === 5000 ? 5 : delay),
    fetch: (path, options = {}) => {
      requests.push({path, options});
      if (path === 'enterprise-policy.json') return Promise.resolve(response(policy));
      if (path === '/enterprise-policy.json') return Promise.resolve(response(scenario === 'policy-refusal'
        ? {...policy, active: true, allow_user_profiles: false} : policy, 200, {pending: scenario === 'policy-deadline'}));
      assert.equal(path, '/api/v1/profiles');
      assert.equal(options.headers.Authorization, `Bearer ${token}`);
      assert.equal(options.credentials, 'omit');
      assert.equal(options.cache, 'no-store');
      assert.equal(options.redirect, 'error');
      assert.ok(options.signal instanceof AbortSignal);
      if (options.method === 'POST') {
        assert.equal(options.headers['Content-Type'], 'application/json');
        const body = JSON.parse(options.body);
        assert.equal(body.replace, false);
        assert.deepEqual(Object.keys(body).sort(), ['profile', 'replace']);
        assert.deepEqual(body.profile, {name: 'new edge', protocol: 'ssh', host: 'edge.example.invalid', port: 2222});
        if (scenario === 'write-deadline') return new Promise(() => {});
        return Promise.resolve(scenario === 'server-refusal' ? response({error: token}, 400)
          : response(row('new edge', 'ssh', 'edge.example.invalid', 2222), 201));
      }
      apiReads += 1;
      if (scenario === 'auth-refusal') return Promise.resolve(response({}, 401));
      if (scenario === 'header-deadline') return new Promise(() => {});
      if (scenario === 'body-deadline') return Promise.resolve(response({}, 200, {pending: true}));
      if (scenario === 'malformed') return Promise.resolve(response('{invalid json'));
      if (scenario === 'oversized') return Promise.resolve(response({profiles: [row('oversized valid metadata')], padding: 'x'.repeat(262145)}));
      if (scenario === 'stale-response') return new Promise(resolve => { releaseStale = resolve; });
      return Promise.resolve(response({profiles: [row('<img src=x>', 'ssh'), row('serial public', 'serial', null), row('local public', 'local-shell', null), row('other public', 'spice')]}));
    },
  });
  milestone('require-enter');
  vm.runInContext(fs.readFileSync(appPath, 'utf8'), context, {filename: appPath});
  milestone('require-return');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(ids.profiles.children[0].textContent, 'ssh • kept demo • demo.invalid');
  ids['catalogue-token'].value = token;
  milestone('submit-enter');
  if (scenario === 'demo-pagehide') {
    windowListeners.pagehide();
    assert.equal(ids['catalogue-token'].value, '');
    assert.equal(vm.runInContext('catalogueMode', context), 'demo');
    assert.equal(ids.profiles.children[0].textContent, 'ssh • kept demo • demo.invalid');
    assert.equal(JSON.parse(records.get('remote-ops-workspace-demo-profiles')).length, 1);
    assert.equal(apiReads, 0);
    milestone('submit-return');
    return;
  }
  const connection = ids['catalogue-form'].listeners.submit({preventDefault() {}});
  assert.equal(ids['catalogue-token'].value, '');
  if (scenario === 'stale-response') {
    ids['catalogue-disconnect'].listeners.click();
    releaseStale(response({profiles: [row('stale private metadata')]}));
  }
  await connection;
  milestone('submit-return');
  assert.equal(records.size, 1);
  assert.ok(!JSON.stringify([...records]).includes(token));
  if (scenario === 'origin-refusal') {
    assert.equal(apiReads, 0);
    assert.match(ids['catalogue-status'].textContent, /loopback/);
  } else if (scenario === 'auth-refusal') {
    assert.match(ids['catalogue-status'].textContent, /Authentication failed/);
  } else if (['header-deadline', 'body-deadline', 'malformed', 'oversized'].includes(scenario)) {
    assert.match(ids['catalogue-status'].textContent, /failed|unsupported/);
    assert.equal(ids.profiles.children.length, 0);
    assert.ok(requests.find(item => item.path === '/api/v1/profiles').options.signal.aborted);
  } else if (scenario === 'stale-response') {
    assert.equal(ids.profiles.children.length, 0);
    assert.match(ids['catalogue-status'].textContent, /disconnected/);
  } else {
    assert.equal(ids.profiles.children.length, 4);
    assert.equal(ids.profiles.children[0].textContent, 'ssh • <img src=x> • edge.example.invalid');
    assert.match(ids.profiles.children[1].textContent, /serial.*No public target/);
    assert.match(ids.profiles.children[2].textContent, /local-shell.*No public target/);
    if (['create', 'policy-refusal', 'server-refusal', 'write-deadline', 'policy-deadline'].includes(scenario)) {
      ids['profile-form'].listeners.submit({preventDefault() {}});
      // Await the actual asynchronous write task, without invoking it twice.
      for (let turn = 0; turn < 50 && vm.runInContext('catalogueBusy', context); turn += 1) {
        await new Promise(resolve => setTimeout(resolve, 1));
      }
      assert.equal(vm.runInContext('catalogueBusy', context), false);
      const writes = requests.filter(item => item.options.method === 'POST');
      if (scenario === 'policy-refusal' || scenario === 'policy-deadline') {
        assert.equal(writes.length, 0);
        assert.match(ids['profile-status'].textContent, scenario === 'policy-refusal' ? /policy refused/ : /failed|unsupported/);
      } else if (scenario === 'server-refusal') {
        assert.equal(writes.length, 1);
        assert.match(ids['profile-status'].textContent, /server refused/);
        assert.ok(!ids['profile-status'].textContent.includes(token));
      } else if (scenario === 'write-deadline') {
        assert.equal(writes.length, 1);
        assert.equal(ids.profiles.children.length, 0);
        assert.match(ids['profile-status'].textContent, /Save was not confirmed/);
        assert.equal(vm.runInContext('catalogueTokenValue', context), '');
      } else {
        assert.equal(writes.length, 1);
        assert.equal(ids.profiles.children.length, 5);
        assert.match(ids['profile-status'].textContent, /Profile saved/);
      }
    }
    if (scenario === 'mapping') {
      const mapped = value => JSON.parse(vm.runInContext(`JSON.stringify(catalogueProfile(${JSON.stringify(value)}))`, context));
      assert.deepEqual(mapped({name: 'v6', protocol: 'ssh', target: '[2001:db8::1]:2222'}), {name: 'v6', protocol: 'ssh', host: '2001:db8::1', port: 2222});
      assert.deepEqual(mapped({name: 'web', protocol: 'https', target: 'https://edge.example.invalid:8443'}), {name: 'web', protocol: 'https', host: 'edge.example.invalid', port: 8443, url: 'https://edge.example.invalid:8443'});
      assert.deepEqual(mapped({name: 'default', protocol: 'https', target: 'https://edge.example.invalid'}), {name: 'default', protocol: 'https', host: 'edge.example.invalid', port: null, url: 'https://edge.example.invalid'});
      assert.deepEqual(mapped({name: 'default', protocol: 'https', target: 'https://edge.example.invalid:443'}), {name: 'default', protocol: 'https', host: 'edge.example.invalid', port: null, url: 'https://edge.example.invalid'});
      assert.deepEqual(mapped({name: 'root', protocol: 'https', target: 'https://edge.example.invalid/'}), {name: 'root', protocol: 'https', host: 'edge.example.invalid', port: null, url: 'https://edge.example.invalid'});
      assert.throws(() => mapped({name: 'bad', protocol: 'https', target: 'https://host:0'}));
      assert.throws(() => mapped({name: 'bad', protocol: 'https', target: 'https://host/private/..'}));
      for (const target of ['user@host', '/dev/ttyS0', 'host:0', 'host:65536', 'host/path', 'https://host/path', 'host?token=x', 'bad host', '-bad', '999.1.1.1']) {
        assert.throws(() => mapped({name: 'bad', protocol: 'ssh', target}));
      }
      assert.throws(() => mapped({name: 'bad', protocol: 'serial', target: '/dev/ttyS0'}));
      assert.throws(() => mapped({name: 'bad', protocol: 'https', target: 'https://host/private'}));
    }
    windowListeners.pagehide();
    assert.equal(vm.runInContext('catalogueTokenValue', context), '');
    assert.equal(ids.profiles.children.length, 0);
  }
  assert.ok(!ids['catalogue-status'].textContent.includes(token));
  assert.equal(vm.runInContext('catalogueMode', context), 'api');
  ids['catalogue-demo'].listeners.click();
  assert.equal(ids.profiles.children[0].textContent, 'ssh • kept demo • demo.invalid');
  assert.equal(JSON.parse(records.get('remote-ops-workspace-demo-profiles')).length, 1);
}

async function workerCase() {
  const handlers = {};
  const puts = [];
  const matches = [];
  const deleted = [];
  let privateInstall = scenario === 'worker-private-install';
  const cached = new Response('public static', {headers: {'Cache-Control': 'public, max-age=60'}});
  const cache = {put: async (request, result) => puts.push(request.url), match: async request => { matches.push(request.url); return cached; }};
  const context = vm.createContext({URL, Request, Response,
    self: {location: {origin: 'http://127.0.0.1:8765'}, registration: {scope: 'http://127.0.0.1:8765/'},
      addEventListener: (name, handler) => { handlers[name] = handler; }, skipWaiting: async () => {}, clients: {claim: async () => {}}},
    caches: {open: async name => { assert.equal(name, 'remote-ops-workspace-static-v3'); return cache; },
      keys: async () => ['remote-ops-workspace-static-v2', 'remote-ops-workspace-static-v3', 'unrelated-private-cache'],
      delete: async name => { deleted.push(name); }},
    fetch: async request => {
      assert.equal(request.credentials, 'omit');
      assert.equal(request.redirect, 'error');
      return new Response('static', {headers: {'Cache-Control': privateInstall ? 'private' : 'public'}});
    },
  });
  milestone('require-enter');
  vm.runInContext(fs.readFileSync(swPath, 'utf8'), context, {filename: swPath});
  milestone('require-return');
  milestone('submit-enter');
  let install;
  handlers.install({waitUntil: promise => { install = promise; }});
  if (privateInstall) {
    await assert.rejects(install, /not publicly cacheable/);
    assert.deepEqual(puts, []);
  } else {
    await install;
    assert.equal(puts.length, 5);
    for (const [path, init] of [
      ['/api/v1/profiles', {}], ['/enterprise-policy.json', {}], ['/healthz', {}], ['/unknown', {}],
      ['/index.html?private=1', {}], ['/index.html', {headers: {Authorization: 'Bearer fixture'}}],
      ['/index.html', {cache: 'no-store'}], ['/index.html', {method: 'POST'}],
      ['http://other.invalid/index.html', {}],
    ]) {
      let intercepted = false;
      handlers.fetch({request: new Request(new URL(path, 'http://127.0.0.1:8765'), init), respondWith: () => { intercepted = true; }});
      assert.equal(intercepted, false, path);
    }
    assert.equal(matches.length, 0);
    let result;
    handlers.fetch({request: new Request('http://127.0.0.1:8765/index.html'), respondWith: promise => { result = promise; }});
    assert.equal(await result, cached);
    assert.equal(matches.length, 1);
    let activation;
    handlers.activate({waitUntil: promise => { activation = promise; }});
    await activation;
    assert.deepEqual(deleted, ['remote-ops-workspace-static-v2']);
    const permits = header => vm.runInContext(`publicStaticResponse(new Response('x', {headers: ${JSON.stringify(header)}}))`, context);
    assert.equal(permits({'Cache-Control': 'no-store'}), false);
    assert.equal(permits({'Cache-Control': 'private="set-cookie"'}), false);
    assert.equal(permits({'Vary': 'Cookie'}), false);
    assert.equal(permits({'Vary': 'Authorization'}), false);
    assert.equal(permits({'Vary': '*'}), false);
  }
  milestone('submit-return');
}

(async () => {
  if (scenario.startsWith('worker-')) await workerCase(); else await frontendCase();
  milestone('result-write-enter');
  fs.writeFileSync(outputPath + '.tmp', JSON.stringify({complete: true, scenario, nonce, saved: 1, blocked: ''}));
  fs.renameSync(outputPath + '.tmp', outputPath);
  milestone('result-published');
  milestone('exit-requested');
  process.exitCode = 0;
})().catch(error => { console.error(error); process.exitCode = 1; });
