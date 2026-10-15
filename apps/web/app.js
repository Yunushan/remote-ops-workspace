const profilesEl = document.querySelector('#profiles');
const form = document.querySelector('#profile-form');
const grid = document.querySelector('#terminal-grid');
const featureTags = document.querySelector('#feature-tags');
const STORAGE_KEY = 'remote-ops-workspace-demo-profiles';
const PROTOCOLS = new Set(['ssh', 'rdp', 'vnc', 'sftp', 'mosh', 'telnet', 'https', 'serial']);
const storage = demoStorage();
const ENTERPRISE_POLICY_TIMEOUT_MS = 5000;
let enterprisePolicy = {
  loaded: false,
  active: true,
  allow_user_profiles: false,
  has_restricted_locks: true,
  locked_settings: [],
};

// Catalogue credentials and returned metadata live only in this page's memory.
const catalogueForm = document.querySelector('#catalogue-form');
const catalogueToken = document.querySelector('#catalogue-token');
const catalogueStatus = document.querySelector('#catalogue-status');
const profileStatus = document.querySelector('#profile-status');
const profileSubmit = document.querySelector('#profile-submit');
const catalogueRefresh = document.querySelector('#catalogue-refresh');
const catalogueDisconnect = document.querySelector('#catalogue-disconnect');
const catalogueDemo = document.querySelector('#catalogue-demo');
const CATALOGUE_TIMEOUT_MS = 5000;
const CATALOGUE_MAX_BYTES = 262144;
const CATALOGUE_MAX_ROWS = 1000;
let catalogueMode = 'demo';
let catalogueTokenValue = '';
let catalogueRows = [];
let catalogueGeneration = 0;
let catalogueBusy = false;
const catalogueControllers = new Set();

function showStatus(node, message) {
  if (node) node.textContent = message;
}

function catalogueControls() {
  if (catalogueRefresh) catalogueRefresh.disabled = catalogueBusy || !catalogueTokenValue;
  if (catalogueDisconnect) catalogueDisconnect.disabled = catalogueMode !== 'api';
  if (profileSubmit) {
    profileSubmit.textContent = catalogueMode === 'api' ? 'Save catalogue profile' : 'Add demo profile';
    profileSubmit.disabled = catalogueMode === 'api' && (catalogueBusy || !catalogueTokenValue);
  }
  if (catalogueForm) catalogueForm.querySelector('button').disabled = catalogueBusy;
}

function resetCatalogue(mode, message) {
  catalogueGeneration += 1;
  for (const controller of catalogueControllers) controller.abort();
  catalogueControllers.clear();
  catalogueTokenValue = '';
  catalogueRows = [];
  catalogueBusy = false;
  catalogueMode = mode;
  if (catalogueToken) catalogueToken.value = '';
  showStatus(catalogueStatus, message);
  showStatus(profileStatus, '');
  catalogueControls();
  renderProfiles();
}

function catalogueOriginAllowed() {
  if (typeof location === 'undefined' || !['http:', 'https:'].includes(location.protocol)) return false;
  const host = location.hostname.toLowerCase();
  if (['localhost', 'ip6-localhost', '[::1]', '::1'].includes(host)) return true;
  const parts = host.split('.');
  return parts.length === 4 && parts[0] === '127'
    && parts.every(part => /^(0|[1-9]\d{0,2})$/.test(part) && Number(part) <= 255);
}

function catalogueFailure(code) {
  const error = new Error(code);
  error.catalogueCode = code;
  return error;
}

function catalogueMessage(error, writing = false) {
  const code = error.catalogueCode;
  if (code === 'auth') return 'Authentication failed. Connect again with the configured API token.';
  if (code === 'disabled') return 'The local catalogue API is unavailable. Start the loopback server with an API token.';
  if (code === 'origin') return 'Catalogue authentication requires a loopback HTTP or HTTPS origin.';
  if (code === 'refused') return 'The server refused this profile. Check the target and enterprise policy; no replacement was requested.';
  if (code === 'policy') return 'Enterprise policy refused this profile; no save request was sent.';
  if (code === 'target') return 'Use a DNS/IP host with an optional port, or an HTTPS origin. Device paths, credentials and URL paths are refused.';
  if (code === 'token') return 'Enter a printable API token of 24 to 256 characters.';
  if (writing) return 'Save was not confirmed. Connect and refresh the catalogue before retrying; the server may have saved it.';
  return 'Catalogue request failed or returned unsupported data. Connect again; demo mode is available separately.';
}

