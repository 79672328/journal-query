// Self-clearing migration SW - clears all caches then returns to normal
const CACHE = 'jq-v12';

// On install, delete ALL existing caches
self.addEventListener('install', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))))
      .then(() => caches.open(CACHE))
  );
  self.skipWaiting();
});

// On activate, re-claim clients so the current page gets fresh content
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Bypass cache for all requests — fetch from network every time
self.addEventListener('fetch', e => {
  e.respondWith(
    fetch(e.request).catch(() => {
      // Offline fallback: try cache
      return caches.match(e.request);
    })
  );
});
