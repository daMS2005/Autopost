import argparse
import os
from pathlib import Path

from moviepy.video.io.VideoFileClip import VideoFileClip
from yt_dlp import YoutubeDL


HIGH_QUALITY_FORMAT = (
    "bestvideo[height>=2160][fps>=60]+bestaudio/"
    "bestvideo[height>=2160]+bestaudio/"
    "bestvideo[height>=1440][fps>=60]+bestaudio/"
    "bestvideo[height>=1440]+bestaudio/"
    "bestvideo[height>=1080]+bestaudio/"
    "best[height>=1080]/best"
)

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_VIDEO_ROOT = PROJECT_ROOT / "videos"
CATEGORY_VIDEO_URLS = {
    "horror": [
        "https://youtu.be/vYnO42QHPWE?si=mFxZEr042Gvt6HqP",
        "https://www.youtube.com/watch?v=Kodhtmve5RI",
        "https://www.youtube.com/watch?v=HCtV6ckVtPY",
        "https://www.youtube.com/watch?v=e2Ku6wqFTBo",
        "https://www.youtube.com/watch?v=3p6DYRHc9_E&list=PLXuAdblJRdbbGdwS9xBHeKEnjY2vlpmcA",
        "https://www.youtube.com/watch?v=zfU1z0cVl_U",
        "https://www.youtube.com/watch?v=g4fWN8C_fvQ",
        "https://www.youtube.com/watch?v=raG4dGo22pE",
    ],
    "general": [
        "https://www.youtube.com/watch?v=Jb-fAwCiSLs",
        "https://www.youtube.com/watch?v=Wgl06wsEuq8",
        "https://www.youtube.com/watch?v=IkJqxIJZBJw",
        "https://www.youtube.com/watch?v=RNaEo6Zooww",
        "https://www.youtube.com/watch?v=OoP7csWPmWo",
        "https://www.youtube.com/watch?v=ZtLrNBdXT7M",
        "https://www.youtube.com/watch?v=e2Ku6wqFTBo",
        "https://www.youtube.com/watch?v=dmgRe9cNED8",
        "https://www.youtube.com/watch?v=3f0SjKNTVhs",
        "https://www.youtube.com/watch?v=chPoBX4aTEo",
        "https://www.youtube.com/watch?v=1AGVABna3xQ",
    ],
}


class VideoManager:
    def __init__(self, video_urls, download_path="videos"):
        self.video_urls = list(video_urls)
        self.download_path = str(Path(download_path).expanduser().resolve())
        self.downloaded_videos = []
        os.makedirs(self.download_path, exist_ok=True)

    def download_videos(self):
        """Download all videos in the list and save them in the specified directory."""
        for url in self.video_urls:
            try:
                ydl_options = {
                    "format": HIGH_QUALITY_FORMAT,
                    "merge_output_format": "mp4",
                    "outtmpl": os.path.join(self.download_path, "%(title).120s.%(ext)s"),
                    "noplaylist": True,
                    "format_sort": ["res", "fps", "codec:h264"],
                }

                with YoutubeDL(ydl_options) as ydl:
                    print(f"Downloading {url}...")
                    info = ydl.extract_info(url, download=True)
                    file_path = ydl.prepare_filename(info)
                    if not file_path.endswith(".mp4"):
                        file_path = os.path.splitext(file_path)[0] + ".mp4"

                video_clip = VideoFileClip(file_path)
                duration = video_clip.duration
                video_clip.close()

                self.downloaded_videos.append(
                    {"path": file_path, "remaining_duration": duration}
                )
                print(
                    f"Downloaded {info.get('title', url)} "
                    f"({duration // 60}m {duration % 60}s) to {file_path}"
                )
            except Exception as exc:
                print(f"Failed to download video from {url}: {exc}")


def resolve_download_path(category=None, explicit_output_dir=None):
    if explicit_output_dir:
        return Path(explicit_output_dir).expanduser().resolve()

    normalized_category = str(category or "").strip().lower()
    if normalized_category == "horror":
        return (DEFAULT_VIDEO_ROOT / "horror").resolve()
    if normalized_category == "general":
        return DEFAULT_VIDEO_ROOT.resolve()
    return DEFAULT_VIDEO_ROOT.resolve()


def resolve_urls(category=None, extra_urls=None):
    urls = []
    normalized_category = str(category or "").strip().lower()
    if normalized_category and normalized_category in CATEGORY_VIDEO_URLS:
        urls.extend(CATEGORY_VIDEO_URLS[normalized_category])
    if extra_urls:
        urls.extend(extra_urls)
    return urls


def build_parser():
    parser = argparse.ArgumentParser(description="Download category background footage.")
    parser.add_argument(
        "--category",
        choices=sorted(CATEGORY_VIDEO_URLS),
        default=None,
        help="Download one of the built-in footage presets.",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="Extra video URL to download. Repeat for more than one.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Where to save videos. Defaults to videos/ or videos/horror for the horror preset.",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    urls = resolve_urls(category=args.category, extra_urls=args.url)
    if not urls:
        raise SystemExit("No URLs provided. Use --category or one or more --url values.")

    manager = VideoManager(
        urls,
        download_path=str(resolve_download_path(args.category, args.output_dir)),
    )
    manager.download_videos()
    print(f"Videos downloaded to: {manager.download_path}")
