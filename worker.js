/**
 * EkceloFoto — Cloudflare Worker CORS-прокси для Яндекс.Диска
 *
 * Деплой (бесплатно, 2 минуты):
 * 1. https://dash.cloudflare.com → Workers → Create Worker
 * 1.1 Выберите "Start with Hello World!"
 * 1.2 Введите имя воркера, например ekcelo-proxy
 * 1.3 Нажмите "Deploy", затем "Edit code"
 * 1.4 Удалите код по умолчанию и вставьте этот скрипт
 * 2. Скопируйте адрес вида https://ekcelo-proxy.ВАШ-SUBDOMAIN.workers.dev
 * 3. Вставьте его в index.html в константу YANDEX_PROXY
 */

const ALLOWED_HOSTS = [
  'cloud-api.yandex.net',
  'downloader.disk.yandex.ru',
  'disk.yandex.ru',
  'yadi.sk',
];

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Max-Age': '86400',
};

export default {
  async fetch(request) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS });
    }

    const incoming = new URL(request.url);
    const target = incoming.searchParams.get('url');

    if (!target) {
      return new Response(JSON.stringify({ error: 'Missing ?url= param' }), {
        status: 400,
        headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
      });
    }

    let targetUrl;
    try { targetUrl = new URL(target); }
    catch {
      return new Response(JSON.stringify({ error: 'Invalid URL' }), {
        status: 400,
        headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
      });
    }

    const hostOk = ALLOWED_HOSTS.some(h => targetUrl.hostname === h || targetUrl.hostname.endsWith('.' + h));
    if (!hostOk) {
      return new Response(JSON.stringify({ error: `Host not allowed: ${targetUrl.hostname}` }), {
        status: 403,
        headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
      });
    }

    const upstream = await fetch(target, {
      redirect: 'follow',
      headers: { 'User-Agent': 'EkceloFoto/1.0 (CORS proxy)' },
    });

    const respHeaders = new Headers(upstream.headers);
    Object.entries(CORS_HEADERS).forEach(([k, v]) => respHeaders.set(k, v));
    respHeaders.delete('Content-Security-Policy');
    respHeaders.delete('X-Frame-Options');

    return new Response(upstream.body, {
      status: upstream.status,
      headers: respHeaders,
    });
  },
};
