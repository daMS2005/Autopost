import json
import os
import platform
import plistlib
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from publish_cli import (
    build_weekly_category_plan,
    cleanup_manifest_after_success,
    prepare_manifest_for_weekly_item,
    successful_publish_responses,
    upload_manifest_parts_to_instagram,
)
from video_splitter import load_post_metadata_for_video, sanitize_slug
from web_publishers import InstagramWebPublisher
from web_publishers import load_manifest


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_QUEUE_PATH = PROJECT_ROOT / "data" / "local_schedules" / "instagram_queue.json"
DEFAULT_LOG_PATH = PROJECT_ROOT / "data" / "local_schedules" / "instagram_scheduler.log"
DEFAULT_LABEL = "com.acc.instagram-local-scheduler"


def now_local():
    return datetime.now().replace(microsecond=0)


def parse_datetime(value):
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return datetime.fromisoformat(text).replace(tzinfo=None, microsecond=0)


def load_queue(queue_path=DEFAULT_QUEUE_PATH):
    path = Path(queue_path).expanduser().resolve()
    if not path.exists():
        return {"version": 1, "items": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_queue(queue, queue_path=DEFAULT_QUEUE_PATH):
    path = Path(queue_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    return path


def append_log(message, log_path=DEFAULT_LOG_PATH):
    path = Path(log_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = now_local().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def queue_item_id(item):
    parts = [
        item.get("run_at"),
        item.get("subreddit"),
        item.get("video_path"),
        str(item.get("part_number") or "all"),
    ]
    return "|".join(str(part or "") for part in parts)


def schedule_weekly_items(args):
    plan = build_weekly_category_plan(args)
    queue = load_queue(args.queue_path)
    existing_ids = {item.get("id") for item in queue.get("items", [])}
    added = []

    for item in plan:
        run_at = item["schedule_at"] or datetime.combine(
            datetime.fromisoformat(item["date"]).date(),
            parse_datetime(f"{item['date']} {args.first_time}").time(),
        )
        queued = {
            "id": None,
            "status": "pending",
            "run_at": run_at.isoformat(timespec="minutes"),
            "created_at": now_local().isoformat(timespec="seconds"),
            "category": item["category"],
            "subreddit": item["subreddit"],
            "date": item["date"],
            "video_path": item["video_path"],
            "manifest_dir": item["manifest_dir"],
            "metadata": item["metadata"],
            "metadata_path": item["metadata_path"],
            "target_seconds": args.target_seconds,
            "min_last_part_seconds": args.min_last_part_seconds,
            "parts_gap_minutes": args.parts_gap_minutes,
            "cleanup_after_success": bool(args.cleanup_after_success),
            "cleanup_source_after_success": bool(
                getattr(args, "cleanup_source_after_success", False)
            ),
            "headless": bool(args.headless),
            "slow_mo_ms": int(args.slow_mo_ms or 0),
            "attempts": 0,
        }
        queued["id"] = queue_item_id(queued)
        if queued["id"] in existing_ids:
            continue
        queue.setdefault("items", []).append(queued)
        existing_ids.add(queued["id"])
        added.append(queued)

    queue["items"].sort(key=lambda item: item.get("run_at") or "")
    save_queue(queue, args.queue_path)
    return added


def schedule_single_video(args):
    video_path = Path(args.video_path).expanduser().resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video was not found: {video_path}")

    metadata = None
    metadata_path = None
    if args.metadata_path:
        metadata_path = Path(args.metadata_path).expanduser().resolve()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata is None:
        metadata = load_post_metadata_for_video(video_path) or {}

    title = args.title or metadata.get("title") or video_path.stem
    category = args.category or metadata.get("category") or "story"
    subreddit = args.subreddit or metadata.get("subreddit") or "instagram"
    run_at = parse_datetime(args.run_at) or now_local()
    manifest_root = Path(args.publish_root).expanduser().resolve()
    manifest_dir = manifest_root / run_at.date().isoformat() / category / subreddit / sanitize_slug(title)

    queued = {
        "id": None,
        "status": "pending",
        "run_at": run_at.isoformat(timespec="minutes"),
        "created_at": now_local().isoformat(timespec="seconds"),
        "category": category,
        "subreddit": subreddit,
        "date": run_at.date().isoformat(),
        "video_path": str(video_path),
        "manifest_dir": str(manifest_dir),
        "metadata": {
            **metadata,
            "title": title,
            "category": category,
            "subreddit": subreddit,
            "final_video_path": str(video_path),
        },
        "metadata_path": str(metadata_path) if metadata_path else None,
        "target_seconds": args.target_seconds,
        "min_last_part_seconds": args.min_last_part_seconds,
        "parts_gap_minutes": args.parts_gap_minutes,
        "cleanup_after_success": bool(args.cleanup_after_success),
        "cleanup_source_after_success": bool(args.cleanup_source_after_success),
        "headless": bool(args.headless),
        "slow_mo_ms": int(args.slow_mo_ms or 0),
        "attempts": 0,
    }
    queued["id"] = queue_item_id(queued)

    queue = load_queue(args.queue_path)
    existing_ids = {item.get("id") for item in queue.get("items", [])}
    if queued["id"] not in existing_ids:
        queue.setdefault("items", []).append(queued)
        queue["items"].sort(key=lambda item: item.get("run_at") or "")
        save_queue(queue, args.queue_path)
        return queued
    return None


def manifest_is_usable(manifest):
    parts = manifest.get("parts") or []
    if not parts:
        return False
    for part in parts:
        video_path = part.get("video_path")
        if not video_path or not Path(video_path).expanduser().exists():
            return False
    return True


def prepare_or_load_manifest_for_item(item):
    manifest_path = Path(item["manifest_dir"]) / "publish_manifest.json"
    if manifest_path.exists():
        try:
            manifest = load_manifest(manifest_path)
            if manifest_is_usable(manifest):
                return manifest
        except Exception:
            pass
    return prepare_manifest_for_weekly_item(
        item,
        target_seconds=item.get("target_seconds") or 60.0,
        min_last_part_seconds=item.get("min_last_part_seconds") or 35.0,
    )


def start_caffeinate_for_current_process():
    if platform.system() != "Darwin":
        return None
    caffeinate_path = "/usr/bin/caffeinate"
    if not Path(caffeinate_path).exists():
        return None
    try:
        return subprocess.Popen(
            [caffeinate_path, "-dimsu", "-w", str(os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None


def is_inside_project_output(path):
    try:
        resolved = Path(path).expanduser().resolve()
        output_root = (PROJECT_ROOT / "output").resolve()
        return resolved == output_root or output_root in resolved.parents
    except Exception:
        return False


def cleanup_source_render_files(item):
    metadata = item.get("metadata") or {}
    deleted = []
    keys = (
        "final_video_path",
        "audio_path",
        "subtitles_path",
        "title_card_path",
        "script_raw_path",
        "script_vocab_path",
        "script_cleaned_path",
        "voice_choice_path",
    )
    paths = [metadata.get(key) for key in keys if metadata.get(key)]
    if item.get("metadata_path"):
        paths.append(item.get("metadata_path"))

    seen = set()
    for path_value in paths:
        path = Path(path_value).expanduser()
        try:
            resolved = path.resolve()
        except Exception:
            continue
        if resolved in seen or not is_inside_project_output(resolved):
            continue
        seen.add(resolved)
        try:
            if resolved.exists() and resolved.is_file():
                resolved.unlink()
                deleted.append(str(resolved))
        except Exception as exc:
            deleted.append(f"failed:{resolved}:{exc}")

    for directory in sorted({Path(path).parent for path in seen}, reverse=True):
        try:
            if directory.exists() and is_inside_project_output(directory) and not any(directory.iterdir()):
                directory.rmdir()
                deleted.append(str(directory))
        except Exception:
            pass
    return deleted


def run_due_items(args):
    queue = load_queue(args.queue_path)
    due_before = now_local() + timedelta(minutes=max(int(args.due_window_minutes or 0), 0))
    pending = [
        item
        for item in queue.get("items", [])
        if item.get("status") in {"pending", "retry"}
        and parse_datetime(item.get("run_at")) is not None
        and parse_datetime(item.get("run_at")) <= due_before
    ]
    if not pending:
        append_log("No due Instagram items.", args.log_path)
        return []

    keep_awake = start_caffeinate_for_current_process()
    results = []
    try:
        for item in pending:
            item["status"] = "running"
            item["started_at"] = now_local().isoformat(timespec="seconds")
            item["attempts"] = int(item.get("attempts") or 0) + 1
            save_queue(queue, args.queue_path)
            append_log(f"Posting {item['subreddit']} from {item['video_path']}.", args.log_path)

            try:
                manifest = prepare_or_load_manifest_for_item(item)
                with InstagramWebPublisher(
                    headless=bool(item.get("headless")),
                    slow_mo_ms=int(item.get("slow_mo_ms") or 0),
                ) as publisher:
                    responses = upload_manifest_parts_to_instagram(
                        publisher,
                        manifest,
                        schedule_at=None,
                        parts_gap_minutes=0,
                    )
                cleanup_deleted = []
                if item.get("cleanup_after_success") and successful_publish_responses(responses):
                    cleanup_deleted = cleanup_manifest_after_success(
                        manifest,
                        manifest.get("parts", []),
                    )
                source_cleanup_deleted = []
                if item.get("cleanup_source_after_success") and successful_publish_responses(responses):
                    source_cleanup_deleted = cleanup_source_render_files(item)
                item["status"] = "posted" if successful_publish_responses(responses) else "failed"
                item["completed_at"] = now_local().isoformat(timespec="seconds")
                item["manifest_path"] = str(Path(item["manifest_dir"]) / "publish_manifest.json")
                item["responses"] = responses
                item["cleanup_deleted"] = cleanup_deleted
                item["source_cleanup_deleted"] = source_cleanup_deleted
                results.append(item)
                append_log(f"Finished {item['subreddit']} with status {item['status']}.", args.log_path)
            except Exception as exc:
                item["status"] = "retry" if item["attempts"] < int(args.max_attempts or 3) else "failed"
                item["last_error"] = str(exc)
                item["completed_at"] = now_local().isoformat(timespec="seconds")
                results.append(item)
                append_log(f"Failed {item.get('subreddit')}: {exc}", args.log_path)
            save_queue(queue, args.queue_path)
    finally:
        if keep_awake is not None:
            keep_awake.terminate()
    return results


def install_launch_agent(args):
    if platform.system() != "Darwin":
        raise RuntimeError("LaunchAgent install is only supported on macOS.")
    python_path = Path(args.python_path or os.environ.get("PYTHON") or "venv/bin/python")
    if not python_path.is_absolute():
        python_path = PROJECT_ROOT / python_path
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{args.label}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    program_arguments = [
        "/usr/bin/caffeinate",
        "-dimsu",
        str(python_path),
        str(PROJECT_ROOT / "publish_cli.py"),
        "instagram-local-run-due",
        "--queue-path",
        str(Path(args.queue_path).expanduser().resolve()),
        "--log-path",
        str(Path(args.log_path).expanduser().resolve()),
        "--due-window-minutes",
        str(args.due_window_minutes),
        "--max-attempts",
        str(args.max_attempts),
    ]
    plist = {
        "Label": args.label,
        "ProgramArguments": program_arguments,
        "StartInterval": int(args.interval_seconds),
        "RunAtLoad": True,
        "WorkingDirectory": str(PROJECT_ROOT),
        "StandardOutPath": str(Path(args.log_path).expanduser().resolve()),
        "StandardErrorPath": str(Path(args.log_path).expanduser().resolve()),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "IMAGEIO_FFMPEG_EXE": "/opt/homebrew/bin/ffmpeg",
        },
    }
    plist_path.write_bytes(plistlib.dumps(plist))
    return plist_path


def wake_commands_for_queue(args):
    queue = load_queue(args.queue_path)
    commands = []
    lead_minutes = max(int(args.wake_lead_minutes or 10), 1)
    for item in queue.get("items", []):
        if item.get("status") not in {"pending", "retry"}:
            continue
        run_at = parse_datetime(item.get("run_at"))
        if run_at is None or run_at <= now_local():
            continue
        wake_at = run_at - timedelta(minutes=lead_minutes)
        commands.append(f"sudo pmset schedule wakeorpoweron \"{wake_at.strftime('%m/%d/%y %H:%M:%S')}\"")
    return commands
