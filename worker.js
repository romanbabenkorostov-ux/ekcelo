/**
 * EkceloFoto — Cloudflare Worker CORS-прокси для Яндекс.Диска
 *
 * Деплой (бесплатно, 2 минуты):
 * 1. https://dash.cloudflare.com → Workers → Create Worker
 * 1.1 На странице создания выберите "Start with Hello World!" (кнопка или карточка с этим текстом)
 * 1.2. В открывшемся окне введите имя воркера. Например ekcelo-proxy
 * 1.3. Нажмите "Deploy" (или "Save and Deploy")
 * 1.4. После деплоя нажмите "Edit code"
 * 1.5. Удалите весь код по умолчанию и вставьте этот скрипт (.js)
 * 2. Скопируйте адрес вида https://ekcelo-proxy.ВАШ-SUBDOMAIN.workers.dev
 * 3. Вставьте его в index.html в константу YANDEX_PROXY (первая строка скрипта)
 *
 * Разрешённые домены (только Яндекс):
 *   cloud-api.yandex.net  — API для получения ссылки скачивания
 *   downloader.disk.yandex.ru — CDN скачивания файла
 *   yadi.sk, disk.yandex.ru   — редиректы
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
    // CORS preflight
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

    // Проверяем, что проксируем только Яндекс
    let targetUrl;
    try {
      targetUrl = new URL(target);
    } catch {
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

    // Проксируем, следуя редиректам
    const upstream = await fetch(target, {
      redirect: 'follow',
      headers: { 'User-Agent': 'EkceloFoto/1.0 (CORS proxy)' },
    });

    const respHeaders = new Headers(upstream.headers);
    Object.entries(CORS_HEADERS).forEach(([k, v]) => respHeaders.set(k, v));
    // Убираем заголовки, которые мешают браузеру читать ответ
    respHeaders.delete('Content-Security-Policy');
    respHeaders.delete('X-Frame-Options');

    return new Response(upstream.body, {
      status: upstream.status,
      headers: respHeaders,
    });
  },
};
