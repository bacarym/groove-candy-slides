import { Innertube } from 'youtubei.js';
import { BG } from 'bgutils-js';
import { JSDOM } from 'jsdom';

const REQUEST_KEY = 'O43z0dpjhgX20SCx4KAo';
const MAX_BYTES = 4_400_000;
const CF_PROXY_URL = process.env.CF_PROXY_URL;
const _nativeFetch = globalThis.fetch;

if (CF_PROXY_URL) {
  const PROXY_DOMAINS = ['youtube.com', 'youtu.be', 'googlevideo.com', 'google.com', 'gstatic.com', 'ytimg.com'];

  globalThis.fetch = function patchedFetch(input, init) {
    let urlStr;
    if (typeof input === 'string') urlStr = input;
    else if (input instanceof URL) urlStr = input.href;
    else if (input && typeof input === 'object' && input.url) urlStr = input.url;
    else return _nativeFetch(input, init);

    const needsProxy = PROXY_DOMAINS.some((d) => urlStr.includes(d));
    if (!needsProxy) return _nativeFetch(input, init);

    const hdrs = {};
    const src = init?.headers || (typeof input !== 'string' && input.headers ? input.headers : null);
    if (src) {
      if (typeof src.forEach === 'function') src.forEach((v, k) => { hdrs[k] = v; });
      else if (typeof src === 'object') Object.assign(hdrs, src);
    }

    const method = init?.method || (typeof input !== 'string' ? input.method : undefined) || 'GET';
    const body = typeof init?.body === 'string' ? init.body : undefined;

    return _nativeFetch(CF_PROXY_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: urlStr, method, headers: hdrs, body }),
    });
  };
}

let domReady = false;

function setupDom() {
  if (domReady) return;
  const dom = new JSDOM('', {
    url: 'https://www.youtube.com/',
    referrer: 'https://www.youtube.com/',
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
  });
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    location: dom.window.location,
    origin: dom.window.origin,
  });
  if (!Reflect.has(globalThis, 'navigator')) {
    Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator });
  }
  domReady = true;
}

async function generatePoToken() {
  setupDom();

  const innertube = await Innertube.create({ retrieve_player: false });
  const visitorData = innertube.session.context.client.visitorData;
  if (!visitorData) throw new Error('Could not get visitor data');

  const bgConfig = {
    fetch: globalThis.fetch,
    globalObj: globalThis,
    identifier: visitorData,
    requestKey: REQUEST_KEY,
  };

  const bgChallenge = await BG.Challenge.create(bgConfig);
  if (!bgChallenge) throw new Error('Could not get BG challenge');

  const js = bgChallenge.interpreterJavascript.privateDoNotAccessOrElseSafeScriptWrappedValue;
  if (!js) throw new Error('Could not load BG interpreter');
  new Function(js)();

  const result = await BG.PoToken.generate({
    program: bgChallenge.program,
    globalName: bgChallenge.globalName,
    bgConfig,
  });

  return { poToken: result.poToken, visitorData };
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });

  try {
    const { url } = req.body || {};
    if (!url) return res.status(400).json({ error: 'URL manquante' });

    const vidMatch = url.match(/(?:v=|youtu\.be\/|shorts\/)([a-zA-Z0-9_-]{11})/);
    if (!vidMatch) return res.status(400).json({ error: 'ID vidéo introuvable' });
    const videoId = vidMatch[1];

    const { poToken, visitorData } = await generatePoToken();

    const innertube = await Innertube.create({
      po_token: poToken,
      visitor_data: visitorData,
      generate_session_locally: true,
    });

    const info = await innertube.getBasicInfo(videoId);
    const format = info.chooseFormat({ quality: 'best', type: 'audio' });
    const streamUrl = format.decipher(innertube.session.player);

    const audioResp = await globalThis.fetch(streamUrl, {
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36' },
    });
    if (!audioResp.ok) throw new Error(`Audio fetch failed: ${audioResp.status}`);

    const reader = audioResp.body.getReader();
    const chunks = [];
    let total = 0;

    while (total < MAX_BYTES) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      total += value.length;
    }
    reader.cancel();

    const audioData = Buffer.concat(chunks).subarray(0, MAX_BYTES);
    const mime = format.mime_type?.split(';')[0] || 'audio/mp4';

    res.setHeader('Content-Type', mime);
    res.setHeader('Content-Length', audioData.length);
    res.status(200).send(audioData);

  } catch (e) {
    console.error('Audio error:', e);
    res.status(500).json({ error: e.message || 'Erreur interne' });
  }
}
