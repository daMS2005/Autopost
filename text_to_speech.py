import json
import os
import re
import tempfile
from base64 import b64decode
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from moviepy.audio.AudioClip import concatenate_audioclips
from moviepy.audio.io.AudioFileClip import AudioFileClip

from transcriber import (
    build_srt_from_word_timings,
    build_word_timings_from_character_alignment,
    estimate_spoken_text_end,
    write_srt,
)
from voice_registry import strip_voice_marker, voice_id_for_name


load_dotenv()

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_TTS_WITH_TIMESTAMPS_URL = (
    "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
)
DEFAULT_ELEVENLABS_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"
DEFAULT_ELEVENLABS_FEMALE_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"
DEFAULT_ELEVENLABS_MALE_VOICE_ID = "CwhRBWXzGAHq8TQ4Fs17"
DEFAULT_ELEVENLABS_ALT_FEMALE_VOICE_ID = DEFAULT_ELEVENLABS_FEMALE_VOICE_ID
DEFAULT_ELEVENLABS_ALT_MALE_VOICE_ID = DEFAULT_ELEVENLABS_MALE_VOICE_ID
DEFAULT_ELEVENLABS_HORROR_FEMALE_VOICE_ID = DEFAULT_ELEVENLABS_FEMALE_VOICE_ID
DEFAULT_ELEVENLABS_HORROR_MALE_VOICE_ID = DEFAULT_ELEVENLABS_MALE_VOICE_ID
DEFAULT_ELEVENLABS_TTS_MODEL = "eleven_v3"
DEFAULT_ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_ELEVENLABS_MAX_CHARS = 9_500
DEFAULT_ELEVENLABS_V3_MAX_CHARS = 5_000
ELEVENLABS_V3_MODEL_IDS = {"eleven_v3", "eleven_ttv_v3"}
CATEGORY_VOICE_SETTING_DEFAULTS = {
    "story": {
        "stability": 0.30,
        "similarity_boost": 0.8,
        "style": 0.0,
        "speed": 1.1,
        "use_speaker_boost": True,
    },
    "horror": {
        "stability": 0.24,
        "similarity_boost": 0.82,
        "style": 0.18,
        "speed": 1.0,
        "use_speaker_boost": True,
    },
    "ask": {
        "stability": 0.36,
        "similarity_boost": 0.8,
        "style": 0.0,
        "speed": 1.08,
        "use_speaker_boost": True,
    },
}


def _env_float(name, default=None):
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return float(value)


def _env_int(name, default=None):
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)


def _env_bool(name, default=None):
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_selected_tts_model():
    return os.getenv("ELEVENLABS_TTS_MODEL", DEFAULT_ELEVENLABS_TTS_MODEL)


def is_v3_model(model_id=None):
    selected_model = model_id or get_selected_tts_model()
    return selected_model in ELEVENLABS_V3_MODEL_IDS


def get_default_max_chars(model_id=None):
    return (
        DEFAULT_ELEVENLABS_V3_MAX_CHARS
        if is_v3_model(model_id)
        else DEFAULT_ELEVENLABS_MAX_CHARS
    )


def resolve_voice_id(
    voice_id=None,
    voice_name=None,
    voice_gender=None,
    category="story",
    speaker_index=0,
):
    if voice_id:
        return voice_id
    if voice_name:
        resolved_voice_id, _ = voice_id_for_name(
            voice_name,
            category=category,
            voice_gender=voice_gender or "female",
        )
        return resolved_voice_id

    is_horror = category == "horror"
    if voice_gender == "male":
        if speaker_index % 2 == 1:
            return os.getenv(
                "ELEVENLABS_ALT_MALE_VOICE_ID",
                DEFAULT_ELEVENLABS_ALT_MALE_VOICE_ID,
            )
        if is_horror:
            return os.getenv(
                "ELEVENLABS_HORROR_MALE_VOICE_ID",
                DEFAULT_ELEVENLABS_HORROR_MALE_VOICE_ID,
            )
        return os.getenv("ELEVENLABS_MALE_VOICE_ID", DEFAULT_ELEVENLABS_MALE_VOICE_ID)
    if voice_gender == "female":
        if speaker_index % 2 == 1:
            return os.getenv(
                "ELEVENLABS_ALT_FEMALE_VOICE_ID",
                DEFAULT_ELEVENLABS_ALT_FEMALE_VOICE_ID,
            )
        if is_horror:
            return os.getenv(
                "ELEVENLABS_HORROR_FEMALE_VOICE_ID",
                DEFAULT_ELEVENLABS_HORROR_FEMALE_VOICE_ID,
            )
        return os.getenv(
            "ELEVENLABS_FEMALE_VOICE_ID",
            DEFAULT_ELEVENLABS_FEMALE_VOICE_ID,
        )
    return os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_ELEVENLABS_VOICE_ID)


