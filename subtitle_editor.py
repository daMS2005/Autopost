from pathlib import Path

import pysrt
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.VideoClip import ImageClip, TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.io.VideoFileClip import VideoFileClip


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_FONT_PATH = PROJECT_ROOT / "resources" / "BebasNeue-Regular.ttf"
FALLBACK_FONT_PATHS = (
    PROJECT_ROOT / "resources" / "Arial.TTF",
)
PORTRAIT_VIDEO_SIZE = (1080, 1920)
MIN_SUBTITLE_GAP_SECONDS = 0.08
MAX_INFERRED_TITLE_CARD_SECONDS = 10.0
DEFAULT_TITLE_CARD_SECONDS = 5.0
TITLE_CARD_VIDEO_WIDTH_RATIO = 0.70
TITLE_CARD_POSITION = ("center", "center")
DEFAULT_MAX_RENDER_FPS = 60
DEFAULT_VIDEO_CRF = 16
DEFAULT_AUDIO_BITRATE = "192k"
SUBTITLE_FONT_SIZE_RATIO = 0.065
SUBTITLE_MIN_FONT_SIZE = 42
SUBTITLE_VERTICAL_POSITION_RATIO = 0.69


def resolve_font_path(font_path=None):
    if font_path:
        resolved_font = Path(font_path).expanduser().resolve()
        if not resolved_font.exists():
            raise FileNotFoundError(f"Subtitle font not found: {resolved_font}")
        return str(resolved_font)

    for candidate in (DEFAULT_FONT_PATH, *FALLBACK_FONT_PATHS):
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError(
        "No subtitle font was found. Pass --font-path or add a fallback font."
    )


def seconds_to_subrip_time(seconds):
    return pysrt.SubRipTime(milliseconds=max(0, int(seconds * 1000)))


def normalize_subtitle_timing(subtitles, min_gap_seconds=MIN_SUBTITLE_GAP_SECONDS):
    """
    Prevent adjacent captions from rendering on top of each other.

    Generated caption files can emit very tight caption boundaries. We leave the
    start times intact for sync, but shorten each caption slightly when it touches the next.
    """
    normalized = list(subtitles)

    for index, subtitle in enumerate(normalized[:-1]):
        next_subtitle = normalized[index + 1]
        latest_end = (next_subtitle.start.ordinal / 1000) - min_gap_seconds
        current_start = subtitle.start.ordinal / 1000
        current_end = subtitle.end.ordinal / 1000

        if current_end > latest_end and latest_end > current_start:
            subtitle.end = seconds_to_subrip_time(latest_end)

    return normalized


def infer_title_card_duration(subtitles, fallback_duration):
    """
    Keep the title card on screen through the first spoken sentence.
    """
    if fallback_duration and fallback_duration > 0:
        return fallback_duration

    text_parts = []
    inferred_end = 0

    for subtitle in subtitles:
        text = subtitle.text.replace("\n", " ").strip()
        if not text:
            continue

        text_parts.append(text)
        inferred_end = subtitle.end.ordinal / 1000

        if any(mark in text for mark in (".", "!", "?")):
            break

        if inferred_end >= MAX_INFERRED_TITLE_CARD_SECONDS:
            break

    return min(inferred_end or DEFAULT_TITLE_CARD_SECONDS, MAX_INFERRED_TITLE_CARD_SECONDS)


def fit_video_to_portrait(video, target_size=PORTRAIT_VIDEO_SIZE):
    """
    Resize and center-crop any source clip to a 9:16 portrait canvas.
    """
    target_width, target_height = target_size
    scale = max(target_width / video.w, target_height / video.h)
    resized_width = int(video.w * scale)
    resized_height = int(video.h * scale)

    return (
        video.resized((resized_width, resized_height))
        .cropped(
            x_center=resized_width / 2,
            y_center=resized_height / 2,
            width=target_width,
            height=target_height,
        )
    )


