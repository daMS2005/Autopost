import json
import os
import re
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from moviepy.audio.AudioClip import concatenate_audioclips
from moviepy.audio.io.AudioFileClip import AudioFileClip


load_dotenv()

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_ELEVENLABS_VOICE_ID = "wWWn96OtTHu1sn8SRGEr"
DEFAULT_ELEVENLABS_TTS_MODEL = "eleven_multilingual_v2"
DEFAULT_ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_ELEVENLABS_MAX_CHARS = 9_500


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


def clean_tts_text(text):
    return " ".join(str(text).replace("\n", " ").split()).strip()


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


def _build_voice_settings():
    settings = {
        "stability": _env_float("ELEVENLABS_STABILITY", 0.45),
        "similarity_boost": _env_float("ELEVENLABS_SIMILARITY_BOOST", 0.8),
        "style": _env_float("ELEVENLABS_STYLE", 0),
        "speed": _env_float("ELEVENLABS_SPEED", 1.08),
        "use_speaker_boost": _env_bool("ELEVENLABS_USE_SPEAKER_BOOST", True),
    }
    return {key: value for key, value in settings.items() if value is not None}


def _build_request_payload(text, previous_text=None, next_text=None):
    payload = {
        "text": text,
        "model_id": os.getenv("ELEVENLABS_TTS_MODEL", DEFAULT_ELEVENLABS_TTS_MODEL),
        "voice_settings": _build_voice_settings(),
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


def _elevenlabs_tts_request(text, previous_text=None, next_text=None):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_ELEVENLABS_VOICE_ID

    if not api_key:
        raise RuntimeError("Missing ELEVENLABS_API_KEY.")

    output_format = os.getenv(
        "ELEVENLABS_OUTPUT_FORMAT", DEFAULT_ELEVENLABS_OUTPUT_FORMAT
    )
    query = {
        "output_format": output_format,
        "enable_logging": str(_env_bool("ELEVENLABS_ENABLE_LOGGING", True)).lower(),
    }
    url = f"{ELEVENLABS_TTS_URL.format(voice_id=voice_id)}?{urlencode(query)}"
    body = json.dumps(_build_request_payload(text, previous_text, next_text)).encode(
        "utf-8"
    )
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


def generate_voiceover(text, filename):
    """
    Generate a voiceover audio file from text using ElevenLabs TTS.
    """
    output_file = Path(filename).expanduser().resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    max_chars = _env_int("ELEVENLABS_MAX_CHARS", DEFAULT_ELEVENLABS_MAX_CHARS)
    chunks = split_text_for_tts(text, max_chars=max_chars)
    if not chunks:
        raise RuntimeError("Cannot generate voiceover from empty text.")

    if len(chunks) == 1:
        output_file.write_bytes(_elevenlabs_tts_request(chunks[0]))
        return

    with tempfile.TemporaryDirectory(prefix="elevenlabs_parts_", dir=output_file.parent) as temp_dir:
        part_paths = []
        for index, chunk in enumerate(chunks):
            previous_text = chunks[index - 1][-500:] if index > 0 else None
            next_text = chunks[index + 1][:500] if index < len(chunks) - 1 else None
            part_path = Path(temp_dir) / f"part_{index:03}.mp3"
            part_path.write_bytes(_elevenlabs_tts_request(chunk, previous_text, next_text))
            part_paths.append(part_path)

        _combine_audio_files(part_paths, output_file)


def get_audio_length(filename):
    """
    Get the duration of an audio file in seconds.
    """
    audio = AudioFileClip(str(Path(filename).expanduser().resolve()))
    try:
        return float(audio.duration)
    finally:
        audio.close()
