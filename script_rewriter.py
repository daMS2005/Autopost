import json
import os
import re

from openai import OpenAI

from voice_registry import build_voice_catalog_prompt, strip_voice_marker

DEFAULT_SCRIPT_MODEL = "gpt-5-mini"
DEFAULT_WORDS_PER_MINUTE = 165
ASK_RESPONSE_PATTERN = re.compile(
    r"(?P<label>[A-Za-z0-9][A-Za-z0-9 ]{0,40} responds:)\s*",
    re.IGNORECASE,
)


SYSTEM_PROMPT = """
You prepare Reddit stories for text-to-speech narration.

Polish the input so it sounds natural when read aloud by a TTS voice.
Keep the meaning and point of view unchanged.
Do not add new facts, jokes, moral judgments, headings, emojis, or markdown.
Do not over-explain common Reddit phrasing that is already easy to understand aloud.
Improve grammar, punctuation, and sentence flow when the original writing would sound clumsy,
choppy, repetitive, or hard to follow when spoken aloud.
Choose whether a male or female narrator voice fits the story better.
Prioritize explicit first-person POV markers over tone.
Return valid JSON only.
"""


V3_AWARE_USER_PROMPT = """
Clean this Reddit post for voiceover narration and choose the narrator voice.

Rules:
- Focus on audibility, not formal rewriting.
- Smooth out rough grammar and awkward sentence flow when it helps the story sound natural out loud.
- Rewrite run-on sentences, fragments, and clunky punctuation into cleaner spoken phrasing when needed.
- Fix common Reddit-style writing issues like missing punctuation, repeated words, abrupt transitions, and confusing phrasing.
- Expand shorthand only when it would sound awkward or confusing in TTS.
- Convert symbols and standalone letters into words when helpful for speech.
- Preserve compact age/gender notation when it is understandable, such as "I, 45 M" or "my sister, 23 F".
- Do not rewrite age/gender notation into phrases like "I am a 45-year-old male" unless the original sentence truly needs it.
- Keep names, ages, subreddit terms, and story details intact.
- Fix grammar, punctuation, spacing, and phrasing wherever it improves spoken clarity and listening flow.
- Preserve paragraph flow, but avoid very long sentences.
- Keep the voice conversational, but remove wording that would sound distractingly ungrammatical when narrated.
- This output is specifically for ElevenLabs eleven_v3.
- You may add very conservative Eleven v3 delivery cues such as [short pause], [long pause], [sighs], [laughs], [whispers], [curious], [sarcastic], [annoyed], [excited], [chuckles].
- Add those cues as inline performance directions that stay in the final text passed to ElevenLabs.
- Use them to shape pauses, laughter, tension, sarcasm, whispers, hesitation, or emphasis when they clearly improve the spoken result.
- Use cues sparingly. Most sentences should have no tag at all.
- Prefer pauses and subtle emotional tags over dramatic acting.
- For horror, subtle tension cues like [whispers], [long pause], [hushed], [uneasy], or [shaken] are usually better than loud or theatrical tags.
- For funny or absurd moments, light tags like [chuckles], [laughs], or [sarcastic] are okay when the line really benefits.
- Do not add non-auditory tags like [standing], [music], or [pacing].
- Do not add SSML break tags.
- If a sentence does not clearly benefit from a cue, leave it alone.
- Category:
  - `story`: natural Reddit storytelling, keep it emotionally clear and easy to follow.
  - `horror`: preserve suspense, creepiness, and pacing. Use pauses and subtle tonal cues a little more intentionally, but still conservatively.
  - `ask`: keep it brisk and clean. The title and comment responses should be easy to follow as short spoken beats.
    Keep the title first. If the text includes comment-response turns, preserve each `{{username}} responds:` beat in a clearly spoken form.
- Available voice names and descriptions:
{voice_catalog}
- OpenAI only has access to those voice names and descriptions, never IDs.
- Choose `voice_gender` as either `male` or `female`.
- Base the choice primarily on the narrator's explicit first-person POV markers.
- If the text says `I (32M)`, `I, 32 M`, `me, 32M`, `my husband and I (28F)`, or anything equivalent, use that marker first.
- If the story is clearly told by a woman in first person, choose `female`.
- If the story is clearly told by a man in first person, choose `male`.
- Only if the POV gender is genuinely unclear should you fall back to overall tone and story fit.
- You may optionally return `segments` when distinct speaker changes are clear and using multiple voices would help.
- Use `segments` when the story truly contains different speakers, direct dialogue, or comment-response turns worth voicing separately.
- For `ask`, prefer returning `segments`: one opening title segment, then one segment per comment response turn.
- For `story` or `horror`, prefer `segments` only when direct dialogue or clearly different speakers would sound better with separate voices.
- When `segments` are used, each segment can carry its own inline delivery cues inside `text`.
- When a segment should use a specific voice, prefix that segment text with `<<VOICE:Name>>`.
- Only use voice names from the provided catalog. Do not invent new names.
- Each segment must preserve the original order and contain:
  - `speaker`
  - `voice_gender`
  - `text`
- If a response or dialogue speaker's gender is unclear, keep the main narrator gender instead of guessing.
- If you use `segments`, the concatenated segment text should closely match `script`.
- Return a JSON object with exactly these keys:
  - `script`
  - `voice_gender`
  - `segments`

Category: {category}
Text:
{text}
"""

