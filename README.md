# YouTube Video Downloader

A lightweight, robust Python script powered by [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) to batch-download YouTube videos directly to your local **Downloads** folder.

## Features

- **Batch Downloads**: Pass a list of YouTube URLs in the script or directly via command-line arguments.
- **Auto-Cleaning URLs**: Automatically strips extra playlist/radio parameters (e.g., `&list=RD...`, `&index=...`) to prevent "Video not available" errors.
- **No FFmpeg Required**: Automatically detects if `ffmpeg` is installed. If missing, it downloads high-quality pre-merged single-stream videos without requiring `ffmpeg` merging.
- **Robust Anti-Bot Bypass**: Configured with alternative YouTube player clients (`android`, `ios`, `web`) and standard browser headers to minimize download failures.
- **Error Recovery**: Automatically retries downloads using alternative formats and player clients if a video fails.

## Prerequisites

- **Python 3.7+**
- **`yt-dlp`** library

Install `yt-dlp` via pip:
```bash
pip install -U yt-dlp
```

> **Note**: `ffmpeg` is optional. If installed on your system, the script will use it to merge separate ultra-HD video and audio streams for maximum quality. If not installed, it safely falls back to pre-merged streams.

## Usage

### Method 1: Command Line Arguments

Pass one or multiple YouTube video URLs directly when running the script:

```bash
python download_videos.py "https://www.youtube.com/watch?v=VIDEO_ID_1" "https://www.youtube.com/watch?v=VIDEO_ID_2"
```

### Method 2: Edit URL List in Script

Open `download_videos.py` in your code editor and add your video links to the `video_urls` list:"

```python
if __name__ == "__main__":
    video_urls = [
        "https://www.youtube.com/watch?v=EXAMPLE_1",
        "https://www.youtube.com/watch?v=EXAMPLE_2",
    ]
```

Then run:

```bash
python download_videos.py
```

## Output Location

Downloaded videos are saved automatically to your operating system's default `Downloads` folder:
- **Windows**: `C:\Users\<YourUsername>\Downloads`
- **macOS / Linux**: `~/Downloads`

## License

MIT License
