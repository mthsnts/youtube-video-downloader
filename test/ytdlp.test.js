import assert from "node:assert/strict";
import { test } from "node:test";
import { validate } from "../server/index.js";
import { cleanYoutubeUrl, downloadArgs, parseProgress, parseTimestamp, playlistFromInfo } from "../server/ytdlp.js";

test("parseTimestamp accepts seconds, mm:ss and hh:mm:ss", () => {
  assert.equal(parseTimestamp(""), null);
  assert.equal(parseTimestamp(null), null);
  assert.equal(parseTimestamp("90"), 90);
  assert.equal(parseTimestamp("1:30"), 90);
  assert.equal(parseTimestamp("01:02:03.5"), 3723.5);
  assert.throws(() => parseTimestamp("abc"));
  assert.throws(() => parseTimestamp("1:2:3:4"));
  assert.throws(() => parseTimestamp("-5"));
});

test("cleanYoutubeUrl drops playlist parameters from single videos", () => {
  assert.equal(cleanYoutubeUrl("https://www.youtube.com/watch?v=abc&list=RDabc&index=2"), "https://www.youtube.com/watch?v=abc");
  assert.equal(cleanYoutubeUrl("https://vimeo.com/123"), "https://vimeo.com/123");
});

test("downloadArgs picks the format and the segment", () => {
  const audio = downloadArgs("https://x/y", { format: "mp3", outDir: "/tmp/j" });
  assert.deepEqual(audio.slice(audio.indexOf("-x"), audio.indexOf("-x") + 3), ["-x", "--audio-format", "mp3"]);
  assert.equal(audio.at(-1), "https://x/y");
  assert.ok(!audio.includes("--download-sections"));

  const clip = downloadArgs("https://x/y", { format: "mp4", start: 30, end: null, outDir: "/tmp/j" });
  assert.equal(clip[clip.indexOf("--download-sections") + 1], "*30-inf");
  assert.match(clip[clip.indexOf("-o") + 1], /section_start/);
  assert.throws(() => downloadArgs("https://x/y", { format: "avi", outDir: "/tmp/j" }));
});

test("parseProgress reads the progress template", () => {
  assert.deepEqual(parseProgress("@@progress 50 200 NA My video"), { title: "My video", percent: 25 });
  assert.deepEqual(parseProgress("@@progress 50 NA 100 Clip"), { title: "Clip", percent: 50 });
  assert.equal(parseProgress("@@progress NA NA NA NA").percent, null);
  assert.equal(parseProgress("[download] Destination: x.mp4"), null);
});

test("playlistFromInfo builds the cards and flags unavailable videos", () => {
  const list = playlistFromInfo({
    _type: "playlist",
    title: "Mix",
    entries: [
      { id: "a1", title: "First", duration: 61, thumbnails: [{ url: "s" }, { url: "big" }] },
      { id: "b2", title: "[Private video]" },
      null,
    ],
  });
  assert.equal(list.title, "Mix");
  assert.equal(list.videos.length, 2);
  assert.deepEqual(list.videos[0], {
    id: "a1", url: "https://www.youtube.com/watch?v=a1", title: "First", thumbnail: "big", duration: 61, available: true,
  });
  assert.equal(list.videos[1].available, false);
  assert.throws(() => playlistFromInfo({ _type: "video" }), /não é de uma playlist/);
});

test("validate checks link, format and segment", () => {
  assert.deepEqual(validate({ url: " https://youtu.be/x ", format: "m4a", start: "1:00", end: "" }), {
    url: "https://youtu.be/x", videos: [], format: "m4a", start: 60, end: null,
  });
  assert.throws(() => validate({ url: "javascript:alert(1)" }), /link válido/);
  assert.throws(() => validate({ url: "https://a", format: "exe" }), /não suportado/);
  assert.throws(() => validate({ url: "https://a", start: "2:00", end: "1:00" }), /depois do início/);
  assert.throws(() => validate({ url: "https://a", videos: ["file:///etc/passwd"] }), /link válido/);
});
