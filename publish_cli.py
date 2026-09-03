import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from content_config import CATEGORY_CONFIGS, normalize_subreddit_name
from social_publishers import (
    DEFAULT_YOUTUBE_CLIENT_SECRETS_FILE,
    DEFAULT_YOUTUBE_TOKEN_FILE,
    TikTokPublisher,
    YouTubePublisher,
    build_publish_metadata,
)
from video_splitter import load_post_metadata_for_video, sanitize_slug, split_video_for_publishing
from web_publishers import (
    InstagramWebPublisher,
    TikTokWebPublisher,
    YouTubeWebPublisher,
    get_manifest_part,
    load_manifest,
)


def build_parser():
    parser = argparse.ArgumentParser(description="Social publishing helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tiktok_auth = subparsers.add_parser("tiktok-auth-url")
    tiktok_auth.add_argument("--redirect-uri", required=True)
    tiktok_auth.add_argument(
        "--scopes",
        default="user.info.basic,video.publish",
        help="Comma-separated TikTok scopes.",
    )

    tiktok_exchange = subparsers.add_parser("tiktok-exchange-code")
    tiktok_exchange.add_argument("--redirect-uri", required=True)
    tiktok_exchange.add_argument("--code", required=True)
    tiktok_exchange.add_argument("--code-verifier", default=None)

    tiktok_info = subparsers.add_parser("tiktok-creator-info")

    prepare_video = subparsers.add_parser("prepare-video")
    prepare_video.add_argument("--video-path", required=True)
    prepare_video.add_argument("--title", default=None)
    prepare_video.add_argument("--category", default=None)
    prepare_video.add_argument("--subreddit", default=None)
    prepare_video.add_argument("--title-card-path", default=None)
    prepare_video.add_argument("--output-dir", required=True)
    prepare_video.add_argument("--target-seconds", type=float, default=60.0)
    prepare_video.add_argument("--min-last-part-seconds", type=float, default=35.0)

    youtube_upload = subparsers.add_parser("youtube-upload")
    youtube_upload.add_argument("--video-path", required=True)
    youtube_upload.add_argument("--title", required=True)
    youtube_upload.add_argument("--description", default="")
    youtube_upload.add_argument("--tags", default="")
    youtube_upload.add_argument("--privacy-status", default="private")
    youtube_upload.add_argument(
        "--client-secrets-file",
        default=str(DEFAULT_YOUTUBE_CLIENT_SECRETS_FILE),
    )
    youtube_upload.add_argument(
        "--token-file",
        default=str(DEFAULT_YOUTUBE_TOKEN_FILE),
    )

    youtube_web_upload = subparsers.add_parser("youtube-web-upload")
    youtube_web_upload.add_argument("--video-path", required=True)
    youtube_web_upload.add_argument("--title", required=True)
    youtube_web_upload.add_argument("--description", default="")
    youtube_web_upload.add_argument("--privacy-status", default="PRIVATE")
    youtube_web_upload.add_argument("--headless", action="store_true")
    youtube_web_upload.add_argument("--slow-mo-ms", type=int, default=0)

    tiktok_web_upload = subparsers.add_parser("tiktok-web-upload")
    tiktok_web_upload.add_argument("--video-path", required=True)
    tiktok_web_upload.add_argument("--caption", required=True)
    tiktok_web_upload.add_argument("--headless", action="store_true")
    tiktok_web_upload.add_argument("--slow-mo-ms", type=int, default=0)

    instagram_web_upload = subparsers.add_parser("instagram-web-upload")
    instagram_web_upload.add_argument("--video-path", required=True)
    instagram_web_upload.add_argument("--cover-path", default=None)
    instagram_web_upload.add_argument(
        "--caption",
        default=None,
        help="Instagram caption. Defaults to --title, inferred post metadata title, or the video filename.",
    )
    instagram_web_upload.add_argument(
        "--title",
        default=None,
        help="Title to use as the Instagram caption when --caption is omitted.",
    )
    instagram_web_upload.add_argument("--headless", action="store_true")
    instagram_web_upload.add_argument("--slow-mo-ms", type=int, default=0)
    instagram_web_upload.add_argument(
        "--schedule-at",
        default=None,
        help="Optional local date/time for Instagram native scheduling, e.g. '2026-05-22 18:30'.",
    )

    instagram_parts_upload = subparsers.add_parser("instagram-web-upload-parts")
    instagram_parts_upload.add_argument("--video-path", required=True)
    instagram_parts_upload.add_argument("--title", default=None)
    instagram_parts_upload.add_argument("--category", default=None)
    instagram_parts_upload.add_argument("--subreddit", default=None)
    instagram_parts_upload.add_argument("--title-card-path", default=None)
    instagram_parts_upload.add_argument("--output-dir", required=True)
    instagram_parts_upload.add_argument("--target-seconds", type=float, default=60.0)
    instagram_parts_upload.add_argument("--min-last-part-seconds", type=float, default=35.0)
    instagram_parts_upload.add_argument("--part-number", type=int, default=None)
    instagram_parts_upload.add_argument("--headless", action="store_true")
    instagram_parts_upload.add_argument("--slow-mo-ms", type=int, default=0)
    instagram_parts_upload.add_argument(
        "--schedule-at",
        default=None,
        help="Optional local date/time for Instagram native scheduling of the first selected part.",
    )
    instagram_parts_upload.add_argument(
        "--schedule-gap-minutes",
        type=int,
        default=0,
        help="Minutes to add between scheduled parts when uploading multiple parts.",
    )
    instagram_parts_upload.add_argument(
        "--cleanup-after-success",
        action="store_true",
        help="Delete prepared local part/cover files only after all selected parts are shared or scheduled.",
    )

    post_manifest_part = subparsers.add_parser("post-manifest-part-web")
    post_manifest_part.add_argument("--manifest-path", required=True)
    post_manifest_part.add_argument("--part-number", type=int, required=True)
    post_manifest_part.add_argument(
        "--platform",
        required=True,
        choices=("youtube", "tiktok", "instagram"),
    )
    post_manifest_part.add_argument("--headless", action="store_true")
    post_manifest_part.add_argument("--slow-mo-ms", type=int, default=0)
    post_manifest_part.add_argument(
        "--schedule-at",
        default=None,
        help="Optional local date/time for Instagram native scheduling, e.g. '2026-05-22 18:30'.",
    )
    post_manifest_part.add_argument(
        "--cleanup-after-success",
        action="store_true",
        help="Delete the posted local part/cover file only after Instagram confirms shared or scheduled.",
    )

    weekly_instagram = subparsers.add_parser(
        "instagram-weekly-category-run",
        aliases=["instagram-weekly-subreddit-run"],
    )
    weekly_instagram.add_argument(
        "--rendered-dir",
        default="output",
        help="Directory containing final_video_*.mp4 and post_metadata_*.json files.",
    )
    weekly_instagram.add_argument(
        "--publish-root",
        default="output/publish/weekly",
        help="Directory where weekly split manifests and part files are written.",
    )
    weekly_instagram.add_argument(
        "--subreddits",
        default="all",
        help="Comma-separated subreddits to post every day, or 'all' for every configured subreddit.",
    )
    weekly_instagram.add_argument(
        "--categories",
        default="story,horror,ask",
        help="Categories used when --subreddits all is selected.",
    )
    weekly_instagram.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to cover. Use 7 for a Monday-through-Sunday run.",
    )
    weekly_instagram.add_argument(
        "--start-date",
        default=None,
        help="Week start date in YYYY-MM-DD. Defaults to today.",
    )
    weekly_instagram.add_argument(
        "--daily-times",
        default="",
        help="Optional comma-separated local posting times by subreddit or category, e.g. 'aitah=18:00,nosleep=21:00,ask=15:00'.",
    )
    weekly_instagram.add_argument(
        "--first-time",
        default="12:00",
        help="Default local time for the first subreddit slot when no exact daily time is configured.",
    )
    weekly_instagram.add_argument(
        "--subreddit-gap-minutes",
        type=int,
        default=45,
        help="Minutes between subreddit slots when no exact daily time is configured.",
    )
    weekly_instagram.add_argument(
        "--parts-gap-minutes",
        type=int,
        default=20,
        help="Minutes between parts of the same scheduled video.",
    )
    weekly_instagram.add_argument("--target-seconds", type=float, default=60.0)
    weekly_instagram.add_argument("--min-last-part-seconds", type=float, default=35.0)
    weekly_instagram.add_argument("--headless", action="store_true")
    weekly_instagram.add_argument("--slow-mo-ms", type=int, default=0)
    weekly_instagram.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the weekly plan without opening Instagram or preparing videos.",
    )
    weekly_instagram.add_argument(
        "--cleanup-after-success",
        action="store_true",
        help="Delete weekly prepared local part/cover files only after each video's parts are shared or scheduled.",
    )
    weekly_instagram.add_argument(
        "--cleanup-source-after-success",
        action="store_true",
        help="Delete source render files after the local scheduled post succeeds.",
    )

    local_weekly = subparsers.add_parser("instagram-local-schedule-weekly")
    for action in weekly_instagram._actions:
        if not action.option_strings:
            continue
        if action.dest in {"help", "dry_run"}:
            continue
        kwargs = {
            "default": action.default,
            "help": action.help,
            "required": getattr(action, "required", False),
        }
        if getattr(action, "type", None):
            kwargs["type"] = action.type
        if getattr(action, "choices", None):
            kwargs["choices"] = action.choices
        if getattr(action, "nargs", None):
            kwargs["nargs"] = action.nargs
        if isinstance(action, argparse._StoreTrueAction):
            local_weekly.add_argument(*action.option_strings, action="store_true", help=action.help)
        else:
            local_weekly.add_argument(*action.option_strings, **kwargs)
    local_weekly.add_argument(
        "--queue-path",
        default="data/local_schedules/instagram_queue.json",
        help="Local JSON queue file for due Instagram posts.",
    )

    local_single = subparsers.add_parser("instagram-local-schedule-video")
    local_single.add_argument("--video-path", required=True)
    local_single.add_argument("--metadata-path", default=None)
    local_single.add_argument("--title", default=None)
    local_single.add_argument("--category", default=None)
    local_single.add_argument("--subreddit", default=None)
    local_single.add_argument(
        "--run-at",
        default=None,
        help="Local run time, e.g. '2026-05-21 20:45'. Defaults to now.",
    )
    local_single.add_argument(
        "--publish-root",
        default="output/publish/local-single",
    )
    local_single.add_argument(
        "--queue-path",
        default="data/local_schedules/instagram_queue.json",
    )
    local_single.add_argument("--target-seconds", type=float, default=60.0)
    local_single.add_argument("--min-last-part-seconds", type=float, default=35.0)
    local_single.add_argument("--parts-gap-minutes", type=int, default=20)
    local_single.add_argument("--headless", action="store_true")
    local_single.add_argument("--slow-mo-ms", type=int, default=0)
    local_single.add_argument("--cleanup-after-success", action="store_true")
    local_single.add_argument("--cleanup-source-after-success", action="store_true")

    local_run_due = subparsers.add_parser("instagram-local-run-due")
    local_run_due.add_argument(
        "--queue-path",
        default="data/local_schedules/instagram_queue.json",
    )
    local_run_due.add_argument(
        "--log-path",
        default="data/local_schedules/instagram_scheduler.log",
    )
    local_run_due.add_argument(
        "--due-window-minutes",
        type=int,
        default=2,
        help="Post items due now or within this many minutes.",
    )
    local_run_due.add_argument("--max-attempts", type=int, default=3)

    local_install = subparsers.add_parser("instagram-local-install-launch-agent")
    local_install.add_argument(
        "--queue-path",
        default="data/local_schedules/instagram_queue.json",
    )
    local_install.add_argument(
        "--log-path",
        default="data/local_schedules/instagram_scheduler.log",
    )
    local_install.add_argument("--label", default="com.acc.instagram-local-scheduler")
    local_install.add_argument("--python-path", default="venv/bin/python")
    local_install.add_argument("--interval-seconds", type=int, default=300)
    local_install.add_argument("--due-window-minutes", type=int, default=2)
    local_install.add_argument("--max-attempts", type=int, default=3)

    local_wake = subparsers.add_parser("instagram-local-wake-commands")
    local_wake.add_argument(
        "--queue-path",
        default="data/local_schedules/instagram_queue.json",
    )
    local_wake.add_argument("--wake-lead-minutes", type=int, default=10)

    return parser


