import os

from openai import OpenAI


DEFAULT_SCRIPT_MODEL = "gpt-5-mini"


SYSTEM_PROMPT = """
You prepare Reddit stories for text-to-speech narration.

Lightly polish the input so it sounds natural when read aloud by a TTS voice.
Keep the meaning and point of view unchanged.
Do not add new facts, jokes, moral judgments, headings, emojis, or markdown.
Do not over-explain common Reddit phrasing that is already easy to understand aloud.
Return only the cleaned narration text.
"""


USER_PROMPT = """
Clean this Reddit post for voiceover narration.

Rules:
- Focus on audibility, not formal rewriting.
- Expand shorthand only when it would sound awkward or confusing in TTS.
- Convert symbols and standalone letters into words when helpful for speech.
- Preserve compact age/gender notation when it is understandable, such as "I, 45 M" or "my sister, 23 F".
- Do not rewrite age/gender notation into phrases like "I am a 45-year-old male" unless the original sentence truly needs it.
- Keep names, ages, subreddit terms, and story details intact.
- Fix obvious grammar, punctuation, and spacing only where it improves spoken clarity.
- Preserve paragraph flow, but avoid very long sentences.

Text:
{text}
"""


def rewrite_for_voiceover(text, model=None):
    """
    Use an OpenAI model as a lightweight script-polishing step before TTS.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY for voiceover script cleanup.")

    selected_model = model or os.getenv("OPENAI_SCRIPT_MODEL") or DEFAULT_SCRIPT_MODEL
    client = OpenAI(api_key=api_key)

    response = client.responses.create(
        model=selected_model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": USER_PROMPT.format(text=text).strip()},
        ],
    )

    cleaned_text = response.output_text.strip()
    if not cleaned_text:
        raise RuntimeError("OpenAI returned an empty cleaned script.")

    return cleaned_text
