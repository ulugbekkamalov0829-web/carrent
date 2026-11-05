/* CarRent service worker: ilova qobig'ini keshlaydi, oflayn holatda sahifa ochiladi.
   API so'rovlari (/api/) va yuklangan suratlar hech qachon keshlanmaydi — shaxsiy ma'lumot qurilmada qolmaydi. */
const VERSION = "carrent-v9";
const SHELL = ["/", "/index.html", "/cars.html", "/info.html", "/auth.html", "/css/styles.css", "/js/app.js", "/js/widgets.js",
  "/locales/uz.json", "/locales/ru.json", "/locales/en.json", "/img/favicon.svg", "/img/icon-192.png", "/offline.html"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/uploads/")) return;   // har doim tarmoqdan
  // Avval tarmoq (yangi versiya), bo'lmasa kesh; sahifa topilmasa — oflayn sahifa
  e.respondWith(fetch(e.request).then((res) => {
    if (res.ok && (url.pathname.match(/\.(css|js|json|svg|png|jpg|webmanifest)$/) || e.request.mode === "navigate")) {
      const copy = res.clone(); caches.open(VERSION).then((c) => c.put(e.request, copy));
    }
    return res;
  }).catch(async () => (await caches.match(e.request)) || (e.request.mode === "navigate" ? caches.match("/offline.html") : Response.error())));
});
