const CACHE_NAME = "health-app-v1";
const OFFLINE_URL = "/static/health_application/offline.html";
const ASSETS = [
  OFFLINE_URL,
  "/static/health_application/assets/css/main.css",
  "/static/health_application/assets/js/main.js",
  "/static/health_application/assets/js/pwa.js",
  "/static/health_application/assets/js/reminders.js",
  "/static/health_application/assets/images/logo.svg",
  "/static/health_application/assets/images/logo-icon.svg",
  "/static/health_application/assets/images/favicon_io/android-chrome-192x192.png",
  "/static/health_application/assets/images/favicon_io/android-chrome-512x512.png",
  "/static/health_application/assets/audio/reminder-alarm.wav",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() =>
        caches.match(event.request).then((cached) => {
          if (cached) {
            return cached;
          }
          if (event.request.mode === "navigate") {
            return caches.match(OFFLINE_URL);
          }
          return new Response("Offline", { status: 503, statusText: "Offline" });
        })
      )
  );
});
