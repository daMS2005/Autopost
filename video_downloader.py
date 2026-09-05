import logging
import os
import random

from moviepy.video.compositing.CompositeVideoClip import concatenate_videoclips
from moviepy.video.io.VideoFileClip import VideoFileClip

LOGGER = logging.getLogger(__name__)
GENERATED_VIDEO_PREFIXES = (
    "final_video",
    "title_card_overlay",
)
DEFAULT_MIN_SOURCE_START_SECONDS = 60.0


class VideoManager:
    def __init__(self, download_path="videos", output_path="output", background_speed=1.0):
        self.download_path = download_path
        self.output_path = output_path
        self.background_speed = max(float(background_speed or 1.0), 0.1)
        self.min_source_start_seconds = DEFAULT_MIN_SOURCE_START_SECONDS
        self.videos = []

        os.makedirs(download_path, exist_ok=True)
        os.makedirs(output_path, exist_ok=True)

        for filename in os.listdir(download_path):
            if not filename.endswith(".mp4"):
                continue

            if filename.startswith(GENERATED_VIDEO_PREFIXES):
                LOGGER.info("Skipping generated video as source footage: %s", filename)
                continue

            file_path = os.path.join(download_path, filename)
            video_clip = VideoFileClip(file_path)
            source_fps = float(getattr(video_clip, "fps", None) or 0.0)
            source_bitrate = float(getattr(video_clip.reader, "bitrate", None) or 0.0)
            quality_score = self._compute_quality_score(
                width=float(video_clip.w),
                height=float(video_clip.h),
                fps=source_fps,
                bitrate=source_bitrate,
            )
            self.videos.append(
                {
                    "path": file_path,
                    "duration": video_clip.duration,
                    "width": video_clip.w,
                    "height": video_clip.h,
                    "fps": source_fps,
                    "bitrate": source_bitrate,
                    "quality_score": quality_score,
                    "used_portions": [],
                }
            )
            video_clip.close()

        if not self.videos:
            LOGGER.warning("No videos found in %s.", download_path)

    def get_video_clip(self, required_duration):
        """Get a clip of the required duration while skipping used portions."""
        if not self.videos:
            raise RuntimeError(
                f"No videos are available in '{self.download_path}'. "
                "Add one or more .mp4 files before running the pipeline."
            )

        source_duration_needed = required_duration * self.background_speed

        if all(video["duration"] < source_duration_needed for video in self.videos):
            LOGGER.info(
                "No single source video is long enough for %.2fs; looping background footage.",
                source_duration_needed,
            )
            return self._create_looped_clip(required_duration)

        attempts = 0
        max_attempts = len(self.videos) * 2

        while attempts < max_attempts:
            video = self._choose_source_video()
            available_clip = self._get_next_available_clip(video, source_duration_needed)

            if available_clip:
                return available_clip

            attempts += 1

        raise RuntimeError(
            "Unable to find an unused source clip. Add more footage or reduce the post length."
        )

    def _compute_quality_score(self, *, width, height, fps, bitrate):
        resolution_score = max(width * height, 1.0)
        fps_score = max(fps, 1.0)
        bitrate_score = max(bitrate, 1.0)
        return resolution_score * fps_score * bitrate_score

    def _choose_source_video(self):
        weights = [max(float(video.get("quality_score", 1.0)), 1.0) for video in self.videos]
        return random.choices(self.videos, weights=weights, k=1)[0]

    def _get_next_available_clip(self, video, required_duration):
        """Find a random unused portion of the video that fits the required duration."""
        used_portions = video["used_portions"]
        video_duration = video["duration"]
        available_ranges = []
        preferred_min_start = self._preferred_min_start(video_duration, required_duration)
        start_time = preferred_min_start

        for used_start, used_end in used_portions:
            effective_used_start = max(used_start, preferred_min_start)
            if effective_used_start - start_time >= required_duration:
                available_ranges.append((start_time, used_start))
            start_time = max(used_end, preferred_min_start)

        if video_duration - start_time >= required_duration:
            available_ranges.append((start_time, video_duration))

        if available_ranges:
            range_start, range_end = random.choice(available_ranges)
            latest_valid_start = range_end - required_duration
            clip_start = (
                random.uniform(range_start, latest_valid_start)
                if latest_valid_start > range_start
                else range_start
            )
            return self._create_clip(
                video["path"],
                clip_start,
                clip_start + required_duration,
            )

        LOGGER.info("Video '%s' fully used, resetting usage.", video["path"])
        video["used_portions"] = []
        return None

    def _preferred_min_start(self, video_duration, required_duration):
        latest_valid_start = max(video_duration - required_duration, 0.0)
        if latest_valid_start <= 0:
            return 0.0
        return min(self.min_source_start_seconds, latest_valid_start)

    def _create_clip(self, video_path, start_time, end_time):
        """Create a video clip and mark the portion as used."""
        video_clip = VideoFileClip(video_path).subclipped(start_time, end_time)
        if self.background_speed != 1.0:
            video_clip = video_clip.with_speed_scaled(factor=self.background_speed)

        video = next(v for v in self.videos if v["path"] == video_path)
        video["used_portions"].append((start_time, end_time))
        video["used_portions"].sort()

        return video_clip

    def _create_looped_clip(self, required_duration):
        """Create a clip by repeating the longest available source video."""
        source = max(self.videos, key=lambda video: video["duration"])
        clips = []
        remaining_duration = required_duration * self.background_speed

        while remaining_duration > 0:
            clip_duration = min(source["duration"], remaining_duration)
            latest_valid_start = max(source["duration"] - clip_duration, 0)
            preferred_min_start = self._preferred_min_start(source["duration"], clip_duration)
            clip_start = (
                random.uniform(preferred_min_start, latest_valid_start)
                if latest_valid_start > preferred_min_start
                else preferred_min_start
            )
            clips.append(
                VideoFileClip(source["path"]).subclipped(
                    clip_start,
                    clip_start + clip_duration,
                )
            )
            remaining_duration -= clip_duration

        looped_clip = concatenate_videoclips(clips, method="compose")
        if self.background_speed != 1.0:
            return looped_clip.with_speed_scaled(factor=self.background_speed)
        return looped_clip
