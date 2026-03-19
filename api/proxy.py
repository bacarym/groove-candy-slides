"""Vercel serverless function — CORS proxy for Discogs images."""

from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import requests


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        url = query.get("url", [""])[0]

        if not url or not url.startswith("https://i.discogs.com/"):
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Invalid URL")
            return

        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "GrooveCandySlideMaker/1.0"})
            resp.raise_for_status()
            self.send_response(200)
            self.send_header("Content-Type", resp.headers.get("Content-Type", "image/jpeg"))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Proxy error")
