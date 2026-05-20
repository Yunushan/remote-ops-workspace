const profilesEl = document.querySelector('#profiles');
const form = document.querySelector('#profile-form');
const grid = document.querySelector('#terminal-grid');
const featureTags = document.querySelector('#feature-tags');
const STORAGE_KEY = 'remote-ops-workspace-demo-profiles';

const features = ['SSH', 'RDP', 'VNC', 'SFTP', 'Mosh', 'Telnet', 'SPICE', 'X2Go', 'ICA', 'HTTP/HTTPS', 'Serial', 'Raw Socket', 'Vault', 'Snippets', 'Split Panes', 'PWA'];
features.forEach(feature => {
  const tag = document.createElement('span');
  tag.textContent = feature;
  featureTags.appendChild(tag);
});

function loadProfiles() {
  return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
}

function saveProfiles(profiles) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(profiles));
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
  const profiles = loadProfiles();
  profiles.push(data);
  saveProfiles(profiles);
  form.reset();
  renderProfiles();
});

document.querySelectorAll('[data-action]').forEach(button => {
  button.addEventListener('click', () => {
    const action = button.dataset.action;
    if (action === 'clear') {
      grid.innerHTML = '<div class="terminal-pane">PWA shell pane<br>Future API/terminal plugin seam.</div>';
      grid.style.gridTemplateColumns = '1fr';
      return;
    }
    const pane = document.createElement('div');
    pane.className = 'terminal-pane';
    pane.textContent = `New ${action === 'split-h' ? 'horizontal' : 'vertical'} pane\nDemo split-pane workspace.`;
    grid.appendChild(pane);
    grid.style.gridTemplateColumns = action === 'split-h' ? 'repeat(2, 1fr)' : '1fr';
  });
});

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').catch(() => {});
}

renderProfiles();
