#!/bin/bash
set -e

WARP_DIR="/warp-config"
WARP_OK=false

# --- Try to set up WARP proxy ---
cd "$WARP_DIR"

if [ ! -f wgcf-account.toml ]; then
    echo "[WARP] Registering new account..."
    wgcf register --accept-tos || echo "[WARP] Registration failed, continuing without WARP"
fi

if [ -f wgcf-account.toml ] && [ ! -f wgcf-profile.conf ]; then
    echo "[WARP] Generating WireGuard profile..."
    wgcf generate || echo "[WARP] Profile generation failed"
fi

if [ -f wgcf-profile.conf ]; then
    echo "[WARP] Building wireproxy config..."
    grep -v "^Address.*:" wgcf-profile.conf > wireproxy.conf
    cat >> wireproxy.conf <<EOF

MTU = 1280

[Socks5]
BindAddress = 127.0.0.1:1080
EOF

    echo "[WARP] Starting wireproxy..."
    wireproxy -c "$WARP_DIR/wireproxy.conf" &

    for i in $(seq 1 10); do
        if curl -s --socks5 127.0.0.1:1080 https://cloudflare.com/cdn-cgi/trace 2>/dev/null | grep -q "warp=on"; then
            echo "[WARP] Connected!"
            WARP_OK=true
            break
        fi
        echo "[WARP] Waiting... ($i/10)"
        sleep 2
    done
fi

if [ "$WARP_OK" = true ]; then
    export WARP_PROXY="socks5://127.0.0.1:1080"
    echo "[WARP] Proxy enabled: $WARP_PROXY"
else
    echo "[WARP] Not available — yt-dlp will connect directly"
fi

# --- Update yt-dlp to latest (YouTube breaks compat frequently) ---
echo "[YT-DLP] Updating to latest version..."
pip install -U yt-dlp 2>&1 | tail -1
echo "[YT-DLP] Version: $(yt-dlp --version)"

# --- Start the app ---
echo "[APP] Starting Groove Candy on port 8080..."
cd /app
exec gunicorn -b 0.0.0.0:8080 -w 2 --timeout 300 app:app