USER_PROMPT = """
Clean this Reddit post for voiceover narration and choose the narrator voice.

Rules:
- Focus on audibility, not formal rewriting.
- Smooth out rough grammar and awkward sentence flow when it helps the story sound natural out loud.
- Rewrite run-on sentences, fragments, and clunky punctuation into cleaner spoken phrasing when needed.
- Fix common Reddit-style writing issues like missing punctuation, repeated words, abrupt transitions, and confusing phrasing.
- Expand shorthand only when it would sound awkward or confusing in TTS.
- Convert symbols and standalone letters into words when helpful for speech.
- Preserve compact age/gender notation when it is understandable, such as "I, 45 M" or "my sister, 23 F".
- Do not rewrite age/gender notation into phrases like "I am a 45-year-old male" unless the original sentence truly needs it.
- Keep names, ages, subreddit terms, and story details intact.
- Fix grammar, punctuation, spacing, and phrasing wherever it improves spoken clarity and listening flow.
- Preserve paragraph flow, but avoid very long sentences.
- Keep the voice conversational, but remove wording that would sound distractingly ungrammatical when narrated.
- You may add light inline delivery cues for ElevenLabs v3 when they clearly help the final speech, such as [short pause], [long pause], [sighs], [laughs], [whispers], [curious], [sarcastic], [annoyed], [excited], [chuckles].
- For horror, prefer subtle tension and pacing cues over dramatic acting.
- Category:
  - `story`: natural Reddit storytelling, keep it emotionally clear and easy to follow.
  - `horror`: preserve suspense, creepiness, and pacing.
  - `ask`: keep it brisk and clean. The title and comment responses should be easy to follow as short spoken beats.
    Keep the title first. If the text includes comment-response turns, preserve each `{{username}} responds:` beat in a clearly spoken form.
- Available voice names and descriptions:
{voice_catalog}
- OpenAI only has access to those voice names and descriptions, never IDs.
- Choose `voice_gender` as either `male` or `female`.
- Base the choice primarily on the narrator's explicit first-person POV markers.
- If the text says `I (32M)`, `I, 32 M`, `me, 32M`, `my husband and I (28F)`, or anything equivalent, use that marker first.
- If the story is clearly told by a woman in first person, choose `female`.
- If the story is clearly told by a man in first person, choose `male`.
- Only if the POV gender is genuinely unclear should you fall back to overall tone and story fit.
- You may optionally return `segments` when distinct speaker changes are clear and using multiple voices would help.
- For `ask`, prefer returning `segments`: one opening title segment, then one segment per comment response turn.
- For `story` or `horror`, prefer `segments` only when direct dialogue or clearly different speakers would sound better with separate voices.
- When a segment should use a specific voice, prefix that segment text with `<<VOICE:Name>>`.
- Only use voice names from the provided catalog. Do not invent new names.
- Each segment must preserve the original order and contain:
  - `speaker`
  - `voice_gender`
  - `text`
- If a response or dialogue speaker's gender is unclear, keep the main narrator gender instead of guessing.
- Return a JSON object with exactly these keys:
  - `script`
  - `voice_gender`
  - `segments`

Category: {category}
Text:
{text}
"""


