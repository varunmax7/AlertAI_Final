// Service Worker for AlertAI
const CACHE_NAME = 'alertai-v1';

self.addEventListener('fetch', event => {
  // Basic fetch handler
  event.respondWith(fetch(event.request));
});