"""
Web interface and API for download_videos.py.

Run it locally with:
    python web_ui.py

Then open http://127.0.0.1:8000 (the browser opens automatically).

Run it as a server reachable by other devices (or on a host such as Render) with:
    python web_ui.py --host 0.0.0.0

Downloads happen on the server in a temporary folder and are then sent to the browser
as a regular file download, so they land on whatever device opened the page.

Environment variables:
    PORT              Port to listen on (overrides --port).
    ALLOWED_ORIGINS   Comma separated origins allowed to call the API (CORS), e.g.
                      "https://my-site.netlify.app". Defaults to "*".
    API_KEY           Optional password. When set, every API call must send it.
    FILE_TTL_MINUTES  How long finished files stay available for download (default 60).
    MAX_CONCURRENT    How many downloads run at the same time (default 2).
"""
import argparse
import json
import mimetypes
import os
import secrets
import shutil
import tempfile
import threading
import time
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import yt_dlp

from download_videos import AUDIO_FORMATS, VIDEO_FORMATS, download_youtube_videos, parse_timestamp

PUBLIC_DIR = Path(__file__).resolve().parent / "public"
STATIC_FILES = {"/": "index.html", "/index.html": "index.html", "/config.js": "config.js"}
WORK_DIR = Path(tempfile.gettempdir()) / "yt-downloader-jobs"

ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
API_KEY = os.environ.get("API_KEY", "")
FILE_TTL = int(os.environ.get("FILE_TTL_MINUTES", "60")) * 60
DOWNLOAD_SLOTS = threading.Semaphore(int(os.environ.get("MAX_CONCURRENT", "2")))

JOBS = {}
JOBS_LOCK = threading.Lock()


def update_job(job_id, **fields):
    with JOBS_LOCK:
        JOBS[job_id].update(fields)


def job_files(job_dir):
    """Finished files of a job, ignoring partial downloads and yt-dlp leftovers."""
    return sorted(
        p.name for p in job_dir.iterdir()
        if p.is_file() and not p.name.endswith((".part", ".ytdl", ".temp", ".zip", ".tmp"))
    )


def run_job(job_id, options):
    job_dir = WORK_DIR / job_id

    def hook(d):
        title = d.get("info_dict", {}).get("title") or os.path.basename(d.get("filename", ""))
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            percent = round(d["downloaded_bytes"] * 100 / total, 1) if total else None
            update_job(job_id, current=title, percent=percent)
        elif d["status"] == "finished":
            update_job(job_id, current=title, percent=100)

    with DOWNLOAD_SLOTS:
        update_job(job_id, status="running")
        try:
            failures = download_youtube_videos(
                options["videos"] or [options["url"]], output_dir=job_dir, progress_hooks=[hook],
                **{k: options[k] for k in ("file_format", "start", "end", "playlist")},
            )
            files = job_files(job_dir) if job_dir.exists() else []
            error = "; ".join(err for _, err in failures) or None
            if files:
                # Partial playlist failures still deliver the videos that worked
                update_job(job_id, status="done", percent=100, files=files, error=error)
            else:
                update_job(job_id, status="error", error=error or "Nenhum arquivo foi gerado.")
        except Exception as e:
            update_job(job_id, status="error", error=str(e))
        update_job(job_id, finished_at=time.time())


def cleanup_loop():
    """Forgets finished jobs and deletes their files once they are older than FILE_TTL."""
    while True:
        time.sleep(60)
        now = time.time()
        with JOBS_LOCK:
            expired = [jid for jid, job in JOBS.items() if job["finished_at"] and now - job["finished_at"] > FILE_TTL]
            for jid in expired:
                del JOBS[jid]
        for jid in expired:
            shutil.rmtree(WORK_DIR / jid, ignore_errors=True)


UNAVAILABLE_TITLES = ("[Private video]", "[Deleted video]")


def list_playlist(url):
    """Returns the playlist title and its videos (id, url, title, thumbnail, duration) without downloading."""
    opts = {"extract_flat": "in_playlist", "skip_download": True, "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") not in ("playlist", "multi_video"):
        raise ValueError("Esse link não é de uma playlist.")

    videos = []
    for entry in info.get("entries") or []:
        if not entry or not entry.get("id"):
            continue
        video_id = entry["id"]
        thumbnails = entry.get("thumbnails") or []
        title = entry.get("title") or video_id
        videos.append({
            "id": video_id,
            "url": entry.get("url") if str(entry.get("url", "")).startswith("http")
            else f"https://www.youtube.com/watch?v={video_id}",
            "title": title,
            "thumbnail": thumbnails[-1]["url"] if thumbnails else f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
            "duration": entry.get("duration"),
            "available": title not in UNAVAILABLE_TITLES,
        })
    return {"title": info.get("title") or "Playlist", "videos": videos}


