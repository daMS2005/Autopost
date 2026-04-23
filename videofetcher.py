import os
from moviepy.video.io.VideoFileClip import VideoFileClip
from yt_dlp import YoutubeDL

class VideoManager:
    def __init__(self, video_urls, download_path="videos"):
        self.video_urls = video_urls  # List of YouTube video URLs
        self.download_path = download_path  # Directory to store downloaded videos
        self.downloaded_videos = []  # Tracks downloaded videos with usage info
        os.makedirs(download_path, exist_ok=True)

    def download_videos(self):
        """Download all videos in the list and save them in the specified directory."""
        for url in self.video_urls:
            try:
                ydl_options = {
                    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "merge_output_format": "mp4",
                    "outtmpl": os.path.join(self.download_path, "%(title).120s.%(ext)s"),
                    "noplaylist": True,
                }

                with YoutubeDL(ydl_options) as ydl:
                    print(f"Downloading {url}...")
                    info = ydl.extract_info(url, download=True)
                    file_path = ydl.prepare_filename(info)
                    if not file_path.endswith(".mp4"):
                        file_path = os.path.splitext(file_path)[0] + ".mp4"

                # Get video duration
                video_clip = VideoFileClip(file_path)
                duration = video_clip.duration
                video_clip.close()

                self.downloaded_videos.append({"path": file_path, "remaining_duration": duration})
                print(f"Downloaded {info.get('title', url)} ({duration // 60}m {duration % 60}s) to {file_path}")
            except Exception as e:
                print(f"Failed to download video from {url}: {e}")

if __name__ == "__main__":
    # Example usage: Replace these with actual video URLs
    video_urls = [
    "https://www.youtube.com/watch?v=lcPTDc9vHkE",
    "https://www.youtube.com/watch?v=u7kdVe8q5zs&t=46s",
    "https://www.youtube.com/watch?v=0jZu2Yx_ies"
    ]


    manager = VideoManager(video_urls)
    manager.download_videos()
    print(f"Videos downloaded to: {os.path.abspath(manager.download_path)}")
