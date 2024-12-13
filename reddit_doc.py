import praw
import text_to_speech as tts
import re
import os
import logging
import time
from pydub import AudioSegment
import assemblyai as aai

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Section 1
""" Opens the connection between PRAW and script. Initializes API authorizations"""

def reader_function(file_path):
    try:
        with open(file_path, 'r') as file:
            name_variable = file.readline().strip()
        return name_variable
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None

client_ID = reader_function(r"C:\Users\Daniel Mora\Documents\Autopost\CLIENT_ID_REDDIT.txt")
client_secret = reader_function(r"C:\Users\Daniel Mora\Documents\Autopost\client_secret_seed.txt")
user_agent = "autopost by /u/No-Arrival-2825"
reddit = praw.Reddit(client_id=client_ID, client_secret=client_secret, user_agent=user_agent)

subreddit = reddit.subreddit('AITAH')
posts = subreddit.hot(limit=1)

def clean_text(text):
    # Remove URLs
    text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
    # Remove or replace special characters
    text = re.sub(r'[\\/*?:"<>|]', '', text)
    text = re.sub(r'[\r\n\t]+', ' ', text)  # Replace newlines and tabs with space
    return text

file_index = 0
for post in posts:
    if post.stickied:
        continue  # Skip pinned posts
    clean_title = clean_text(post.title)
    clean_selftext = clean_text(post.selftext)
    full_text = f"{clean_title}. {clean_selftext}"
    
    full_text = f"{post.title}. {post.selftext}"
    output_filename = f'output_{file_index}.mp3'
    tts.generate_voiceover(full_text, output_filename)
    file_index += 1
    logging.info(f"Processing post {file_index}: {post.title}")
    logging.info(f"Voiceover saved as {output_filename}")
    print(f"Saved audio to {output_filename}")
    filepath = rf'C:\Users\Daniel Mora\Documents\Autopost\{output_filename}'
    print(filepath)
    file_length = tts.get_audio_length(output_filename)
    logging.info(f"The length of file'{output_filename}'" + f'is: {file_length} seconds')

def check_filepath():
    
    if os.path.isfile(filepath):
        logging.info(f"File {filepath} created successfully.")
        return True
    else:
        logging.error(f"File {filepath} not found.")
        return False
# Start time
start_time = time.time()
tries = 0
max_tries = 100
# Check if the file path exists with a delay and log elapsed time
time.sleep(0)

while not check_filepath() and tries < max_tries:
    elapsed_time = time.time() - start_time
    logging.info(f"Elapsed time: {elapsed_time:.2f} seconds")
    time.sleep(1)  # Wait for 5 seconds before checking again
    tries += 1
    continue
if tries == max_tries:
    logging.error(f"File {filepath} was not found after {max_tries} retries.")

def reader_function2(file_path):
    try:
        with open(file_path, 'r') as file:
            name_variable = file.readline().strip()
        return name_variable
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None

aai.settings.api_key= reader_function(r"C:\Users\Daniel Mora\Documents\Autopost\AssemblyAIkey.txt")

transcript = aai.Transcriber().transcribe(f"output_{file_index}.mp3")
logging.info(f"Transcribing post {file_index}: {post.title}")
subs = transcript.export_subtitles_srt(chars_per_caption=50)

f = open(f'subtitles_{file_index}.srt','a')
f.write(subs)
f.close
logging.info(f"Post {file_index}: Has been succesfully transcribed")
