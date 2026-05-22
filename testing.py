from text_to_speech import generate_voiceover_and_subtitles


transcription = generate_voiceover_and_subtitles(
    "Quick test line for the unified ElevenLabs voice and subtitle flow.",
    "/Users/danielmora/Desktop/ACC/output/testing_voice.mp3",
    "/Users/danielmora/Desktop/ACC/output/test.srt",
    chars_per_caption=40,
)

print(transcription)
