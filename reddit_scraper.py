import os
import re
from pathlib import Path

import praw
from dotenv import load_dotenv

from content_config import (
    get_category_config,
    infer_category_for_subreddit,
    normalize_subreddit_name,
)
from processed_posts import compute_post_hash, is_processed_post

load_dotenv()

DEFAULT_USER_AGENT = "autopost-video-pipeline/1.0"
DEFAULT_WORDS_PER_MINUTE = 165
MAX_ASK_COMMENTS = 6


def get_reddit_client():
    client_id = os.getenv("CLIENT_ID_REDDIT")
    client_secret = os.getenv("CLIENT_SECRET_REDDIT")

    if not client_id or not client_secret:
        raise RuntimeError(
            "Missing Reddit credentials. Set CLIENT_ID_REDDIT and CLIENT_SECRET_REDDIT."
        )

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=os.getenv("REDDIT_USER_AGENT", DEFAULT_USER_AGENT),
    )


def clean_text(text):
    """Remove URLs and filename-invalid characters from Reddit text."""
    text = re.sub(r"http\S+|www\S+|https\S+", "", text or "", flags=re.MULTILINE)
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def estimate_spoken_seconds(text, words_per_minute=DEFAULT_WORDS_PER_MINUTE):
    word_count = len(clean_text(text).split())
    if word_count <= 0:
        return 0.0
    return (word_count / max(words_per_minute, 1)) * 60


def humanize_username(username):
    cleaned = str(username or "").strip()
    cleaned = re.sub(r"^u/", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[_\-]+", " ", cleaned)
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned)
    cleaned = re.sub(r"([A-Za-z])(\d)", r"\1 \2", cleaned)
    cleaned = re.sub(r"(\d)([A-Za-z])", r"\1 \2", cleaned)
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned or "A Reddit user"


def build_ask_post_text(post, clean_title, max_seconds):
    """
    Build an Ask-style script from the title plus a few audible comments.
    """
    title_intro = f"{clean_title}."
    parts = [title_intro]
    comments = []
    target_seconds = max_seconds or 120

    post.comment_sort = "top"
    post.comments.replace_more(limit=0)

    for comment in post.comments:
        if len(comments) >= MAX_ASK_COMMENTS:
            break
        if getattr(comment, "stickied", False):
            continue

        clean_comment = clean_text(getattr(comment, "body", ""))
        if not clean_comment or clean_comment.lower() in {"[deleted]", "[removed]"}:
            continue

        username = humanize_username(getattr(getattr(comment, "author", None), "name", ""))
        comment_line = f"{username} responds: {clean_comment}"
        candidate_parts = [*parts, comment_line]
        if estimate_spoken_seconds(" ".join(candidate_parts)) > target_seconds and comments:
            break

        parts.append(comment_line)
        comments.append(
            {
                "username": username,
                "text": clean_comment,
                "score": getattr(comment, "score", 0),
            }
        )

    return {
        "title": clean_title or "Untitled",
        "body": "",
        "text": " ".join(parts),
        "comments": comments,
    }


def scrape_reddit_posts(subreddit_name, limit=2, filename=None, processed_index=None):
    """
    Scrape non-stickied Reddit posts and optionally save the titles to disk.

    Returns a list of dictionaries with title, body, and voiceover text.
    """
    reddit = get_reddit_client()
    subreddit_names = [
        normalize_subreddit_name(name)
        for name in str(subreddit_name).split(",")
        if normalize_subreddit_name(name)
    ]
    if not subreddit_names:
        raise RuntimeError("At least one subreddit name is required.")

    posts = []
    titles = []
    fetch_per_subreddit = max(limit * 3, 10)

    for subreddit_name_item in subreddit_names:
        subreddit = reddit.subreddit(subreddit_name_item)
        category = infer_category_for_subreddit(subreddit_name_item)
        category_config = get_category_config(category)

        for post in subreddit.hot(limit=fetch_per_subreddit):
            if post.stickied:
                continue

            clean_title = clean_text(post.title)
            clean_selftext = clean_text(post.selftext)
            post_id = str(getattr(post, "id", "") or "").strip()

            if category == "ask":
                built_post = build_ask_post_text(
                    post,
                    clean_title,
                    max_seconds=category_config["target_max_seconds"],
                )
                if not clean_text(built_post["text"]):
                    continue
                built_post["category"] = category
                built_post["subreddit"] = subreddit_name_item
            else:
                parts = [part for part in (clean_title, clean_selftext) if part]
                if not parts:
                    continue

                built_post = {
                    "title": clean_title or "Untitled",
                    "body": clean_selftext,
                    "text": ". ".join(parts),
                    "category": category,
                    "subreddit": subreddit_name_item,
                }

            post_hash = compute_post_hash(built_post.get("text", ""))
            if processed_index and is_processed_post(
                processed_index,
                post_id=post_id,
                post_hash=post_hash,
            ):
                continue

            built_post["id"] = post_id or None
            built_post["hash"] = post_hash
            posts.append(built_post)
            titles.append(clean_title or "Untitled")
            if processed_index:
                if post_id:
                    processed_index["ids"].add(post_id)
                if post_hash:
                    processed_index["hashes"].add(post_hash)

            if len(posts) >= limit:
                break

        if len(posts) >= limit:
            break

    if filename:
        title_file = Path(filename).expanduser()
        title_file.parent.mkdir(parents=True, exist_ok=True)
        title_file.write_text("\n".join(titles) + ("\n" if titles else ""), encoding="utf-8")

    return posts
