from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip
import pysrt
import text_to_speech as tts
import reddit_doc as rd
# Define file paths
original_video_path = r"C:\Users\Daniel Mora\Documents\Autopost\mc_30_ncr.webm"
copy_path = fr"C:\Users\Daniel Mora\Documents\Autopost\copy_mc_0_ncr.webm"
output_video_path = r"C:\Users\Daniel Mora\Documents\Autopost\video_with_subtitles.mp4"
subtitles_path = r"C:\Users\Daniel Mora\Documents\Autopost\subtitles.srt"

audio = AudioFileClip(fr"C:\Users\Daniel Mora\Documents\Autopost\output_0.mp3")


original_video_path.write_videofile(copy_path, codec='libx264', audio_codec='aac')
start_time = 0
end_time = tts.get_audio_length(rd.output_filename)
cut_video = copy_path.subclip(start_time, end_time)
cut_video_with_audio = cut_video.set_audio(audio)
cut_video_with_audio.write_videofile(fr"C:\Users\Daniel Mora\Documents\Autopost\cut_video_with_audio{rd.file_index}.mp4", codec='libx264', audio_codec='aac')
