import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from text_to_speech import (
    DEFAULT_ELEVENLABS_OUTPUT_FORMAT,
    DEFAULT_ELEVENLABS_TTS_MODEL,
    DEFAULT_ELEVENLABS_VOICE_ID,
    clean_tts_text,
    get_default_max_chars,
)

load_dotenv()

ELEVENLABS_VOICES_URL = "https://api.elevenlabs.io/v1/voices"
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_VOICE_LAB_OUTPUT_DIR = Path("output") / "voice_lab"


def _require_api_key():
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ELEVENLABS_API_KEY.")
    return api_key


def _request_json(url, method="GET", body=None, headers=None, timeout=120):
    request = Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ElevenLabs request failed with HTTP {exc.code}: {error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"ElevenLabs request failed: {exc}") from exc


def _request_bytes(url, method="GET", body=None, headers=None, timeout=240):
    request = Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ElevenLabs request failed with HTTP {exc.code}: {error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"ElevenLabs request failed: {exc}") from exc


def list_voices():
    """
    Return the available voices from the connected ElevenLabs account.
    """
    api_key = _require_api_key()
    payload = _request_json(
        ELEVENLABS_VOICES_URL,
        headers={
            "xi-api-key": api_key,
            "Accept": "application/json",
        },
    )

    voices = []
    for voice in payload.get("voices", []):
        labels = voice.get("labels") or {}
        voices.append(
            {
                "name": voice.get("name"),
                "voice_id": voice.get("voice_id"),
                "category": voice.get("category"),
                "accent": labels.get("accent"),
                "age": labels.get("age"),
                "description": labels.get("description"),
                "gender": labels.get("gender"),
                "use_case": labels.get("use_case"),
            }
        )

    return voices


def default_voice_settings(
    stability=0.30,
    similarity_boost=0.8,
    style=0.0,
    speed=1.1,
    use_speaker_boost=True,
):
    return {
        "stability": float(stability),
        "similarity_boost": float(similarity_boost),
        "style": float(style),
        "speed": float(speed),
        "use_speaker_boost": bool(use_speaker_boost),
    }


def estimate_preview_characters(text, runs=1):
    normalized = clean_tts_text(text)
    return {
        "characters_per_run": len(normalized),
        "runs": int(runs),
        "total_characters": len(normalized) * int(runs),
        "default_model": os.getenv("ELEVENLABS_TTS_MODEL") or DEFAULT_ELEVENLABS_TTS_MODEL,
        "recommended_max_chars": get_default_max_chars(
            os.getenv("ELEVENLABS_TTS_MODEL") or DEFAULT_ELEVENLABS_TTS_MODEL
        ),
    }


def generate_preview(
    text,
    output_name,
    voice_id=None,
    model_id=None,
    output_format=None,
    voice_settings=None,
    apply_text_normalization="auto",
    language_code=None,
    seed=None,
    output_dir=DEFAULT_VOICE_LAB_OUTPUT_DIR,
):
    """
    Generate one short ElevenLabs preview clip with explicit settings.
    """
    api_key = _require_api_key()
    normalized = clean_tts_text(text)
    if not normalized:
        raise RuntimeError("Preview text cannot be empty.")

    selected_voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_ELEVENLABS_VOICE_ID
    selected_model = model_id or os.getenv("ELEVENLABS_TTS_MODEL") or DEFAULT_ELEVENLABS_TTS_MODEL
    selected_output_format = (
        output_format or os.getenv("ELEVENLABS_OUTPUT_FORMAT") or DEFAULT_ELEVENLABS_OUTPUT_FORMAT
    )
    selected_language_code = language_code or os.getenv("ELEVENLABS_LANGUAGE_CODE")
    selected_seed = seed if seed is not None else os.getenv("ELEVENLABS_SEED")
    selected_voice_settings = voice_settings or default_voice_settings()

    query = urlencode(
        {
            "output_format": selected_output_format,
            "enable_logging": "false",
        }
    )
    url = f"{ELEVENLABS_TTS_URL.format(voice_id=selected_voice_id)}?{query}"
    payload = {
        "text": normalized,
        "model_id": selected_model,
        "voice_settings": selected_voice_settings,
        "apply_text_normalization": apply_text_normalization,
    }
    if selected_language_code:
        payload["language_code"] = selected_language_code
    if selected_seed not in (None, ""):
        payload["seed"] = int(selected_seed)

    audio_bytes = _request_bytes(
        url,
        method="POST",
        body=json.dumps(payload).encode("utf-8"),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )

    output_root = Path(output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    file_name = output_name if output_name.endswith(".mp3") else f"{output_name}.mp3"
    output_path = output_root / file_name
    output_path.write_bytes(audio_bytes)
    return output_path


def generate_preview_grid(text, experiments, output_dir=DEFAULT_VOICE_LAB_OUTPUT_DIR):
    """
    Run several preview experiments and return structured metadata.
    """
    results = []
    for experiment in experiments:
        name = experiment["name"]
        output_name = experiment.get("output_name", name.replace(" ", "_").lower())
        output_path = generate_preview(
            text=text,
            output_name=output_name,
            voice_id=experiment.get("voice_id"),
            model_id=experiment.get("model_id"),
            output_format=experiment.get("output_format"),
            voice_settings=experiment.get("voice_settings"),
            apply_text_normalization=experiment.get("apply_text_normalization", "auto"),
            language_code=experiment.get("language_code"),
            seed=experiment.get("seed"),
            output_dir=output_dir,
        )
        results.append(
            {
                "name": name,
                "voice_id": experiment.get("voice_id"),
                "output_path": str(output_path),
                "voice_settings": experiment.get("voice_settings"),
            }
        )

    return results
