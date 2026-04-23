from pathlib import Path

from gtts import gTTS
from moviepy.audio.io.AudioFileClip import AudioFileClip


def generate_voiceover(text, filename):
    """
    Generate a voiceover audio file from the given text.
    """
    output_file = Path(filename).expanduser().resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    tts = gTTS(text)
    tts.save(str(output_file))


def get_audio_length(filename):
    """
    Get the duration of an audio file in seconds.
    """
    audio = AudioFileClip(str(Path(filename).expanduser().resolve()))
    try:
        return float(audio.duration)
    finally:
        audio.close()
