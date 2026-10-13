# YouTube Video Downloader

Download YouTube videos, playlists and clips from any device (phone, tablet, computer). A single Node.js server runs [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) and `ffmpeg` and serves the React interface, so the whole app is hosted in one place (for example one Render web service). Files are sent to the browser as a normal download, so they land on whatever device opened the page.

## Features

- **Works from any device**: paste a link, pick the format and download, with live progress for each job. When it's ready the browser saves the file on the device you are using.
- **Playlist picker**: paste a playlist link and every video shows up as a card with thumbnail, title and duration. Choose exactly which videos to download.
- **Video or audio**: MP4, WebM and MKV video, or audio-only MP3 and M4A.
- **Clip a segment**: set a start and/or end timestamp to download only part of a video.
- **Download everything at once**: playlists get one button per video plus **Salvar todos (.zip)**.
- **Private per device**: each browser only sees the downloads it started.
- **Optional password** (`API_KEY`) so only you can use your server.
- **Auto-cleaning URLs**: strips extra playlist/radio parameters (e.g. `&list=RD...`, `&index=...`) from single-video links to avoid "Video not available" errors.
- **Error recovery**: retries videos YouTube reports as unavailable with alternative player clients; when some videos of a playlist fail, the rest are still delivered.

## How it works

| Part | Folder | What it does |
| --- | --- | --- |
| Interface | `src/` (React, built with Vite) | Form, playlist cards, progress and download buttons |
| API | `server/` (Express) | Lists playlists, runs `yt-dlp` / `ffmpeg` as child processes, streams the files to the browser |

In production the Express server serves the built interface from `dist/` and the API under `/api`, on the same address. There is no separate frontend host and no CORS to configure.

## Run it locally

