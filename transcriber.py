import re
from pathlib import Path


def format_srt_timestamp(seconds):
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def clean_caption_text(text):
    return " ".join(str(text).replace("\n", " ").split()).strip()


def _strip_nonspoken_markup(text):
    stripped = re.sub(r"\[[^\]]*\]", " ", str(text))
    stripped = re.sub(r"<[^>]*>", " ", stripped)
    return clean_caption_text(stripped)


def _normalize_match_token(token):
    normalized = re.sub(r"(^[^\w']+|[^\w']+$)", "", str(token).lower())
    return normalized.strip("_")


def extract_spoken_tokens(text):
    stripped = _strip_nonspoken_markup(text)
    return [
        normalized
        for normalized in (_normalize_match_token(part) for part in stripped.split())
        if normalized
    ]


def estimate_spoken_text_end(words, text):
    """
    Estimate when a known leading spoken phrase finishes in the generated word timings.
    """
    target_tokens = extract_spoken_tokens(text)
    if not target_tokens:
        return None

    remaining_tokens = list(target_tokens)

    for word in words:
        spoken_token = _normalize_match_token(word.get("text", ""))
        if not spoken_token:
            continue

        if spoken_token != remaining_tokens[0]:
            break

        remaining_tokens.pop(0)
        if not remaining_tokens:
            return float(word.get("end", 0) or 0)

    return None


def _iter_spoken_characters(alignment):
    characters = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []

    square_bracket_depth = 0
    angle_bracket_depth = 0

    for char, start, end in zip(characters, starts, ends):
        if char == "[":
            square_bracket_depth += 1
            continue
        if char == "]" and square_bracket_depth > 0:
            square_bracket_depth -= 1
            continue
        if char == "<":
            angle_bracket_depth += 1
            continue
        if char == ">" and angle_bracket_depth > 0:
            angle_bracket_depth -= 1
            continue
        if square_bracket_depth or angle_bracket_depth:
            continue

        yield char, float(start), float(end)


def build_word_timings_from_character_alignment(alignment, time_offset=0.0):
    """
    Convert ElevenLabs character-level timings into word-level timings.
    """
    words = []
    current_characters = []
    current_start = None
    current_end = None

    for char, start, end in _iter_spoken_characters(alignment):
        if char.isspace():
            if current_characters:
                word_text = clean_caption_text("".join(current_characters))
                if word_text:
                    words.append(
                        {
                            "text": word_text,
                            "start": current_start + time_offset,
                            "end": current_end + time_offset,
                        }
                    )
                current_characters = []
                current_start = None
                current_end = None
            continue

        if current_start is None:
            current_start = start
        current_characters.append(char)
        current_end = end

    if current_characters:
        word_text = clean_caption_text("".join(current_characters))
        if word_text:
            words.append(
                {
                    "text": word_text,
                    "start": current_start + time_offset,
                    "end": current_end + time_offset,
                }
            )

    return words


def build_srt_from_word_timings(words, chars_per_caption):
    captions = []
    current_words = []
    current_start = None
    current_end = None
    max_chars = max(8, chars_per_caption)

    for word in words:
        text = clean_caption_text(word.get("text", ""))
        start = word.get("start")
        end = word.get("end")
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
            current_start = float(start)
        current_words.append(text)
        current_end = float(end)

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


def write_srt(subtitles, output_path):
    output_file = Path(output_path).expanduser()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(subtitles, encoding="utf-8")
    return subtitles
