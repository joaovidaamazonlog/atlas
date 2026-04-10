const CACHE_NAME = 'atlas-cache-v2';
const urlsToCache = [
  'ATLAS.html',
  'css/app.css',
  'css/stats-panel.css',
  'css/dashboard.css',
  'js/main.js',
  'icons/hub.png',
  'icons/AmazonHub.ico',
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
