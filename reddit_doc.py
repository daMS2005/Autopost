import praw
import text_to_speech as tts
import re
import os
import logging
import time
import assemblyai as aai
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# API Authentication
client_ID = os.getenv('CLIENT_ID_REDDIT')
client_secret = os.getenv('CLIENT_SECRET_REDDIT')
aai.settings.api_key = os.getenv('ASSEMBLYAI_API_KEY')
user_agent = "autopost by /u/No-Arrival-2825"

# PRAW initialization
reddit = praw.Reddit(client_id=client_ID, client_secret=client_secret, user_agent=user_agent)
subreddit = reddit.subreddit('AITAH')
posts = subreddit.hot(limit=2)

# Clean text function
def clean_text(text):
    text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[\\/*?:"<>|]', '', text)
    text = re.sub(r'[\r\n\t]+', ' ', text)
    return text

# Create output directory if needed
output_dir = os.path.expanduser('~/Desktop/ACC')
os.makedirs(output_dir, exist_ok=True)

file_index = 0

for post in posts:
    if post.stickied:
        continue  # Skip pinned posts

    clean_title = clean_text(post.title)
    clean_selftext = clean_text(post.selftext)
    full_text = f"{clean_title}. {clean_selftext}"

    output_filename = f'output_{file_index}.mp3'
    filepath = os.path.join(output_dir, output_filename)

    # Generate TTS
    tts.generate_voiceover(full_text, filepath)
    logging.info(f"Processing post {file_index}: {post.title}")
    logging.info(f"Voiceover saved as {filepath}")

    # Check if file exists with retry logic
    tries = 0
    max_tries = 10
    while not os.path.isfile(filepath) and tries < max_tries:
        time.sleep(5)  # Wait 5 seconds
        tries += 1
        logging.info(f"Retry {tries}/{max_tries}: Checking for {filepath}")

    if not os.path.isfile(filepath):
        logging.error(f"File {filepath} not created after {max_tries} retries.")
        continue

    # Transcribe the audio
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(filepath)
    subs = transcript.export_subtitles_srt(chars_per_caption=50)

    # Save subtitles
    subtitles_path = os.path.join(output_dir, f'subtitles_{file_index}.srt')
    with open(subtitles_path, 'w') as f:
        f.write(subs)
    logging.info(f"Subtitles saved at {subtitles_path}")

    file_index += 1
