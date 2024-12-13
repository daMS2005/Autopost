from gtts import gTTS
from pydub import AudioSegment
def generate_voiceover(text, filename):
    tts = gTTS(text)
    tts.save(filename)
def get_audio_length(filename):
    audio = AudioSegment.from_file(filename)
    return len(audio) / 1000  # Length in seconds