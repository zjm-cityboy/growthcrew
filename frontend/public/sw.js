/* GrowthCrew Service Worker — 离线缓存 + 补传队列触发 */
const CACHE_NAME = "growthcrew-v1";
const APP_SHELL = ["/", "/chat", "/archive", "/settings", "/login", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// 网络优先（API 数据新鲜），失败回缓存（离线兜底）
self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return; // 只缓存 GET
  const url = new URL(request.url);
  // 不缓存 API 请求（需要实时数据）；缓存页面和静态资源
  if (url.pathname.startsWith("/api/")) return;

  event.respondWith(
    fetch(request)
      .then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        return response;
      })
      .catch(() =>
        caches.match(request).then((cached) => {
          if (cached) return cached;
          // 离线且无缓存：返回首页（SPA 兜底）
          return caches.match("/");
        })
      )
  );
});

// 收到消息：通知所有客户端补传离线队列
self.addEventListener("message", (event) => {
  if (event.data === "sync-offline-queue") {
    self.clients.matchAll().then((clients) => {
      clients.forEach((client) => client.postMessage("retry-offline-queue"));
    });
  }
});
