import os
from pathlib import Path

import assemblyai as aai
from dotenv import load_dotenv


load_dotenv()


def format_srt_timestamp(seconds):
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def clean_caption_text(text):
    return " ".join(text.replace("\n", " ").split()).strip()


def _word_text(word):
    return clean_caption_text(getattr(word, "text", "") or "")


def _word_start_seconds(word):
    start = getattr(word, "start", None)
    if start is None:
        return None
    return float(start) / 1000


def _word_end_seconds(word):
    end = getattr(word, "end", None)
    if end is None:
        return None
    return float(end) / 1000


def build_srt_from_words(words, chars_per_caption):
    captions = []
    current_words = []
    current_start = None
    current_end = None
    max_chars = max(8, chars_per_caption)

    for word in words:
        text = _word_text(word)
        start = _word_start_seconds(word)
        end = _word_end_seconds(word)
        if not text or start is None or end is None:
            continue

        candidate = clean_caption_text(" ".join([*current_words, text]))
        should_flush = (
            current_words
            and len(candidate) > max_chars
            and clean_caption_text(" ".join(current_words))
        )

        if should_flush:
            captions.append(
                (
                    current_start,
                    current_end,
                    clean_caption_text(" ".join(current_words)),
                )
            )
            current_words = []
            current_start = None

        if current_start is None:
            current_start = start
        current_words.append(text)
        current_end = end

        if text.endswith((".", "!", "?")):
            captions.append(
                (
                    current_start,
                    current_end,
                    clean_caption_text(" ".join(current_words)),
                )
            )
            current_words = []
            current_start = None
            current_end = None

    if current_words and current_start is not None and current_end is not None:
        captions.append(
            (
                current_start,
                current_end,
                clean_caption_text(" ".join(current_words)),
            )
        )

    return "\n\n".join(
        "\n".join(
            (
                str(index),
                f"{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}",
                text,
            )
        )
        for index, (start, end, text) in enumerate(captions, start=1)
    ) + ("\n" if captions else "")


def request_assemblyai_transcription(filepath):
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ASSEMBLYAI_API_KEY.")

    aai.settings.api_key = api_key
    transcript = aai.Transcriber().transcribe(filepath)

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI transcription failed: {transcript.error}")

    return transcript


def transcribe_audio(filepath, output_path, chars_per_caption=15):
    """
    Transcribe an audio file with AssemblyAI and save subtitles in SRT format.
    """
    transcript = request_assemblyai_transcription(filepath)
    subtitles = build_srt_from_words(
        getattr(transcript, "words", []) or [],
        chars_per_caption=chars_per_caption,
    )
    if not subtitles:
        raise RuntimeError("AssemblyAI returned no timestamped words for subtitles.")

    output_file = Path(output_path).expanduser()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(subtitles, encoding="utf-8")

    return subtitles
