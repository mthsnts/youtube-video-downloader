// One server for everything: the API under /api and the React interface on every other path.
//   npm run dev    -> Vite middleware with hot reload
//   npm start      -> serves the built interface from dist/ (run `npm run build` first)
//
// Environment variables:
//   PORT              Port to listen on (default 8000).
//   API_KEY           Optional password. When set, every API call must send it.
//   FILE_TTL_MINUTES  How long finished files stay available for download (default 60).
//   MAX_CONCURRENT    How many downloads run at the same time (default 2).
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import archiver from "archiver";
import express from "express";
import { createJob, getJob, jobDir, publicJob, startCleanup } from "./jobs.js";
import { AUDIO_FORMATS, VIDEO_FORMATS, listPlaylist, parseTimestamp } from "./ytdlp.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const API_KEY = process.env.API_KEY || "";
const PORT = Number(process.env.PORT || 8000);
const DEV = process.argv.includes("--dev");

export function checkUrl(value) {
  const url = String(value ?? "").trim();
  if (!/^https?:\/\//i.test(url)) throw new Error("Informe um link válido (http:// ou https://).");
  return url;
}

export function validate(body) {
  const url = checkUrl(body.url);
  const videos = body.videos ?? [];
  if (!Array.isArray(videos)) throw new Error("Lista de vídeos inválida.");
  const format = body.format || "mp4";
  if (![...VIDEO_FORMATS, ...AUDIO_FORMATS].includes(format)) throw new Error(`Formato não suportado: ${format}`);
  let start, end;
  try {
    start = parseTimestamp(body.start);
    end = parseTimestamp(body.end);
  } catch {
    throw new Error("Use timestamps no formato hh:mm:ss, mm:ss ou segundos.");
  }
  if (start != null && end != null && end <= start) throw new Error("O fim do trecho precisa ser depois do início.");
  return { url, videos: videos.map(checkUrl), format, start, end };
}

/** Checks API_KEY, sent as the X-Api-Key header or, for file links, as ?key=. */
function auth(req, res, next) {
  if (!API_KEY) return next();
  const given = Buffer.from(String(req.get("X-Api-Key") || req.query.key || ""));
  const expected = Buffer.from(API_KEY);
  if (given.length === expected.length && crypto.timingSafeEqual(given, expected)) return next();
  res.status(401).json({ error: "Senha de acesso inválida.", auth: true });
}

function finishedJob(req, res) {
  const job = getJob(req.params.id);
  if (job && job.status === "done") return job;
  res.status(404).json({ error: "Arquivo não encontrado ou expirado." });
  return null;
}

export function createApi() {
  const api = express.Router();
  api.use(express.json({ limit: "1mb" }));

  api.get("/health", (req, res) => res.json({ ok: true, auth: Boolean(API_KEY) }));
  api.use(auth);

  api.post("/playlist", async (req, res) => {
    let url;
    try {
      url = checkUrl(req.body.url);
    } catch (err) {
      return res.status(400).json({ error: err.message });
    }
    try {
      res.json(await listPlaylist(url));
    } catch (err) {
      const notPlaylist = err.message === "Esse link não é de uma playlist.";
      res.status(notPlaylist ? 400 : 502).json({ error: notPlaylist ? err.message : `Não foi possível ler a playlist: ${err.message}` });
    }
  });

  api.post("/download", (req, res) => {
    let options;
    try {
      options = validate(req.body || {});
    } catch (err) {
      return res.status(400).json({ error: err.message });
    }
    res.status(202).json({ id: createJob(options).id });
  });

  // Each browser asks only for the jobs it created, so devices don't see each other's downloads
  api.get("/jobs", (req, res) => {
    const ids = String(req.query.ids || "").split(",").filter(Boolean);
    res.json(ids.map(getJob).filter(Boolean).map(publicJob));
  });

  api.get("/jobs/:id/files/:index", (req, res) => {
    const job = finishedJob(req, res);
    if (!job) return;
    const name = job.files[Number(req.params.index)];
    if (!/^\d+$/.test(req.params.index) || !name) return res.status(404).json({ error: "Arquivo não encontrado." });
    res.download(path.join(jobDir(job.id), name), name, { dotfiles: "allow" });
  });

  // Streams every file of the job as a .zip, without compressing (videos are already compressed)
  api.get("/jobs/:id/zip", (req, res) => {
    const job = finishedJob(req, res);
    if (!job) return;
    res.attachment("videos.zip");
    const zip = archiver("zip", { store: true });
    zip.on("error", () => res.destroy());
    zip.pipe(res);
    for (const name of job.files) zip.file(path.join(jobDir(job.id), name), { name });
    zip.finalize();
  });

  api.use((req, res) => res.status(404).json({ error: "Not found" }));
  return api;
}

async function main() {
  startCleanup();
  const app = express();
  app.disable("x-powered-by");
  app.use("/api", createApi());

  if (DEV) {
    const { createServer } = await import("vite");
    const vite = await createServer({ root: ROOT, server: { middlewareMode: true }, appType: "spa" });
    app.use(vite.middlewares);
  } else {
    const dist = path.join(ROOT, "dist");
    if (!fs.existsSync(path.join(dist, "index.html"))) {
      console.error("Interface não encontrada em dist/. Rode `npm run build` antes de `npm start`.");
      process.exit(1);
    }
    app.use(express.static(dist, { index: false, maxAge: "1h" }));
    app.get(/.*/, (req, res) => res.sendFile(path.join(dist, "index.html")));
  }

  app.listen(PORT, () => console.log(`Interface disponível em http://localhost:${PORT} (Ctrl+C para sair)`));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
