from pathlib import Path

import pytest

from content_config import (
    get_category_config,
    infer_category_for_subreddit,
    normalize_subreddit_name,
    resolve_video_dir,
)
from main import validate_environment


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("r/AITAH", "aitah"), (" NoSleep ", "nosleep"), (None, "")],
)
def test_normalize_subreddit_name(raw, expected):
    assert normalize_subreddit_name(raw) == expected


def test_category_inference_defaults_to_story():
    assert infer_category_for_subreddit("r/NoSleep") == "horror"
    assert infer_category_for_subreddit("askreddit") == "ask"
    assert infer_category_for_subreddit("unknown") == "story"


def test_unknown_category_uses_story_config():
    assert get_category_config("unknown") == get_category_config("story")


def test_resolve_video_dir_prefers_populated_category(tmp_path):
    category_dir = tmp_path / "horror"
    category_dir.mkdir()
    (category_dir / "clip.mp4").touch()
    assert resolve_video_dir(tmp_path, "horror") == category_dir.resolve()


def test_resolve_video_dir_falls_back_to_root(tmp_path):
    (tmp_path / "horror").mkdir()
    assert resolve_video_dir(tmp_path, "horror") == tmp_path.resolve()


def test_environment_validation_matches_selected_path(monkeypatch):
    for key in ("CLIENT_ID_REDDIT", "CLIENT_SECRET_REDDIT", "ELEVENLABS_API_KEY"):
        monkeypatch.setenv(key, "test-value")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    validate_environment(use_script_cleanup=False, use_v3_directions=True)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        validate_environment(use_script_cleanup=True)


def test_default_title_card_asset_exists():
    from title_card import DEFAULT_TEMPLATE_PATH

    assert isinstance(DEFAULT_TEMPLATE_PATH, Path)
    assert DEFAULT_TEMPLATE_PATH.exists()
