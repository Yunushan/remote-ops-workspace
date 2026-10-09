const CACHE_PREFIX = 'remote-ops-workspace-static-';
const CACHE = 'remote-ops-workspace-static-v3';
const ASSETS = ['./', './index.html', './styles.css', './app.js', './manifest.json'];
const PUBLIC_PATHS = new Set(ASSETS.map(asset => new URL(asset, self.registration.scope).pathname));

function publicStaticResponse(response) {
  const policy = response.headers.get('Cache-Control') || '';
  const vary = response.headers.get('Vary') || '';
  return response.ok && !response.redirected && response.type !== 'opaque'
    && !/(?:^|,)\s*(?:private|no-store)(?:\s*(?:=|,|$))/i.test(policy)
    && !vary.split(',').some(name => ['*', 'authorization', 'cookie'].includes(name.trim().toLowerCase()));
}

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    for (const asset of ASSETS) {
      const request = new Request(new URL(asset, self.registration.scope), {
        credentials: 'omit', cache: 'no-store', redirect: 'error',
      });
      const response = await fetch(request);
      if (!publicStaticResponse(response)) throw new Error('Static asset is not publicly cacheable');
      await cache.put(request, response);
    }
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key.startsWith(CACHE_PREFIX) && key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // API, policy, health, unknown paths, authenticated requests and queries bypass all cache reads.
  if (event.request.method !== 'GET' || url.origin !== self.location.origin
      || url.search || !PUBLIC_PATHS.has(url.pathname)
      || event.request.headers.has('Authorization') || event.request.cache === 'no-store') {
    return;
  }
  event.respondWith(caches.open(CACHE).then(async cache => {
    const response = await cache.match(event.request);
    return response && publicStaticResponse(response) ? response : fetch(event.request);
  }));
});
