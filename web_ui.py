"""
Local web interface for download_videos.py.

Run it with:
    python web_ui.py

Then open http://127.0.0.1:8000 (the browser opens automatically).
"""
import argparse
import json
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yt_dlp

from download_videos import AUDIO_FORMATS, VIDEO_FORMATS, download_youtube_videos, parse_timestamp

JOBS = {}
JOBS_LOCK = threading.Lock()


def update_job(job_id, **fields):
    with JOBS_LOCK:
        JOBS[job_id].update(fields)


def run_job(job_id, options):
    def hook(d):
        filename = d.get("info_dict", {}).get("title") or d.get("filename", "")
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            percent = round(d["downloaded_bytes"] * 100 / total, 1) if total else None
            update_job(job_id, current=filename, percent=percent)
        elif d["status"] == "finished":
            with JOBS_LOCK:
                JOBS[job_id]["percent"] = 100
                if filename not in JOBS[job_id]["files"]:
                    JOBS[job_id]["files"].append(filename)

    try:
        failures = download_youtube_videos(options["videos"] or [options["url"]], progress_hooks=[hook], **{
            k: options[k] for k in ("file_format", "start", "end", "playlist")
        })
        if failures:
            update_job(job_id, status="error", error="; ".join(err for _, err in failures))
        else:
            update_job(job_id, status="done", percent=100)
    except Exception as e:
        update_job(job_id, status="error", error=str(e))


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


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/jobs":
            with JOBS_LOCK:
                jobs = [dict(job, files=list(job["files"])) for job in JOBS.values()]
            self.send_json(200, jobs[::-1])
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/api/playlist":
            try:
                length = int(self.headers.get("Content-Length", 0))
                url = check_url(json.loads(self.rfile.read(length) or b"{}").get("url"))
                self.send_json(200, list_playlist(url))
            except (ValueError, json.JSONDecodeError) as e:
                self.send_json(400, {"error": str(e)})
            except Exception as e:
                self.send_json(502, {"error": f"Não foi possível ler a playlist: {e}"})
            return
        if self.path != "/api/download":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            options = validate(json.loads(self.rfile.read(length) or b"{}"))
        except (ValueError, json.JSONDecodeError) as e:
            self.send_json(400, {"error": str(e)})
            return

        job_id = uuid.uuid4().hex[:8]
        with JOBS_LOCK:
            JOBS[job_id] = {
                "id": job_id,
                "url": options["url"],
                "label": payload_label(options),
                "format": options["file_format"],
                "status": "running",
                "percent": None,
                "current": "",
                "files": [],
                "error": None,
            }
        threading.Thread(target=run_job, args=(job_id, options), daemon=True).start()
        self.send_json(202, {"id": job_id})

    def log_message(self, format, *args):
        pass