Requirements: **Node.js 20+**, **[yt-dlp](https://github.com/yt-dlp/yt-dlp#installation)** and **[ffmpeg](https://ffmpeg.org/download.html)** on your `PATH`.

```bash
npm install
npm run dev        # interface + API on http://localhost:8000, with hot reload
```

To run it the way it runs in production:

```bash
npm run build
npm start          # http://localhost:8000
```

Or with Docker, which already includes yt-dlp and ffmpeg:

```bash
docker build -t ytdl .
docker run -p 8000:8000 ytdl
```

**Using it from your phone on the same Wi-Fi**: open `http://<your-computer-ip>:8000` on the phone.

`npm test` runs the server's unit tests.

## Usage

1. Paste a video or playlist link.
2. Pick the file format.
3. Optionally fill in **Início** and **Fim** (`hh:mm:ss`, `mm:ss` or seconds) to keep only that segment. Leave both blank for the full video.
4. Click **Baixar**. Progress for each download appears below the form.
5. When it finishes, a single file is saved by the browser automatically (and a **Salvar** button stays available). Playlists get one button per video plus **Salvar todos (.zip)**.

**Playlists**: when the link contains a playlist (`list=`), the videos load as cards below the link field.

- Every video starts selected. Click a card to select or unselect it, or use **Selecionar todos** / **Nenhum**.
- A counter shows how many videos are selected.
- Private or deleted videos are shown greyed out and can't be selected.
- If the link points to a single video inside a playlist (`watch?v=...&list=...`), only that video starts selected; the rest of the playlist is there to add.
- The format and the start/end timestamps apply to every selected video.

Videos are downloaded on the server, in a temporary folder, and then sent to your browser. Files stay available for 60 minutes and are then deleted.

## Deploy on Render

1. On [render.com](https://render.com), choose **New > Blueprint** and pick this repository. It reads `render.yaml` and builds the `Dockerfile` (Node, yt-dlp and ffmpeg).
   Without the Blueprint: **New > Web Service**, pick the repository, runtime **Docker**, health check path `/api/health`.
2. Set `API_KEY` to a password (recommended). The interface asks for it once and remembers it on each device. Without it, anyone with the address can use your server.
3. When the deploy finishes, open `https://<your-service>.onrender.com` on any device.

Notes:

- yt-dlp is downloaded when the image is built, so a new deploy (**Manual Deploy > Clear build cache & deploy**) updates it. Do this when YouTube downloads start failing.
- YouTube often blocks cloud servers with "Sign in to confirm you're not a bot". See [YouTube cookies](#youtube-cookies-sign-in-to-confirm-youre-not-a-bot) below.
- Render's free plan sleeps after a while without use, so the first request can take up to a minute, and its disk is temporary (fine here, since files are deleted after an hour anyway).

The same `Dockerfile` works on Railway, Fly.io or any VPS.

### YouTube cookies ("Sign in to confirm you're not a bot")

YouTube treats most datacenter addresses (Render, Railway, Fly.io...) as bots and refuses to serve videos to them. Cookies from a logged-in YouTube account get past that check, so the server can use a `cookies.txt` file.

**Use a separate Google account, not your main one.** The cookies give full access to that account, and YouTube can flag or suspend accounts used by automated downloaders.

1. **Export the cookies** (Netscape `cookies.txt` format) in a way YouTube won't immediately rotate them:
   1. Open a private/incognito window and log in to YouTube with the separate account.
   2. In the same tab, open `https://www.youtube.com/robots.txt`.
   3. Export the cookies of `youtube.com` with an extension such as **Get cookies.txt LOCALLY** (Chrome/Edge) or **cookies.txt** (Firefox), allowing it in private windows.
   4. Close the private window right away, without logging out. Logging out or browsing YouTube in that session invalidates the exported cookies.

   Alternatively, with yt-dlp installed on your computer and the account logged in on Firefox: `yt-dlp --cookies-from-browser firefox --cookies cookies.txt --skip-download "https://www.youtube.com/watch?v=dQw4w9WgXcQ"` (extracting from Chrome on Windows usually fails).
2. **Give them to the server**. On Render, open the service, **Environment > Secret Files**, add a file named `cookies.txt` with the file's content, and save (Render redeploys). The server finds it at `/etc/secrets/cookies.txt`.
   Other hosts: set `YT_COOKIES_FILE` to the file's path, or put the content (plain or base64) in the `YT_COOKIES` variable.
3. Open `https://<your-service>.onrender.com/api/health`: it should show `"cookies": true`. The server log also says `Usando cookies do YouTube.`

When the cookies expire, the interface says so: export new ones and replace the Secret File.

Cookies don't always solve it: YouTube can still block a datacenter address (or ask for the account to be verified), and a new yt-dlp release is often needed when YouTube changes something (**Manual Deploy > Clear build cache & deploy** fetches it). If downloads keep failing on the server, run the same container on your own computer, where your home connection isn't blocked (`docker run -p 8000:8000 ytdl`, or `npm start`), and use it from other devices on the same Wi-Fi or through [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (`cloudflared tunnel --url http://localhost:8000`).

### Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `API_KEY` | empty | Password required by every API call |
| `PORT` | `8000` | Port to listen on (Render sets it) |
| `FILE_TTL_MINUTES` | `60` | How long finished files stay available |
| `MAX_CONCURRENT` | `2` | Downloads running at the same time |
| `YT_COOKIES_FILE` | `/etc/secrets/cookies.txt` if present | Path to a YouTube `cookies.txt` |
| `YT_COOKIES` | empty | Content of a YouTube `cookies.txt` (plain or base64) |
| `YTDLP_PATH` | `yt-dlp` | Path to another yt-dlp binary |

## Command line (optional)

`download_videos.py` is a standalone Python script for batch downloads without the interface (`pip install -r requirements.txt`, plus ffmpeg for merging the best quality):

```bash
python download_videos.py "https://www.youtube.com/watch?v=VIDEO_ID_1" "https://www.youtube.com/watch?v=VIDEO_ID_2"
```

It saves MP4 files to your `Downloads` folder.

## License

MIT License
