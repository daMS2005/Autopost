#!/usr/bin/env python3
"""
post.py — upload a video to TikTok and/or Instagram via browser automation.

Usage examples:
  # Post to both platforms
  python post.py --video path/to/clip.mp4 --caption "My caption #fyp" --platform all

  # TikTok only (headless)
  python post.py --video clip.mp4 --caption "caption" --platform tiktok --headless

  # Instagram only, slow so you can see what's happening
  python post.py --video clip.mp4 --caption "caption" --platform instagram --slow-mo 500
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publishers import InstagramPublisher, TikTokPublisher


def build_parser():
    p = argparse.ArgumentParser(description="Post a video to TikTok and/or Instagram.")
    p.add_argument("--video", default=None, help="Path to the video file to upload.")
    p.add_argument("--caption", default=None, help="Caption / description for the post.")
    p.add_argument(
        "--platform",
        choices=("tiktok", "instagram", "all"),
        default="all",
        help="Which platform(s) to post to (default: all).",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser in headless mode (no visible window). "
             "First run without this flag to complete any login challenges.",
    )
    p.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        metavar="MS",
        help="Add a delay (ms) between browser actions — useful for debugging.",
    )
    p.add_argument(
        "--login-only",
        action="store_true",
        help="Open the browser, log in manually, then exit. Saves the session so future runs are automatic.",
    )
    return p


def main():
    args = build_parser().parse_args()
    results = []

    do_tiktok = args.platform in ("tiktok", "all")
    do_instagram = args.platform in ("instagram", "all")

    if args.login_only:
        if do_tiktok:
            with TikTokPublisher(headless=False, slow_mo_ms=args.slow_mo) as pub:
                pub.ensure_logged_in()
            print("[TikTok] Session saved.")
        if do_instagram:
            with InstagramPublisher(headless=False, slow_mo_ms=args.slow_mo) as pub:
                pub.ensure_logged_in()
            print("[Instagram] Session saved.")
        return

    if do_tiktok:
        print("[TikTok] Starting upload...")
        with TikTokPublisher(headless=args.headless, slow_mo_ms=args.slow_mo) as pub:
            result = pub.post_video(args.video, caption=args.caption)
        results.append(result)
        print(f"[TikTok] Done — status: {result['status']}")

    if do_instagram:
        print("[Instagram] Starting upload...")
        with InstagramPublisher(headless=args.headless, slow_mo_ms=args.slow_mo) as pub:
            result = pub.post_reel(args.video, caption=args.caption)
        results.append(result)
        print(f"[Instagram] Done — status: {result['status']}")

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
