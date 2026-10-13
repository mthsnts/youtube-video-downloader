# Backend (web_ui.py) with yt-dlp and ffmpeg, ready for Render, Railway, Fly.io or any Docker host.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -U -r requirements.txt
COPY download_videos.py web_ui.py ./
COPY public ./public

ENV PORT=8000
EXPOSE 8000
CMD ["python", "web_ui.py", "--host", "0.0.0.0", "--no-browser"]
