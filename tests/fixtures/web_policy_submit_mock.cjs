const fs = require('node:fs');
const path = require('node:path');
// Keep source, completion and progress separate so the parent can diagnose
// where execution stopped without accepting an unobserved completion.
const [appPath, scenario, outputPath, nonce, progressPath] = process.argv.slice(2);
const marks = [];
const started = process.hrtime.bigint();
function milestone(stage) {
  marks.push({stage, elapsed_ms: Number((process.hrtime.bigint() - started) / 1000000n)});
  const temp = progressPath + '.tmp';
  fs.writeFileSync(temp, JSON.stringify(marks));
  fs.renameSync(temp, progressPath);
}
milestone('harness-start');
process.once('exit', () => milestone('exit-event'));
const windowsPendingFallback = process.platform === 'win32' && scenario === 'pending';
const records = new Map();
const listeners = {};
const harnessForm = {
  dataset: {},
  addEventListener: (name, callback) => { listeners[name] = callback; },
  reset: () => {},
};
const inertElement = () => ({
  appendChild: () => {},
  replaceChildren: () => {},
  style: {},
  dataset: {},
  textContent: '',
  innerHTML: '',
  className: '',
});
const elements = {
  '#profiles': inertElement(),
  '#profile-form': harnessForm,
  '#terminal-grid': inertElement(),
  '#feature-tags': inertElement(),
};
const harnessSetTimeout = scenario === 'pending'
  ? callback => {
      // Resolve the timeout branch immediately so the test exercises the
      // production fallback without leaving a timer alive.
      callback();
      return {};
    }
  : setTimeout;
const harnessClearTimeout = scenario === 'pending' ? () => {} : clearTimeout;
const harnessDocument = {
  querySelector: selector => elements[selector],
  querySelectorAll: () => [],
  createElement: inertElement,
  documentElement: {dataset: {}},
};
const sessionStorage = {
  getItem: key => records.get(key) ?? null,
  setItem: (key, value) => records.set(key, String(value)),
  removeItem: key => records.delete(key),
};
const FormData = function () {
  return {entries: () => [
    ['name', 'edge'],
    ['protocol', 'ssh'],
    ['target', 'edge.example.invalid'],
  ][Symbol.iterator]()};
};
if (!('navigator' in globalThis)) {
  Object.defineProperty(globalThis, 'navigator', {value: {}, configurable: true});
}
// Load the actual application as CommonJS, avoiding an unnecessary VM context.
Object.assign(globalThis, {
  document: harnessDocument,
  sessionStorage,
  FormData,
  setTimeout: harnessSetTimeout,
  clearTimeout: harnessClearTimeout,
});
const validPolicy = {
  active: true,
  allow_user_profiles: true,
  has_restricted_locks: scenario === 'restricted',
  locked_settings: [],
};
let fetchResult;
if (scenario === 'pending') {
  if (windowsPendingFallback) {
    // Keep this case synchronous so it exercises the unavailable-policy
    // fallback without leaving an unresolved promise behind.
    globalThis.fetch = () => {
      throw new Error('enterprise policy is unavailable');
    };
  } else {
    fetchResult = new Promise(() => {});
    globalThis.fetch = () => fetchResult;
  }
} else if (scenario === 'reject') {
  fetchResult = Promise.reject(new Error('offline'));
  globalThis.fetch = () => fetchResult;
} else {
  const body = scenario === 'malformed' ? {active: false} : validPolicy;
  fetchResult = Promise.resolve({ok: true, json: async () => body});
  globalThis.fetch = () => fetchResult;
}
milestone('require-enter');
require(path.resolve(appPath));
milestone('require-return');
const finish = () => {
  milestone('submit-enter');
  listeners.submit({preventDefault: () => {}});
  milestone('submit-return');
  const saved = JSON.parse(
    records.get('remote-ops-workspace-demo-profiles') || '[]',
  );
  const output = JSON.stringify({
    complete: true, scenario, nonce,
    saved: saved.length,
    blocked: harnessForm.dataset.enterprisePolicyBlocked || '',
  });
  milestone('result-write-enter');
  fs.writeFileSync(outputPath + '.tmp', output);
  fs.renameSync(outputPath + '.tmp', outputPath);
  milestone('result-published');
  milestone('exit-requested');
  // Let handled policy promises settle and the event loop finish naturally.
  // The parent still requires an observed zero exit within its original limit.
  process.exitCode = 0;
};
// The pending case intentionally submits before policy loading completes, so
// finish it synchronously. All other scenarios allow policy-loading promises
// to settle before submitting.
if (scenario === 'pending') {
  finish();
} else {
  setImmediate(finish);
}
