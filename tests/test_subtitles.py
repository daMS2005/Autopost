from transcriber import (
    build_srt_from_word_timings,
    build_word_timings_from_character_alignment,
    estimate_spoken_text_end,
    extract_spoken_tokens,
    format_srt_timestamp,
)


def test_srt_timestamp_formatting():
    assert format_srt_timestamp(3661.234) == "01:01:01,234"
    assert format_srt_timestamp(-1) == "00:00:00,000"


def test_alignment_omits_performance_directions():
    text = "[whispers] Hello world"
    starts = [index * 0.05 for index in range(len(text))]
    ends = [(index + 1) * 0.05 for index in range(len(text))]
    words = build_word_timings_from_character_alignment(
        {
            "characters": list(text),
            "character_start_times_seconds": starts,
            "character_end_times_seconds": ends,
        }
    )
    assert [word["text"] for word in words] == ["Hello", "world"]


def test_caption_builder_splits_on_sentence_end():
    words = [
        {"text": "Hello", "start": 0.0, "end": 0.3},
        {"text": "world.", "start": 0.31, "end": 0.7},
        {"text": "Again!", "start": 0.8, "end": 1.2},
    ]
    subtitles = build_srt_from_word_timings(words, chars_per_caption=40)
    assert "Hello world." in subtitles
    assert "Again!" in subtitles
    assert "00:00:00,000 --> 00:00:00,700" in subtitles


def test_spoken_title_duration_ignores_markup():
    words = [
        {"text": "A", "start": 0.0, "end": 0.2},
        {"text": "title", "start": 0.2, "end": 0.8},
    ]
    assert extract_spoken_tokens("[curious] A title") == ["a", "title"]
    assert estimate_spoken_text_end(words, "[curious] A title") == 0.8
