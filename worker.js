/**
 * EkceloFoto — Cloudflare Worker CORS-прокси
 *
 * Деплой (бесплатно, 2 минуты):
 * 1. https://dash.cloudflare.com → Workers → Create Worker
 * 2. Вставьте этот код → Deploy
 * 3. Скопируйте адрес вида https://ekcelo-proxy.ВАШ-SUBDOMAIN.workers.dev
 * 4. Вставьте его в index.html в константу YANDEX_PROXY (первая строка скрипта)
 *
 * Разрешённые домены:
 *   Яндекс.Диск:
 *     cloud-api.yandex.net          — API для получения ссылки скачивания
 *     downloader.disk.yandex.ru     — CDN скачивания файла
 *     yadi.sk, disk.yandex.ru       — редиректы
 *   Росреестр:
 *     pkk.rosreestr.ru              — Публичная кадастровая карта (PKK5), поиск по номеру
 *   НСПД:
 *     nspd.gov.ru                   — Национальная система пространственных данных, WFS геометрия
 */

const ALLOWED_HOSTS = [
  // Яндекс.Диск
  'cloud-api.yandex.net',
  'downloader.disk.yandex.ru',
  'disk.yandex.ru',
  'yadi.sk',
  // Росреестр — Публичная кадастровая карта
  'pkk.rosreestr.ru',
  // НСПД — Национальная система пространственных данных
  'nspd.gov.ru',
];

// Заголовки реферера, которые ожидают некоторые эндпоинты Росреестра/НСПД
const REFERERS = {
  'pkk.rosreestr.ru': 'https://pkk.rosreestr.ru/',
  'nspd.gov.ru':      'https://nspd.gov.ru/',
};

const CORS_HEADERS = {
  'Access-Control-Allow-Origin':  '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Max-Age':       '86400',
};

export default {
  async fetch(request) {
    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS });
    }

    const incoming = new URL(request.url);
    const target   = incoming.searchParams.get('url');
    if (!target) {
      return new Response(JSON.stringify({ error: 'Missing ?url= param' }), {
        status:  400,
        headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
      });
    }

    // Валидируем URL
    let targetUrl;
    try {
      targetUrl = new URL(target);
    } catch {
      return new Response(JSON.stringify({ error: 'Invalid URL' }), {
        status:  400,
        headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
      });
    }

    // Проверяем белый список хостов
    const hostOk = ALLOWED_HOSTS.some(
      h => targetUrl.hostname === h || targetUrl.hostname.endsWith('.' + h)
    );
    if (!hostOk) {
      return new Response(JSON.stringify({ error: `Host not allowed: ${targetUrl.hostname}` }), {
        status:  403,
        headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
      });
    }

    // Подбираем Referer для хостов, которые его проверяют
    const referer = REFERERS[targetUrl.hostname]
      ?? Object.entries(REFERERS).find(([h]) => targetUrl.hostname.endsWith('.' + h))?.[1]
      ?? null;

    // Проксируем, следуя редиректам
    const upstream = await fetch(target, {
      redirect: 'follow',
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept':     'application/json, application/geo+json, */*',
        ...(referer ? { 'Referer': referer } : {}),
      },
    });

    const respHeaders = new Headers(upstream.headers);
    Object.entries(CORS_HEADERS).forEach(([k, v]) => respHeaders.set(k, v));

    // Убираем заголовки, которые мешают браузеру читать ответ
    respHeaders.delete('Content-Security-Policy');
    respHeaders.delete('X-Frame-Options');

    return new Response(upstream.body, {
      status:  upstream.status,
      headers: respHeaders,
    });
  },
};
