// Download jobs: each runs yt-dlp in its own temporary folder and keeps the files until FILE_TTL expires.
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { cleanYoutubeUrl, downloadVideo } from "./ytdlp.js";

export const WORK_DIR = path.join(os.tmpdir(), "yt-downloader-jobs");
const FILE_TTL = Number(process.env.FILE_TTL_MINUTES || 60) * 60 * 1000;
const MAX_CONCURRENT = Math.max(1, Number(process.env.MAX_CONCURRENT || 2));
const LEFTOVERS = /\.(part|ytdl|temp|tmp)$|\.part-Frag\d+/;

const jobs = new Map();
const queue = [];
let running = 0;

export function jobDir(id) {
  return path.join(WORK_DIR, id);
}

export function getJob(id) {
  return jobs.get(id);
}

export function publicJob(job) {
  const { id, url, label, format, status, percent, current, files, error } = job;
  return { id, url, label, format, status, percent, current, files, error };
}

/** Finished files of a job, ignoring partial downloads and yt-dlp leftovers. */
function finishedFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && !LEFTOVERS.test(entry.name))
    .map((entry) => entry.name)
    .sort();
}

export function createJob(options) {
  const id = crypto.randomBytes(16).toString("hex");
  const count = options.videos.length;
  const job = {
    id,
    url: options.url,
    label: count ? `${count} vídeo${count > 1 ? "s" : ""} da playlist` : options.url,
    format: options.format,
    status: "queued",
    percent: null,
    current: "",
    files: [],
    error: null,
    finishedAt: null,
    options,
  };
  jobs.set(id, job);
  queue.push(job);
  pump();
  return job;
}

function pump() {
  while (running < MAX_CONCURRENT && queue.length) {
    const job = queue.shift();
    running++;
    runJob(job).finally(() => {
      running--;
      pump();
    });
  }
}

async function runJob(job) {
  const { options } = job;
  const dir = jobDir(job.id);
  fs.mkdirSync(dir, { recursive: true });
  job.status = "running";
  const urls = options.videos.length ? options.videos : [cleanYoutubeUrl(options.url)];
  const failures = [];
  for (const url of urls) {
    try {
      await downloadVideo(url, { format: options.format, start: options.start, end: options.end, outDir: dir }, (p) => {
        if (p.title) job.current = p.title;
        job.percent = p.percent;
      });
    } catch (err) {
      failures.push(err.message);
    }
  }
  job.files = finishedFiles(dir);
  // Partial playlist failures still deliver the videos that worked
  job.error = failures.join("; ") || null;
  job.status = job.files.length ? "done" : "error";
  if (!job.files.length && !job.error) job.error = "Nenhum arquivo foi gerado.";
  if (job.status === "done") job.percent = 100;
  job.finishedAt = Date.now();
}

/** Forgets finished jobs and deletes their files once they are older than FILE_TTL. */
export function startCleanup() {
  fs.rmSync(WORK_DIR, { recursive: true, force: true });
  fs.mkdirSync(WORK_DIR, { recursive: true });
  setInterval(() => {
    const now = Date.now();
    for (const [id, job] of jobs) {
      if (job.finishedAt && now - job.finishedAt > FILE_TTL) {
        jobs.delete(id);
        fs.rmSync(jobDir(id), { recursive: true, force: true });
      }
    }
  }, 60 * 1000).unref();
}
