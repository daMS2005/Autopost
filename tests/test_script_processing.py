import json

import pytest

from reddit_vocabulary import normalize_reddit_vocabulary
from script_rewriter import _parse_voiceover_json, finalize_prepared_voiceover
from voice_registry import strip_voice_marker


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("AITA for leaving?", "Am I the asshole for leaving?"),
        ("My TL;DR is short", "My Too long, didn't read is short"),
        ("scuba/c", "scuba/c"),
    ],
)
def test_reddit_vocabulary_replaces_whole_tokens(source, expected):
    assert normalize_reddit_vocabulary(source) == expected


def test_voiceover_json_accepts_fenced_payload_and_voice_marker():
    payload = {
        "script": "Hello there.",
        "voice_gender": "male",
        "segments": [
            {
                "speaker": "Narrator",
                "voice_gender": "male",
                "text": "<<VOICE:Mark>>Hello there.",
            }
        ],
    }
    parsed = _parse_voiceover_json(f"```json\n{json.dumps(payload)}\n```")
    assert parsed["segments"][0]["voice_name"] == "Mark"
    assert parsed["segments"][0]["text"] == "Hello there."


def test_voiceover_json_rejects_invalid_gender():
    with pytest.raises(RuntimeError, match="invalid voice gender"):
        _parse_voiceover_json('{"script":"Hello","voice_gender":"robot"}')


def test_ask_script_is_split_into_speaker_segments():
    prepared = {
        "script": "Best advice? Alex responds: Start now. Sam responds: Stay curious.",
        "voice_gender": "female",
        "segments": [],
    }
    result = finalize_prepared_voiceover(prepared, category="ask")
    assert [segment["speaker"] for segment in result["segments"]] == [
        "Narrator",
        "Alex",
        "Sam",
    ]


def test_strip_voice_marker_preserves_regular_text():
    assert strip_voice_marker("Plain text") == (None, "Plain text")
