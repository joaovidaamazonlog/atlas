// Service Worker — ATLAS PWA
const CACHE_NAME = 'atlas-v2';
const STATIC_ASSETS = ['/', '/atlas/', '/atlas/index.html', '/atlas/manifest.json'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Dados geoespaciais (output_data/ e config/) — sempre network-first, sem cache
  // Suporta tanto /output_data/ (raiz) quanto /atlas/output_data/ (GitHub Pages)
  const isData =
    url.pathname.includes('/output_data/') ||
    url.pathname.includes('/config/');

  if (isData) {
    // Network-first: busca sempre a versão mais recente, sem fallback de cache
    event.respondWith(fetch(event.request));
    return;
  }

  // Assets estáticos: cache-first
  event.respondWith(
    caches.match(event.request).then(cached => cached || fetch(event.request))
  );
});
