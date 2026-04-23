import os
import re
from pathlib import Path

import praw
from dotenv import load_dotenv


load_dotenv()

USER_AGENT = "autopost by /u/No-Arrival-2825"


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
        user_agent=USER_AGENT,
    )


def clean_text(text):
    """Remove URLs and filename-invalid characters from Reddit text."""
    text = re.sub(r"http\S+|www\S+|https\S+", "", text or "", flags=re.MULTILINE)
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def scrape_reddit_posts(subreddit_name, limit=2, filename=None):
    """
    Scrape non-stickied Reddit posts and optionally save the titles to disk.

    Returns a list of dictionaries with title, body, and voiceover text.
    """
    subreddit = get_reddit_client().subreddit(subreddit_name)
    posts = []
    titles = []

    fetch_limit = max(limit * 3, 10)
    for post in subreddit.hot(limit=fetch_limit):
        if post.stickied:
            continue

        clean_title = clean_text(post.title)
        clean_selftext = clean_text(post.selftext)
        parts = [part for part in (clean_title, clean_selftext) if part]

        if not parts:
            continue

        posts.append(
            {
                "title": clean_title or "Untitled",
                "body": clean_selftext,
                "text": ". ".join(parts),
            }
        )
        titles.append(clean_title or "Untitled")

        if len(posts) >= limit:
            break

    if filename:
        title_file = Path(filename).expanduser()
        title_file.parent.mkdir(parents=True, exist_ok=True)
        title_file.write_text("\n".join(titles) + ("\n" if titles else ""), encoding="utf-8")

    return posts