def parse_schedule_at(value):
    value = str(value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError(
            "Schedule time must look like '2026-05-22 18:30' or ISO format."
        ) from exc


def part_schedule_time(first_schedule_at, index, gap_minutes):
    scheduled_for = parse_schedule_at(first_schedule_at)
    if scheduled_for is None:
        return None
    return scheduled_for + timedelta(minutes=max(int(gap_minutes or 0), 0) * index)


def parse_date(value):
    if not value:
        return datetime.now().date()
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def parse_categories(value):
    categories = [item.strip().lower() for item in str(value or "").split(",") if item.strip()]
    if not categories:
        raise ValueError("At least one category is required.")
    return categories


def configured_subreddits_for_categories(categories):
    subreddits = []
    for category in categories:
        for subreddit in sorted(CATEGORY_CONFIGS.get(category, {}).get("subreddits", [])):
            normalized = normalize_subreddit_name(subreddit)
            if normalized and normalized not in subreddits:
                subreddits.append(normalized)
    return subreddits


def parse_subreddits(value, categories):
    raw_value = str(value or "").strip()
    if not raw_value or raw_value.lower() == "all":
        subreddits = configured_subreddits_for_categories(categories)
    else:
        subreddits = [
            normalize_subreddit_name(item)
            for item in raw_value.split(",")
            if normalize_subreddit_name(item)
        ]
    if not subreddits:
        raise ValueError("At least one subreddit is required.")
    return subreddits


def parse_time_value(value):
    return datetime.strptime(str(value).strip(), "%H:%M").time()


def parse_daily_times(value):
    result = {}
    for item in str(value or "").split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError("Daily times must look like 'aitah=18:00,nosleep=21:00'.")
        key, time_value = item.split("=", 1)
        result[normalize_subreddit_name(key)] = parse_time_value(time_value)
    return result


def discover_rendered_posts(rendered_dir):
    rendered_root = Path(rendered_dir).expanduser().resolve()
    posts_by_subreddit = {}
    for metadata_path in rendered_root.rglob("post_metadata_*.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        video_path = Path(metadata.get("final_video_path") or "").expanduser()
        if not video_path.is_absolute():
            video_path = (metadata_path.parent / video_path).resolve()
        if not video_path.exists():
            continue
        category = str(metadata.get("category") or "story").strip().lower()
        subreddit = normalize_subreddit_name(metadata.get("subreddit"))
        if not subreddit:
            continue
        post = {
            "metadata_path": metadata_path.resolve(),
            "metadata": metadata,
            "video_path": video_path.resolve(),
            "category": category,
            "subreddit": subreddit,
            "mtime": metadata_path.stat().st_mtime,
        }
        posts_by_subreddit.setdefault(subreddit, []).append(post)

    for posts in posts_by_subreddit.values():
        posts.sort(key=lambda post: post["mtime"], reverse=True)
    return posts_by_subreddit


def build_weekly_category_plan(args):
    categories = parse_categories(args.categories)
    subreddits = parse_subreddits(args.subreddits, categories)
    days = max(int(args.days or 7), 1)
    start_date = parse_date(args.start_date)
    daily_times = parse_daily_times(args.daily_times)
    first_time = parse_time_value(args.first_time)
    subreddit_gap_minutes = max(int(args.subreddit_gap_minutes or 0), 0)
    posts_by_subreddit = discover_rendered_posts(args.rendered_dir)
    publish_root = Path(args.publish_root).expanduser().resolve() / start_date.isoformat()

    missing = [
        subreddit
        for subreddit in subreddits
        if len(posts_by_subreddit.get(subreddit, [])) < days
    ]
    if missing:
        details = ", ".join(
            f"{subreddit} has {len(posts_by_subreddit.get(subreddit, []))}/{days}"
            for subreddit in missing
        )
        raise RuntimeError(
            "Not enough rendered videos for the weekly subreddit plan: "
            f"{details}. Generate more videos before running this."
        )

    plan = []
    selected_by_subreddit = {}
    for subreddit in subreddits:
        selected = list(reversed(posts_by_subreddit[subreddit][:days]))
        selected_by_subreddit[subreddit] = selected

    for day_index in range(days):
        post_date = start_date + timedelta(days=day_index)
        for subreddit_index, subreddit in enumerate(subreddits):
            post = selected_by_subreddit[subreddit][day_index]
            metadata = post["metadata"]
            category = post["category"]
            daily_time = daily_times.get(subreddit) or daily_times.get(category)
            if daily_time is None:
                daily_time = (
                    datetime.combine(post_date, first_time)
                    + timedelta(minutes=subreddit_gap_minutes * subreddit_index)
                ).time()
            schedule_at = None
            if day_index > 0:
                schedule_at = datetime.combine(post_date, daily_time)
            title = metadata.get("title") or post["video_path"].stem
            slug = sanitize_slug(title)
            manifest_dir = publish_root / post_date.isoformat() / category / subreddit / slug
            plan.append(
                {
                    "day_index": day_index,
                    "date": post_date.isoformat(),
                    "category": category,
                    "subreddit": subreddit,
                    "schedule_at": schedule_at,
                    "video_path": str(post["video_path"]),
                    "manifest_dir": str(manifest_dir),
                    "metadata": metadata,
                    "metadata_path": str(post["metadata_path"]),
                }
            )
    return plan


def printable_weekly_plan(plan, parts_gap_minutes):
    printable = []
    for item in plan:
        mode = "post-now" if item["schedule_at"] is None else "schedule"
        printable.append(
            {
                "date": item["date"],
                "category": item["category"],
                "subreddit": item["subreddit"],
                "mode": mode,
                "first_part_at": item["schedule_at"].isoformat(timespec="minutes")
                if item["schedule_at"]
                else None,
                "parts_gap_minutes": parts_gap_minutes,
                "title": item["metadata"].get("title"),
                "video_path": item["video_path"],
                "manifest_dir": item["manifest_dir"],
            }
        )
    return printable


def prepare_manifest_for_weekly_item(item, target_seconds, min_last_part_seconds):
    metadata = item["metadata"]
    return split_video_for_publishing(
        item["video_path"],
        item["manifest_dir"],
        title=metadata.get("title") or Path(item["video_path"]).stem,
        category=item["category"],
        subreddit=item["subreddit"],
        title_card_path=metadata.get("title_card_path"),
        target_seconds=target_seconds,
        min_last_part_seconds=min_last_part_seconds,
    )


def upload_manifest_parts_to_instagram(publisher, manifest, schedule_at, parts_gap_minutes):
    responses = []
    for index, part in enumerate(manifest.get("parts", [])):
        part_schedule_at = (
            schedule_at + timedelta(minutes=max(int(parts_gap_minutes or 0), 0) * index)
            if schedule_at
            else None
        )
        responses.append(
            publisher.upload_video(
                part["video_path"],
                caption=part["caption"],
                cover_path=part.get("cover_path"),
                schedule_at=part_schedule_at,
            )
        )
    return responses


def successful_publish_responses(responses):
    return bool(responses) and all(
        str(response.get("status") or "").lower() in {"shared", "scheduled"}
        for response in responses
    )


def cleanup_manifest_part_files(parts):
    deleted = []
    for part in parts:
        for key in ("video_path", "cover_path"):
            path_value = part.get(key)
            if not path_value:
                continue
            path = Path(path_value).expanduser()
            try:
                if path.exists() and path.is_file():
                    path.unlink()
                    deleted.append(str(path.resolve()))
            except Exception as exc:
                deleted.append(f"failed:{path}:{exc}")
    return deleted


def cleanup_manifest_directory_if_empty(manifest):
    manifest_path_value = manifest.get("manifest_path")
    if not manifest_path_value:
        return []
    manifest_path = Path(manifest_path_value).expanduser().resolve()
    deleted = []
    directory = manifest_path.parent
    try:
        for child in sorted(directory.rglob("*"), reverse=True):
            if child == manifest_path:
                continue
            if child.is_dir() and not any(child.iterdir()):
                child.rmdir()
                deleted.append(str(child.resolve()))
    except Exception:
        pass
    return deleted


def mark_manifest_cleanup(manifest, deleted_files):
    manifest_copy = dict(manifest)
    manifest_path_value = manifest_copy.get("manifest_path")
    if not manifest_path_value:
        return manifest_copy
    manifest_path = Path(manifest_path_value).expanduser().resolve()
    manifest_copy["local_cleanup"] = {
        "deleted_files": deleted_files,
        "completed_at": datetime.now().isoformat(timespec="seconds"),
    }
    manifest_path.write_text(json.dumps(manifest_copy, indent=2), encoding="utf-8")
    return manifest_copy


def cleanup_manifest_after_success(manifest, parts):
    deleted = cleanup_manifest_part_files(parts)
    deleted.extend(cleanup_manifest_directory_if_empty(manifest))
    mark_manifest_cleanup(manifest, deleted)
    return deleted


def main():
    args = build_parser().parse_args()

    if args.command == "tiktok-auth-url":
        publisher = TikTokPublisher()
        scopes = tuple(scope.strip() for scope in args.scopes.split(",") if scope.strip())
        url, state = publisher.build_authorization_url(args.redirect_uri, scopes=scopes)
        print(json.dumps({"authorization_url": url, "state": state}, indent=2))
        return

    if args.command == "tiktok-exchange-code":
        publisher = TikTokPublisher()
        tokens = publisher.exchange_code_for_token(
            code=args.code,
            redirect_uri=args.redirect_uri,
            code_verifier=args.code_verifier,
        )
        print(json.dumps(tokens, indent=2))
        return

    if args.command == "tiktok-creator-info":
        publisher = TikTokPublisher()
        print(json.dumps(publisher.query_creator_info(), indent=2))
        return

    if args.command == "prepare-video":
        inferred_metadata = load_post_metadata_for_video(args.video_path)
        title = args.title or (inferred_metadata or {}).get("title")
        category = args.category or (inferred_metadata or {}).get("category")
        subreddit = args.subreddit or (inferred_metadata or {}).get("subreddit")
        title_card_path = args.title_card_path or (inferred_metadata or {}).get("title_card_path")
        if not title:
            raise RuntimeError(
                "No title was provided and no post metadata could be inferred from the video path."
            )
        manifest = split_video_for_publishing(
            args.video_path,
            args.output_dir,
            title=title,
            category=category,
            subreddit=subreddit,
            title_card_path=title_card_path,
            target_seconds=args.target_seconds,
            min_last_part_seconds=args.min_last_part_seconds,
        )
        print(json.dumps(manifest, indent=2))
        return

    if args.command == "youtube-upload":
        publisher = YouTubePublisher(
            client_secrets_file=args.client_secrets_file,
            token_file=args.token_file,
        )
        metadata = build_publish_metadata(
            title=args.title,
            description=args.description,
            tags=[tag.strip() for tag in args.tags.split(",") if tag.strip()],
            privacy_status=args.privacy_status,
        )
        response = publisher.upload_video(Path(args.video_path), metadata)
        print(json.dumps(response, indent=2))
        return

    if args.command == "youtube-web-upload":
        with YouTubeWebPublisher(
            headless=args.headless,
            slow_mo_ms=args.slow_mo_ms,
        ) as publisher:
            response = publisher.upload_video(
                args.video_path,
                title=args.title,
                description=args.description,
                privacy_status=args.privacy_status,
            )
        print(json.dumps(response, indent=2))
        return

    if args.command == "tiktok-web-upload":
        with TikTokWebPublisher(
            headless=args.headless,
            slow_mo_ms=args.slow_mo_ms,
        ) as publisher:
            response = publisher.upload_video(
                args.video_path,
                caption=args.caption,
            )
        print(json.dumps(response, indent=2))
        return

    if args.command == "instagram-web-upload":
        inferred_metadata = load_post_metadata_for_video(args.video_path) or {}
        caption = (
            args.caption
            or args.title
            or inferred_metadata.get("title")
            or Path(args.video_path).expanduser().stem
        )
        with InstagramWebPublisher(
            headless=args.headless,
            slow_mo_ms=args.slow_mo_ms,
        ) as publisher:
            response = publisher.upload_video(
                args.video_path,
                caption=caption,
                cover_path=args.cover_path,
                schedule_at=args.schedule_at,
            )
        print(json.dumps(response, indent=2))
        return

    if args.command == "instagram-web-upload-parts":
        inferred_metadata = load_post_metadata_for_video(args.video_path) or {}
        title = args.title or inferred_metadata.get("title")
        category = args.category or inferred_metadata.get("category")
        subreddit = args.subreddit or inferred_metadata.get("subreddit")
        title_card_path = args.title_card_path or inferred_metadata.get("title_card_path")
        if not title:
            raise RuntimeError(
                "No title was provided and no post metadata could be inferred from the video path."
            )
        manifest = split_video_for_publishing(
            args.video_path,
            args.output_dir,
            title=title,
            category=category,
            subreddit=subreddit,
            title_card_path=title_card_path,
            target_seconds=args.target_seconds,
            min_last_part_seconds=args.min_last_part_seconds,
        )
        parts = manifest.get("parts", [])
        if args.part_number is not None:
            parts = [get_manifest_part(manifest, args.part_number)]

        responses = []
        schedule_gap_minutes = max(int(args.schedule_gap_minutes or 0), 0)
        with InstagramWebPublisher(
            headless=args.headless,
            slow_mo_ms=args.slow_mo_ms,
        ) as publisher:
            for index, part in enumerate(parts):
                responses.append(
                    publisher.upload_video(
                        part["video_path"],
                        caption=part["caption"],
                        cover_path=part.get("cover_path"),
                        schedule_at=part_schedule_time(
                            args.schedule_at,
                            index,
                            schedule_gap_minutes,
                        ),
                    )
                )
        cleanup_deleted = []
        if args.cleanup_after_success and successful_publish_responses(responses):
            cleanup_deleted = cleanup_manifest_after_success(manifest, parts)
        print(
            json.dumps(
                {
                    "manifest": manifest,
                    "responses": responses,
                    "cleanup_deleted": cleanup_deleted,
                },
                indent=2,
            )
        )
        return

    if args.command == "post-manifest-part-web":
        manifest = load_manifest(args.manifest_path)
        manifest["manifest_path"] = str(Path(args.manifest_path).expanduser().resolve())
        part = get_manifest_part(manifest, args.part_number)
        if args.platform == "youtube":
            with YouTubeWebPublisher(
                headless=args.headless,
                slow_mo_ms=args.slow_mo_ms,
            ) as publisher:
                response = publisher.upload_video(
                    part["video_path"],
                    title=part["title"],
                    description=part["caption"],
                    privacy_status="PRIVATE",
                )
        elif args.platform == "tiktok":
            with TikTokWebPublisher(
                headless=args.headless,
                slow_mo_ms=args.slow_mo_ms,
            ) as publisher:
                response = publisher.upload_video(
                    part["video_path"],
                    caption=part["caption"],
                )
        else:
            with InstagramWebPublisher(
                headless=args.headless,
                slow_mo_ms=args.slow_mo_ms,
            ) as publisher:
                response = publisher.upload_video(
                    part["video_path"],
                    caption=part["caption"],
                    cover_path=part.get("cover_path"),
                    schedule_at=args.schedule_at,
                )
        cleanup_deleted = []
        if (
            args.cleanup_after_success
            and str(response.get("status") or "").lower() in {"shared", "scheduled"}
        ):
            cleanup_deleted = cleanup_manifest_after_success(manifest, [part])
        print(json.dumps({**response, "cleanup_deleted": cleanup_deleted}, indent=2))
        return

    if args.command == "instagram-local-schedule-weekly":
        from local_instagram_scheduler import schedule_weekly_items

        added = schedule_weekly_items(args)
        print(
            json.dumps(
                {
                    "status": "queued",
                    "queue_path": str(Path(args.queue_path).expanduser().resolve()),
                    "added_count": len(added),
                    "added": [
                        {
                            "id": item["id"],
                            "run_at": item["run_at"],
                            "subreddit": item["subreddit"],
                            "video_path": item["video_path"],
                        }
                        for item in added
                    ],
                },
                indent=2,
            )
        )
        return

    if args.command == "instagram-local-schedule-video":
        from local_instagram_scheduler import schedule_single_video

        added = schedule_single_video(args)
        print(
            json.dumps(
                {
                    "status": "queued" if added else "duplicate",
                    "queue_path": str(Path(args.queue_path).expanduser().resolve()),
                    "item": {
                        "id": added.get("id"),
                        "run_at": added.get("run_at"),
                        "subreddit": added.get("subreddit"),
                        "video_path": added.get("video_path"),
                    }
                    if added
                    else None,
                },
                indent=2,
            )
        )
        return

    if args.command == "instagram-local-run-due":
        from local_instagram_scheduler import run_due_items

        results = run_due_items(args)
        print(
            json.dumps(
                {
                    "status": "checked",
                    "queue_path": str(Path(args.queue_path).expanduser().resolve()),
                    "processed_count": len(results),
                    "results": [
                        {
                            "id": item.get("id"),
                            "status": item.get("status"),
                            "run_at": item.get("run_at"),
                            "subreddit": item.get("subreddit"),
                            "last_error": item.get("last_error"),
                        }
                        for item in results
                    ],
                },
                indent=2,
            )
        )
        return

    if args.command == "instagram-local-install-launch-agent":
        from local_instagram_scheduler import install_launch_agent

        plist_path = install_launch_agent(args)
        print(
            json.dumps(
                {
                    "status": "installed",
                    "plist_path": str(plist_path),
                    "load_command": f"launchctl load {plist_path}",
                    "unload_command": f"launchctl unload {plist_path}",
                },
                indent=2,
            )
        )
        return

    if args.command == "instagram-local-wake-commands":
        from local_instagram_scheduler import wake_commands_for_queue

        commands = wake_commands_for_queue(args)
        print(json.dumps({"status": "ok", "commands": commands}, indent=2))
        return

    if args.command in ("instagram-weekly-category-run", "instagram-weekly-subreddit-run"):
        plan = build_weekly_category_plan(args)
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "status": "planned",
                        "plan": printable_weekly_plan(plan, args.parts_gap_minutes),
                    },
                    indent=2,
                )
            )
            return

        prepared_items = []
        for item in plan:
            manifest = prepare_manifest_for_weekly_item(
                item,
                target_seconds=args.target_seconds,
                min_last_part_seconds=args.min_last_part_seconds,
            )
            prepared_items.append((item, manifest))

        results = []
        with InstagramWebPublisher(
            headless=args.headless,
            slow_mo_ms=args.slow_mo_ms,
        ) as publisher:
            for item, manifest in prepared_items:
                responses = upload_manifest_parts_to_instagram(
                    publisher,
                    manifest,
                    item["schedule_at"],
                    args.parts_gap_minutes,
                )
                cleanup_deleted = []
                if args.cleanup_after_success and successful_publish_responses(responses):
                    cleanup_deleted = cleanup_manifest_after_success(
                        manifest,
                        manifest.get("parts", []),
                    )
                results.append(
                    {
                        "date": item["date"],
                        "category": item["category"],
                        "subreddit": item["subreddit"],
                        "schedule_at": item["schedule_at"].isoformat(timespec="minutes")
                        if item["schedule_at"]
                        else None,
                        "manifest_path": str(Path(item["manifest_dir"]) / "publish_manifest.json"),
                        "responses": responses,
                        "cleanup_deleted": cleanup_deleted,
                    }
                )

        print(json.dumps({"status": "completed", "results": results}, indent=2))
        return


if __name__ == "__main__":
    main()
