import argparse
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from reddit_scraper import scrape_reddit_posts
from reddit_vocabulary import normalize_reddit_vocabulary
from script_rewriter import rewrite_for_voiceover
from subtitle_editor import add_subtitles_to_video
from text_to_speech import generate_voiceover, get_audio_length
from title_card import DEFAULT_TEMPLATE_PATH, render_title_card
from transcriber import transcribe_audio
from video_downloader import VideoManager


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_VIDEO_DIR = PROJECT_ROOT / "videos"
DEFAULT_TITLE_CARD_SECONDS = 0
REQUIRED_ENV_VARS = (
    "CLIENT_ID_REDDIT",
    "CLIENT_SECRET_REDDIT",
    "ASSEMBLYAI_API_KEY",
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Generate narrated Reddit videos with subtitles."
    )
    parser.add_argument("--subreddit", default=os.getenv("SUBREDDIT", "AITAH"))
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--chars-per-caption", type=int, default=22)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--video-dir", default=str(DEFAULT_VIDEO_DIR))
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


def validate_environment(use_script_cleanup=True):
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
    title,
    title_card_template,
    title_card_duration,
    use_title_card,
):
    audio_path = output_dir / f"output_{index}.mp3"
    temp_video_path = output_dir / f"temp_video_{index}.mp4"
    subtitles_path = output_dir / f"subtitles_{index}.srt"
    final_video_path = output_dir / f"final_video_{index}.mp4"
    raw_script_path = output_dir / f"script_raw_{index}.txt"
    vocab_script_path = output_dir / f"script_vocab_{index}.txt"
    cleaned_script_path = output_dir / f"script_cleaned_{index}.txt"
    title_card_path = output_dir / f"title_card_{index}.png"

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
        logging.info("Rendered title card for post %s at %s", index, rendered_title_card)

    if use_script_cleanup:
        voiceover_text = rewrite_for_voiceover(voiceover_text, model=script_model)
        cleaned_script_path.write_text(voiceover_text, encoding="utf-8")
        logging.info("Cleaned voiceover script for post %s at %s", index, cleaned_script_path)

    generate_voiceover(voiceover_text, str(audio_path))
    logging.info("Generated voiceover for post %s at %s", index, audio_path)

    required_duration = get_audio_length(str(audio_path)) + 0.25
    video_clip = video_manager.get_video_clip(required_duration)

    try:
        video_clip.write_videofile(
            str(temp_video_path),
            codec="libx264",
            audio=False,
            fps=video_clip.fps or 24,
        )
    finally:
        video_clip.close()

    transcribe_audio(
        str(audio_path),
        str(subtitles_path),
        chars_per_caption=chars_per_caption,
    )
    logging.info("Subtitles saved at %s", subtitles_path)

    add_subtitles_to_video(
        str(temp_video_path),
        str(subtitles_path),
        str(final_video_path),
        audio_path=str(audio_path),
        font_path=font_path,
        title_card_path=str(rendered_title_card) if rendered_title_card else None,
        title_card_duration=title_card_duration,
    )
    logging.info("Final video created at %s", final_video_path)

    return final_video_path


def main():
    load_dotenv()
    args = build_parser().parse_args()
    validate_environment(use_script_cleanup=not args.skip_script_cleanup)

    output_dir = Path(args.output_dir).expanduser().resolve()
    video_dir = Path(args.video_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    video_manager = VideoManager(download_path=str(video_dir), output_path=str(output_dir))
    posts = scrape_reddit_posts(
        args.subreddit,
        limit=args.limit,
        filename=args.titles_file,
    )

    if not posts:
        raise RuntimeError(f"No usable posts were found in r/{args.subreddit}.")

    created_videos = []
    for index, post in enumerate(posts):
        post_text = post["text"] if isinstance(post, dict) else post
        title = post.get("title", post_text.split(".", 1)[0]) if isinstance(post, dict) else post_text.split(".", 1)[0]

        try:
            created_videos.append(
                process_post(
                    index=index,
                    post_text=post_text,
                    output_dir=output_dir,
                    video_manager=video_manager,
                    chars_per_caption=args.chars_per_caption,
                    font_path=args.font_path,
                    script_model=args.script_model,
                    use_script_cleanup=not args.skip_script_cleanup,
                    title=title,
                    title_card_template=args.title_card_template,
                    title_card_duration=args.title_card_duration,
                    use_title_card=not args.skip_title_card,
                )
            )
        except Exception as exc:
            logging.exception("Error processing post %s: %s", index, exc)

    if not created_videos:
        raise RuntimeError("The pipeline did not produce any videos.")

    logging.info("Created %s video(s) in %s", len(created_videos), output_dir)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc
