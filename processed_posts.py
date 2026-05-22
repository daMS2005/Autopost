import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PROCESSED_POSTS_PATH = (
    Path(__file__).resolve().parent / "data" / "processed_posts.jsonl"
)


def normalize_hash_source(text, prefix_length=20):
    normalized = " ".join(str(text or "").replace("\n", " ").split()).strip().lower()
    return normalized[: max(1, int(prefix_length))]


def compute_post_hash(text, prefix_length=20):
    hash_source = normalize_hash_source(text, prefix_length=prefix_length)
    return hashlib.sha256(hash_source.encode("utf-8")).hexdigest()


def load_processed_post_index(path=None):
    registry_path = Path(path or DEFAULT_PROCESSED_POSTS_PATH).expanduser().resolve()
    processed_ids = set()
    processed_hashes = set()

    if not registry_path.exists():
        return {
            "path": registry_path,
            "ids": processed_ids,
            "hashes": processed_hashes,
        }

    for line in registry_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        post_id = str(record.get("id", "")).strip()
        post_hash = str(record.get("hash", "")).strip()
        if post_id:
            processed_ids.add(post_id)
        if post_hash:
            processed_hashes.add(post_hash)

    return {
        "path": registry_path,
        "ids": processed_ids,
        "hashes": processed_hashes,
    }


def is_processed_post(processed_index, post_id=None, post_hash=None):
    normalized_id = str(post_id or "").strip()
    normalized_hash = str(post_hash or "").strip()
    return (
        (normalized_id and normalized_id in processed_index["ids"])
        or (normalized_hash and normalized_hash in processed_index["hashes"])
    )


def append_processed_post(
    path,
    *,
    title,
    post_id,
    post_hash,
    processed_at=None,
    **extra_fields,
):
    registry_path = Path(path or DEFAULT_PROCESSED_POSTS_PATH).expanduser().resolve()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "title": str(title or "").strip() or "Untitled",
        "id": str(post_id or "").strip() or None,
        "hash": str(post_hash or "").strip(),
        "processed_at": processed_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    record.update(extra_fields)

    with registry_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    return record
