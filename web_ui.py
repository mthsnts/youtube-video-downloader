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
        failures = download_youtube_videos([options["url"]], progress_hooks=[hook], **{
            k: options[k] for k in ("file_format", "start", "end", "playlist")
        })
        if failures:
            update_job(job_id, status="error", error="; ".join(err for _, err in failures))
        else:
            update_job(job_id, status="done", percent=100)
    except Exception as e:
        update_job(job_id, status="error", error=str(e))


def validate(payload):
    url = str(payload.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Informe um link válido (http:// ou https://).")
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
        "playlist": bool(payload.get("playlist")),
    }


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
  main { max-width: 640px; margin: 40px auto; padding: 0 16px; }
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
</style>
</head>
<body>
<main>
  <h1>YouTube Downloader</h1>
  <form id="form">
    <label for="url">Link do vídeo ou playlist</label>
    <input id="url" type="url" required placeholder="https://www.youtube.com/watch?v=...">
    <label class="check"><input id="playlist" type="checkbox"> Baixar a playlist inteira</label>

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
const STATUS = { running: "Baixando...", done: "Concluído", error: "Erro" };

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorEl.textContent = "";
  const button = document.getElementById("submit");
  button.disabled = true;
  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: document.getElementById("url").value,
        playlist: document.getElementById("playlist").checked,
        format: document.getElementById("format").value,
        start: document.getElementById("start").value,
        end: document.getElementById("end").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    document.getElementById("url").value = "";
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
      <div class="url">${escape(job.url)}</div>
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
