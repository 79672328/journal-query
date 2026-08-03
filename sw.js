// Service Worker — network-first for code, cache-first for assets
// Bumping VERSION forces cache refresh on next page load
const VERSION = '10';
const CACHE = 'jq-v1.' + VERSION;

// Static assets that never change between deploys (cached)
const ASSETS = ['manifest.json', 'icon-192.png', 'icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(cache => {
      const fetches = ASSETS.map(url =>
        fetch(url, {cache: 'no-cache'}).then(resp => {
          if (resp.ok) cache.put(url, resp.clone());
          return resp;
        }).catch(() => {})
      );
      return Promise.allSettled(fetches);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = e.request.url;
  // Network-first for HTML pages — always serve latest, never lock
  if (e.request.mode === 'navigate' || url.endsWith('/') || url.endsWith('.html')) {
    e.respondWith(
      fetch(e.request, {cache: 'no-cache'}).catch(() => caches.match(e.request))
    );
    return;
  }
  // Network-first data-like files with cache fallback
  if (url.includes('journal_data.json.gz') || url.includes('api.crossref.org')) {
    e.respondWith(
      fetch(e.request).then(resp => {
        if (resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return resp;
      }).catch(() => caches.match(e.request))
    );
    return;
  }
  // Cache-first for static assets
  if (ASSETS.some(a => url.endsWith(a))) {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
    return;
  }
  // CDN resources: stale-while-revalidate
  if (url.includes('cdnjs.cloudflare.com')) {
    e.respondWith(
      caches.match(e.request).then(cached =>
        cached || fetch(e.request).then(resp => {
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
          return resp;
        })
      )
    );
  }
});
