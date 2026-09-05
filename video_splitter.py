import json
import math
import re
from pathlib import Path

from moviepy.video.compositing.CompositeVideoClip import concatenate_videoclips
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.VideoClip import ImageClip
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from subtitle_editor import (
    DEFAULT_AUDIO_BITRATE,
    DEFAULT_MAX_RENDER_FPS,
    DEFAULT_VIDEO_CRF,
)
from title_card import load_font

DEFAULT_TARGET_PART_SECONDS = 60.0
DEFAULT_MIN_LAST_PART_SECONDS = 35.0
COVER_INTRO_SECONDS = 1.25
COVER_SIZE = (1080, 1920)
COVER_BACKGROUND = (246, 247, 248, 255)
COVER_BACKDROP_OVERLAY = (246, 247, 248, 84)
COVER_SHADOW = (0, 0, 0, 58)
COVER_BADGE_FILL = (255, 69, 0, 255)
COVER_BADGE_TEXT_FILL = (255, 255, 255, 255)
COVER_FOOTER_FILL = (245, 247, 250, 255)


def sanitize_slug(text):
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", str(text or "").strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "untitled"


def format_hashtag(value):
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", str(value or ""))
    if not cleaned:
        return None
    return f"#{cleaned.lower()}"


def build_default_hashtags(category=None, subreddit=None):
    category_key = str(category or "").strip().lower()
    base_tags = [
        "reddit",
        "redditstories",
        "storytime",
        "viral",
        "fyp",
        "reels",
        "reelstrending",
    ]
    category_tags = {
        "story": ["aita", "aitah", "redditreadings", "relationshipdrama"],
        "horror": ["horrortok", "scarystories", "creepytok", "scaryreddit"],
        "ask": ["askreddit", "questions", "redditanswers", "redditthread"],
    }.get(category_key, ["redditreadings", "redditthread"])

    ordered = []
    for tag in [*base_tags, *category_tags, subreddit]:
        formatted = format_hashtag(tag)
        if formatted and formatted not in ordered:
            ordered.append(formatted)
    return ordered


def build_part_hook(part_number, total_parts):
    if total_parts <= 1:
        return "Full story in this reel."
    if part_number == 1:
        return "Start here."
    return "You can jump in here - this is where it gets messy."


def build_part_caption(title, part_number, total_parts, category=None, subreddit=None):
    normalized_title = " ".join(str(title or "").split()).strip() or "Untitled"
    title_line = f"{normalized_title} (Part {part_number})" if total_parts > 1 else normalized_title
    hook = build_part_hook(part_number, total_parts)
    hashtags = build_default_hashtags(category=category, subreddit=subreddit)
    return {
        "title": title_line,
        "caption": f"{hook}\n\n{title_line}\n\n{' '.join(hashtags)}".strip(),
        "hashtags": hashtags,
        "hook": hook,
    }


def infer_title_card_path_for_video(video_path):
    source_path = Path(video_path).expanduser().resolve()
    match = re.search(r"final_video_(\d+)\.mp4$", source_path.name)
    if not match:
        return None
    candidate = source_path.with_name(f"title_card_{match.group(1)}.png")
    return candidate if candidate.exists() else None


def _rounded_rectangle(draw, box, radius, fill):
    try:
        draw.rounded_rectangle(box, radius=radius, fill=fill)
    except AttributeError:
        draw.rectangle(box, fill=fill)