async function boundedCatalogueJson(response, signal) {
  if (!/^application\/json(?:\s*;|$)/i.test(response.headers.get('Content-Type') || '')
      || !/(?:^|,)\s*no-store(?:\s*,|$)/i.test(response.headers.get('Cache-Control') || '')) {
    throw catalogueFailure('response');
  }
  const length = response.headers.get('Content-Length');
  if (length !== null && (!/^\d+$/.test(length) || Number(length) > CATALOGUE_MAX_BYTES)) {
    throw catalogueFailure('response');
  }
  if (!response.body || typeof response.body.getReader !== 'function') throw catalogueFailure('response');
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', {fatal: true});
  let text = '';
  let bytes = 0;
  try {
    while (true) {
      if (signal.aborted) throw catalogueFailure('cancelled');
      const chunk = await reader.read();
      if (chunk.done) break;
      bytes += chunk.value.byteLength;
      if (bytes > CATALOGUE_MAX_BYTES) throw catalogueFailure('response');
      text += decoder.decode(chunk.value, {stream: true});
    }
    text += decoder.decode();
    return JSON.parse(text);
  } finally {
    reader.releaseLock();
  }
}

async function catalogueRequest(path, method, generation, payload) {
  if (!catalogueOriginAllowed()) throw catalogueFailure('origin');
  if (generation !== catalogueGeneration || !catalogueTokenValue) throw catalogueFailure('cancelled');
  if (!['/api/v1/profiles', '/enterprise-policy.json'].includes(path)
      || !['GET', 'POST'].includes(method) || (path !== '/api/v1/profiles' && method !== 'GET')) {
    throw catalogueFailure('request');
  }
  const controller = new AbortController();
  catalogueControllers.add(controller);
  const headers = {'Accept': 'application/json'};
  if (path === '/api/v1/profiles') headers.Authorization = `Bearer ${catalogueTokenValue}`;
  if (method === 'POST') headers['Content-Type'] = 'application/json';
  let timeout;
  const work = (async () => {
    const response = await fetch(path, {
      method, headers, credentials: 'omit', cache: 'no-store', redirect: 'error',
      signal: controller.signal,
      ...(method === 'POST' ? {body: JSON.stringify(payload)} : {}),
    });
    if (response.status === 401) throw catalogueFailure('auth');
    if (response.status === 404 && path === '/api/v1/profiles') throw catalogueFailure('disabled');
    if (response.status === 400 && method === 'POST') throw catalogueFailure('refused');
    if (response.status !== (method === 'POST' ? 201 : 200)) throw catalogueFailure('response');
    return boundedCatalogueJson(response, controller.signal);
  })();
  try {
    const result = await Promise.race([work, new Promise((_, reject) => {
      timeout = setTimeout(() => { controller.abort(); reject(catalogueFailure('timeout')); }, CATALOGUE_TIMEOUT_MS);
    })]);
    if (generation !== catalogueGeneration) throw catalogueFailure('cancelled');
    return result;
  } finally {
    clearTimeout(timeout);
    controller.abort();
    catalogueControllers.delete(controller);
  }
}

function publicCatalogueRow(profile) {
  // Read every legitimate public protocol, including local/serial rows with no public target.
  if (!profile || typeof profile !== 'object' || Array.isArray(profile)) throw catalogueFailure('response');
  const safeText = value => typeof value === 'string' && value.length <= 4096 && !/[\u0000-\u001f\u007f]/.test(value);
  if (!safeText(profile.name) || !safeText(profile.protocol)
      || (profile.host !== null && !safeText(profile.host))
      || (profile.url !== null && !safeText(profile.url))
      || (profile.port !== null && (!Number.isInteger(profile.port) || profile.port < 1 || profile.port > 65535))) {
    throw catalogueFailure('response');
  }
  const host = profile.host && profile.host.includes(':') ? `[${profile.host}]` : profile.host;
  return {
    name: profile.name, protocol: profile.protocol,
    target: profile.url || (host ? `${host}${profile.port === null ? '' : `:${profile.port}`}` : 'No public target'),
  };
}

async function refreshCatalogue(generation) {
  const result = await catalogueRequest('/api/v1/profiles', 'GET', generation);
  if (!result || !Array.isArray(result.profiles) || result.profiles.length > CATALOGUE_MAX_ROWS) throw catalogueFailure('response');
  catalogueRows = result.profiles.map(publicCatalogueRow);
  renderProfiles();
  showStatus(catalogueStatus, `Connected to the local catalogue: ${catalogueRows.length} profiles. Metadata only; this page does not start sessions.`);
}

