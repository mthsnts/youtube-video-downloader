import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { decodeCookies, getCookiesPath, readCookieSource, setupCookies } from "../server/cookies.js";
import { downloadArgs, friendlyError } from "../server/ytdlp.js";

const COOKIES = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n";

test("decodeCookies accepts plain text or base64", () => {
  assert.equal(decodeCookies(COOKIES), COOKIES);
  assert.equal(decodeCookies(Buffer.from(COOKIES).toString("base64")), COOKIES);
  assert.equal(decodeCookies("  "), "");
});

test("readCookieSource prefers YT_COOKIES_FILE, then YT_COOKIES", () => {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "ck-")), "c.txt");
  fs.writeFileSync(file, "from file");
  assert.equal(readCookieSource({ YT_COOKIES_FILE: file, YT_COOKIES: COOKIES }), "from file");
  assert.equal(readCookieSource({ YT_COOKIES: COOKIES }), COOKIES);
});

test("setupCookies writes a private copy that yt-dlp gets with --cookies", () => {
  assert.equal(setupCookies({}), null);
  assert.ok(!downloadArgs("https://x/y", { format: "mp4", outDir: "/tmp/j" }).includes("--cookies"));

  const copy = setupCookies({ YT_COOKIES: COOKIES });
  assert.equal(getCookiesPath(), copy);
  assert.equal(fs.readFileSync(copy, "utf8"), COOKIES);
  assert.equal(fs.statSync(copy).mode & 0o777, 0o600);
  const args = downloadArgs("https://x/y", { format: "mp4", outDir: "/tmp/j" });
  assert.equal(args[args.indexOf("--cookies") + 1], copy);
  setupCookies({});
});

test("friendlyError explains YouTube's bot check", () => {
  const bot = "[youtube] abc: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies";
  assert.match(friendlyError(bot, false), /Configure cookies/);
  assert.match(friendlyError(bot, true), /expiraram/);
  assert.equal(friendlyError("HTTP Error 404", false), "HTTP Error 404");
});