def clean_tts_text(text):
    return " ".join(str(text).replace("\n", " ").split()).strip()


def _normalize_category(category):
    normalized = str(category or "").strip().lower()
    return normalized if normalized in CATEGORY_VOICE_SETTING_DEFAULTS else "story"


def split_text_for_tts(text, max_chars=DEFAULT_ELEVENLABS_MAX_CHARS):
    """
    Split long stories into TTS-safe chunks while preferring sentence boundaries.
    """
    normalized = clean_tts_text(text)
    if not normalized:
        return []

    max_chars = max(500, int(max_chars))
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    chunks = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue

        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_sentence(sentence, max_chars))
            continue

        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def _split_long_sentence(sentence, max_chars):
    words = sentence.split()
    chunks = []
    current_words = []

    for word in words:
        candidate = " ".join([*current_words, word])
        if current_words and len(candidate) > max_chars:
            chunks.append(" ".join(current_words))
            current_words = [word]
        else:
            current_words.append(word)

    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


def _build_voice_settings(category="story"):
    defaults = CATEGORY_VOICE_SETTING_DEFAULTS[_normalize_category(category)]
    normalized_category = _normalize_category(category)
    settings = {
        "stability": _env_float("ELEVENLABS_STABILITY", defaults["stability"]),
        "similarity_boost": _env_float(
            "ELEVENLABS_SIMILARITY_BOOST",
            defaults["similarity_boost"],
        ),
        "style": _env_float("ELEVENLABS_STYLE", defaults["style"]),
        "speed": (
            defaults["speed"]
            if normalized_category == "horror"
            else _env_float("ELEVENLABS_SPEED", defaults["speed"])
        ),
        "use_speaker_boost": _env_bool(
            "ELEVENLABS_USE_SPEAKER_BOOST",
            defaults["use_speaker_boost"],
        ),
    }
    return {key: value for key, value in settings.items() if value is not None}


def _build_request_payload(text, previous_text=None, next_text=None, category="story"):
    model_id = get_selected_tts_model()
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": _build_voice_settings(category=category),
        "apply_text_normalization": os.getenv(
            "ELEVENLABS_APPLY_TEXT_NORMALIZATION", "auto"
        ),
    }

    language_code = os.getenv("ELEVENLABS_LANGUAGE_CODE")
    if language_code:
        payload["language_code"] = language_code

    seed = _env_int("ELEVENLABS_SEED")
    if seed is not None:
        payload["seed"] = seed

    if previous_text:
        payload["previous_text"] = previous_text
    if next_text:
        payload["next_text"] = next_text

    return payload


def _elevenlabs_tts_request(
    text,
    previous_text=None,
    next_text=None,
    voice_id=None,
    category="story",
):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    selected_voice_id = resolve_voice_id(voice_id=voice_id)

    if not api_key:
        raise RuntimeError("Missing ELEVENLABS_API_KEY.")

    output_format = os.getenv(
        "ELEVENLABS_OUTPUT_FORMAT", DEFAULT_ELEVENLABS_OUTPUT_FORMAT
    )
    query = {
        "output_format": output_format,
        "enable_logging": str(_env_bool("ELEVENLABS_ENABLE_LOGGING", True)).lower(),
    }
    url = f"{ELEVENLABS_TTS_URL.format(voice_id=selected_voice_id)}?{urlencode(query)}"
    body = json.dumps(
        _build_request_payload(
            text,
            previous_text,
            next_text,
            category=category,
        )
    ).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=240) as response:
            return response.read()
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"ElevenLabs TTS failed with HTTP {exc.code}: {error_body}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"ElevenLabs TTS request failed: {exc}") from exc


