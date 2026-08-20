import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    import yt_dlp
except ImportError:
    print("Error: 'yt-dlp' is required. Please install it using: pip install yt-dlp")
    sys.exit(1)


def clean_youtube_url(url):
    """
    Strips unnecessary playlist/radio query parameters (like &list=RD... or &index=...)
    that often cause YouTube to report 'This video is not available'.
    """
    try:
        parsed = urlparse(url)
        if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
            qs = parse_qs(parsed.query)
            if "v" in qs:
                video_id = qs["v"][0]
                return f"https://www.youtube.com/watch?v={video_id}"
    except Exception:
        pass
    return url


def download_youtube_videos(url_list, output_dir=None):
    """
    Downloads YouTube videos given a list of URLs into the specified output directory.

    :param url_list: List of YouTube URL strings
    :param output_dir: Directory path to save videos (defaults to user's Downloads folder)
    """
    if output_dir is None:
        output_dir = Path.home() / "Downloads"
    else:
        output_dir = Path(output_dir)

    import shutil

    output_dir.mkdir(parents=True, exist_ok=True)

    has_ffmpeg = shutil.which("ffmpeg") is not None
    if not has_ffmpeg:
        print("Note: 'ffmpeg' not detected in system PATH.")
        print("Downloading single-file streams directly (no ffmpeg merging required).\n")

    format_spec = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' if has_ffmpeg else 'best[ext=mp4]/best'

    ydl_opts = {
        'format': format_spec,
        'outtmpl': str(output_dir / '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': False,
        'no_warnings': False,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web', 'mweb'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }

    print(f"Target Download Folder: {output_dir}\n")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for index, raw_url in enumerate(url_list, start=1):
            url = clean_youtube_url(raw_url.strip())
            print(f"[{index}/{len(url_list)}] Processing URL: {url}")
            try:
                ydl.download([url])
                print(f" Successfully downloaded video {index}.\n")
            except Exception as e:
                err_str = str(e).lower()
                # Fallback 1: Retry with single-stream format if ffmpeg missing error
                if "ffmpeg" in err_str and format_spec != 'best':
                    print(" FFmpeg missing error detected. Retrying with single-stream format ('best')...")
                    fallback_opts = dict(ydl_opts, format='best')
                    try:
                        with yt_dlp.YoutubeDL(fallback_opts) as fallback_ydl:
                            fallback_ydl.download([url])
                            print(f" Successfully downloaded video {index} using fallback format.\n")
                            continue
                    except Exception as fb_err:
                        err_str = str(fb_err).lower()
                        e = fb_err

                # Fallback 2: Retry with iOS player client if "not available" error
                if "not available" in err_str or "unavailable" in err_str:
                    print(" Video marked unavailable by default player. Retrying with alternative player client (iOS)...")
                    alt_opts = dict(ydl_opts)
                    alt_opts['extractor_args'] = {'youtube': {'player_client': ['ios', 'android']}}
                    try:
                        with yt_dlp.YoutubeDL(alt_opts) as alt_ydl:
                            alt_ydl.download([url])
                            print(f" Successfully downloaded video {index} using alternative player client.\n")
                            continue
                    except Exception as alt_err:
                        e = alt_err

                print(f" Failed to download video {index}: {e}\n")


if __name__ == "__main__":
    # Add your YouTube video URLs to this list
    video_urls = [] 

    # If URLs are provided via command-line arguments, use those instead  
    if len(sys.argv) > 1:
        video_urls = sys.argv[1:]

    if not video_urls:
        print("No URLs provided.")
        print("Please edit the 'video_urls' list inside the script or pass URLs as arguments:")
        print("  python download_videos.py https://www.youtube.com/watch?v=... https://www.youtube.com/watch?v=...")
        sys.exit(0)

    download_youtube_videos(video_urls)
