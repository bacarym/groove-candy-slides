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
# Runs in the background so the server answers immediately: with Railway
# Serverless the container restarts on every wake-up, and a blocking pip
# install there delayed (or 502'd) the first request. yt-dlp is called as a
# subprocess per job, so the next job picks up the updated binary.
(
  echo "[YT-DLP] Updating to latest version in background..."
  pip install -U "yt-dlp[default]" 2>&1 | tail -1
  echo "[YT-DLP] Version: $(yt-dlp --version)"
  echo "[YT-DLP] Deno: $(deno --version 2>&1 | head -1)"
) &

# --- Start the app ---
echo "[APP] Starting Groove Candy on port 8080..."
cd /app
exec gunicorn -b 0.0.0.0:8080 -w 1 --threads 4 --timeout 300 app:app
