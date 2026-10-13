import { useEffect, useRef, useState } from "react";
import { api, fileUrl } from "./api.js";
import JobList from "./components/JobList.jsx";
import PlaylistPicker from "./components/PlaylistPicker.jsx";
import { storeGet, storeSet } from "./storage.js";

function playlistUrl(value) {
  try {
    const url = new URL(value.trim());
    return url.searchParams.get("list") ? url.href : null;
  } catch {
    return null;
  }
}

/** Sends a finished file to the device through a normal browser download. */
function saveToDevice(href) {
  const a = document.createElement("a");
  a.href = href;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export default function App() {
  const [url, setUrl] = useState("");
  const [format, setFormat] = useState("mp4");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  // { loading } while the cards load, { error } when they fail, { data } once loaded
  const [playlist, setPlaylist] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [jobs, setJobs] = useState([]);
  const [offline, setOffline] = useState("");
  const myJobs = useRef(storeGet("jobs", [])); // ids of this browser's downloads, newest first
  const saved = useRef(new Set(storeGet("saved", []))); // ids already sent to the device

  // Loads the playlist cards whenever the link contains a playlist
  const listUrl = playlistUrl(url);
  useEffect(() => {
    setSelected(new Set());
    if (!listUrl) {
      setPlaylist(null);
      return;
    }
    let cancelled = false;
    setPlaylist({ loading: true });
    const timer = setTimeout(async () => {
      try {
        const data = await api("/api/playlist", { url: listUrl });
        if (cancelled) return;
        // A watch link inside a playlist preselects just that video; a playlist link selects everything
        const current = new URL(listUrl).searchParams.get("v");
        const available = data.videos.filter((v) => v.available);
        setSelected(new Set(current && available.some((v) => v.id === current) ? [current] : available.map((v) => v.id)));
        setPlaylist({ data });
      } catch (err) {
        if (!cancelled) setPlaylist({ error: err.message });
      }
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [listUrl]);

  async function refresh() {
    let list = [];
    if (myJobs.current.length) {
      try {
        list = await api(`/api/jobs?ids=${myJobs.current.join(",")}`, null, { askKey: false });
      } catch (err) {
        setOffline(err.message);
        return;
      }
      // Forget downloads the server already deleted
      const known = new Set(list.map((j) => j.id));
      myJobs.current = myJobs.current.filter((id) => known.has(id));
      storeSet("jobs", myJobs.current);
    }
    list.sort((a, b) => myJobs.current.indexOf(a.id) - myJobs.current.indexOf(b.id));

    // A single finished file goes straight to the device; playlists get a button per file and a .zip
    for (const job of list) {
      if (job.status === "done" && !saved.current.has(job.id)) {
        saved.current.add(job.id);
        if (job.files.length === 1) saveToDevice(fileUrl(job.id, "/files/0"));
      }
    }
    saved.current = new Set([...saved.current].filter((id) => myJobs.current.includes(id)));
    storeSet("saved", [...saved.current]);
    setOffline("");
    setJobs(list);
  }

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 1000);
    return () => clearInterval(timer);
  }, []);

  async function submit(e) {
    e.preventDefault();
    setError("");
    const data = playlist?.data;
    if (listUrl && !data) {
      setError(playlist?.error ? "Não foi possível carregar a playlist." : "Aguarde a lista de vídeos da playlist carregar.");
      return;
    }
    const videos = data ? data.videos.filter((v) => selected.has(v.id)).map((v) => v.url) : [];
    if (data && !videos.length) {
      setError("Selecione pelo menos um vídeo da playlist.");
      return;
    }
    setSubmitting(true);
    try {
      const job = await api("/api/download", { url, videos, format, start, end });
      myJobs.current = [job.id, ...myJobs.current];
      storeSet("jobs", myJobs.current);
      setUrl("");
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main>
      <h1>YouTube Downloader</h1>
      <form onSubmit={submit}>
        <label htmlFor="url">Link do vídeo ou playlist</label>
        <input
          id="url"
          type="url"
          required
          placeholder="https://www.youtube.com/watch?v=..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <div className="hint">Cole um link de playlist para escolher quais vídeos baixar.</div>
        {playlist?.loading ? <div className="loading">Carregando vídeos da playlist...</div> : null}
        {playlist?.error ? <div className="error">{playlist.error}</div> : null}
        {playlist?.data ? <PlaylistPicker playlist={playlist.data} selected={selected} onChange={setSelected} /> : null}

        <label htmlFor="format">Formato do arquivo</label>
        <select id="format" value={format} onChange={(e) => setFormat(e.target.value)}>
          <optgroup label="Vídeo">
            <option value="mp4">MP4</option>
            <option value="webm">WebM</option>
            <option value="mkv">MKV</option>
          </optgroup>
          <optgroup label="Somente áudio">
            <option value="mp3">MP3</option>
            <option value="m4a">M4A</option>
          </optgroup>
        </select>

        <div className="row">
          <div>
            <label htmlFor="start">Início (opcional)</label>
            <input id="start" type="text" placeholder="00:01:30" value={start} onChange={(e) => setStart(e.target.value)} />
          </div>
          <div>
            <label htmlFor="end">Fim (opcional)</label>
            <input id="end" type="text" placeholder="00:02:45" value={end} onChange={(e) => setEnd(e.target.value)} />
          </div>
        </div>
        <div className="hint">Formato hh:mm:ss, mm:ss ou segundos. Deixe em branco para baixar o vídeo completo.</div>

        <button type="submit" disabled={submitting}>
          Baixar
        </button>
        <div className="error">{error}</div>
      </form>
      <div className="jobs">
        <JobList jobs={jobs} offline={offline} />
      </div>
    </main>
  );
}
