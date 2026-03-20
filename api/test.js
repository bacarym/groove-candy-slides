import { Innertube } from 'youtubei.js';
import { BG } from 'bgutils-js';
import { JSDOM } from 'jsdom';

const REQUEST_KEY = 'O43z0dpjhgX20SCx4KAo';

function parseCookieFile(raw) {
  return raw.split('\n')
    .filter(l => l && !l.startsWith('#') && l.includes('\t'))
    .map(l => { const p = l.split('\t'); return p[5] + '=' + p[6]; })
    .join('; ');
}

export default async function handler(req, res) {
  const steps = [];
  try {
    const dom = new JSDOM('', { url: 'https://www.youtube.com/', referrer: 'https://www.youtube.com/' });
    Object.assign(globalThis, { window: dom.window, document: dom.window.document, location: dom.window.location, origin: dom.window.origin });
    if (!Reflect.has(globalThis, 'navigator')) Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator });

    let cookieStr = '';
    const b64 = process.env.YT_COOKIES || '';
    if (b64) {
      const raw = Buffer.from(b64, 'base64').toString('utf-8');
      const ytLines = raw.split('\n').filter(l => l.includes('.youtube.com') || l.includes('.google.com'));
      cookieStr = ytLines
        .filter(l => l && !l.startsWith('#') && l.includes('\t'))
        .map(l => { const p = l.split('\t'); return p[5] + '=' + p[6]; })
        .join('; ');
      steps.push('cookies: ' + ytLines.length + ' lines, ' + cookieStr.length + ' chars');
    } else {
      steps.push('cookies: NONE (no env var)');
    }

    const yt0 = await Innertube.create({ retrieve_player: false, cookie: cookieStr || undefined });
    const visitorData = yt0.session.context.client.visitorData;
    steps.push('visitorData: ' + (visitorData ? 'OK' : 'NONE'));

    const bgConfig = { fetch: (u, o) => fetch(u, o), globalObj: globalThis, identifier: visitorData, requestKey: REQUEST_KEY };
    const bgChallenge = await BG.Challenge.create(bgConfig);
    const js = bgChallenge?.interpreterJavascript?.privateDoNotAccessOrElseSafeScriptWrappedValue;
    if (js) new Function(js)();
    steps.push('challenge+interpreter: OK');

    const result = await BG.PoToken.generate({ program: bgChallenge.program, globalName: bgChallenge.globalName, bgConfig });
    steps.push('poToken: ' + (result.poToken ? 'OK' : 'NONE'));

    const yt = await Innertube.create({
      po_token: result.poToken,
      visitor_data: visitorData,
      cookie: cookieStr || undefined,
      generate_session_locally: true,
    });
    steps.push('innertube (cookies+PO): OK');

    const info = await yt.getInfo('hC8CH0Z3L54');
    steps.push('playability: ' + (info.playability_status?.status || 'N/A') + ' - ' + (info.playability_status?.reason || 'OK'));

    const sd = info.streaming_data;
    const audioFmts = (sd?.adaptive_formats || []).filter(f => f.mime_type?.startsWith('audio/'));
    steps.push('formats: ' + (sd?.formats?.length || 0) + ' + ' + (sd?.adaptive_formats?.length || 0) + ' adaptive, ' + audioFmts.length + ' audio');

    if (audioFmts.length) {
      const fmt = info.chooseFormat({ quality: 'best', type: 'audio' });
      const streamUrl = fmt.decipher(yt.session.player);
      steps.push('audio URL: ' + (streamUrl ? streamUrl.substring(0, 60) + '...' : 'NONE'));
    }

    res.status(200).json({ ok: true, steps });
  } catch (e) {
    steps.push('ERROR: ' + e.message);
    res.status(500).json({ error: e.message, steps });
  }
}