def _elevenlabs_tts_with_timestamps_request(
    text,
    previous_text=None,
    next_text=None,
    voice_id=None,
    category="story",
):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    selected_voice_id = resolve_voice_id(voice_id=voice_id)

    if not api_key:
        raise RuntimeError("Missing ELEVENLABS_API_KEY.")

    output_format = os.getenv(
        "ELEVENLABS_OUTPUT_FORMAT", DEFAULT_ELEVENLABS_OUTPUT_FORMAT
    )
    query = {
        "output_format": output_format,
        "enable_logging": str(_env_bool("ELEVENLABS_ENABLE_LOGGING", True)).lower(),
    }
    url = f"{ELEVENLABS_TTS_WITH_TIMESTAMPS_URL.format(voice_id=selected_voice_id)}?{urlencode(query)}"
    body = json.dumps(
        _build_request_payload(
            text,
            previous_text,
            next_text,
            category=category,
        )
    ).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=240) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"ElevenLabs TTS with timestamps failed with HTTP {exc.code}: {error_body}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"ElevenLabs TTS with timestamps request failed: {exc}") from exc


def _combine_audio_files(part_paths, output_file):
    clips = [AudioFileClip(str(path)) for path in part_paths]
    combined = None
    try:
        combined = concatenate_audioclips(clips)
        combined.write_audiofile(str(output_file), codec="libmp3lame", logger=None)
    finally:
        if combined is not None:
            combined.close()
        for clip in clips:
            clip.close()


def _generate_words_and_audio_for_text(
    text,
    output_file,
    voice_id=None,
    voice_name=None,
    voice_gender=None,
    category="story",
    speaker_index=0,
):
    selected_model = get_selected_tts_model()
    max_chars = _env_int("ELEVENLABS_MAX_CHARS", get_default_max_chars(selected_model))
    explicit_voice_name, cleaned_text = strip_voice_marker(text)
    effective_voice_name = voice_name or explicit_voice_name
    chunks = split_text_for_tts(cleaned_text, max_chars=max_chars)
    if not chunks:
        raise RuntimeError("Cannot generate voiceover from empty text.")

    all_word_timings = []
    selected_voice_id = resolve_voice_id(
        voice_id=voice_id,
        voice_name=effective_voice_name,
        voice_gender=voice_gender,
        category=category,
        speaker_index=speaker_index,
    )

    if len(chunks) == 1:
        response = _elevenlabs_tts_with_timestamps_request(
            chunks[0],
            voice_id=selected_voice_id,
            category=category,
        )
        audio_base64 = response.get("audio_base64")
        alignment = response.get("normalized_alignment") or response.get("alignment")
        if not audio_base64 or not alignment:
            raise RuntimeError("ElevenLabs did not return audio and alignment data.")

        output_file.write_bytes(b64decode(audio_base64))
        all_word_timings.extend(build_word_timings_from_character_alignment(alignment))
        return (
            all_word_timings,
            get_audio_length(output_file),
            selected_voice_id,
            effective_voice_name,
        )

    with tempfile.TemporaryDirectory(prefix="elevenlabs_parts_", dir=output_file.parent) as temp_dir:
        part_paths = []
        time_offset = 0.0

        for index, chunk in enumerate(chunks):
            previous_text = chunks[index - 1][-500:] if index > 0 else None
            next_text = chunks[index + 1][:500] if index < len(chunks) - 1 else None
            response = _elevenlabs_tts_with_timestamps_request(
                chunk,
                previous_text,
                next_text,
                voice_id=selected_voice_id,
                category=category,
            )
            audio_base64 = response.get("audio_base64")
            alignment = response.get("normalized_alignment") or response.get("alignment")
            if not audio_base64 or not alignment:
                raise RuntimeError(
                    f"ElevenLabs did not return audio and alignment data for chunk {index}."
                )

            part_path = Path(temp_dir) / f"part_{index:03}.mp3"
            part_path.write_bytes(b64decode(audio_base64))
            part_paths.append(part_path)

            all_word_timings.extend(
                build_word_timings_from_character_alignment(
                    alignment,
                    time_offset=time_offset,
                )
            )
            time_offset += get_audio_length(part_path)

        _combine_audio_files(part_paths, output_file)

    return (
        all_word_timings,
        get_audio_length(output_file),
        selected_voice_id,
        effective_voice_name,
    )