async function connectCatalogue(event) {
  event.preventDefault();
  const token = catalogueToken.value.trim();
  resetCatalogue('api', 'Connecting to the local catalogue…');
  const generation = catalogueGeneration;
  try {
    if (!catalogueOriginAllowed()) throw catalogueFailure('origin');
    if (!/^[\x21-\x7e]{24,256}$/.test(token)) throw catalogueFailure('token');
    catalogueTokenValue = token;
    catalogueBusy = true;
    catalogueControls();
    await refreshCatalogue(generation);
  } catch (error) {
    if (generation === catalogueGeneration) resetCatalogue('api', catalogueMessage(error));
  } finally {
    if (generation === catalogueGeneration) { catalogueBusy = false; catalogueControls(); }
  }
}

function catalogueProfile(data) {
  const name = String(data.name || '').trim();
  const protocol = String(data.protocol || '').toLowerCase();
  const target = String(data.target || '').trim();
  if (!name || name.length > 80 || /[\u0000-\u001f\u007f]/.test(name)
      || !PROTOCOLS.has(protocol) || protocol === 'serial' || !target || target.length > 253
      || /[\s\u0000-\u001f\u007f@\\?#%]/.test(target)) throw catalogueFailure('target');
  if (protocol === 'https') {
    const rawUrl = target.includes('://') ? target : `https://${target}`;
    if (!/^https:\/\/[^/]+\/?$/i.test(rawUrl)) throw catalogueFailure('target');
    let url;
    try { url = new URL(rawUrl); } catch { throw catalogueFailure('target'); }
    if (url.protocol !== 'https:' || url.username || url.password || url.pathname !== '/' || url.search || url.hash) throw catalogueFailure('target');
    const host = validateCatalogueHost(url.hostname);
    const port = url.port ? Number(url.port) : null;
    if (port !== null && (!Number.isInteger(port) || port < 1 || port > 65535)) throw catalogueFailure('target');
    const authority = host.includes(':') ? `[${host}]` : host;
    return {name, protocol, host, port, url: `https://${authority}${port === null ? '' : `:${port}`}`};
  }
  if (target.includes('/')) throw catalogueFailure('target');
  let host = target;
  let port = null;
  if (target.startsWith('[')) {
    const match = /^\[([^\]]+)\](?::(\d+))?$/.exec(target);
    if (!match) throw catalogueFailure('target');
    host = match[1];
    port = match[2] === undefined ? null : Number(match[2]);
  } else if ((target.match(/:/g) || []).length === 1) {
    const parts = target.split(':');
    if (!/^\d+$/.test(parts[1])) throw catalogueFailure('target');
    host = parts[0]; port = Number(parts[1]);
  }
  host = validateCatalogueHost(host);
  if (port !== null && (!Number.isInteger(port) || port < 1 || port > 65535)) throw catalogueFailure('target');
  return {name, protocol, host, port};
}

function validateCatalogueHost(value) {
  const host = value.replace(/^\[|\]$/g, '').toLowerCase();
  if (host.includes(':')) {
    try {
      const parsed = new URL(`http://[${host}]/`);
      return parsed.hostname.slice(1, -1);
    } catch { throw catalogueFailure('target'); }
  }
  if (/^(?:\d+\.){3}\d+$/.test(host) && host.split('.').some(part => Number(part) > 255)) throw catalogueFailure('target');
  if (host.length > 253 || !host.split('.').every(label => label.length <= 63 && /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label))) throw catalogueFailure('target');
  return host;
}

