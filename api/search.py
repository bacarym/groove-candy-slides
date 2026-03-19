"""Vercel serverless function — YouTube metadata + Discogs image search."""

from http.server import BaseHTTPRequestHandler
import json
import os
import re

import requests

DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "")
DISCOGS_UA = "GrooveCandySlideMaker/1.0"


def parse_youtube_oembed(url):
    resp = requests.get(
        "https://www.youtube.com/oembed",
        params={"url": url, "format": "json"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    title = data.get("title", "")

    match = re.match(r"^(.+?)\s*[-–—]\s*(.+)$", title)
    if match:
        artist = match.group(1).strip()
        track = match.group(2).strip()
    else:
        artist = data.get("author_name", "Unknown")
        track = title

    artist = re.sub(r"^[\(\[]\d{4}[\)\]]\s*", "", artist).strip()
    return {"artist": artist, "track": track}


def score_from_metadata(img_meta):
    """Lightweight scoring using Discogs metadata only (no image download)."""
    score = 0
    w = img_meta.get("width", 0)
    h = img_meta.get("height", 0)

    if w > 0 and h > 0:
        ratio = min(w, h) / max(w, h)
        score += ratio * 30
        score += min(min(w, h) / 600, 1.0) * 10

    img_type = img_meta.get("type", "")
    if img_type == "secondary":
        score += 25
    elif img_type == "primary":
        score += 5

    return round(score, 1)


def search_discogs(artist, track):
    if not DISCOGS_TOKEN:
        return []

    headers = {"User-Agent": DISCOGS_UA}
    clean_track = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", track).strip()

    queries = [f"{artist} {clean_track}", f"{artist} {track}", clean_track]
    release_ids = []

    for q in queries:
        resp = requests.get(
            "https://api.discogs.com/database/search",
            params={"q": q, "type": "release", "token": DISCOGS_TOKEN, "per_page": 5},
            headers=headers, timeout=10,
        )
        resp.raise_for_status()
        for r in resp.json().get("results", []):
            rid = r.get("id")
            if rid and rid not in release_ids:
                release_ids.append(rid)
        if release_ids:
            break

    if not release_ids:
        return []

    all_images = []
    for rid in release_ids[:3]:
        try:
            resp = requests.get(
                f"https://api.discogs.com/releases/{rid}",
                params={"token": DISCOGS_TOKEN},
                headers=headers, timeout=10,
            )
            resp.raise_for_status()
            release = resp.json()
            release_title = release.get("title", "?")
            labels = release.get("labels", [])
            label_name = labels[0].get("name", "") if labels else ""
            year = release.get("year", 0)

            for img_meta in release.get("images", []):
                uri = img_meta.get("uri")
                uri150 = img_meta.get("uri150", "")
                if not uri:
                    continue
                score = score_from_metadata(img_meta)
                all_images.append({
                    "url": uri,
                    "thumb": uri150 or uri,
                    "score": score,
                    "type": img_meta.get("type", "?"),
                    "release_title": release_title,
                    "label": label_name,
                    "year": year,
                })
        except Exception:
            continue

    all_images.sort(key=lambda x: x["score"], reverse=True)
    return all_images


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._json({"status": "ok", "token_set": bool(DISCOGS_TOKEN)})

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            url = body.get("url", "").strip()
            if not url:
                return self._json({"error": "Pas de lien YouTube fourni"}, 400)

            try:
                meta = parse_youtube_oembed(url)
            except Exception as e:
                return self._json({"error": f"Erreur YouTube: {e}"}, 400)

            images = search_discogs(meta["artist"], meta["track"])

            if not images:
                return self._json({
                    "error": f"Aucune image trouvée sur Discogs pour \"{meta['artist']} - {meta['track']}\"",
                }, 404)

            self._json({
                "artist": meta["artist"],
                "track": meta["track"],
                "images": images,
            })
        except Exception as e:
            self._json({"error": f"Internal error: {e}"}, 500)

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
