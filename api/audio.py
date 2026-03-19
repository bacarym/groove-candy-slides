"""Vercel serverless function — Download YouTube audio via yt-dlp."""

from http.server import BaseHTTPRequestHandler
import json
import os
import tempfile

import yt_dlp


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            url = body.get("url", "").strip()
            if not url:
                return self._json({"error": "URL manquante"}, 400)

            with tempfile.TemporaryDirectory() as tmp:
                output_tpl = os.path.join(tmp, "audio.%(ext)s")
                ydl_opts = {
                    "format": "bestaudio",
                    "outtmpl": output_tpl,
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "postprocessors": [],
                    "socket_timeout": 6,
                    "extractor_args": {
                        "youtube": {"player_client": ["tv_embedded", "mweb"]},
                    },
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                audio_file = None
                for f in os.listdir(tmp):
                    if f.startswith("audio."):
                        audio_file = os.path.join(tmp, f)
                        break

                if not audio_file:
                    return self._json({"error": "Audio introuvable après téléchargement"}, 500)

                size = os.path.getsize(audio_file)
                if size > 4_400_000:
                    return self._json({"error": f"Audio trop volumineux ({size // 1_000_000}MB). Essaie un morceau plus court."}, 413)

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
