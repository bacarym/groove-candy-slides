#!/usr/bin/env python3
"""Groove Candy Slide Maker — Interface web (2-step flow)."""

import os
import shutil
import uuid
import threading
import tempfile

from flask import Flask, request, send_from_directory, jsonify, make_response

from groove_candy import (
    parse_youtube, download_audio, search_discogs_all_images,
    make_vinyl_image, generate_slides,
)
from config import SLIDE_DURATION, SLIDE_COUNT

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
CANDIDATES_DIR = os.path.join(OUTPUT_DIR, "candidates")
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static")
jobs = {}


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/output/<path:filename>")
def serve_output(filename):
    response = make_response(send_from_directory(OUTPUT_DIR, filename))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/search", methods=["POST"])
def search():
    data = request.get_json()
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "Pas de lien YouTube fourni"}), 400

    try:
        meta = parse_youtube(url)
    except Exception as e:
        return jsonify({"error": f"Erreur YouTube: {e}"}), 400

    search_id = str(uuid.uuid4())[:8]
    save_dir = os.path.join(CANDIDATES_DIR, search_id)
    os.makedirs(save_dir, exist_ok=True)

    images = search_discogs_all_images(meta["artist"], meta["track"], save_dir)

    if not images:
        return jsonify({
            "error": f"Aucune image trouvee sur Discogs pour \"{meta['artist']} - {meta['track']}\"",
        }), 404

    return jsonify({
        "search_id": search_id,
        "artist": meta["artist"],
        "track": meta["track"],
        "images": [
            {
                "filename": img["filename"],
                "score": img["score"],
                "type": img["type"],
                "label": img["label"],
                "year": img["year"] if img["year"] else "",
                "release_title": img["release_title"],
            }
            for img in images
        ],
    })


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    url = data.get("url", "").strip()
    search_id = data.get("search_id", "")
    image_filename = data.get("image_filename", "")
    duration = data.get("duration", SLIDE_DURATION)
    start = data.get("start", 0)

    if not url or not search_id or not image_filename:
        return jsonify({"error": "Donnees manquantes"}), 400

    cand_file = os.path.join(CANDIDATES_DIR, search_id, image_filename)
    if not os.path.exists(cand_file):
        return jsonify({"error": "Image candidate introuvable"}), 404

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "running", "step": "Initialisation..."}

    thread = threading.Thread(
        target=run_pipeline,
        args=(job_id, url, cand_file, duration, start),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "error", "error": "Job introuvable"}), 404
    return jsonify(job)


def run_pipeline(job_id, url, image_path, duration, start):
    temp_dir = tempfile.mkdtemp(prefix="groove_candy_")
    try:
        meta = parse_youtube(url)
        artist = meta["artist"]
        track = meta["track"]

        jobs[job_id]["step"] = f"Telechargement audio — {artist} - {track}..."
        audio_path = download_audio(url, temp_dir)

        jobs[job_id]["step"] = "Creation de l'image vinyl..."
        vinyl_path = os.path.join(temp_dir, "vinyl.png")
        make_vinyl_image(image_path, vinyl_path)

        jobs[job_id]["step"] = "Generation des 3 slides video..."
        slides = generate_slides(
            vinyl_path, audio_path, OUTPUT_DIR,
            duration, start, SLIDE_COUNT,
            prefix=f"{job_id}_",
        )

        files = [{"name": os.path.basename(s)} for s in slides]
        jobs[job_id] = {
            "status": "done",
            "artist": artist,
            "track": track,
            "files": files,
        }

    except Exception as e:
        jobs[job_id] = {"status": "error", "error": str(e)}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    print("\n  Groove Candy Slide Maker")
    print("  http://localhost:8080\n")
    app.run(debug=False, port=8080)
