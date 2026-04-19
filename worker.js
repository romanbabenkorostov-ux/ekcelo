// Cloudflare Worker — CORS-прокси для Яндекс.Диска
// Деплой: https://dash.cloudflare.com → Workers → Create Worker → вставить код
// После деплоя: вставьте URL воркера в YANDEX_PROXY в index.html

const ALLOWED_HOSTS = [
  'cloud-api.yandex.net',
  'downloader.disk.yandex.ru',
  'disk.yandex.ru',
  'yadi.sk',
];

const MAX_SIZE = 50 * 1024 * 1024; // 50 МБ

export default {
  async fetch(request, env, ctx) {
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: corsHeaders(request),
      });
    }

    const urlParam = new URL(request.url).searchParams.get('url');
    if (!urlParam) {
      return new Response('Missing ?url=', { status: 400, headers: corsHeaders(request) });
    }

    let target;
    try { target = new URL(urlParam); }
    catch (_) { return new Response('Invalid URL', { status: 400, headers: corsHeaders(request) }); }

    if (!ALLOWED_HOSTS.some(h => target.hostname === h || target.hostname.endsWith('.' + h))) {
      return new Response('Host not allowed: ' + target.hostname, { status: 403, headers: corsHeaders(request) });
    }

    const upstream = await fetch(target.toString(), {
      headers: { 'User-Agent': 'EkceloFoto/2.5' },
      redirect: 'follow',
    });

    const ct = upstream.headers.get('content-type') || '';
    const cl = parseInt(upstream.headers.get('content-length') || '0');

    if (cl > MAX_SIZE) {
      return new Response('File too large', { status: 413, headers: corsHeaders(request) });
    }

    return new Response(upstream.body, {
      status:  upstream.status,
      headers: {
        ...corsHeaders(request),
        'content-type': ct,
        'cache-control': 'no-store',
      },
    });
  },
};

function corsHeaders(req) {
  const origin = req.headers.get('origin') || '*';
  return {
    'access-control-allow-origin':  origin,
    'access-control-allow-methods': 'GET, OPTIONS',
    'access-control-allow-headers': 'content-type',
    'access-control-max-age':       '86400',
    'vary': 'origin',
  };
}
