// EkceloFoto — sw.js v2.10.0
// Service Worker: кэширует тайлы кадастрового слоя (nspd.gov.ru)
// Срок хранения: 30 дней. Лимит: 2000000 тайлов (FIFO при переполнении).
// Центральные тайлы загружаются браузером первыми (Leaflet сам приоритизирует центр).

const CACHE_NAME   = 'ekcelo-cadastre-v3';
const CACHE_HOST   = 'nspd.gov.ru';
const MAX_AGE_MS   = 30 * 24 * 60 * 60 * 1000;  // 30 дней
const MAX_ENTRIES  = 2000000;   // S3: bump CACHE_NAME v2→v3 — переезд sw.js в
// viewer/ меняет его URL; activate (ниже) одноразово вычистит старый кэш тайлов.

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

// Закэшированный кадастровый тайл = WMS GetMap к nspd.gov.ru.
// z17 в URL нет (WMS адресуется по BBOX) — фильтруем по host + REQUEST=GetMap.
function _isCadastreTileUrl(u){
  return u.includes('nspd.gov.ru') && u.includes('REQUEST=GetMap');
}
const _DUMP_CHUNK = 200;

// Команды от основного потока
self.addEventListener('message', async e => {
  const d = e.data;
  if (d === 'clearCadastreCache') {
    await caches.delete(CACHE_NAME);
    e.source?.postMessage('cadastreCacheCleared');
    return;
  }
  if (d === 'getCacheSize') {
    const cache = await caches.open(CACHE_NAME);
    const keys  = await cache.keys();
    e.source?.postMessage({ type: 'cacheSize', count: keys.length });
    return;
  }
  if (d && d.type === 'dumpZ17Tiles') {
    const cache = await caches.open(CACHE_NAME);
    const keys  = (await cache.keys()).filter(r => _isCadastreTileUrl(r.url));
    let seq = 0, count = 0;
    for (let i = 0; i < keys.length; i += _DUMP_CHUNK) {
      const slice = keys.slice(i, i + _DUMP_CHUNK);
      const tiles = [];
      for (const req of slice) {
        const resp = await cache.match(req);
        if (!resp) continue;
        tiles.push({ url: req.url, bytes: await resp.arrayBuffer() });
        count++;
      }
      e.source?.postMessage(
        { type: 'z17TilesDumpChunk', reqId: d.reqId, seq: seq++, tiles },
        tiles.map(t => t.bytes)
      );
    }
    e.source?.postMessage({ type: 'z17TilesDumpDone', reqId: d.reqId, count });
    return;
  }
  if (d && d.type === 'importZ17Tiles') {
    const cache = await caches.open(CACHE_NAME);
    let added = 0, skipped = 0;
    for (const t of (d.tiles || [])) {
      if (!t || !t.url) { skipped++; continue; }
      if (await cache.match(t.url)) { skipped++; continue; }  // обогащение: не перезаписываем
      const headers = new Headers({ 'content-type': 'image/png' });
      headers.set('x-sw-cached-at', String(Date.now()));
      await cache.put(t.url, new Response(t.bytes, { status: 200, headers }));
      added++;
    }
    if (d.last) await pruneCache(cache);
    e.source?.postMessage({ type: 'z17TilesImported', reqId: d.reqId, seq: d.seq, added, skipped, last: !!d.last });
    return;
  }
});
