FROM python:3.12-slim

# System deps: ffmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

# Install yt-dlp
RUN pip install --no-cache-dir yt-dlp

# Install wgcf + wireproxy (Cloudflare WARP fallback if YouTube blocks Railway IPs)
RUN curl -L https://github.com/ViRb3/wgcf/releases/download/v2.2.30/wgcf_2.2.30_linux_amd64 \
    -o /usr/local/bin/wgcf && chmod +x /usr/local/bin/wgcf
RUN curl -L https://github.com/pufferffish/wireproxy/releases/download/v1.0.9/wireproxy_linux_amd64.tar.gz \
    | tar xz -C /usr/local/bin/

# Python deps
WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt gunicorn

# App files
COPY app.py config.py groove_candy.py entrypoint.sh ./
COPY static/ static/
RUN chmod +x entrypoint.sh && mkdir -p output /warp-config

EXPOSE 8080

ENTRYPOINT ["./entrypoint.sh"]
