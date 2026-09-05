"""Manual paid-provider smoke test for narration and subtitle generation.

This script intentionally lives outside the automated test suite because it
requires an ElevenLabs credential and consumes API quota.
"""

from text_to_speech import generate_voiceover_and_subtitles


def main() -> None:
    transcription = generate_voiceover_and_subtitles(
        "Quick test line for the unified ElevenLabs voice and subtitle flow.",
        "output/testing_voice.mp3",
        "output/test.srt",
        chars_per_caption=40,
    )
    print(transcription)


if __name__ == "__main__":
    main()
