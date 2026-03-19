#!/usr/bin/env python3
"""Groove Candy Slide Maker — 1 YouTube link → 3 Instagram carousel videos."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

from pathlib import Path

import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageStat

from config import (
    DISCOGS_TOKEN,
    DISCOGS_USER_AGENT,
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
    BACKGROUND_COLOR,
    VINYL_SIZE,
    SLIDE_DURATION,
    SLIDE_COUNT,
    VIDEO_FPS,
    AUDIO_BITRATE,
    VIDEO_CODEC,
    PIXEL_FORMAT,
)


def parse_youtube(url):
    """Extract metadata from a YouTube URL using yt-dlp."""
    result = subprocess.run(
        ["yt-dlp", "--dump-json", "--no-playlist", url],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    title = data.get("title", "")

    # Parse "Artist - Track (Remix Info)" — keep remix/version info in track title
    match = re.match(r"^(.+?)\s*[-–—]\s*(.+)$", title)
    if match:
        artist = match.group(1).strip()
        track = match.group(2).strip()
    else:
        artist = data.get("uploader", "Unknown")
        track = title

    # Strip leading (year) or [year] prefix from artist, e.g. "(1997) Dina Carroll" → "Dina Carroll"
    artist = re.sub(r"^[\(\[]\d{4}[\)\]]\s*", "", artist).strip()

    print(f"  Artiste : {artist}")
    print(f"  Titre   : {track}")
    return {"artist": artist, "track": track, "title": title}


def download_audio(url, output_dir):
    """Download audio from YouTube as m4a."""
    output_template = os.path.join(output_dir, "audio.%(ext)s")
    subprocess.run(
        [
            "yt-dlp", "-x", "--audio-format", "m4a",
            "--no-playlist",
            "-o", output_template,
            url,
        ],
        check=True,
    )
    audio_path = os.path.join(output_dir, "audio.m4a")
    if not os.path.exists(audio_path):
        # yt-dlp may keep original format if conversion fails
        for f in os.listdir(output_dir):
            if f.startswith("audio."):
                audio_path = os.path.join(output_dir, f)
                break
    print(f"  Audio : {audio_path}")
    return audio_path


def _score_image(img_data, img_meta):
    """Score an image to find the best vinyl label for a black background.

    Criteria (higher = better):
    - Square aspect ratio → likely a label photo (not a rectangular cover)
    - Dark average brightness → renders well on black background
    - Type "secondary" on Discogs → usually the label side
    - Good resolution → sharper result
    - Has visual content in center → not a blank or mostly-empty image
    """
    try:
        img = Image.open(BytesIO(img_data)).convert("RGB")
    except Exception:
        return -1

    w, h = img.size
    if w < 100 or h < 100:
        return -1

    score = 0

    # 1. Square ratio bonus (labels are photographed square)
    #    ratio=1.0 → perfect square → +30 pts
    ratio = min(w, h) / max(w, h)
    score += ratio * 30

    # 2. Darkness bonus (vinyl labels are typically dark → good on black bg)
    #    Average brightness 0-255, darker = higher score, max +25 pts
    stat = ImageStat.Stat(img)
    avg_brightness = sum(stat.mean) / 3  # average across R,G,B
    darkness_score = max(0, (180 - avg_brightness) / 180) * 25
    score += darkness_score

    # 3. Discogs type bonus
    img_type = img_meta.get("type", "")
    if img_type == "secondary":
        score += 25  # label images on Discogs are "secondary"
    elif img_type == "primary":
        score += 5   # cover art, less ideal but usable

    # 4. Resolution bonus (max +10 pts, capped at 600px)
    min_dim = min(w, h)
    score += min(min_dim / 600, 1.0) * 10

    # 5. Center content check — the center of a label has the actual design
    #    Crop center 50% and check it has enough contrast (not blank)
    cx, cy = w // 4, h // 4
    center = img.crop((cx, cy, w - cx, h - cy))
    center_stat = ImageStat.Stat(center)
    center_stddev = sum(center_stat.stddev) / 3
    # stddev > 30 means there's real visual content, max +10 pts
    score += min(center_stddev / 30, 1.0) * 10

    return score


def search_discogs_label(artist, track):
    """Search Discogs across multiple releases and pick the best label image."""
    if DISCOGS_TOKEN == "YOUR_DISCOGS_TOKEN_HERE":
        print("  Discogs : pas de token configuré, utilise --image pour fournir une image")
        return None

    headers = {"User-Agent": DISCOGS_USER_AGENT}

    clean_track = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", track).strip()

    queries = [
        f"{artist} {clean_track}",
        f"{artist} {track}",
        clean_track,
    ]

    release_ids = []
    for q in queries:
        params = {
            "q": q,
            "type": "release",
            "token": DISCOGS_TOKEN,
            "per_page": 5,
        }
        resp = requests.get(
            "https://api.discogs.com/database/search",
            params=params, headers=headers, timeout=15,
        )
        resp.raise_for_status()
        for r in resp.json().get("results", []):
            rid = r.get("id")
            if rid and rid not in release_ids:
                release_ids.append(rid)
        if release_ids:
            break

    if not release_ids:
        print("  Discogs : aucun résultat trouvé")
        return None

    # Collect all images from the top releases (max 3 releases to stay fast)
    candidates = []
    releases_info = {}
    for rid in release_ids[:3]:
        try:
            resp = requests.get(
                f"https://api.discogs.com/releases/{rid}",
                params={"token": DISCOGS_TOKEN},
                headers=headers, timeout=15,
            )
            resp.raise_for_status()
            release = resp.json()
            release_title = release.get("title", "?")
            # Extract label name and year
            labels = release.get("labels", [])
            label_name = labels[0].get("name", "") if labels else ""
            year = release.get("year", 0)
            releases_info[rid] = {"label": label_name, "year": year}
            for img_meta in release.get("images", []):
                url = img_meta.get("uri")
                if url:
                    candidates.append({
                        "url": url,
                        "meta": img_meta,
                        "release_title": release_title,
                        "release_id": rid,
                    })
        except Exception:
            continue

    if not candidates:
        print("  Discogs : releases trouvées mais aucune image")
        return None

    print(f"  Discogs : {len(candidates)} images candidates trouvées, analyse en cours...")

    # Download and score each candidate
    best_url = None
    best_score = -1
    best_info = ""
    best_release_id = None

    for c in candidates:
        try:
            resp = requests.get(c["url"], headers=headers, timeout=15)
            resp.raise_for_status()
            img_data = resp.content
            sc = _score_image(img_data, c["meta"])
            img_type = c["meta"].get("type", "?")
            print(f"    → {c['release_title']} [{img_type}] = score {sc:.1f}")
            if sc > best_score:
                best_score = sc
                best_url = c["url"]
                best_info = f"{c['release_title']} [{img_type}] (score {sc:.1f})"
                best_release_id = c["release_id"]
        except Exception:
            continue

    if best_url:
        print(f"  Discogs : meilleure image → {best_info}")
        info = releases_info.get(best_release_id, {})
        return {
            "image_url": best_url,
            "label": info.get("label", ""),
            "year": info.get("year", 0),
        }
    else:
        print("  Discogs : impossible de télécharger les images")
        return None


def search_discogs_all_images(artist, track, save_dir):
    """Search Discogs and return ALL candidate images saved to save_dir.

    Returns a list of dicts: {path, score, type, release_title, label, year}
    sorted by score descending (best first).
    """
    if DISCOGS_TOKEN == "YOUR_DISCOGS_TOKEN_HERE":
        return []

    headers = {"User-Agent": DISCOGS_USER_AGENT}

    # Strip remix/version info from track for broader Discogs search
    clean_track = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", track).strip()

    queries = [
        f"{artist} {clean_track}",
        f"{artist} {track}",
        clean_track,
    ]
    release_ids = []
    for q in queries:
        params = {
            "q": q, "type": "release",
            "token": DISCOGS_TOKEN, "per_page": 5,
        }
        resp = requests.get(
            "https://api.discogs.com/database/search",
            params=params, headers=headers, timeout=15,
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

    # Fetch releases and collect all images
    all_images = []
    idx = 0
    for rid in release_ids[:3]:
        try:
            resp = requests.get(
                f"https://api.discogs.com/releases/{rid}",
                params={"token": DISCOGS_TOKEN},
                headers=headers, timeout=15,
            )
            resp.raise_for_status()
            release = resp.json()
            release_title = release.get("title", "?")
            labels = release.get("labels", [])
            label_name = labels[0].get("name", "") if labels else ""
            year = release.get("year", 0)

            for img_meta in release.get("images", []):
                url = img_meta.get("uri")
                if not url:
                    continue
                try:
                    r = requests.get(url, headers=headers, timeout=15)
                    r.raise_for_status()
                    img_data = r.content
                    sc = _score_image(img_data, img_meta)
                    if sc < 0:
                        continue
                    # Save to disk
                    fname = f"candidate_{idx}.jpg"
                    fpath = os.path.join(save_dir, fname)
                    with open(fpath, "wb") as f:
                        f.write(img_data)
                    all_images.append({
                        "filename": fname,
                        "path": fpath,
                        "score": round(sc, 1),
                        "type": img_meta.get("type", "?"),
                        "release_title": release_title,
                        "label": label_name,
                        "year": year,
                    })
                    idx += 1
                except Exception:
                    continue
        except Exception:
            continue

    # Sort by score descending
    all_images.sort(key=lambda x: x["score"], reverse=True)
    return all_images


def download_image(url, path):
    """Download an image from a URL."""
    headers = {"User-Agent": DISCOGS_USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)
    return path


def make_vinyl_image(image_path, output_path):
    """Create a circular vinyl label centered on a black 1080x1920 canvas."""
    # Open and crop to square
    img = Image.open(image_path).convert("RGBA")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))

    # Resize to vinyl size
    img = img.resize((VINYL_SIZE, VINYL_SIZE), Image.LANCZOS)

    # Create circular mask
    mask = Image.new("L", (VINYL_SIZE, VINYL_SIZE), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, VINYL_SIZE - 1, VINYL_SIZE - 1), fill=255)

    # Apply mask
    vinyl = Image.new("RGBA", (VINYL_SIZE, VINYL_SIZE), (0, 0, 0, 0))
    vinyl.paste(img, (0, 0), mask)

    # Place on black canvas
    canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), BACKGROUND_COLOR)
    x = (CANVAS_WIDTH - VINYL_SIZE) // 2
    y = (CANVAS_HEIGHT - VINYL_SIZE) // 2
    canvas.paste(vinyl, (x, y), vinyl)

    canvas.save(output_path, "PNG")
    print(f"  Image vinyl : {output_path}")
    return output_path


def get_duration(audio_path):
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "json",
            audio_path,
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    duration = float(data["format"]["duration"])
    print(f"  Durée audio : {duration:.1f}s")
    return duration


def generate_slides(image_path, audio_path, output_dir, duration, start, count, prefix=""):
    """Generate video slides using ffmpeg."""
    total_duration = get_duration(audio_path)
    available = total_duration - start

    if available <= 0:
        print(f"Erreur : le point de départ ({start}s) dépasse la durée audio ({total_duration:.0f}s)")
        sys.exit(1)

    # Calculate segment duration
    total_needed = duration * count
    if available < total_needed:
        seg_duration = available / count
        print(f"  Audio trop court — segments ajustés à {seg_duration:.1f}s chacun")
    else:
        seg_duration = duration

    os.makedirs(output_dir, exist_ok=True)
    output_files = []

    for i in range(count):
        seg_start = start + i * seg_duration
        output_file = os.path.join(output_dir, f"{prefix}slide_{i + 1}.mp4")

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-loop", "1", "-i", image_path,
                "-ss", str(seg_start), "-i", audio_path,
                "-t", str(seg_duration),
                "-c:v", VIDEO_CODEC,
                "-tune", "stillimage",
                "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                "-r", str(VIDEO_FPS),
                "-pix_fmt", PIXEL_FORMAT,
                "-shortest",
                "-movflags", "+faststart",
                output_file,
            ],
            check=True,
        )
        output_files.append(output_file)
        print(f"  Slide {i + 1}/{count} : {output_file} ({seg_duration:.1f}s)")

    return output_files


def main():
    parser = argparse.ArgumentParser(
        description="Groove Candy Slide Maker — 1 lien YouTube → 3 slides vidéo Instagram"
    )
    parser.add_argument("url", help="Lien YouTube du morceau")
    parser.add_argument("--image", help="Image manuelle (skip Discogs)", default=None)
    parser.add_argument("--duration", type=float, default=SLIDE_DURATION,
                        help=f"Durée par slide en secondes (défaut: {SLIDE_DURATION})")
    parser.add_argument("--start", type=float, default=0,
                        help="Point de départ dans le morceau en secondes (défaut: 0)")
    parser.add_argument("--keep-temp", action="store_true",
                        help="Garder les fichiers temporaires")

    args = parser.parse_args()

    script_dir = Path(__file__).parent
    output_dir = script_dir / "output"
    output_dir.mkdir(exist_ok=True)

    temp_dir = tempfile.mkdtemp(prefix="groove_candy_")

    try:
        # 1. Parse YouTube metadata
        print("\n[1/5] Métadonnées YouTube...")
        meta = parse_youtube(args.url)

        # 2. Download audio
        print("\n[2/5] Téléchargement audio...")
        audio_path = download_audio(args.url, temp_dir)

        # 3. Get vinyl label image
        print("\n[3/5] Image du macaron...")
        vinyl_image_path = os.path.join(temp_dir, "vinyl.png")

        if args.image:
            # Manual image provided
            make_vinyl_image(args.image, vinyl_image_path)
        else:
            # Search Discogs
            discogs_result = search_discogs_label(meta["artist"], meta["track"])
            if discogs_result:
                raw_image = os.path.join(temp_dir, "label_raw.jpg")
                download_image(discogs_result["image_url"], raw_image)
                make_vinyl_image(raw_image, vinyl_image_path)

                # Show Instagram caption
                label_name = discogs_result.get("label", "")
                year = discogs_result.get("year", "")
                print(f"\n--- Caption Instagram ---")
                print(f"Artist: {meta['artist']}")
                print(f"Music: {meta['track']}")
                if label_name:
                    print(f"Label: {label_name}")
                if year:
                    print(f"Year: {year}")
                print(f"\n.\n.\n.")
                print(f"\n#deephouse #funkyhouse #chicagohouse #house #garagehouse")
                print(f"---")
            else:
                print("\nPas d'image trouvée sur Discogs.")
                print("Utilise --image <chemin> pour fournir une image manuellement.")
                sys.exit(1)

        # 4. Generate slides
        print("\n[4/5] Génération des slides...")
        slides = generate_slides(
            vinyl_image_path, audio_path, str(output_dir),
            args.duration, args.start, SLIDE_COUNT,
        )

        # 5. Done
        print(f"\n[5/5] Terminé !")
        print(f"\n{len(slides)} slides générées dans {output_dir}/")
        for s in slides:
            print(f"  → {s}")

    finally:
        # Cleanup temp files
        if not args.keep_temp:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            print("\nFichiers temporaires supprimés.")
        else:
            print(f"\nFichiers temporaires conservés dans : {temp_dir}")


if __name__ == "__main__":
    main()
