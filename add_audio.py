from pathlib import Path

from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.io.VideoFileClip import VideoFileClip


def add_audio_to_video(video_path, audio_path, output_path):
    """
    Attach an audio track to a video and export a new file.
    """
    output_file = Path(output_path).expanduser().resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)

    try:
        video_with_audio = video.with_audio(audio.subclipped(0, video.duration))
        video_with_audio.write_videofile(
            str(output_file),
            codec="libx264",
            audio_codec="aac",
            threads=4,
            fps=video.fps or 24,
        )
        video_with_audio.close()
    finally:
        video.close()
        audio.close()
