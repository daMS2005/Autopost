import argparse
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from content_config import CATEGORY_CONFIGS, normalize_subreddit_name


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_QUEUE_PATH = PROJECT_ROOT / "data" / "local_schedules" / "instagram_queue.json"


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Generate a weekly batch of Reddit videos and queue them for the "
            "local Instagram scheduler."
        )
    )
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--subreddits", default="all")
    parser.add_argument("--categories", default="story,horror,ask")
    parser.add_argument(
        "--start-date",
        default=None,
        help=(
            "First posting date in YYYY-MM-DD. Defaults to Monday when run on "
            "Sunday, otherwise today."
        ),
    )
    parser.add_argument("--first-time", default="12:00")
    parser.add_argument("--subreddit-gap-minutes", type=int, default=45)
    parser.add_argument("--parts-gap-minutes", type=int, default=20)
    parser.add_argument("--daily-times", default="")
    parser.add_argument("--chars-per-caption", type=int, default=22)
    parser.add_argument("--output-root", default="output/weekly_render")
    parser.add_argument("--publish-root", default="output/publish/local-weekly")
    parser.add_argument("--processed-posts-file", default="data/processed_posts.jsonl")
    parser.add_argument("--queue-path", default=str(DEFAULT_QUEUE_PATH))
    parser.add_argument("--slow-mo-ms", type=int, default=50)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--skip-launch-agent-install",
        action="store_true",
        help="Queue posts but do not install/refresh the macOS LaunchAgent.",
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Only queue already-rendered videos from the weekly output folder.",
    )
    parser.add_argument(
        "--keep-source-renders",
        action="store_true",
        help="Keep generated source render files after each scheduled post succeeds.",
    )
    return parser.parse_args()


def parse_categories(value):
    categories = [item.strip().lower() for item in str(value or "").split(",") if item.strip()]
    if not categories:
        raise ValueError("At least one category is required.")
    return categories


def resolve_subreddits(raw_value, categories):
    if str(raw_value or "").strip().lower() == "all":
        subreddits = []
        for category in categories:
            for subreddit in sorted(CATEGORY_CONFIGS.get(category, {}).get("subreddits", [])):
                normalized = normalize_subreddit_name(subreddit)
                if normalized and normalized not in subreddits:
                    subreddits.append(normalized)
        return subreddits
    subreddits = [
        normalize_subreddit_name(item)
        for item in str(raw_value or "").split(",")
        if normalize_subreddit_name(item)
    ]
    if not subreddits:
        raise ValueError("At least one subreddit is required.")
    return subreddits


def default_start_date():
    today = date.today()
    if today.weekday() == 6:
        return today + timedelta(days=1)
    return today


def run_command(command, env):
    print("\n$ " + " ".join(str(part) for part in command), flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def main():
    args = parse_args()
    categories = parse_categories(args.categories)
    subreddits = resolve_subreddits(args.subreddits, categories)
    start_date = date.fromisoformat(args.start_date) if args.start_date else default_start_date()
    days = max(int(args.days or 7), 1)
    python = sys.executable
    env = os.environ.copy()

    output_root = (PROJECT_ROOT / args.output_root).resolve() / start_date.isoformat()
    output_root.mkdir(parents=True, exist_ok=True)

    if not args.skip_generation:
        for subreddit in subreddits:
            subreddit_output = output_root / subreddit
            subreddit_output.mkdir(parents=True, exist_ok=True)
            run_command(
                [
                    python,
                    "main.py",
                    "--subreddit",
                    subreddit,
                    "--limit",
                    str(days),
                    "--output-dir",
                    str(subreddit_output),
                    "--chars-per-caption",
                    str(args.chars_per_caption),
                    "--processed-posts-file",
                    args.processed_posts_file,
                ],
                env,
            )

    schedule_command = [
        python,
        "publish_cli.py",
        "instagram-local-schedule-weekly",
        "--rendered-dir",
        str(output_root),
        "--publish-root",
        args.publish_root,
        "--subreddits",
        ",".join(subreddits),
        "--categories",
        args.categories,
        "--days",
        str(days),
        "--start-date",
        start_date.isoformat(),
        "--first-time",
        args.first_time,
        "--subreddit-gap-minutes",
        str(args.subreddit_gap_minutes),
        "--parts-gap-minutes",
        str(args.parts_gap_minutes),
        "--queue-path",
        args.queue_path,
        "--slow-mo-ms",
        str(args.slow_mo_ms),
        "--cleanup-after-success",
    ]
    if not args.keep_source_renders:
        schedule_command.append("--cleanup-source-after-success")
    if args.daily_times:
        schedule_command.extend(["--daily-times", args.daily_times])
    if args.headless:
        schedule_command.append("--headless")
    run_command(schedule_command, env)

    if not args.skip_launch_agent_install:
        run_command(
            [
                python,
                "publish_cli.py",
                "instagram-local-install-launch-agent",
                "--queue-path",
                args.queue_path,
            ],
            env,
        )

    wake_command = [
        python,
        "publish_cli.py",
        "instagram-local-wake-commands",
        "--queue-path",
        args.queue_path,
        "--wake-lead-minutes",
        "10",
    ]
    print("\nWake commands, if you want macOS to schedule wakeups:", flush=True)
    completed = subprocess.run(
        wake_command,
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    print(completed.stdout.strip(), flush=True)
    print(
        json.dumps(
            {
                "status": "weekly_queue_ready",
                "start_date": start_date.isoformat(),
                "days": days,
                "subreddits": subreddits,
                "rendered_dir": str(output_root),
                "queue_path": str(Path(args.queue_path).expanduser().resolve()),
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
