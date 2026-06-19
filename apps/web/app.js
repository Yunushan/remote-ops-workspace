const profilesEl = document.querySelector('#profiles');
const form = document.querySelector('#profile-form');
const grid = document.querySelector('#terminal-grid');
const featureTags = document.querySelector('#feature-tags');
const STORAGE_KEY = 'remote-ops-workspace-demo-profiles';
const PROTOCOLS = new Set(['ssh', 'rdp', 'vnc', 'sftp', 'mosh', 'telnet', 'https', 'serial']);
const storage = demoStorage();
let enterprisePolicy = {active: false, allow_user_profiles: true, locked_settings: []};

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
  for (const profile of loadProfiles()) {
    const li = document.createElement('li');
    li.textContent = `${profile.protocol} • ${profile.name} • ${profile.target}`;
    profilesEl.appendChild(li);
  }
}

form.addEventListener('submit', event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form).entries());
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
    return;
  }
  const profiles = loadProfiles();
  profiles.push(profile);
  saveProfiles(profiles);
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
  enterprisePolicy = {active: false, allow_user_profiles: true, locked_settings: []};
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
  const response = await fetch('enterprise-policy.json', {cache: 'no-store'});
  if (!response.ok) {
    return {active: false, allow_user_profiles: true, locked_settings: []};
  }
  const policy = await response.json();
  return {
    active: Boolean(policy.active),
    allow_user_profiles: policy.allow_user_profiles !== false,
    locked_settings: Array.isArray(policy.locked_settings) ? policy.locked_settings : [],
  };
}

function reviewEnterpriseWebProfile(profile) {
  if (!enterprisePolicy.active) {
    return {allowed: true, blocked: []};
  }
  const blocked = [];
  if (!enterprisePolicy.allow_user_profiles) {
    blocked.push('user profile changes are disabled by enterprise policy');
  }
  for (const item of enterprisePolicy.locked_settings) {
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
