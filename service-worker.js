const CACHE_NAME = 'atlas-cache-v1';
const urlsToCache = [
  'ATLAS_responsive.html',
  'atlas_responsive.css',
  'atlas_stats_panel_responsive.css',
  'script.js',
  'icons/hub.png',
  'icons/AmazonHub.ico'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});