async function saveCatalogueProfile(data) {
  if (catalogueBusy || !catalogueTokenValue) { showStatus(profileStatus, 'Connect to the local catalogue before saving.'); return; }
  if (catalogueRows.length >= CATALOGUE_MAX_ROWS) { showStatus(profileStatus, 'The browser catalogue limit is 1,000 profiles. Use the CLI or GUI for larger catalogues.'); return; }
  const generation = catalogueGeneration;
  catalogueBusy = true;
  catalogueControls();
  let writeStarted = false;
  try {
    const profile = catalogueProfile(data);
    const policy = validateEnterprisePolicy(await catalogueRequest('/enterprise-policy.json', 'GET', generation));
    const review = reviewEnterpriseWebProfile(profile, policy);
    form.dataset.enterprisePolicySurface = 'web';
    form.dataset.enterprisePolicyBlocked = review.blocked.join('|');
    if (!review.allowed) throw catalogueFailure('policy');
    writeStarted = true;
    const result = await catalogueRequest('/api/v1/profiles', 'POST', generation, {profile, replace: false});
    const row = publicCatalogueRow(result);
    if (row.name !== profile.name || row.protocol !== profile.protocol) throw catalogueFailure('response');
    catalogueRows.push(row);
    form.reset();
    renderProfiles();
    showStatus(profileStatus, 'Profile saved by the local catalogue. Refresh to read the stored catalogue again.');
  } catch (error) {
    if (generation !== catalogueGeneration) return;
    const message = catalogueMessage(error, writeStarted);
    if (error.catalogueCode === 'auth' || error.catalogueCode === 'disabled'
        || (writeStarted && !['refused', 'policy', 'target'].includes(error.catalogueCode))) {
      resetCatalogue('api', message);
    }
    showStatus(profileStatus, message);
  } finally {
    if (generation === catalogueGeneration) { catalogueBusy = false; catalogueControls(); }
  }
}

if (catalogueForm && catalogueToken) catalogueForm.addEventListener('submit', connectCatalogue);
if (catalogueDemo) catalogueDemo.addEventListener('click', () => resetCatalogue('demo', 'Demo mode: profiles stay in this tab.'));
if (catalogueDisconnect) catalogueDisconnect.addEventListener('click', () => resetCatalogue('api', 'Catalogue disconnected. Connect again or select demo mode.'));
if (catalogueRefresh) catalogueRefresh.addEventListener('click', async () => {
  if (catalogueBusy || !catalogueTokenValue) return;
  const generation = catalogueGeneration;
  catalogueBusy = true;
  catalogueControls();
  try { await refreshCatalogue(generation); }
  catch (error) { if (generation === catalogueGeneration) resetCatalogue('api', catalogueMessage(error)); }
  finally { if (generation === catalogueGeneration) { catalogueBusy = false; catalogueControls(); } }
});
if (typeof window !== 'undefined') window.addEventListener('pagehide', () => {
  if (catalogueToken) catalogueToken.value = '';
  if (catalogueMode === 'api') resetCatalogue('api', 'Catalogue disconnected after leaving this page.');
});
catalogueControls();

const features = ['SSH', 'RDP', 'VNC', 'SFTP', 'Mosh', 'Telnet', 'SPICE', 'X2Go', 'ICA', 'HTTP/HTTPS', 'Serial', 'Raw Socket', 'Vault', 'Snippets', 'Split Panes', 'PWA'];
features.forEach(feature => {
  const tag = document.createElement('span');
  tag.textContent = feature;
  featureTags.appendChild(tag);
});

function loadProfiles() {
  if (!storage) {
    return [];
  }
  try {
    const profiles = JSON.parse(storage.getItem(STORAGE_KEY) || '[]');
    return Array.isArray(profiles) ? profiles.filter(isDemoProfile).slice(0, 50) : [];
  } catch {
    return [];
  }
}

function saveProfiles(profiles) {
  if (storage) {
    storage.setItem(STORAGE_KEY, JSON.stringify(profiles.slice(-50)));
  }
}

function renderProfiles() {
  profilesEl.innerHTML = '';
  for (const profile of catalogueMode === 'api' ? catalogueRows : loadProfiles()) {
    const li = document.createElement('li');
    li.textContent = `${profile.protocol} • ${profile.name} • ${profile.target}`;
    profilesEl.appendChild(li);
  }
}

form.addEventListener('submit', event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form).entries());
  if (catalogueMode === 'api') { void saveCatalogueProfile(data); return; }
  const protocol = String(data.protocol || '').toLowerCase();
  const profile = {
    name: cleanDemoField(data.name, 80),
    protocol: PROTOCOLS.has(protocol) ? protocol : 'ssh',
    target: cleanDemoField(data.target, 160),
  };
  if (!profile.name || !profile.target) {
    return;
  }
  const policyReview = reviewEnterpriseWebProfile(profile);
  form.dataset.enterprisePolicySurface = 'web';
  form.dataset.enterprisePolicyBlocked = policyReview.blocked.join('|');
  if (!policyReview.allowed) {
    showStatus(profileStatus, policyReview.blocked.join('; '));
    return;
  }
  const profiles = loadProfiles();
  profiles.push(profile);
  saveProfiles(profiles);
  showStatus(profileStatus, 'Demo profile saved in this tab.');
  form.reset();
  renderProfiles();
});

