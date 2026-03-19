"""Download YouTube audio via YouTube's innertube API (iOS client).

Bypasses bot detection by using the iOS YouTube app's internal API
instead of web scraping. No yt-dlp dependency needed.
"""

from http.server import BaseHTTPRequestHandler
import json
import random
import re
import string

import requests

INNERTUBE_URL = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"

_IOS = {
    "clientName": "IOS",
    "clientVersion": "19.45.4",
    "deviceMake": "Apple",
    "deviceModel": "iPhone16,2",
    "userAgent": (
        "com.google.ios.youtube/19.45.4 "
        "(iPhone16,2; U; CPU iOS 18_1_1 like Mac OS X; en_US)"
    ),
    "osName": "iPhone",
    "osVersion": "18.1.1.22B91",
    "hl": "en",
    "gl": "US",
}

_HDRS = {
    "User-Agent": _IOS["userAgent"],
    "Content-Type": "application/json",
    "X-YouTube-Client-Name": "5",
    "X-YouTube-Client-Version": _IOS["clientVersion"],
}

MAX_BYTES = 4_400_000


def _vid_id(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else None


def _cpn():
    return "".join(random.choices(string.ascii_letters + string.digits + "-_", k=16))


def _best_audio(video_id):
    payload = {
        "videoId": video_id,
        "context": {"client": _IOS},
        "contentCheckOk": True,
        "racyCheckOk": True,
    }
    r = requests.post(INNERTUBE_URL, json=payload, headers=_HDRS, timeout=8)
    r.raise_for_status()
    data = r.json()

    ps = data.get("playabilityStatus", {})
    if ps.get("status") != "OK":
        raise ValueError(ps.get("reason", "Vidéo indisponible"))

    fmts = data.get("streamingData", {}).get("adaptiveFormats", [])
    audio = [f for f in fmts if f.get("mimeType", "").startswith("audio/") and "url" in f]
    if not audio:
        raise ValueError("Aucun flux audio trouvé")

    audio.sort(key=lambda f: ("mp4a" in f.get("mimeType", ""), f.get("bitrate", 0)), reverse=True)
    return audio[0]


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            url = body.get("url", "").strip()
            if not url:
                return self._json({"error": "URL manquante"}, 400)

            vid = _vid_id(url)
            if not vid:
                return self._json({"error": "ID vidéo introuvable dans l'URL"}, 400)

            stream = _best_audio(vid)
            audio_url = stream["url"] + "&cpn=" + _cpn()
            mime = stream.get("mimeType", "audio/mp4").split(";")[0]

            dl = requests.get(
                audio_url,
                headers={"User-Agent": _IOS["userAgent"]},
                timeout=8,
                stream=True,
            )
            dl.raise_for_status()

            chunks = []
            total = 0
            for chunk in dl.iter_content(8192):
                chunks.append(chunk)
                total += len(chunk)
                if total >= MAX_BYTES:
                    break
            dl.close()
            audio_data = b"".join(chunks)

            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(audio_data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(audio_data)

        except ValueError as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
