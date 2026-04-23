import logging
import os

from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.CompositeVideoClip import concatenate_videoclips


GENERATED_VIDEO_PREFIXES = (
    "final_video",
    "title_card_overlay",
)


class VideoManager:
    def __init__(self, download_path="videos", output_path="output"):
        self.download_path = download_path
        self.output_path = output_path
        self.videos = []
        self.current_video_index = 0

        os.makedirs(download_path, exist_ok=True)
        os.makedirs(output_path, exist_ok=True)

        for filename in os.listdir(download_path):
            if not filename.endswith(".mp4"):
                continue

            if filename.startswith(GENERATED_VIDEO_PREFIXES):
                logging.info("Skipping generated video as source footage: %s", filename)
                continue

            file_path = os.path.join(download_path, filename)
            video_clip = VideoFileClip(file_path)
            self.videos.append(
                {
                    "path": file_path,
                    "duration": video_clip.duration,
                    "used_portions": [],
                }
            )
            video_clip.close()

        if not self.videos:
            logging.warning("No videos found in %s.", download_path)

    def get_video_clip(self, required_duration):
        """Get a clip of the required duration while skipping used portions."""
        if not self.videos:
            raise RuntimeError(
                f"No videos are available in '{self.download_path}'. "
                "Add one or more .mp4 files before running the pipeline."
            )

        if all(video["duration"] < required_duration for video in self.videos):
            logging.info(
                "No single source video is long enough for %.2fs; looping background footage.",
                required_duration,
            )
            return self._create_looped_clip(required_duration)

        attempts = 0
        max_attempts = len(self.videos) * 2

        while attempts < max_attempts:
            video = self.videos[self.current_video_index]
            available_clip = self._get_next_available_clip(video, required_duration)

            if available_clip:
                return available_clip

            self.current_video_index = (self.current_video_index + 1) % len(self.videos)
            attempts += 1

        raise RuntimeError(
            "Unable to find an unused source clip. Add more footage or reduce the post length."
        )

    def _get_next_available_clip(self, video, required_duration):
        """Find the next unused portion of the video that fits the required duration."""
        used_portions = video["used_portions"]
        video_duration = video["duration"]

        start_time = 0
        for used_start, used_end in used_portions:
            if used_start - start_time >= required_duration:
                return self._create_clip(video["path"], start_time, start_time + required_duration)
            start_time = used_end

        if video_duration - start_time >= required_duration:
            return self._create_clip(video["path"], start_time, start_time + required_duration)

        logging.info("Video '%s' fully used, resetting usage.", video["path"])
        video["used_portions"] = []
        return None

    def _create_clip(self, video_path, start_time, end_time):
        """Create a video clip and mark the portion as used."""
        video_clip = VideoFileClip(video_path).subclipped(start_time, end_time)

        video = next(v for v in self.videos if v["path"] == video_path)
        video["used_portions"].append((start_time, end_time))
        video["used_portions"].sort()

        return video_clip

    def _create_looped_clip(self, required_duration):
        """Create a clip by repeating the longest available source video."""
        source = max(self.videos, key=lambda video: video["duration"])
        clips = []
        remaining_duration = required_duration

        while remaining_duration > 0:
            clip_duration = min(source["duration"], remaining_duration)
            clips.append(VideoFileClip(source["path"]).subclipped(0, clip_duration))
            remaining_duration -= clip_duration

        return concatenate_videoclips(clips, method="compose")
