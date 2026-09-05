import json
import stat

from social_publishers import TikTokPublisher, build_publish_metadata
from video_splitter import (
    build_default_hashtags,
    build_part_caption,
    plan_video_parts,
    sanitize_slug,
)


def test_video_part_planning_avoids_tiny_final_clip():
    assert plan_video_parts(125, target_seconds=60, min_last_part_seconds=35) == [
        (0.0, 62.5),
        (62.5, 125.0),
    ]
    assert plan_video_parts(45, target_seconds=60) == [(0.0, 45.0)]


def test_publish_caption_is_structured_and_deduplicated():
    payload = build_part_caption("A title", 1, 2, category="story", subreddit="AITAH")
    assert payload["title"] == "A title (Part 1)"
    assert payload["hook"] == "Start here."
    assert payload["hashtags"].count("#aitah") == 1


def test_slug_and_hashtag_sanitization():
    assert sanitize_slug("  Hello, World! ") == "hello-world"
    assert "#nosleep" in build_default_hashtags("horror", "NoSleep")


def test_publish_metadata_keeps_safe_default_privacy():
    metadata = build_publish_metadata(title="Story", category="story", subreddit="aitah")
    assert metadata.privacy_status == "private"
    assert metadata.tags == ["aitah", "story", "reddit", "viral", "storytime"]


def test_tiktok_token_file_is_owner_only(tmp_path):
    token_file = tmp_path / "tokens.json"
    publisher = TikTokPublisher(
        client_key="client",
        client_secret="secret",
        token_file=token_file,
    )
    publisher.save_tokens({"access_token": "sensitive"})

    assert json.loads(token_file.read_text()) == {"access_token": "sensitive"}
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
