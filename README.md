# Autopost

Generate short-form Reddit videos with:

- Reddit post scraping
- OpenAI voiceover script cleanup
- Opening Reddit title card rendering
- ElevenLabs voiceover generation
- AssemblyAI subtitle transcription
- MoviePy subtitle rendering on top of background video

## Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Create a `.env` file:

```bash
CLIENT_ID_REDDIT=your_reddit_client_id
CLIENT_SECRET_REDDIT=your_reddit_client_secret
ASSEMBLYAI_API_KEY=your_assemblyai_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=wWWn96OtTHu1sn8SRGEr
ELEVENLABS_TTS_MODEL=eleven_multilingual_v2
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
ELEVENLABS_STABILITY=0.45
ELEVENLABS_SIMILARITY_BOOST=0.8
ELEVENLABS_STYLE=0
ELEVENLABS_SPEED=1
ELEVENLABS_USE_SPEAKER_BOOST=true
OPENAI_API_KEY=your_openai_api_key
OPENAI_SCRIPT_MODEL=gpt-5-mini
SUBREDDIT=AITAH
```

`ELEVENLABS_VOICE_ID` defaults to Hale. Swap it for any voice ID from your ElevenLabs voice library.

3. Add one or more background `.mp4` files to the `videos/` folder.

## Run

```bash
python main.py --subreddit AITAH --limit 2 --chars-per-caption 22
```

Optional flags:

- `--video-dir` to point at a different folder of background clips
- `--output-dir` to change where rendered files are written
- `--titles-file output/titles.txt` to save scraped titles
- `--font-path /path/to/font.ttf` to override the bundled subtitle font
- `--script-model gpt-5-mini` to choose the OpenAI cleanup model
- `--skip-script-cleanup` to bypass OpenAI and use raw Reddit text
- `--title-card-template official_image.png` to choose the title card template
- `--title-card-duration 0` to infer title card timing from the first spoken sentence
- `--skip-title-card` to render videos without the opening title image

## Output

Rendered assets are written to `output/`:

- `output_*.mp3` for ElevenLabs narration
- `script_raw_*.txt` for the original Reddit text
- `script_vocab_*.txt` for deterministic vocabulary replacements before OpenAI
- `script_cleaned_*.txt` for the OpenAI-polished voiceover script
- `title_card_*.png` for the generated post title image
- `subtitles_*.srt` for AssemblyAI transcript captions
- `temp_video_*.mp4` for trimmed background clips
- `final_video_*.mp4` for finished videos with narration and subtitles

## Notes

- The app now fails clearly if required API keys are missing or there are no usable background videos.
- Short background clips are looped automatically when the narration is longer than the source footage.
- Final videos render as 9:16 portrait clips, with source footage center-cropped to `1080x1920`.
- Reddit text gets deterministic vocab cleanup before OpenAI, using `reddit_vocabulary.py` for exact shorthand such as `AITAH`, `WIBTAH`, `TLDR`, and `bc`.
- OpenAI then lightly polishes for audibility without over-explaining common Reddit notation like `I, 45 M`.
- ElevenLabs generates narration in chunks for long posts, then the app joins the chunks into one MP3 before transcription.
- AssemblyAI generates word timestamps, then the app chunks those words into SRT captions using `--chars-per-caption`.
- Subtitle timings are lightly normalized before rendering so adjacent captions do not visually stack.
- Subtitles and narration are rendered in one pass so the final video keeps both overlays and audio.
- `videofetcher.py` can still be used to download source footage, but the main pipeline only needs local `.mp4` files in the video directory.