def _parse_voiceover_json(text):
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
    payload = json.loads(candidate)
    script = str(payload.get("script", "")).strip()
    voice_gender = str(payload.get("voice_gender", "")).strip().lower()
    if not script:
        raise RuntimeError("OpenAI returned an empty narration script.")
    if voice_gender not in {"male", "female"}:
        raise RuntimeError("OpenAI returned an invalid voice gender.")
    segments = []
    for segment in payload.get("segments") or []:
        segment_text = str(segment.get("text", "")).strip()
        marker_voice_name, segment_text = strip_voice_marker(segment_text)
        explicit_voice_name = str(segment.get("voice_name", "")).strip() or None
        segment_gender = str(segment.get("voice_gender", "")).strip().lower()
        speaker = str(segment.get("speaker", "")).strip() or "Narrator"
        if not segment_text:
            continue
        if segment_gender not in {"male", "female"}:
            segment_gender = voice_gender
        segments.append(
            {
                "speaker": speaker,
                "voice_gender": segment_gender,
                "text": segment_text,
                "voice_name": explicit_voice_name or marker_voice_name,
            }
        )

    if not segments:
        marker_voice_name, script_text = strip_voice_marker(script)
        script = script_text or script
        segments = [
            {
                "speaker": "Narrator",
                "voice_gender": voice_gender,
                "text": script,
                "voice_name": marker_voice_name,
            }
        ]

    return {
        "script": script,
        "voice_gender": voice_gender,
        "segments": segments,
    }


def _estimate_spoken_seconds(text, words_per_minute=DEFAULT_WORDS_PER_MINUTE):
    word_count = len(str(text or "").split())
    if word_count <= 0:
        return 0.0
    return (word_count / max(words_per_minute, 1)) * 60


def _infer_ask_segments(script, voice_gender):
    text = str(script or "").strip()
    if not text:
        return []

    matches = list(ASK_RESPONSE_PATTERN.finditer(text))
    if not matches:
        return [
            {
                "speaker": "Narrator",
                "voice_gender": voice_gender,
                "text": text,
                "voice_name": None,
            }
        ]

    segments = []
    title_text = text[: matches[0].start()].strip()
    if title_text:
        segments.append(
            {
                "speaker": "Narrator",
                "voice_gender": voice_gender,
                "text": title_text,
                "voice_name": None,
            }
        )

    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment_text = text[match.start() : next_start].strip()
        if not segment_text:
            continue

        speaker = match.group("label").rsplit(" responds:", 1)[0].strip() or "A Reddit user"
        segments.append(
            {
                "speaker": speaker,
                "voice_gender": voice_gender,
                "text": segment_text,
                "voice_name": None,
            }
        )

    return segments or [
        {
            "speaker": "Narrator",
            "voice_gender": voice_gender,
            "text": text,
            "voice_name": None,
        }
    ]


def finalize_prepared_voiceover(prepared_voiceover, category="story", target_max_seconds=None):
    script = str(prepared_voiceover.get("script", "")).strip()
    voice_gender = str(prepared_voiceover.get("voice_gender", "female")).strip().lower() or "female"
    segments = list(prepared_voiceover.get("segments") or [])

    if category == "ask":
        if len(segments) <= 1:
            segments = _infer_ask_segments(script, voice_gender)

        if target_max_seconds:
            kept_segments = []
            elapsed_seconds = 0.0

            for segment in segments:
                segment_seconds = _estimate_spoken_seconds(segment.get("text", ""))
                if kept_segments and elapsed_seconds + segment_seconds > target_max_seconds:
                    break

                kept_segments.append(segment)
                elapsed_seconds += segment_seconds

            if kept_segments:
                segments = kept_segments

    if segments:
        script = " ".join(str(segment.get("text", "")).strip() for segment in segments).strip()

    return {
        "script": script,
        "voice_gender": voice_gender,
        "segments": segments
        or [
            {
                "speaker": "Narrator",
                "voice_gender": voice_gender,
                "text": script,
                "voice_name": None,
            }
        ],
    }


def prepare_voiceover(text, model=None, add_v3_directions=False, category="story"):
    """
    Use one OpenAI call to clean the narration and choose a male/female narrator voice.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY for voiceover script cleanup.")

    selected_model = model or os.getenv("OPENAI_SCRIPT_MODEL") or DEFAULT_SCRIPT_MODEL
    client = OpenAI(api_key=api_key)
    prompt_template = V3_AWARE_USER_PROMPT if add_v3_directions else USER_PROMPT
    voice_catalog = build_voice_catalog_prompt()

    response = client.responses.create(
        model=selected_model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {
                "role": "user",
                "content": prompt_template.format(
                    text=text,
                    category=category,
                    voice_catalog=voice_catalog,
                ).strip(),
            },
        ],
    )

    response_text = response.output_text.strip()
    if not response_text:
        raise RuntimeError("OpenAI returned an empty voiceover response.")

    return _parse_voiceover_json(response_text)


def rewrite_for_voiceover(text, model=None, add_v3_directions=False, category="story"):
    """
    Compatibility wrapper that returns only the cleaned script text.
    """
    return prepare_voiceover(
        text,
        model=model,
        add_v3_directions=add_v3_directions,
        category=category,
    )["script"]
