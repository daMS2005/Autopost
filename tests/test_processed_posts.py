import json

from processed_posts import (
    append_processed_post,
    compute_post_hash,
    is_processed_post,
    load_processed_post_index,
    normalize_hash_source,
)


def test_hash_normalization_is_stable():
    assert normalize_hash_source("  Hello\n  WORLD  ") == "hello world"
    assert compute_post_hash("Hello world") == compute_post_hash(" hello\nworld ")


def test_registry_round_trip(tmp_path):
    registry = tmp_path / "nested" / "processed.jsonl"
    record = append_processed_post(
        registry,
        title="A title",
        post_id="abc123",
        post_hash="hash123",
        processed_at="2026-01-02T03:04:05+00:00",
        subreddit="aitah",
    )

    assert json.loads(registry.read_text()) == record
    index = load_processed_post_index(registry)
    assert is_processed_post(index, post_id="abc123")
    assert is_processed_post(index, post_hash="hash123")
    assert not is_processed_post(index, post_id="new")


def test_registry_skips_malformed_lines(tmp_path):
    registry = tmp_path / "processed.jsonl"
    registry.write_text('{"id": "ok", "hash": "h"}\nnot-json\n', encoding="utf-8")
    index = load_processed_post_index(registry)
    assert index["ids"] == {"ok"}
    assert index["hashes"] == {"h"}
