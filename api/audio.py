"""Download YouTube audio via yt-dlp with cookie support for cloud IPs."""

from http.server import BaseHTTPRequestHandler
import base64
import json
import os
import tempfile

import yt_dlp

YT_COOKIES_B64 = os.environ.get("YT_COOKIES", "")


def _write_cookies(tmp_dir):
    """Decode YT_COOKIES env var (base64 Netscape format) to a temp file."""
    if not YT_COOKIES_B64:
        return None
    try:
        raw = base64.b64decode(YT_COOKIES_B64)
        path = os.path.join(tmp_dir, "cookies.txt")
        with open(path, "wb") as f:
            f.write(raw)
        return path
    except Exception:
        return None


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            url = body.get("url", "").strip()
            if not url:
                return self._json({"error": "URL manquante"}, 400)

            with tempfile.TemporaryDirectory() as tmp:
                tpl = os.path.join(tmp, "audio.%(ext)s")
                cookie_file = _write_cookies(tmp)

                base_opts = {
                    "format": "140/bestaudio[ext=m4a]/bestaudio",
                    "outtmpl": tpl,
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "postprocessors": [],
                    "socket_timeout": 7,
                }
                if cookie_file:
                    base_opts["cookiefile"] = cookie_file

                strategies = [
                    {},
                    {"extractor_args": {"youtube": {"player_client": ["mweb"]}}},
                    {"extractor_args": {"youtube": {"player_client": ["android"]}}, "format": "bestaudio"},
                ]

                last_err = None
                for strat in strategies:
                    try:
                        opts = {**base_opts, **strat}
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            ydl.download([url])
                        break
                    except Exception as e:
                        last_err = e
                        for f in os.listdir(tmp):
                            if f.startswith("audio."):
                                os.remove(os.path.join(tmp, f))
                        continue
                else:
                    raise last_err

                audio_file = None
                for f in os.listdir(tmp):
                    if f.startswith("audio."):
                        audio_file = os.path.join(tmp, f)
                        break

                if not audio_file:
                    return self._json({"error": "Audio introuvable"}, 500)

                size = os.path.getsize(audio_file)
                if size > 4_400_000:
                    return self._json({"error": "Audio trop volumineux. Essaie un morceau plus court."}, 413)

                with open(audio_file, "rb") as f:
                    audio_data = f.read()

            ext = os.path.splitext(audio_file)[1].lstrip(".")
            mime_map = {"m4a": "audio/mp4", "webm": "audio/webm", "opus": "audio/ogg"}
            mime = mime_map.get(ext, "audio/mpeg")

            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(audio_data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(audio_data)

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