document.querySelectorAll('[data-action]').forEach(button => {
  button.addEventListener('click', () => {
    const action = button.dataset.action;
    if (action === 'clear') {
      grid.replaceChildren(defaultPane());
      grid.style.gridTemplateColumns = '1fr';
      return;
    }
    grid.appendChild(terminalPane(`New ${action === 'split-h' ? 'horizontal' : 'vertical'} pane\nDemo split-pane workspace.`));
    grid.style.gridTemplateColumns = action === 'split-h' ? 'repeat(2, 1fr)' : '1fr';
  });
});

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').catch(() => {});
}

loadEnterprisePolicy().then(policy => {
  enterprisePolicy = policy;
  document.documentElement.dataset.enterprisePolicyActive = policy.active ? 'true' : 'false';
}).catch(() => {
  enterprisePolicy = {
    loaded: false,
    active: true,
    allow_user_profiles: false,
    has_restricted_locks: true,
    locked_settings: [],
  };
  document.documentElement.dataset.enterprisePolicyActive = 'unavailable';
});

function demoStorage() {
  try {
    const testKey = `${STORAGE_KEY}-probe`;
    sessionStorage.setItem(testKey, '1');
    sessionStorage.removeItem(testKey);
    return sessionStorage;
  } catch {
    return null;
  }
}

function isDemoProfile(profile) {
  return Boolean(
    profile
      && typeof profile.name === 'string'
      && typeof profile.protocol === 'string'
      && typeof profile.target === 'string'
      && PROTOCOLS.has(profile.protocol),
  );
}

function cleanDemoField(value, maxLength) {
  return String(value || '')
    .replace(/[\u0000-\u001f\u007f]/g, '')
    .trim()
    .slice(0, maxLength);
}

async function loadEnterprisePolicy() {
  let timeoutId = null;
  try {
    const request = fetch('enterprise-policy.json', {cache: 'no-store'});
    const response = typeof setTimeout === 'function'
      ? await Promise.race([
          request,
          new Promise((_, reject) => {
            timeoutId = setTimeout(
              () => reject(new Error('enterprise policy is unavailable')),
              ENTERPRISE_POLICY_TIMEOUT_MS,
            );
          }),
        ])
      : await request;
    if (!response.ok) {
      throw new Error('enterprise policy is unavailable');
    }
    const policy = await response.json();
    return validateEnterprisePolicy(policy);
  } finally {
    if (timeoutId !== null && typeof clearTimeout === 'function') {
      clearTimeout(timeoutId);
    }
  }
}

function validateEnterprisePolicy(policy) {
  if (
    !policy
      || typeof policy.active !== 'boolean'
      || typeof policy.allow_user_profiles !== 'boolean'
      || typeof policy.has_restricted_locks !== 'boolean'
      || !Array.isArray(policy.locked_settings)
      || policy.locked_settings.some(item => (
        !item
          || typeof item !== 'object'
          || Object.keys(item).length !== 2
          || item.key !== 'protocol'
          || typeof item.value !== 'string'
      ))
  ) {
    throw new Error('enterprise policy response is malformed');
  }
  return {
    loaded: true,
    active: policy.active,
    allow_user_profiles: policy.allow_user_profiles,
    has_restricted_locks: policy.has_restricted_locks,
    locked_settings: policy.locked_settings,
  };
}

function reviewEnterpriseWebProfile(profile, policy = enterprisePolicy) {
  if (!policy.loaded) {
    return {allowed: false, blocked: ['enterprise policy is unavailable']};
  }
  if (!policy.active) {
    return {allowed: true, blocked: []};
  }
  const blocked = [];
  if (!policy.allow_user_profiles) {
    blocked.push('user profile changes are disabled by enterprise policy');
  }
  if (policy.has_restricted_locks) {
    blocked.push('profile changes require a trusted enterprise policy surface');
  }
  for (const item of policy.locked_settings) {
    const key = String(item.key || '');
    const expected = String(item.value ?? '');
    if (Object.prototype.hasOwnProperty.call(profile, key) && String(profile[key] ?? '') !== expected) {
      blocked.push(`web cannot set locked enterprise setting ${key}`);
    }
  }
  return {allowed: blocked.length === 0, blocked};
}

function terminalPane(text) {
  const pane = document.createElement('div');
  pane.className = 'terminal-pane';
  pane.textContent = text;
  return pane;
}

function defaultPane() {
  return terminalPane('PWA shell pane\nFuture API/terminal plugin seam.');
}

renderProfiles();
