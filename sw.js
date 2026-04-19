// EkceloFoto — sw.js v2.6
// Service Worker: кэширует тайлы кадастрового слоя (nspd.gov.ru)
// Срок хранения: 7 дней. При следующем входе тайлы не скачиваются заново.

const CACHE_NAME   = 'ekcelo-cadastre-v1';
const CACHE_HOST   = 'nspd.gov.ru';
const MAX_AGE_MS   = 7 * 24 * 60 * 60 * 1000;   // 7 дней
const MAX_ENTRIES  = 8000;                         // максимум тайлов в кэше

self.addEventListener('install',  () => self.skipWaiting());
self.addEventListener('activate', e  => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', e => {
  const { url } = e.request;
  if (!url.includes(CACHE_HOST)) return;          // пропускаем не-кадастровые запросы

  e.respondWith(handleCadastre(e.request));
});

async function handleCadastre(request) {
  const cache  = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  if (cached) {
    const age = parseInt(cached.headers.get('x-sw-cached-at') || '0');
    if (Date.now() - age < MAX_AGE_MS) {
      return cached;                               // свежий кэш — отдаём сразу
    }
  }

  try {
    const response = await fetch(request, { mode: 'cors', credentials: 'omit' });
    if (response.ok) {
      // Копируем ответ, добавляем метку времени
      const headers = new Headers(response.headers);
      headers.set('x-sw-cached-at', String(Date.now()));
      const clone = new Response(await response.arrayBuffer(), {
        status:  response.status,
        headers,
      });
      // Ограничиваем размер кэша
      await pruneCache(cache, MAX_ENTRIES - 1);
      cache.put(request, clone.clone());
      return clone;
    }
    return response;
  } catch (_) {
    // Offline или ошибка сети — вернуть устаревший кэш если есть
    return cached || new Response('', { status: 503 });
  }
}

async function pruneCache(cache, limit) {
  const keys = await cache.keys();
  if (keys.length <= limit) return;
  // Удаляем старейшие записи (FIFO)
  const toDelete = keys.slice(0, keys.length - limit);
  await Promise.all(toDelete.map(k => cache.delete(k)));
}

// Сообщение от основного потока: очистить кэш вручную
self.addEventListener('message', async e => {
  if (e.data === 'clearCadastreCache') {
    await caches.delete(CACHE_NAME);
    e.source?.postMessage('cadastreCacheCleared');
  }
  if (e.data === 'getCacheSize') {
    const cache = await caches.open(CACHE_NAME);
    const keys  = await cache.keys();
    e.source?.postMessage({ type: 'cacheSize', count: keys.length });
  }
});