def check_url(url):
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Informe um link válido (http:// ou https://).")
    return url


def validate(payload):
    url = check_url(payload.get("url"))
    videos = payload.get("videos") or []
    if not isinstance(videos, list):
        raise ValueError("Lista de vídeos inválida.")
    videos = [check_url(v) for v in videos]
    file_format = payload.get("format", "mp4")
    if file_format not in VIDEO_FORMATS + AUDIO_FORMATS:
        raise ValueError(f"Formato não suportado: {file_format}")
    try:
        start = parse_timestamp(payload.get("start"))
        end = parse_timestamp(payload.get("end"))
    except ValueError:
        raise ValueError("Use timestamps no formato hh:mm:ss, mm:ss ou segundos.")
    if start is not None and end is not None and end <= start:
        raise ValueError("O fim do trecho precisa ser depois do início.")
    return {
        "url": url,
        "file_format": file_format,
        "start": start,
        "end": end,
        "playlist": bool(payload.get("playlist")) and not videos,
        "videos": videos,
    }


def payload_label(options):
    count = len(options["videos"])
    if count:
        return f"{count} vídeo{'s' if count > 1 else ''} da playlist"
    return options["url"]


def public_job(job):
    return {k: job[k] for k in ("id", "url", "label", "format", "status", "percent", "current", "files", "error")}


def content_disposition(name):
    fallback = name.encode("ascii", "replace").decode().replace('"', "'").replace("?", "_")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"


class Handler(BaseHTTPRequestHandler):
    def cors_headers(self):
        origin = self.headers.get("Origin")
        if "*" in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Api-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, content_type, download_name=None):
        self.send_response(200)
        self.cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        if download_name:
            self.send_header("Content-Disposition", content_disposition(download_name))
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile, 1024 * 1024)

    def authorized(self, query):
        """Checks API_KEY, sent as the X-Api-Key header or, for file links, as ?key=."""
        if not API_KEY:
            return True
        given = self.headers.get("X-Api-Key") or query.get("key", [""])[0]
        if secrets.compare_digest(given.encode(), API_KEY.encode()):
            return True
        self.send_json(401, {"error": "Senha de acesso inválida.", "auth": True})
        return False

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors_headers()
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)

        if path in STATIC_FILES and (PUBLIC_DIR / STATIC_FILES[path]).exists():
            name = STATIC_FILES[path]
            self.send_file(PUBLIC_DIR / name, mimetypes.guess_type(name)[0] + "; charset=utf-8")
            return
        if path == "/api/health":
            self.send_json(200, {"ok": True, "auth": bool(API_KEY)})
            return
        if not path.startswith("/api/"):
            self.send_json(404, {"error": "Not found"})
            return
        if not self.authorized(query):
            return

        if path == "/api/jobs":
            # Each browser asks only for the jobs it created, so devices don't see each other's downloads
            ids = [i for i in ",".join(query.get("ids", [])).split(",") if i]
            with JOBS_LOCK:
                jobs = [public_job(JOBS[i]) for i in ids if i in JOBS]
            self.send_json(200, jobs)
            return

        # /api/jobs/<id>/files/<index> and /api/jobs/<id>/zip
        parts = path.strip("/").split("/")
        if len(parts) >= 4 and parts[:2] == ["api", "jobs"]:
            with JOBS_LOCK:
                job = JOBS.get(parts[2])
                job = dict(job) if job else None
            if not job or job["status"] != "done":
                self.send_json(404, {"error": "Arquivo não encontrado ou expirado."})
                return
            job_dir = WORK_DIR / job["id"]
            if parts[3] == "files" and len(parts) == 5 and parts[4].isdigit() and int(parts[4]) < len(job["files"]):
                name = job["files"][int(parts[4])]
                self.send_file(job_dir / name, "application/octet-stream", name)
                return
            if parts[3] == "zip" and len(parts) == 4:
                archive = job_dir / "videos.zip"
                if not archive.exists():
                    tmp = job_dir / f"videos-{secrets.token_hex(4)}.tmp"
                    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
                        for name in job["files"]:
                            zf.write(job_dir / name, name)
                    tmp.replace(archive)
                self.send_file(archive, "application/zip", "videos.zip")
                return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if not self.authorized(parse_qs(parsed.query)):
            return
        if parsed.path == "/api/playlist":
            try:
                url = check_url(self.read_json().get("url"))
                self.send_json(200, list_playlist(url))
            except (ValueError, json.JSONDecodeError) as e:
                self.send_json(400, {"error": str(e)})
            except Exception as e:
                self.send_json(502, {"error": f"Não foi possível ler a playlist: {e}"})
            return
        if parsed.path != "/api/download":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            options = validate(self.read_json())
        except (ValueError, json.JSONDecodeError) as e:
            self.send_json(400, {"error": str(e)})
            return

        job_id = secrets.token_hex(16)
        with JOBS_LOCK:
            JOBS[job_id] = {
                "id": job_id,
                "url": options["url"],
                "label": payload_label(options),
                "format": options["file_format"],
                "status": "queued",
                "percent": None,
                "current": "",
                "files": [],
                "error": None,
                "finished_at": None,
            }
        threading.Thread(target=run_job, args=(job_id, options), daemon=True).start()
        self.send_json(202, {"id": job_id})

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="Web interface and API for the YouTube downloader.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Address to listen on. Use 0.0.0.0 to accept other devices or when hosting it")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--no-browser", action="store_true", help="Don't open the browser automatically")
    args = parser.parse_args()

    shutil.rmtree(WORK_DIR, ignore_errors=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=cleanup_loop, daemon=True).start()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Interface disponível em {url} (Ctrl+C para sair)")
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"Aceitando conexões de outros dispositivos em {args.host}:{args.port}")
    elif not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
