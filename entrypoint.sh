#!/bin/bash
set -e

# --- Write YouTube cookies from env var if provided ---
if [ -n "$YOUTUBE_COOKIES" ]; then
    echo "$YOUTUBE_COOKIES" > /app/cookies.txt
    echo "[COOKIES] YouTube cookies written to /app/cookies.txt"
else
    echo "[COOKIES] No YOUTUBE_COOKIES env var — yt-dlp will run without cookies"
    echo "[COOKIES] If YouTube blocks, export cookies with 'Get cookies.txt LOCALLY' browser extension"
fi

# --- Update yt-dlp to latest (YouTube breaks compat frequently) ---
echo "[YT-DLP] Updating to latest version..."
pip install -U "yt-dlp[default]" 2>&1 | tail -1
echo "[YT-DLP] Version: $(yt-dlp --version)"
echo "[YT-DLP] Deno: $(deno --version 2>&1 | head -1)"

# --- Start the app ---
echo "[APP] Starting Groove Candy on port 8080..."
cd /app
exec gunicorn -b 0.0.0.0:8080 -w 2 --timeout 300 app:app
