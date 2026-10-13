// YouTube cookies for yt-dlp. Servers in datacenters (Render, Railway...) are often asked to
// "Sign in to confirm you're not a bot"; cookies from a logged-in account get past that check.
//
// Sources, first match wins:
//   YT_COOKIES_FILE   Path to a cookies.txt file (Netscape format).
//   YT_COOKIES        The cookies.txt content itself, as plain text or base64.
//   /etc/secrets/cookies.txt   Where a Render Secret File named cookies.txt is mounted.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const RENDER_SECRET = "/etc/secrets/cookies.txt";

/** Returns the cookies.txt content from the environment, or "" when none is configured. */
export function readCookieSource(env = process.env) {
  if (env.YT_COOKIES_FILE) return fs.readFileSync(env.YT_COOKIES_FILE, "utf8");
  if (env.YT_COOKIES) return decodeCookies(env.YT_COOKIES);
  if (fs.existsSync(RENDER_SECRET)) return fs.readFileSync(RENDER_SECRET, "utf8");
  return "";
}

/** Accepts the file content as is, or base64 of it (handy where values can't hold line breaks). */
export function decodeCookies(value) {
  const text = value.trim();
  if (!text || /\t/.test(text) || text.startsWith("#")) return text ? `${text}\n` : "";
  const decoded = Buffer.from(text, "base64").toString("utf8");
  return /\t/.test(decoded) ? decoded : `${text}\n`;
}

let cookiesPath = null;

/**
 * Copies the configured cookies to a writable temporary file, because yt-dlp saves refreshed
 * cookies back into the file it was given (Render Secret Files are read-only).
 * Returns the path to pass to --cookies, or null when no cookies are configured.
 */
export function setupCookies(env = process.env) {
  let content;
  try {
    content = readCookieSource(env);
  } catch (err) {
    console.error(`Não foi possível ler os cookies do YouTube: ${err.message}`);
    return (cookiesPath = null);
  }
  if (!content.trim()) return (cookiesPath = null);
  if (!/youtube\.com/.test(content)) {
    console.warn("Os cookies configurados não têm nenhum cookie do youtube.com.");
  }
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "yt-cookies-"));
  cookiesPath = path.join(dir, "cookies.txt");
  fs.writeFileSync(cookiesPath, content, { mode: 0o600 });
  console.log("Usando cookies do YouTube.");
  return cookiesPath;
}

export function getCookiesPath() {
  return cookiesPath;
}
