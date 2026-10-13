// Builds yt-dlp commands and runs them as child processes. yt-dlp and ffmpeg must be on the PATH
// (the Dockerfile installs both); YTDLP_PATH points to another yt-dlp binary.
import { spawn } from "node:child_process";

export const YTDLP = process.env.YTDLP_PATH || "yt-dlp";
export const VIDEO_FORMATS = ["mp4", "webm", "mkv"];
export const AUDIO_FORMATS = ["mp3", "m4a"];

const UNAVAILABLE_TITLES = new Set(["[Private video]", "[Deleted video]"]);
const PROGRESS_PREFIX = "@@progress ";

// yt-dlp needs a JavaScript runtime to solve YouTube's challenges; Node is already here, so use it.
const COMMON_ARGS = ["--js-runtimes", "node", "--no-warnings", "--no-color"];

/** Converts "90", "1:30" or "01:02:03.5" into seconds. Returns null when empty, throws when invalid. */
export function parseTimestamp(value) {
  if (value == null) return null;
  const text = String(value).trim();
  if (!text) return null;
  const parts = text.split(":");
  if (parts.length > 3 || parts.some((p) => !/^\d+(\.\d+)?$/.test(p.trim()))) {
    throw new Error(`Invalid timestamp: ${text}`);
  }
  return parts.reduce((total, p) => total * 60 + Number(p), 0);
}

/**
 * Strips playlist/radio parameters (&list=RD..., &index=...) from single YouTube video links,
 * which often make YouTube answer "This video is not available".
 */
export function cleanYoutubeUrl(url) {
  try {
    const parsed = new URL(url);
    const id = parsed.searchParams.get("v");
    if (/(^|\.)youtube\.com$/.test(parsed.hostname) && id) return `https://www.youtube.com/watch?v=${id}`;
  } catch {}
  return url;
}

function formatArgs(format) {
  switch (format) {
    case "mp3":
    case "m4a":
      return ["-f", "bestaudio/best", "-x", "--audio-format", format, "--audio-quality", "0"];
    case "mp4":
      return ["-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b", "--merge-output-format", "mp4"];
    case "webm":
      // Re-encodes only when the source has no webm streams
      return ["-f", "bv*[ext=webm]+ba[ext=webm]/b[ext=webm]/bv*+ba/b", "--merge-output-format", "webm", "--recode-video", "webm"];
    case "mkv":
      return ["-f", "bv*+ba/b", "--merge-output-format", "mkv", "--remux-video", "mkv"];
    default:
      throw new Error(`Unsupported format: ${format}`);
  }
}

/** Arguments to download one video into outDir with the chosen format and optional segment. */
export function downloadArgs(url, { format, start = null, end = null, outDir, playerClients = null }) {
  const trimming = start != null || end != null;
  const name = trimming ? "%(title)s [%(section_start)s-%(section_end)s].%(ext)s" : "%(title)s.%(ext)s";
  const args = [
    ...COMMON_ARGS,
    "--no-playlist",
    "--newline",
    "--windows-filenames",
    "--progress-template",
    `download:${PROGRESS_PREFIX}%(progress.downloaded_bytes)s %(progress.total_bytes)s %(progress.total_bytes_estimate)s %(info.title)s`,
    "-P", outDir,
    "-o", name,
    ...formatArgs(format),
  ];
  if (trimming) {
    args.push("--download-sections", `*${start ?? 0}-${end ?? "inf"}`, "--force-keyframes-at-cuts");
  }
  if (playerClients) args.push("--extractor-args", `youtube:player_client=${playerClients}`);
  args.push("--", url);
  return args;
}

/** Reads a progress line printed through --progress-template. */
export function parseProgress(line) {
  if (!line.startsWith(PROGRESS_PREFIX)) return null;
  const [downloaded, total, estimate, ...title] = line.slice(PROGRESS_PREFIX.length).split(" ");
  const done = Number(downloaded);
  const size = Number(total) || Number(estimate);
  return {
    title: title.join(" ") === "NA" ? "" : title.join(" "),
    percent: done >= 0 && size > 0 ? Math.min(100, Math.round((done * 1000) / size) / 10) : null,
  };
}

/** Runs yt-dlp; resolves with stdout, rejects with the last error line. onLine gets each stdout line. */
export function runYtdlp(args, { onLine, signal } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(YTDLP, args, { stdio: ["ignore", "pipe", "pipe"], signal });
    let stdout = "";
    let stderr = "";
    let buffer = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
      if (!onLine) return;
      buffer += chunk;
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop();
      lines.forEach(onLine);
    });
    child.stderr.on("data", (chunk) => {
      stderr = (stderr + chunk).slice(-8000);
    });
    child.on("error", (err) => {
      reject(err.code === "ENOENT" ? new Error("yt-dlp não está instalado no servidor.") : err);
    });
    child.on("close", (code) => {
      if (code === 0) return resolve(stdout);
      const errors = stderr.split("\n").filter((l) => l.startsWith("ERROR:"));
      const message = (errors.pop() || stderr.trim().split("\n").pop() || `yt-dlp saiu com código ${code}`)
        .replace(/^ERROR:\s*/, "");
      reject(new Error(message));
    });
  });
}

/**
 * Downloads one video. When YouTube reports it as unavailable with the default player,
 * retries once with alternative player clients.
 */
export async function downloadVideo(url, options, onProgress) {
  const onLine = (line) => {
    const progress = parseProgress(line);
    if (progress) onProgress(progress);
  };
  try {
    await runYtdlp(downloadArgs(url, options), { onLine });
  } catch (err) {
    if (!/not available|unavailable/i.test(err.message)) throw err;
    await runYtdlp(downloadArgs(url, { ...options, playerClients: "ios,android" }), { onLine });
  }
}

/** Lists a playlist's videos (id, url, title, thumbnail, duration) without downloading them. */
export async function listPlaylist(url) {
  const output = await runYtdlp([...COMMON_ARGS, "--flat-playlist", "--yes-playlist", "-J", "--", url]);
  return playlistFromInfo(JSON.parse(output));
}

export function playlistFromInfo(info) {
  if (!["playlist", "multi_video"].includes(info._type)) throw new Error("Esse link não é de uma playlist.");
  const videos = (info.entries || [])
    .filter((entry) => entry && entry.id)
    .map((entry) => {
      const thumbnails = entry.thumbnails || [];
      const title = entry.title || entry.id;
      return {
        id: entry.id,
        url: /^https?:\/\//.test(entry.url || "") ? entry.url : `https://www.youtube.com/watch?v=${entry.id}`,
        title,
        thumbnail: thumbnails.length ? thumbnails[thumbnails.length - 1].url : `https://i.ytimg.com/vi/${entry.id}/mqdefault.jpg`,
        duration: entry.duration ?? null,
        available: !UNAVAILABLE_TITLES.has(title),
      };
    });
  return { title: info.title || "Playlist", videos };
}