def _fit_cover(image, size):
    target_width, target_height = size
    scale = max(target_width / image.width, target_height / image.height)
    resized = image.resize(
        (int(image.width * scale), int(image.height * scale)),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - target_width) // 2)
    top = max(0, (resized.height - target_height) // 2)
    return resized.crop((left, top, left + target_width, top + target_height))


def _build_cover_background(background_frame=None):
    if background_frame is None:
        return Image.new("RGBA", COVER_SIZE, COVER_BACKGROUND)

    background = Image.fromarray(background_frame).convert("RGBA")
    background = _fit_cover(background, COVER_SIZE)
    background = background.filter(ImageFilter.GaussianBlur(radius=14))
    background = ImageEnhance.Brightness(background).enhance(0.72)
    background = ImageEnhance.Color(background).enhance(0.82)

    overlay = Image.new("RGBA", COVER_SIZE, COVER_BACKDROP_OVERLAY)
    background.alpha_composite(overlay)
    return background


def render_part_cover(
    title_card_path, output_path, *, part_number, total_parts, background_frame=None
):
    title_card = Path(title_card_path).expanduser().resolve()
    if not title_card.exists():
        return None

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    cover = _build_cover_background(background_frame)
    draw = ImageDraw.Draw(cover)

    card = Image.open(title_card).convert("RGBA")
    max_card_width = 980
    scale = min(max_card_width / card.width, 1.0)
    card = card.resize(
        (int(card.width * scale), int(card.height * scale)),
        Image.Resampling.LANCZOS,
    )

    card_x = (COVER_SIZE[0] - card.width) // 2
    card_y = 520
    shadow_pad = 18
    shadow_box = (
        card_x + shadow_pad,
        card_y + shadow_pad,
        card_x + card.width + shadow_pad,
        card_y + card.height + shadow_pad,
    )
    _rounded_rectangle(draw, shadow_box, 32, COVER_SHADOW)
    cover.alpha_composite(card, (card_x, card_y))

    badge_text = f"PART {part_number}/{total_parts}" if total_parts > 1 else "FULL STORY"
    badge_font = load_font(56)
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_width = badge_bbox[2] - badge_bbox[0] + 72
    badge_height = badge_bbox[3] - badge_bbox[1] + 42
    badge_x = (COVER_SIZE[0] - badge_width) // 2
    badge_y = card_y + card.height + 96
    _rounded_rectangle(
        draw,
        (badge_x, badge_y, badge_x + badge_width, badge_y + badge_height),
        badge_height // 2,
        COVER_BADGE_FILL,
    )
    draw.text(
        (
            badge_x + (badge_width - (badge_bbox[2] - badge_bbox[0])) // 2,
            badge_y + (badge_height - (badge_bbox[3] - badge_bbox[1])) // 2 - badge_bbox[1],
        ),
        badge_text,
        font=badge_font,
        fill=COVER_BADGE_TEXT_FILL,
    )

    footer_font = load_font(38)
    footer_text = "reddit story"
    footer_bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
    footer_padding_x = 36
    footer_padding_y = 22
    footer_width = footer_bbox[2] - footer_bbox[0] + footer_padding_x * 2
    footer_height = footer_bbox[3] - footer_bbox[1] + footer_padding_y * 2
    footer_x = (COVER_SIZE[0] - footer_width) // 2
    footer_y = 1516
    _rounded_rectangle(
        draw,
        (footer_x, footer_y, footer_x + footer_width, footer_y + footer_height),
        footer_height // 2,
        (20, 24, 31, 132),
    )
    draw.text(
        (
            footer_x + footer_padding_x,
            footer_y + footer_padding_y - footer_bbox[1],
        ),
        footer_text,
        font=footer_font,
        fill=COVER_FOOTER_FILL,
    )

    cover.convert("RGB").save(output, quality=95)
    return output


def plan_video_parts(
    total_duration,
    target_seconds=DEFAULT_TARGET_PART_SECONDS,
    min_last_part_seconds=DEFAULT_MIN_LAST_PART_SECONDS,
):
    duration = max(float(total_duration or 0), 0.0)
    target = max(float(target_seconds or DEFAULT_TARGET_PART_SECONDS), 1.0)
    min_last = max(float(min_last_part_seconds or DEFAULT_MIN_LAST_PART_SECONDS), 1.0)

    if duration <= target:
        return [(0.0, duration)]

    part_count = max(1, math.ceil(duration / target))
    while part_count > 1:
        last_duration = duration - (target * (part_count - 1))
        if last_duration >= min_last:
            break
        part_count -= 1

    part_duration = duration / part_count
    parts = []
    for index in range(part_count):
        start = index * part_duration
        end = duration if index == part_count - 1 else (index + 1) * part_duration
        parts.append((start, end))
    return parts


def split_video_for_publishing(
    video_path,
    output_dir,
    *,
    title,
    category=None,
    subreddit=None,
    title_card_path=None,
    target_seconds=DEFAULT_TARGET_PART_SECONDS,
    min_last_part_seconds=DEFAULT_MIN_LAST_PART_SECONDS,
):
    source_path = Path(video_path).expanduser().resolve()
    destination_dir = Path(output_dir).expanduser().resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    resolved_title_card_path = (
        Path(title_card_path).expanduser().resolve()
        if title_card_path
        else infer_title_card_path_for_video(source_path)
    )
    if resolved_title_card_path and not resolved_title_card_path.exists():
        resolved_title_card_path = None

    manifest = {
        "source_video": str(source_path),
        "title": str(title or "").strip() or "Untitled",
        "category": category,
        "subreddit": subreddit,
        "title_card_path": str(resolved_title_card_path) if resolved_title_card_path else None,
        "target_seconds": float(target_seconds),
        "min_last_part_seconds": float(min_last_part_seconds),
        "parts": [],
    }

    video = VideoFileClip(str(source_path))
    clips_to_close = []
    try:
        parts = plan_video_parts(
            video.duration,
            target_seconds=target_seconds,
            min_last_part_seconds=min_last_part_seconds,
        )
        total_parts = len(parts)
        fps = max(
            24,
            min(
                round(getattr(video, "fps", None) or DEFAULT_MAX_RENDER_FPS),
                DEFAULT_MAX_RENDER_FPS,
            ),
        )
        slug = sanitize_slug(title)

        for part_index, (start, end) in enumerate(parts, start=1):
            subclip = video.subclipped(start, end)
            clips_to_close.append(subclip)
            output_path = destination_dir / f"{slug}_part_{part_index:02}.mp4"
            cover_path = None
            if resolved_title_card_path:
                background_time = min(max(start + 1.0, start), max(end - 0.1, start))
                cover_path = render_part_cover(
                    resolved_title_card_path,
                    destination_dir / f"{slug}_cover_part_{part_index:02}.jpg",
                    part_number=part_index,
                    total_parts=total_parts,
                    background_frame=video.get_frame(background_time),
                )

            render_clip = subclip
            if cover_path:
                cover_clip = ImageClip(str(cover_path)).with_duration(COVER_INTRO_SECONDS)
                clips_to_close.append(cover_clip)
                render_clip = concatenate_videoclips([cover_clip, subclip], method="compose")
                clips_to_close.append(render_clip)

            render_clip.write_videofile(
                str(output_path),
                codec="libx264",
                audio_codec="aac",
                audio_bitrate=DEFAULT_AUDIO_BITRATE,
                threads=4,
                fps=fps,
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

            caption_info = build_part_caption(
                title=title,
                part_number=part_index,
                total_parts=total_parts,
                category=category,
                subreddit=subreddit,
            )
            manifest["parts"].append(
                {
                    "part_number": part_index,
                    "total_parts": total_parts,
                    "start_seconds": round(start, 3),
                    "end_seconds": round(end, 3),
                    "duration_seconds": round(end - start, 3),
                    "video_path": str(output_path),
                    "cover_path": str(cover_path) if cover_path else None,
                    "cover_intro_seconds": COVER_INTRO_SECONDS if cover_path else 0,
                    **caption_info,
                }
            )
    finally:
        for clip in clips_to_close:
            clip.close()
        video.close()

    manifest_path = destination_dir / "publish_manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def infer_post_metadata_path_from_video(video_path):
    source_path = Path(video_path).expanduser().resolve()
    match = re.search(r"final_video_(\d+)\.mp4$", source_path.name)
    if not match:
        return None
    return source_path.with_name(f"post_metadata_{match.group(1)}.json")


def load_post_metadata_for_video(video_path):
    metadata_path = infer_post_metadata_path_from_video(video_path)
    if not metadata_path or not metadata_path.exists():
        return None
    return json.loads(metadata_path.read_text(encoding="utf-8"))
