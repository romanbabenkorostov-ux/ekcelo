// EkceloFoto — sw.js v2.7
// Service Worker: кэширует тайлы кадастрового слоя (nspd.gov.ru)
// Срок хранения: 30 дней. Лимит: 40000 тайлов (FIFO при переполнении).
// Центральные тайлы загружаются браузером первыми (Leaflet сам приоритизирует центр).

const CACHE_NAME   = 'ekcelo-cadastre-v2';
const CACHE_HOST   = 'nspd.gov.ru';
const MAX_AGE_MS   = 30 * 24 * 60 * 60 * 1000;  // 30 дней
const MAX_ENTRIES  = 40000;

self.addEventListener('install',  () => self.skipWaiting());
self.addEventListener('activate', e  => e.waitUntil(
  caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
  ).then(() => self.clients.claim())
));

self.addEventListener('fetch', e => {
  if (!e.request.url.includes(CACHE_HOST)) return;
  e.respondWith(handleCadastre(e.request));
});

async function handleCadastre(request) {
  const cache  = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  if (cached) {
    const age = parseInt(cached.headers.get('x-sw-cached-at') || '0');
    if (Date.now() - age < MAX_AGE_MS) {
      return cached;  // Свежий кэш — отдаём немедленно
    }
    // Устаревший — обновляем в фоне, отдаём пока старый
    refreshInBackground(cache, request);
    return cached;
  }

  return fetchAndCache(cache, request);
}

async function fetchAndCache(cache, request) {
  try {
    const response = await fetch(request, { mode: 'cors', credentials: 'omit' });
    if (response.ok) {
      const headers = new Headers(response.headers);
      headers.set('x-sw-cached-at', String(Date.now()));
      const clone = new Response(await response.arrayBuffer(), {
        status: response.status,
        headers,
      });
      await pruneCache(cache);
      cache.put(request, clone.clone());
      return clone;
    }
    return response;
  } catch (_) {
    return new Response('', { status: 503 });
  }
}

async function refreshInBackground(cache, request) {
  try {
    const response = await fetch(request, { mode: 'cors', credentials: 'omit' });
    if (response.ok) {
      const headers = new Headers(response.headers);
      headers.set('x-sw-cached-at', String(Date.now()));
      const clone = new Response(await response.arrayBuffer(), { status: response.status, headers });
      cache.put(request, clone);
    }
  } catch (_) {}
}

// FIFO pruning: удаляем самые старые записи при переполнении
async function pruneCache(cache) {
  const keys = await cache.keys();
  if (keys.length <= MAX_ENTRIES - 1) return;
  // Удаляем первые (самые старые по порядку insertion)
  const toDelete = keys.slice(0, keys.length - (MAX_ENTRIES - 1));
  await Promise.all(toDelete.map(k => cache.delete(k)));
}

// Команды от основного потока
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
