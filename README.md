# YouTube Video Downloader

A lightweight Python downloader powered by [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), with a web interface and a command-line mode. The web interface works from any device (phone, tablet, other computers): the file is sent to the browser as a normal download. The interface can be deployed on Netlify, with the download backend hosted separately (see [Deploy](#deploy-netlify--backend)).

## Features

- **Web interface for any device**: paste a link, pick the format and download, with live progress for each job. When it's ready the file is saved by the browser on the device you are using.
- **Playlist picker**: paste a playlist link and every video shows up as a card with thumbnail, title and duration. Choose exactly which videos to download.
- **Video or audio**: MP4, WebM and MKV video, or audio-only MP3 and M4A.
- **Clip a segment**: set a start and/or end timestamp to download only part of a video.
- **Batch downloads** from the command line.
- **Auto-cleaning URLs**: strips extra playlist/radio parameters (e.g. `&list=RD...`, `&index=...`) from single-video links to avoid "Video not available" errors.
- **Works without FFmpeg** for plain MP4 downloads, falling back to pre-merged single-stream videos.
- **Error recovery**: retries failed downloads with alternative formats and YouTube player clients.

## Prerequisites

- **Python 3.7+**
- **`yt-dlp`**:
  ```bash
  pip install -U yt-dlp
  ```
- **`ffmpeg`** (optional): needed for trimming, audio extraction (MP3/M4A), WebM/MKV, and for merging separate high-quality video and audio streams. Without it, only full MP4 downloads are available.

## Usage

### Web interface

```bash
python web_ui.py
```

The interface opens in your browser at `http://127.0.0.1:8000`.

1. Paste a video or playlist link.
2. Pick the file format.
3. Optionally fill in **Início** and **Fim** (`hh:mm:ss`, `mm:ss` or seconds) to keep only that segment. Leave both blank for the full video.
4. Click **Baixar**. Progress for each download appears below the form.
5. When it finishes, a single file is saved by the browser automatically (and a **Salvar** button stays available). Playlists get one button per video plus **Salvar todos (.zip)**.

The video is downloaded on the machine running `web_ui.py`, in a temporary folder, and then sent to your browser. Files stay available for 60 minutes and are then deleted from the server.

**Using it from your phone or another computer on the same Wi-Fi**: start it with `python web_ui.py --host 0.0.0.0` and open `http://<your-computer-ip>:8000` on the other device.

**Playlists**: when the link contains a playlist (`list=`), the videos load as cards below the link field.

- Every video starts selected. Click a card to select or unselect it, or use **Selecionar todos** / **Nenhum**.
- A counter shows how many videos are selected.
- Private or deleted videos are shown greyed out and can't be selected.
- If the link points to a single video inside a playlist (`watch?v=...&list=...`), only that video starts selected; the rest of the playlist is there to add.
- The format and the start/end timestamps apply to every selected video.

Options:

- `--port 8080` serves the interface on another port.
- `--no-browser` skips opening the browser automatically.
- `--host 0.0.0.0` accepts connections from other devices (needed on a server).

### Command line

Pass one or more video URLs:

```bash
python download_videos.py "https://www.youtube.com/watch?v=VIDEO_ID_1" "https://www.youtube.com/watch?v=VIDEO_ID_2"
```

Or add them to the `video_urls` list in `download_videos.py`:

```python
if __name__ == "__main__":
    video_urls = [
        "https://www.youtube.com/watch?v=EXAMPLE_1",
        "https://www.youtube.com/watch?v=EXAMPLE_2",
    ]
```

and run:

```bash
python download_videos.py
```

The command line downloads MP4 videos in full; formats, trimming and playlist selection are available in the web interface.

## Deploy (Netlify + backend)

Netlify only hosts static sites and short serverless functions (10 to 26 seconds, no `ffmpeg`, small responses), so it can't run `yt-dlp` to download, merge or cut videos. The project is therefore split in two:

| Part | What it is | Where it runs |
| --- | --- | --- |
| Interface | `public/` (HTML, CSS and JS) | Netlify |
| Backend | `web_ui.py` + `download_videos.py`, with `yt-dlp` and `ffmpeg` | Any host that runs Docker or Python (Render, Railway, Fly.io, a VPS) or your own computer |

The interface on Netlify calls the backend's API. The backend downloads the video and streams it back, so the browser saves it on whatever device is being used.

### 1. Deploy the backend (example: Render)

1. On [render.com](https://render.com), create a **New > Blueprint** from this repository. It uses `render.yaml` and the `Dockerfile` (Python, `yt-dlp` and `ffmpeg`).
   Without the Blueprint: **New > Web Service**, pick the repository, runtime **Docker**.
2. Set the environment variables:
   - `ALLOWED_ORIGINS`: your Netlify address, e.g. `https://my-downloader.netlify.app` (use `*` while testing).
   - `API_KEY` (recommended): a password. The interface asks for it once and remembers it on each device. Without it, anyone with the address can use your server.
3. After the deploy, open `https://<your-service>.onrender.com/api/health`. It should answer `{"ok": true, ...}`.

The same `Dockerfile` works on Railway, Fly.io or any VPS (`docker build -t ytdl . && docker run -p 8000:8000 ytdl`).

Notes:
- The backend must be served over **HTTPS** (Render, Railway and Fly.io do this for you), because a Netlify page can't call an `http://` address.
- YouTube sometimes blocks downloads from cloud servers ("Sign in to confirm you're not a bot"). If that happens, run the backend on your own computer and expose it with [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (`cloudflared tunnel --url http://localhost:8000`), then use that HTTPS address as the backend.
- Render's free plan sleeps after a while without use, so the first request can take up to a minute.

Optional backend settings: `FILE_TTL_MINUTES` (how long files stay available, default 60) and `MAX_CONCURRENT` (simultaneous downloads, default 2).

### 2. Deploy the interface on Netlify

1. On [netlify.com](https://app.netlify.com), **Add new site > Import an existing project** and pick this repository. `netlify.toml` already sets the publish folder (`public`) and the build command.
2. In **Site configuration > Environment variables**, add `API_URL` with the backend address, e.g. `https://my-downloader-api.onrender.com`.
3. Deploy (or **Trigger deploy** after changing `API_URL`). The build writes the address into `public/config.js`.
4. Put the Netlify address in the backend's `ALLOWED_ORIGINS`.

Open the Netlify site on any device, paste a link and the file is saved by that device's browser.

## Output location

Through the web interface, files are saved by the browser on the device you are using (usually its Downloads folder).

The command line saves files to your operating system's `Downloads` folder:

- **Windows**: `C:\Users\<YourUsername>\Downloads`
- **macOS / Linux**: `~/Downloads`

Clipped segments get the start and end times in brackets in the file name.

## License

MIT License
