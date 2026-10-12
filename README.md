# YouTube Video Downloader

A lightweight Python downloader powered by [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), with a local web interface and a command-line mode. Videos are saved to your **Downloads** folder.

## Features

- **Local web interface**: paste a link, pick the format and download, with live progress for each job.
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

**Playlists**: when the link contains a playlist (`list=`), the videos load as cards below the link field.

- Every video starts selected. Click a card to select or unselect it, or use **Selecionar todos** / **Nenhum**.
- A counter shows how many videos are selected.
- Private or deleted videos are shown greyed out and can't be selected.
- If the link points to a single video inside a playlist (`watch?v=...&list=...`), only that video starts selected; the rest of the playlist is there to add.
- The format and the start/end timestamps apply to every selected video.

Options:

- `--port 8080` serves the interface on another port.
- `--no-browser` skips opening the browser automatically.

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

## Output location

Files are saved to your operating system's `Downloads` folder:

- **Windows**: `C:\Users\<YourUsername>\Downloads`
- **macOS / Linux**: `~/Downloads`

Clipped segments get the start and end times in brackets in the file name.

## License

MIT License
