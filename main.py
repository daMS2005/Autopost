import argparse
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from content_config import (
    get_category_config,
    infer_category_for_subreddit,
    resolve_video_dir,
)
from processed_posts import (
    DEFAULT_PROCESSED_POSTS_PATH,
    append_processed_post,
    load_processed_post_index,
)
from reddit_scraper import scrape_reddit_posts
from reddit_vocabulary import normalize_reddit_vocabulary
from script_rewriter import finalize_prepared_voiceover, prepare_voiceover
from subtitle_editor import add_subtitles_to_video
from text_to_speech import (
    DEFAULT_ELEVENLABS_FEMALE_VOICE_ID,
    DEFAULT_ELEVENLABS_MALE_VOICE_ID,
    generate_voiceover_and_subtitles,
    get_audio_length,
    resolve_voice_id,
)
from title_card import DEFAULT_TEMPLATE_PATH, render_title_card
from video_downloader import VideoManager
from voice_registry import default_voice_name_for

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_VIDEO_DIR = PROJECT_ROOT / "videos"
DEFAULT_TITLE_CARD_SECONDS = 0
REQUIRED_ENV_VARS = (
    "CLIENT_ID_REDDIT",
    "CLIENT_SECRET_REDDIT",
    "ELEVENLABS_API_KEY",
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
LOGGER = logging.getLogger(__name__)


def build_parser():
    parser = argparse.ArgumentParser(description="Generate narrated Reddit videos with subtitles.")
    parser.add_argument("--subreddit", default=os.getenv("SUBREDDIT", "AITAH"))
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--chars-per-caption", type=int, default=22)
    parser.add_argument(
        "--background-speed",
        type=float,
        default=float(os.getenv("BACKGROUND_SPEED")) if os.getenv("BACKGROUND_SPEED") else None,
        help="Playback speed multiplier for the background footage only. Leave unset to use category defaults.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--video-dir", default=str(DEFAULT_VIDEO_DIR))
    parser.add_argument(
        "--processed-posts-file",
        default=str(DEFAULT_PROCESSED_POSTS_PATH),
        help="JSONL registry of already processed Reddit posts used to skip duplicates.",
    )
    parser.add_argument(
        "--script-model",
        default=os.getenv("OPENAI_SCRIPT_MODEL", "gpt-5-mini"),
        help="OpenAI model used to clean Reddit text before TTS.",
    )
    parser.add_argument(
        "--skip-script-cleanup",
        action="store_true",
        help="Skip OpenAI voiceover cleanup and send raw Reddit text to TTS.",
    )
    parser.add_argument(
        "--skip-v3-directions",
        action="store_true",
        help="Skip conservative Eleven v3 cueing inside the OpenAI cleanup pass.",
    )
    parser.add_argument(
        "--titles-file",
        default=None,
        help="Optional path to save scraped Reddit titles.",
    )
    parser.add_argument(
        "--font-path",
        default=None,
        help="Optional .ttf font path for subtitle rendering.",
    )
    parser.add_argument(
        "--title-card-template",
        default=str(DEFAULT_TEMPLATE_PATH),
        help="Template image used for the opening Reddit title card.",
    )
    parser.add_argument(
        "--title-card-duration",
        type=float,
        default=DEFAULT_TITLE_CARD_SECONDS,
        help="How long to show the opening title card. Use 0 to infer from the first spoken sentence.",
    )
    parser.add_argument(
        "--skip-title-card",
        action="store_true",
        help="Do not render or overlay the opening Reddit title card.",
    )
    return parser


def validate_environment(use_script_cleanup=True, use_v3_directions=True):
    """Validate credentials needed by the selected generation path.

    V3 directions are created inside the optional OpenAI cleanup pass, so they
    do not independently require an OpenAI key when cleanup is disabled. The
    ``use_v3_directions`` parameter remains for backward compatibility.
    """
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if use_script_cleanup and not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")

    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(
            f"Missing required environment variables: {missing_list}. "
            "Create a .env file or export them before running the pipeline."
        )


def process_post(
    index,
    post_text,
    output_dir,
    video_manager,
    chars_per_caption,
    font_path,
    script_model,
    use_script_cleanup,
    use_v3_directions,
    title,
    category,
    subreddit_name,
    target_max_seconds,
    title_card_template,
    title_card_duration,
    use_title_card,
):
    audio_path = output_dir / f"output_{index}.mp3"
    subtitles_path = output_dir / f"subtitles_{index}.srt"
    final_video_path = output_dir / f"final_video_{index}.mp4"
    raw_script_path = output_dir / f"script_raw_{index}.txt"
    vocab_script_path = output_dir / f"script_vocab_{index}.txt"
    cleaned_script_path = output_dir / f"script_cleaned_{index}.txt"
    voice_choice_path = output_dir / f"voice_choice_{index}.txt"
    title_card_path = output_dir / f"title_card_{index}.png"
    post_metadata_path = output_dir / f"post_metadata_{index}.json"

    raw_script_path.write_text(post_text, encoding="utf-8")
    normalized_title = normalize_reddit_vocabulary(title)
    voiceover_text = normalize_reddit_vocabulary(post_text)
    vocab_script_path.write_text(voiceover_text, encoding="utf-8")
    rendered_title_card = None

    if use_title_card:
        rendered_title_card = render_title_card(
            title=normalized_title,
            output_path=title_card_path,
            template_path=title_card_template,
        )
        LOGGER.info("Rendered title card for post %s at %s", index, rendered_title_card)

    if use_script_cleanup:
        prepared_voiceover = prepare_voiceover(
            voiceover_text,
            model=script_model,
            add_v3_directions=use_v3_directions,
            category=category,
        )
        prepared_voiceover = finalize_prepared_voiceover(
            prepared_voiceover,
            category=category,
            target_max_seconds=target_max_seconds,
        )
        voiceover_text = prepared_voiceover["script"]
        selected_voice_gender = prepared_voiceover["voice_gender"]
        speaker_segments = prepared_voiceover["segments"]
        cleaned_script_path.write_text(voiceover_text, encoding="utf-8")
        LOGGER.info("Cleaned voiceover script for post %s at %s", index, cleaned_script_path)
    else:
        prepared_voiceover = finalize_prepared_voiceover(
            {
                "script": voiceover_text,
                "voice_gender": "female",
                "segments": [
                    {
                        "speaker": "Narrator",
                        "voice_gender": "female",
                        "text": voiceover_text,
                    }
                ],
            },
            category=category,
            target_max_seconds=target_max_seconds,
        )
        voiceover_text = prepared_voiceover["script"]
        selected_voice_gender = prepared_voiceover["voice_gender"]
        speaker_segments = prepared_voiceover["segments"]

    spoken_title_text = normalized_title
    selected_voice_name = (
        speaker_segments[0].get("voice_name")
        if speaker_segments
        else default_voice_name_for(category=category, voice_gender=selected_voice_gender)
    ) or default_voice_name_for(category=category, voice_gender=selected_voice_gender)

    selected_voice_id = resolve_voice_id(
        voice_name=selected_voice_name,
        voice_gender=selected_voice_gender,
        category=category,
    )
    voice_choice_path.write_text(
        "\n".join(
            [
                f"category={category}",
                f"subreddit={subreddit_name}",
                f"voice_gender={selected_voice_gender}",
                f"voice_name={selected_voice_name}",
                f"voice_id={selected_voice_id}",
                f"female_voice_id={DEFAULT_ELEVENLABS_FEMALE_VOICE_ID}",
                f"male_voice_id={DEFAULT_ELEVENLABS_MALE_VOICE_ID}",
            ]
            + [
                f"segment_{segment_index}={segment['speaker']}|{segment['voice_gender']}|{segment.get('voice_name') or ''}|{segment['text']}"
                for segment_index, segment in enumerate(speaker_segments)
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    LOGGER.info(
        "Selected %s narrator voice for post %s (%s)",
        selected_voice_gender,
        index,
        selected_voice_id,
    )

    generation_result = generate_voiceover_and_subtitles(
        voiceover_text,
        str(audio_path),
        str(subtitles_path),
        chars_per_caption=chars_per_caption,
        voice_id=selected_voice_id,
        category=category,
        segments=speaker_segments,
        spoken_title_text=spoken_title_text,
        return_metadata=True,
    )
    LOGGER.info("Generated voiceover for post %s at %s", index, audio_path)

    inferred_title_card_duration = generation_result.get("spoken_title_duration")
    if inferred_title_card_duration:
        LOGGER.info(
            "Measured spoken title duration for post %s: %.2fs",
            index,
            inferred_title_card_duration,
        )

    required_duration = get_audio_length(str(audio_path)) + 0.25
    video_clip = video_manager.get_video_clip(required_duration)

    try:
        LOGGER.info("Subtitles saved at %s", subtitles_path)

        add_subtitles_to_video(
            video_clip,
            str(subtitles_path),
            str(final_video_path),
            audio_path=str(audio_path),
            font_path=font_path,
            title_card_path=str(rendered_title_card) if rendered_title_card else None,
            title_card_duration=title_card_duration or inferred_title_card_duration or 0,
        )
    finally:
        video_clip.close()

    LOGGER.info("Final video created at %s", final_video_path)

    post_metadata = {
        "index": index,
        "title": title,
        "normalized_title": normalized_title,
        "category": category,
        "subreddit": subreddit_name,
        "final_video_path": str(final_video_path),
        "audio_path": str(audio_path),
        "subtitles_path": str(subtitles_path),
        "title_card_path": str(rendered_title_card) if rendered_title_card else None,
        "script_raw_path": str(raw_script_path),
        "script_vocab_path": str(vocab_script_path),
        "script_cleaned_path": str(cleaned_script_path) if use_script_cleanup else None,
        "voice_choice_path": str(voice_choice_path),
    }
    post_metadata_path.write_text(
        json.dumps(post_metadata, indent=2),
        encoding="utf-8",
    )
    LOGGER.info("Saved post metadata for post %s at %s", index, post_metadata_path)

    return final_video_path


def main():
    load_dotenv()
    args = build_parser().parse_args()
    validate_environment(
        use_script_cleanup=not args.skip_script_cleanup,
        use_v3_directions=not args.skip_v3_directions,
    )

    output_dir = Path(args.output_dir).expanduser().resolve()
    video_dir = Path(args.video_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)
    processed_index = load_processed_post_index(args.processed_posts_file)

    posts = scrape_reddit_posts(
        args.subreddit,
        limit=args.limit,
        filename=args.titles_file,
        processed_index=processed_index,
    )

    if not posts:
        raise RuntimeError(f"No usable posts were found in r/{args.subreddit}.")

    created_videos = []
    video_managers = {}
    for index, post in enumerate(posts):
        post_text = post["text"] if isinstance(post, dict) else post
        title = (
            post.get("title", post_text.split(".", 1)[0])
            if isinstance(post, dict)
            else post_text.split(".", 1)[0]
        )
        subreddit_name = (
            post.get("subreddit", args.subreddit) if isinstance(post, dict) else args.subreddit
        )
        category = (
            post.get("category", infer_category_for_subreddit(subreddit_name))
            if isinstance(post, dict)
            else infer_category_for_subreddit(subreddit_name)
        )
        post_id = post.get("id") if isinstance(post, dict) else None
        post_hash = post.get("hash") if isinstance(post, dict) else None
        category_config = get_category_config(category)
        resolved_background_speed = (
            args.background_speed
            if args.background_speed is not None
            else category_config["default_background_speed"]
        )
        video_root_for_category = resolve_video_dir(video_dir, category)
        manager_key = (str(video_root_for_category), resolved_background_speed)
        if manager_key not in video_managers:
            video_managers[manager_key] = VideoManager(
                download_path=str(video_root_for_category),
                output_path=str(output_dir),
                background_speed=resolved_background_speed,
            )
        video_manager = video_managers[manager_key]

        try:
            final_video_path = process_post(
                index=index,
                post_text=post_text,
                output_dir=output_dir,
                video_manager=video_manager,
                chars_per_caption=args.chars_per_caption,
                font_path=args.font_path,
                script_model=args.script_model,
                use_script_cleanup=not args.skip_script_cleanup,
                use_v3_directions=not args.skip_v3_directions,
                title=title,
                category=category,
                subreddit_name=subreddit_name,
                target_max_seconds=category_config["target_max_seconds"],
                title_card_template=args.title_card_template,
                title_card_duration=args.title_card_duration,
                use_title_card=not args.skip_title_card,
            )
            created_videos.append(final_video_path)
            append_processed_post(
                args.processed_posts_file,
                title=title,
                post_id=post_id,
                post_hash=post_hash,
                subreddit=subreddit_name,
                category=category,
                output_video=str(final_video_path),
            )
            if post_id:
                processed_index["ids"].add(post_id)
            if post_hash:
                processed_index["hashes"].add(post_hash)
        except Exception:
            LOGGER.exception("Error processing post %s", index)

    if not created_videos:
        raise RuntimeError("The pipeline did not produce any videos.")

    LOGGER.info("Created %s video(s) in %s", len(created_videos), output_dir)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        LOGGER.error("%s", exc)
        raise SystemExit(1) from exc