def resolve_render_fps(video):
    source_fps = getattr(video, "fps", None) or DEFAULT_MAX_RENDER_FPS
    return max(24, min(int(round(source_fps)), DEFAULT_MAX_RENDER_FPS))


def add_subtitles_to_video(
    video_source,
    subtitles_path,
    output_path,
    audio_path=None,
    font_path=None,
    title_card_path=None,
    title_card_duration=0,
):
    """
    Render subtitles onto a video and optionally attach narration audio.
    """
    output_file = Path(output_path).expanduser().resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    owns_video = isinstance(video_source, (str, Path))
    video = (
        VideoFileClip(str(Path(video_source).expanduser().resolve()))
        if owns_video
        else video_source
    )
    background_clip = None
    narration_clip = None
    final_video = None
    title_card_clip = None
    text_clips = []

    try:
        background_clip = fit_video_to_portrait(video)
        canvas_width, canvas_height = PORTRAIT_VIDEO_SIZE
        font = resolve_font_path(font_path)
        subtitles = normalize_subtitle_timing(pysrt.open(subtitles_path))
        active_title_card_duration = (
            infer_title_card_duration(subtitles, title_card_duration)
            if title_card_path
            else 0
        )
        font_size = max(SUBTITLE_MIN_FONT_SIZE, int(canvas_width * SUBTITLE_FONT_SIZE_RATIO))
        text_width = int(canvas_width * 0.82)
        y_position = int(canvas_height * SUBTITLE_VERTICAL_POSITION_RATIO)
        line_spacing = max(10, int(font_size * 0.3))

        for subtitle in subtitles:
            text = subtitle.text.replace("\n", " ").strip()
            if not text:
                continue

            start_time = subtitle.start.ordinal / 1000
            if active_title_card_duration and start_time < active_title_card_duration:
                continue

            duration = max((subtitle.end.ordinal - subtitle.start.ordinal) / 1000, 0.1)

            text_clip = (
                TextClip(
                    font=font,
                    text=text,
                    font_size=font_size,
                    color="white",
                    bg_color=None,
                    stroke_color="black",
                    stroke_width=4,
                    size=(text_width, None),
                    method="caption",
                    text_align="center",
                    horizontal_align="center",
                    vertical_align="center",
                    interline=line_spacing,
                    margin=(18, 10),
                    duration=duration,
                )
                .with_position(("center", y_position))
                .with_start(start_time)
            )
            text_clips.append(text_clip)

        if audio_path:
            narration_clip = AudioFileClip(audio_path)
            render_duration = min(background_clip.duration, narration_clip.duration)
        else:
            render_duration = background_clip.duration

        render_fps = resolve_render_fps(video)

        overlay_clips = [background_clip]

        if title_card_path:
            title_card_clip = (
                ImageClip(title_card_path)
                .resized(width=int(canvas_width * TITLE_CARD_VIDEO_WIDTH_RATIO))
                .with_duration(min(active_title_card_duration, render_duration))
                .with_position(TITLE_CARD_POSITION)
            )
            overlay_clips.append(title_card_clip)

        overlay_clips.extend(text_clips)
        final_video = CompositeVideoClip(overlay_clips, size=PORTRAIT_VIDEO_SIZE)
        final_video = final_video.subclipped(0, render_duration)

        if audio_path:
            narration_clip = narration_clip.subclipped(0, render_duration)
            final_video = final_video.with_audio(narration_clip)

        final_video.write_videofile(
            str(output_file),
            codec="libx264",
            audio_codec="aac",
            audio_bitrate=DEFAULT_AUDIO_BITRATE,
            threads=4,
            fps=render_fps,
            ffmpeg_params=[
                "-preset",
                "slow",
                "-crf",
                str(DEFAULT_VIDEO_CRF),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
            ],
        )
    finally:
        for clip in text_clips:
            clip.close()

        if final_video is not None:
            final_video.close()

        if narration_clip is not None:
            narration_clip.close()

        if title_card_clip is not None:
            title_card_clip.close()

        if background_clip is not None:
            background_clip.close()

        if owns_video:
            video.close()
