from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_VIDEO_ROOT = PROJECT_ROOT / "videos"

CATEGORY_CONFIGS = {
    "story": {
        "subreddits": {"aitah", "amitheasshole", "tifu", "advice"},
        "video_subdir": "story",
        "default_background_speed": 1.15,
        "target_max_seconds": None,
    },
    "horror": {
        "subreddits": {"nosleep", "creepypasta", "scarystories"},
        "video_subdir": "horror",
        "default_background_speed": 1.0,
        "target_max_seconds": None,
    },
    "ask": {
        "subreddits": {"askreddit", "askmen", "askscience", "nostupidquestions"},
        "video_subdir": "ask",
        "default_background_speed": 1.15,
        "target_max_seconds": 120,
    },
}

SUBREDDIT_TO_CATEGORY = {
    subreddit: category
    for category, config in CATEGORY_CONFIGS.items()
    for subreddit in config["subreddits"]
}


def normalize_subreddit_name(name):
    return str(name or "").strip().lower().removeprefix("r/")


def infer_category_for_subreddit(subreddit_name):
    return SUBREDDIT_TO_CATEGORY.get(normalize_subreddit_name(subreddit_name), "story")


def get_category_config(category):
    return CATEGORY_CONFIGS.get(category, CATEGORY_CONFIGS["story"])


def resolve_video_dir(base_video_dir, category):
    base_dir = Path(base_video_dir).expanduser().resolve()
    category_dir = base_dir / get_category_config(category)["video_subdir"]
    if category_dir.exists() and any(category_dir.glob("*.mp4")):
        return category_dir
    return base_dir