PAGE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube Downloader</title>
<style>
  :root { --bg: #f5f5f7; --card: #fff; --text: #1d1d1f; --muted: #6e6e73; --accent: #d93025; --border: #d2d2d7; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #111; --card: #1c1c1e; --text: #f5f5f7; --muted: #a1a1a6; --accent: #ff453a; --border: #3a3a3c; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }
  main { max-width: 760px; margin: 40px auto; padding: 0 16px; }
  h1 { font-size: 1.5rem; margin-bottom: 24px; }
  form, .job { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
  label { display: block; font-size: .875rem; color: var(--muted); margin: 14px 0 6px; }
  input[type=text], input[type=url], select { width: 100%; padding: 10px 12px; font-size: 1rem; border: 1px solid var(--border); border-radius: 8px; background: transparent; color: var(--text); }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .check { display: flex; align-items: center; gap: 8px; margin-top: 14px; color: var(--text); font-size: .95rem; }
  button { margin-top: 20px; width: 100%; padding: 12px; font-size: 1rem; font-weight: 600; border: 0; border-radius: 8px; background: var(--accent); color: #fff; cursor: pointer; }
  button:disabled { opacity: .6; cursor: wait; }
  .hint { font-size: .8rem; color: var(--muted); margin-top: 6px; }
  .error { color: var(--accent); margin-top: 12px; min-height: 1em; }
  #jobs { margin-top: 24px; display: grid; gap: 12px; }
  .job { padding: 14px 16px; font-size: .9rem; }
  .job .url { word-break: break-all; color: var(--muted); }
  .bar { height: 6px; background: var(--border); border-radius: 3px; margin-top: 8px; overflow: hidden; }
  .bar div { height: 100%; background: var(--accent); transition: width .3s; }
  #playlist { margin-top: 16px; }
  #playlist[hidden] { display: none; }
  .pl-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin-bottom: 10px; }
  .pl-head strong { flex: 1 1 100%; }
  .pl-count { color: var(--muted); font-size: .875rem; flex: 1; }
  .link { margin: 0; width: auto; padding: 4px 8px; background: transparent; color: var(--accent); font-size: .875rem; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; max-height: 460px; overflow-y: auto; padding: 2px; }
  .card { position: relative; border: 2px solid var(--border); border-radius: 10px; overflow: hidden; cursor: pointer; background: var(--bg); margin: 0; color: var(--text); font-size: .85rem; }
  .card.selected { border-color: var(--accent); }
  .card.disabled { opacity: .45; cursor: not-allowed; }
  .card img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; background: var(--border); }
  .card input { position: absolute; top: 8px; left: 8px; width: 18px; height: 18px; accent-color: var(--accent); }
  .card .dur { position: absolute; top: 8px; right: 8px; background: rgba(0,0,0,.75); color: #fff; font-size: .75rem; padding: 1px 5px; border-radius: 4px; }
  .card .title { margin: 8px; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .loading { color: var(--muted); font-size: .9rem; }
</style>
</head>
<body>
<main>
  <h1>YouTube Downloader</h1>
  <form id="form">
    <label for="url">Link do vídeo ou playlist</label>
    <input id="url" type="url" required placeholder="https://www.youtube.com/watch?v=...">
    <div class="hint">Cole um link de playlist para escolher quais vídeos baixar.</div>
    <div id="playlist" hidden></div>

    <label for="format">Formato do arquivo</label>
    <select id="format">
      <optgroup label="Vídeo">
        <option value="mp4" selected>MP4</option>
        <option value="webm">WebM</option>
        <option value="mkv">MKV</option>
      </optgroup>
      <optgroup label="Somente áudio">
        <option value="mp3">MP3</option>
        <option value="m4a">M4A</option>
      </optgroup>
    </select>

    <div class="row">
      <div>
        <label for="start">Início (opcional)</label>
        <input id="start" type="text" placeholder="00:01:30">
      </div>
      <div>
        <label for="end">Fim (opcional)</label>
        <input id="end" type="text" placeholder="00:02:45">
      </div>
    </div>
    <div class="hint">Formato hh:mm:ss, mm:ss ou segundos. Deixe em branco para baixar o vídeo completo.</div>

    <button id="submit" type="submit">Baixar</button>
    <div class="error" id="error"></div>
  </form>
  <div id="jobs"></div>
</main>
<script>
const form = document.getElementById("form");
const errorEl = document.getElementById("error");
const jobsEl = document.getElementById("jobs");
const urlEl = document.getElementById("url");
const playlistEl = document.getElementById("playlist");
const STATUS = { running: "Baixando...", done: "Concluído", error: "Erro" };
let playlist = null;      // { title, videos } of the loaded playlist
let selected = new Set(); // ids of the selected videos
let loadedUrl = "";
let loadToken = 0;

function playlistUrl(value) {
  try {
    const u = new URL(value.trim());
    return u.searchParams.get("list") ? u.href : null;
  } catch { return null; }
}

function fmtDuration(sec) {
  if (sec == null) return "";
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
  const mm = h ? String(m).padStart(2, "0") : m;
  return (h ? h + ":" : "") + mm + ":" + String(s).padStart(2, "0");
}

async function loadPlaylist() {
  const url = playlistUrl(urlEl.value);
  if (url === loadedUrl) return;
  loadedUrl = url;
  playlist = null;
  selected = new Set();
  const token = ++loadToken;
  if (!url) { playlistEl.hidden = true; playlistEl.innerHTML = ""; return; }
  playlistEl.hidden = false;
  playlistEl.innerHTML = '<div class="loading">Carregando vídeos da playlist...</div>';
  try {
    const res = await fetch("/api/playlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (token !== loadToken) return;
    if (!res.ok) throw new Error(data.error);
    playlist = data;
    // A watch link inside a playlist preselects just that video; a playlist link selects everything
    const current = new URL(url).searchParams.get("v");
    const available = data.videos.filter((v) => v.available);
    const preselect = current && available.some((v) => v.id === current) ? [current] : available.map((v) => v.id);
    selected = new Set(preselect);
    renderPlaylist();
  } catch (err) {
    if (token !== loadToken) return;
    playlistEl.innerHTML = '<div class="error">' + escape(err.message) + "</div>";
  }
}

function renderPlaylist() {
  playlistEl.innerHTML = `<div class="pl-head">
      <strong>${escape(playlist.title)}</strong>
      <span class="pl-count" id="pl-count"></span>
      <button type="button" class="link" data-select="all">Selecionar todos</button>
      <button type="button" class="link" data-select="none">Nenhum</button>
    </div>
    <div class="cards">${playlist.videos.map((v) => `
      <label class="card${v.available ? "" : " disabled"}" data-id="${escape(v.id)}">
        <img src="${escape(v.thumbnail)}" alt="" loading="lazy">
        <input type="checkbox" ${v.available ? "" : "disabled"}>
        ${v.duration ? `<span class="dur">${fmtDuration(v.duration)}</span>` : ""}
        <div class="title" title="${escape(v.title)}">${escape(v.title)}</div>
      </label>`).join("")}
    </div>`;
  syncSelection();
}

function syncSelection() {
  playlistEl.querySelectorAll(".card").forEach((card) => {
    const on = selected.has(card.dataset.id);
    card.classList.toggle("selected", on);
    card.querySelector("input").checked = on;
  });
  const count = playlistEl.querySelector("#pl-count");
  if (count) count.textContent = selected.size + " de " + playlist.videos.length + " selecionados";
}

playlistEl.addEventListener("change", (e) => {
  const card = e.target.closest(".card");
  if (!card) return;
  if (e.target.checked) selected.add(card.dataset.id); else selected.delete(card.dataset.id);
  syncSelection();
});

playlistEl.addEventListener("click", (e) => {
  const mode = e.target.dataset && e.target.dataset.select;
  if (!mode || !playlist) return;
  selected = new Set(mode === "all" ? playlist.videos.filter((v) => v.available).map((v) => v.id) : []);
  syncSelection();
});

let debounce;
urlEl.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(loadPlaylist, 400); });

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorEl.textContent = "";
  if (playlistUrl(urlEl.value) && !playlist) {
    errorEl.textContent = "Aguarde a lista de vídeos da playlist carregar.";
    return;
  }
  const videos = playlist ? playlist.videos.filter((v) => selected.has(v.id)).map((v) => v.url) : [];
  if (playlist && !videos.length) {
    errorEl.textContent = "Selecione pelo menos um vídeo da playlist.";
    return;
  }
  const button = document.getElementById("submit");
  button.disabled = true;
  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: urlEl.value,
        videos,
        format: document.getElementById("format").value,
        start: document.getElementById("start").value,
        end: document.getElementById("end").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    urlEl.value = "";
    loadPlaylist();
    refresh();
  } catch (err) {
    errorEl.textContent = err.message;
  } finally {
    button.disabled = false;
  }
});

function escape(s) {
  const div = document.createElement("div");
  div.textContent = s == null ? "" : String(s);
  return div.innerHTML;
}

async function refresh() {
  const jobs = await (await fetch("/api/jobs")).json();
  jobsEl.innerHTML = jobs.map((job) => {
    const pct = job.percent == null ? 0 : job.percent;
    const detail = job.status === "error" ? escape(job.error)
      : job.status === "done" ? escape(job.files.join(", "))
      : escape(job.current) + (job.percent == null ? "" : " (" + pct + "%)");
    return `<div class="job">
      <strong>${STATUS[job.status]}</strong> · ${escape(job.format.toUpperCase())}
      <div class="url">${escape(job.label || job.url)}</div>
      <div>${detail}</div>
      ${job.status === "running" ? `<div class="bar"><div style="width:${pct}%"></div></div>` : ""}
    </div>`;
  }).join("");
}

setInterval(refresh, 1000);
refresh();
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Local web interface for the YouTube downloader.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="Don't open the browser automatically")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Interface disponível em {url} (Ctrl+C para sair)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
