const CACHE = 'jq-v1';
const ASSETS = [
  './',
  'index.html',
  'manifest.json',
  'journal_data.json.gz',
  'icon-192.png',
  'icon-512.png'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  // Cache-first for static assets
  if (ASSETS.some(a => e.request.url.endsWith(a))) {
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request))
    );
  }
  // Network-first for API calls (CrossRef)
  else if (e.request.url.includes('api.crossref.org')) {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
  }
  // Network-first for CDN (pdf.js)
  else if (e.request.url.includes('cdnjs.cloudflare.com')) {
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