def generate_voiceover(
    text,
    filename,
    voice_id=None,
    voice_name=None,
    voice_gender=None,
    category="story",
):
    """
    Generate a voiceover audio file from text using ElevenLabs TTS.
    """
    output_file = Path(filename).expanduser().resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    _generate_words_and_audio_for_text(
        text,
        output_file,
        voice_id=voice_id,
        voice_name=voice_name,
        voice_gender=voice_gender,
        category=category,
    )


def generate_voiceover_and_subtitles(
    text,
    audio_path,
    subtitles_path,
    chars_per_caption,
    voice_id=None,
    voice_gender=None,
    category="story",
    segments=None,
    spoken_title_text=None,
    return_metadata=False,
):
    """
    Generate narration audio and subtitle timings from the same ElevenLabs requests.
    """
    output_file = Path(audio_path).expanduser().resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    all_word_timings = []
    segments = segments or [
        {
            "speaker": "Narrator",
            "voice_gender": voice_gender or "female",
            "text": text,
        }
    ]
    part_paths = []
    segment_voice_choices = []

    with tempfile.TemporaryDirectory(prefix="elevenlabs_segments_", dir=output_file.parent) as temp_dir:
        time_offset = 0.0

        for index, segment in enumerate(segments):
            segment_text = clean_tts_text(segment.get("text", ""))
            if not segment_text:
                continue

            part_path = Path(temp_dir) / f"segment_{index:03}.mp3"
            segment_words, segment_duration, selected_voice_id, resolved_voice_name = _generate_words_and_audio_for_text(
                segment_text,
                part_path,
                voice_id=segment.get("voice_id") or voice_id,
                voice_name=segment.get("voice_name"),
                voice_gender=segment.get("voice_gender") or voice_gender,
                category=category,
                speaker_index=index,
            )
            part_paths.append(part_path)
            segment_voice_choices.append(
                {
                    "speaker": segment.get("speaker", "Narrator"),
                    "voice_gender": segment.get("voice_gender") or voice_gender,
                    "voice_name": resolved_voice_name,
                    "voice_id": selected_voice_id,
                    "text": clean_tts_text(strip_voice_marker(segment_text)[1]),
                }
            )

            all_word_timings.extend(
                {
                    **word,
                    "start": word["start"] + time_offset,
                    "end": word["end"] + time_offset,
                }
                for word in segment_words
            )
            time_offset += segment_duration

        if not part_paths:
            raise RuntimeError("Cannot generate voiceover from empty text.")

        _combine_audio_files(part_paths, output_file)

    subtitles = build_srt_from_word_timings(all_word_timings, chars_per_caption)
    if not subtitles:
        raise RuntimeError("ElevenLabs returned no usable alignment data for subtitles.")

    write_srt(subtitles, subtitles_path)
    metadata = {
        "subtitles": subtitles,
        "spoken_title_duration": estimate_spoken_text_end(
            all_word_timings,
            spoken_title_text,
        ),
        "segments": segment_voice_choices,
    }

    if return_metadata:
        return metadata

    return subtitles


def get_audio_length(filename):
    """
    Get the duration of an audio file in seconds.
    """
    audio = AudioFileClip(str(Path(filename).expanduser().resolve()))
    try:
        return float(audio.duration)
    finally:
        audio.close()
