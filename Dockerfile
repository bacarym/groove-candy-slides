FROM python:3.12-slim

# System deps: ffmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl unzip && \
    rm -rf /var/lib/apt/lists/*

# Install Deno (required by yt-dlp as JS runtime for YouTube extraction)
RUN curl -fsSL https://dl.deno.land/release/v2.2.11/deno-x86_64-unknown-linux-gnu.zip -o /tmp/deno.zip && \
    unzip /tmp/deno.zip -d /usr/local/bin/ && \
    chmod +x /usr/local/bin/deno && \
    rm /tmp/deno.zip

# Install yt-dlp with EJS component
RUN pip install --no-cache-dir "yt-dlp[default]"

# Python deps
WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt gunicorn

# App files
COPY app.py config.py groove_candy.py entrypoint.sh ./
COPY static/ static/
RUN chmod +x entrypoint.sh && mkdir -p output

EXPOSE 8080

ENTRYPOINT ["./entrypoint.sh"]
