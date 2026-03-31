const ALLOWED_HOSTS = [
  'youtube.com',
  'youtu.be',
  'googlevideo.com',
  'google.com',
  'gstatic.com',
  'ytimg.com',
];

function isAllowedUrl(urlStr) {
  try {
    const host = new URL(urlStr).hostname;
    return ALLOWED_HOSTS.some((d) => host === d || host.endsWith('.' + d));
  } catch {
    return false;
  }
}

export default {
  async fetch(request) {
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        },
      });
    }

    if (request.method !== 'POST') {
      return new Response('POST only', { status: 405 });
    }

    try {
      const { url, method, headers, body } = await request.json();

      if (!url || !isAllowedUrl(url)) {
        return new Response('Blocked: URL not in allowlist', { status: 403 });
      }

      const resp = await fetch(url, {
        method: method || 'GET',
        headers: headers || {},
        body: body || undefined,
      });

      const out = new Headers();
      out.set('Access-Control-Allow-Origin', '*');
      for (const [k, v] of resp.headers.entries()) {
        if (!['transfer-encoding', 'connection'].includes(k.toLowerCase())) {
          out.set(k, v);
        }
      }

      return new Response(resp.body, { status: resp.status, headers: out });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), {
        status: 502,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*',
        },
      });
    }
  },
};
