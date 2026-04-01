#!/bin/bash
set -e

WARP_DIR="/warp-config"
WARP_OK=false

# --- Try to set up WARP proxy ---
cd "$WARP_DIR"

if [ ! -f wgcf-account.toml ]; then
    echo "[WARP] Registering new account..."
    if wgcf register --accept-tos 2>&1; then
        echo "[WARP] Registration OK"
    else
        echo "[WARP] Registration FAILED"
        cat wgcf-account.toml 2>/dev/null || true
    fi
fi

if [ -f wgcf-account.toml ] && [ ! -f wgcf-profile.conf ]; then
    echo "[WARP] Generating WireGuard profile..."
    if wgcf generate 2>&1; then
        echo "[WARP] Profile OK"
    else
        echo "[WARP] Profile generation FAILED"
    fi
fi

if [ -f wgcf-profile.conf ]; then
    echo "[WARP] Profile content:"
    cat wgcf-profile.conf

    echo "[WARP] Building wireproxy config..."
    # Remove IPv6 addresses (not supported on all Railway hosts)
    grep -v "^Address.*:" wgcf-profile.conf > wireproxy.conf
    # Also remove IPv6 DNS and AllowedIPs with :
    sed -i '/^DNS.*:/d' wireproxy.conf

    cat >> wireproxy.conf <<EOF

MTU = 1280

[Socks5]
BindAddress = 127.0.0.1:1080
EOF

    echo "[WARP] wireproxy config:"
    cat wireproxy.conf

    echo "[WARP] Starting wireproxy..."
    wireproxy -c "$WARP_DIR/wireproxy.conf" &
    WIREPROXY_PID=$!
    sleep 3

    # Check if wireproxy is still running
    if kill -0 $WIREPROXY_PID 2>/dev/null; then
        echo "[WARP] wireproxy running (PID $WIREPROXY_PID)"
    else
        echo "[WARP] wireproxy CRASHED"
        wait $WIREPROXY_PID 2>/dev/null || true
    fi

    for i in $(seq 1 15); do
        if curl -s -m 5 --socks5 127.0.0.1:1080 https://cloudflare.com/cdn-cgi/trace 2>/dev/null | grep -q "warp=on"; then
            echo "[WARP] Connected!"
            WARP_OK=true
            break
        fi
        echo "[WARP] Waiting... ($i/15)"
        sleep 2
    done

    if [ "$WARP_OK" = false ]; then
        echo "[WARP] Connection check failed. Trying without warp=on check..."
        if curl -s -m 5 --socks5 127.0.0.1:1080 https://www.youtube.com 2>/dev/null | grep -q "youtube"; then
            echo "[WARP] Proxy is working (YouTube reachable)!"
            WARP_OK=true
        else
            echo "[WARP] Proxy not working at all"
            curl -v --socks5 127.0.0.1:1080 https://cloudflare.com/cdn-cgi/trace 2>&1 | tail -5 || true
        fi
    fi
else
    echo "[WARP] No wgcf-profile.conf generated — skipping proxy"
fi

if [ "$WARP_OK" = true ]; then
    export WARP_PROXY="socks5://127.0.0.1:1080"
    echo "[WARP] Proxy enabled: $WARP_PROXY"
else
    echo "[WARP] Not available — yt-dlp will connect directly (YouTube may block)"
fi

# --- Update yt-dlp to latest (YouTube breaks compat frequently) ---
echo "[YT-DLP] Updating to latest version..."
pip install -U "yt-dlp[default]" 2>&1 | tail -1
echo "[YT-DLP] Version: $(yt-dlp --version)"
echo "[YT-DLP] Deno: $(deno --version 2>&1 | head -1)"

# --- Quick yt-dlp test ---
echo "[TEST] Testing yt-dlp with a short video..."
if yt-dlp --dump-json --no-playlist ${WARP_PROXY:+--proxy "$WARP_PROXY"} "https://www.youtube.com/watch?v=jNQXAC9IVRw" 2>&1 | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'[TEST] OK: {d[\"title\"]}')" 2>/dev/null; then
    echo "[TEST] yt-dlp works!"
else
    echo "[TEST] yt-dlp FAILED — YouTube may be blocking this IP"
fi

# --- Start the app ---
echo "[APP] Starting Groove Candy on port 8080..."
cd /app
exec gunicorn -b 0.0.0.0:8080 -w 2 --timeout 300 app:app
