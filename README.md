# Autopost

Generate short-form Reddit videos with:

- Reddit post scraping
- Story, horror, and ask subreddit modes
- OpenAI voiceover script cleanup
- Opening Reddit title card rendering
- ElevenLabs voiceover generation
- ElevenLabs subtitle timing generation
- MoviePy subtitle rendering on top of background video
- Optional YouTube and TikTok publisher helpers
- Optional YouTube Studio and TikTok web automation fallback

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
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=wWWn96OtTHu1sn8SRGEr
ELEVENLABS_FEMALE_VOICE_ID=EXAVITQu4vr4xnSDxMaL
ELEVENLABS_MALE_VOICE_ID=CwhRBWXzGAHq8TQ4Fs17
ELEVENLABS_TTS_MODEL=eleven_v3
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
ELEVENLABS_STABILITY=0.30
ELEVENLABS_SIMILARITY_BOOST=0.8
ELEVENLABS_STYLE=0
ELEVENLABS_SPEED=1.1
ELEVENLABS_USE_SPEAKER_BOOST=true
OPENAI_API_KEY=your_openai_api_key
OPENAI_SCRIPT_MODEL=gpt-5-mini
SUBREDDIT=AITAH
```

The pipeline can automatically choose between Sarah and Roger by narrator gender.
`ELEVENLABS_FEMALE_VOICE_ID` defaults to Sarah and `ELEVENLABS_MALE_VOICE_ID` defaults to Roger.
`ELEVENLABS_VOICE_ID` is still supported as a general fallback override.

For social publishing helpers:

```bash
TIKTOK_CLIENT_KEY=your_tiktok_client_key
TIKTOK_CLIENT_SECRET=your_tiktok_client_secret
TIKTOK_REDIRECT_URI=https://your-app.example.com/tiktok/callback
YOUTUBE_CLIENT_SECRETS_FILE=client_secrets.json
GOOGLE_LOGIN_EMAIL=you@example.com
GOOGLE_LOGIN_PASSWORD=your_google_password
TIKTOK_LOGIN_EMAIL=you@example.com
TIKTOK_LOGIN_PASSWORD=your_tiktok_password
INSTAGRAM_USERNAME=your_instagram_username
INSTAGRAM_PASSWORD=your_instagram_password
```

3. Add one or more background `.mp4` files to the `videos/` folder.
You can keep everything in `videos/`, or organize by category:

- `videos/story/` for AITAH, TIFU, advice-style story clips
- `videos/horror/` for NoSleep, creepypasta, scary story clips
- `videos/ask/` for AskReddit-style clips

If a category subfolder does not exist, or exists but has no `.mp4` files yet, the pipeline falls back to the root `videos/` folder.

## Run

```bash
python main.py --subreddit AITAH --limit 2 --chars-per-caption 22
```

You can also pass multiple subreddits in one run:

```bash
python main.py --subreddit "aitah,tifu,advice"
python main.py --subreddit "nosleep,creepypasta,scarystories"
python main.py --subreddit "askreddit,askmen,askscience,nostupidquestions"
```

Optional flags:

- `--background-speed 1.1` to speed up the background footage without changing narration
- `--video-dir` to point at a different folder of background clips
- `--output-dir` to change where rendered files are written
- `--processed-posts-file data/processed_posts.jsonl` to track already processed Reddit posts and skip duplicates
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
- `script_cleaned_*.txt` for the OpenAI-polished voiceover script, including optional conservative v3 cues
- `voice_choice_*.txt` for the selected narrator gender and resolved voice ID
- `title_card_*.png` for the generated post title image
- `subtitles_*.srt` for ElevenLabs timing-based captions
- `temp_video_*.mp4` for trimmed background clips
- `final_video_*.mp4` for finished videos with narration and subtitles
- `post_metadata_*.json` for the original Reddit title, subreddit, category, and related output paths
- `data/processed_posts.jsonl` for dedupe history with the post title, Reddit ID, content hash, and processing date

## Publishing

The project now includes a separate publisher helper in [publish_cli.py](/Users/danielmora/Desktop/ACC/publish_cli.py) and the underlying client logic in [social_publishers.py](/Users/danielmora/Desktop/ACC/social_publishers.py).

TikTok auth URL:

```bash
python publish_cli.py tiktok-auth-url --redirect-uri "$TIKTOK_REDIRECT_URI"
```

Exchange the returned `code`:

```bash
python publish_cli.py tiktok-exchange-code \
  --redirect-uri "$TIKTOK_REDIRECT_URI" \
  --code "PASTE_CALLBACK_CODE_HERE"
```

Query creator posting options:

```bash
python publish_cli.py tiktok-creator-info
```

Prepare a finished video for social posting by splitting it into roughly 60-second parts:

```bash
python publish_cli.py prepare-video \
  --video-path output/final_video_0.mp4 \
  --category story \
  --subreddit aitah \
  --output-dir output/publish/post_0
```

If the video came from the main pipeline, the helper can automatically reuse the original Reddit post title from the matching `post_metadata_*.json` file, so `--title` is optional in the normal flow.

This creates:

- part videos like `..._part_01.mp4`
- cover images like `..._cover_part_01.jpg`, using the Reddit title card plus the part number
- `publish_manifest.json` with:
  - the split timings
  - the generated cover image path for each part
  - the per-part title
  - the full caption with hashtags
  - the hashtag list for each part

YouTube upload:

```bash
python publish_cli.py youtube-upload \
  --video-path output/final_video_0.mp4 \
  --title "Your title here" \
  --description "Your description here" \
  --tags "reddit,stories" \
  --privacy-status private
```

Browser automation fallback for YouTube Studio:

```bash
python publish_cli.py youtube-web-upload \
  --video-path output/final_video_0.mp4 \
  --title "Your title here" \
  --description "Your description here"
```

Browser automation fallback for TikTok web:

```bash
python publish_cli.py tiktok-web-upload \
  --video-path output/publish/post_0/your-title_part_01.mp4 \
  --caption "Your caption here"
```

Browser automation fallback for Instagram Reels:

```bash
python publish_cli.py instagram-web-upload \
  --video-path output/publish/post_0/your-title_part_01.mp4 \
  --cover-path output/publish/post_0/your-title_cover_part_01.jpg \
  --title "Your title here"
```

Schedule an Instagram Reel through Instagram's native scheduler, when the current
account and composer UI expose scheduling:

```bash
python publish_cli.py instagram-web-upload \
  --video-path output/publish/post_0/your-title_part_01.mp4 \
  --cover-path output/publish/post_0/your-title_cover_part_01.jpg \
  --caption "Your caption here" \
  --schedule-at "2026-05-22 18:30"
```

Split a finished video into Instagram-ready parts and upload them:

```bash
python publish_cli.py instagram-web-upload-parts \
  --video-path output/final_video_0.mp4 \
  --output-dir output/publish/post_0
```

Schedule split Instagram parts with a delay between parts:

```bash
python publish_cli.py instagram-web-upload-parts \
  --video-path output/final_video_0.mp4 \
  --output-dir output/publish/post_0 \
  --schedule-at "2026-05-22 18:30" \
  --schedule-gap-minutes 20
```

Monday weekly workflow: post one video per configured subreddit today, then
schedule one video per subreddit for each remaining day of the week. This scans
rendered `post_metadata_*.json` files, groups videos by subreddit, prepares
split part manifests, posts day 1 immediately, and schedules days 2-7 through
Instagram's native scheduler:

```bash
python publish_cli.py instagram-weekly-subreddit-run \
  --rendered-dir output \
  --publish-root output/publish/weekly \
  --subreddits all \
  --categories story,horror,ask \
  --start-date 2026-05-25 \
  --first-time "12:00" \
  --subreddit-gap-minutes 45 \
  --daily-times "aitah=18:00,nosleep=21:00,askreddit=15:00" \
  --parts-gap-minutes 20 \
  --cleanup-after-success
```

Preview the Monday plan without opening Instagram:

```bash
python publish_cli.py instagram-weekly-subreddit-run \
  --rendered-dir output \
  --subreddits all \
  --categories story,horror,ask \
  --start-date 2026-05-25 \
  --dry-run
```

Local sleep-resistant scheduler: instead of relying on Instagram's native
scheduler, queue the weekly posts locally and let macOS run the due-post checker
every few minutes. The checker wraps runs in `caffeinate`, so the Mac should not
sleep while a browser post is in progress:

```bash
python publish_cli.py instagram-local-schedule-weekly \
  --rendered-dir output \
  --publish-root output/publish/local-weekly \
  --subreddits all \
  --categories story,horror,ask \
  --start-date 2026-05-25 \
  --first-time "12:00" \
  --subreddit-gap-minutes 45 \
  --daily-times "aitah=18:00,nosleep=21:00,askreddit=15:00" \
  --parts-gap-minutes 20 \
  --cleanup-after-success

python publish_cli.py instagram-local-install-launch-agent
```

For stronger sleep resistance on macOS, print wake commands for the queued post
times and run the ones you want. These ask macOS to wake before each due post;
the LaunchAgent then handles the actual post when the machine is awake:

```bash
python publish_cli.py instagram-local-wake-commands --wake-lead-minutes 10
```

One-file weekly run: generate the week, queue the local scheduler, refresh the
LaunchAgent, and print optional macOS wake commands:

```bash
./run_weekly_instagram.sh
```

The default run covers every configured subreddit for 7 days. When run on a
Sunday, the first posting date defaults to Monday; on other days it defaults to
today. To choose the date and times yourself:

```bash
./run_weekly_instagram.sh \
  --start-date 2026-05-25 \
  --first-time "12:00" \
  --subreddit-gap-minutes 45 \
  --parts-gap-minutes 20 \
  --daily-times "aitah=18:00,nosleep=21:00,askreddit=15:00"
```

This renders into `output/weekly_render/<start-date>/`, queues posts in
`data/local_schedules/instagram_queue.json`, and deletes prepared Instagram part
videos/covers plus source render files only after each queued post succeeds.
Pass `--keep-source-renders` if you want to keep the generated originals.

Upload only one split Instagram part:

```bash
python publish_cli.py instagram-web-upload-parts \
  --video-path output/final_video_0.mp4 \
  --output-dir output/publish/post_0 \
  --part-number 1 \
  --cleanup-after-success
```

Post one prepared manifest part automatically through the browser:

```bash
python publish_cli.py post-manifest-part-web \
  --manifest-path output/publish/post_0/publish_manifest.json \
  --part-number 1 \
  --platform instagram \
  --cleanup-after-success
```

Notes:

- TikTok uses OAuth v2 and the Content Posting API. This helper stores tokens in `data/social/tiktok_tokens.json`.
- YouTube uses OAuth client secrets and stores its token in `data/social/youtube_token.json`.
- The publisher layer is separate from the render pipeline right now, so nothing auto-posts unless you explicitly call the publishing commands.
- Video splitting for publishing targets 60-second parts by default. If the final leftover part would be too short, the helper redistributes the duration across the whole set instead of leaving a tiny last clip.
- Instagram part videos start with the generated Reddit title-card cover intro, including the part badge, before the story/background footage.
- Instagram uses the generated full part caption, including a short hook, the title, part number, and hashtag set.
- Instagram uses the generated Reddit title-card cover image for each part when `cover_path` is present in the manifest and the cover editor is available.
- Instagram scheduling uses Instagram's own composer scheduler if it is visible. If the account or UI does not expose scheduling, the command fails with a debug screenshot instead of silently posting immediately.
- Local scheduling stores due posts in `data/local_schedules/instagram_queue.json`, checks them with a macOS LaunchAgent, and posts due items immediately through the Instagram web automation. It can wake a sleeping Mac only when paired with macOS `pmset` wake events.
- Local cleanup is opt-in with `--cleanup-after-success`. It runs only after Instagram confirms every selected part was shared or scheduled, deletes prepared local part videos and cover images, and keeps `publish_manifest.json` as the receipt.
- The weekly Instagram workflow expects at least one rendered video per selected subreddit for every day being planned. With the current configured `story,horror,ask` subreddits, a full week needs 77 rendered videos.
- The browser automation fallback stores persistent login sessions in `data/browser_profiles/`.
- The browser automation path can fill normal login forms automatically, but Google, TikTok, or Instagram may still interrupt with captcha, suspicious-login checks, or 2FA that must be completed manually once.

## Notes

- The app now fails clearly if required API keys are missing or there are no usable background videos.
- Short background clips are looped automatically when the narration is longer than the source footage.
- Final videos render as 9:16 portrait clips, with source footage center-cropped to `1080x1920`.
- Category behavior:
  - `story`: title + post body, normal Reddit-story pacing
  - `horror`: title + post body, horror background folder if present, more suspense-friendly ElevenLabs delivery defaults
  - `ask`: title + top comments only, no selftext, automatically trimmed to fit within the short-form target
- Reddit text gets deterministic vocab cleanup before OpenAI, using `reddit_vocabulary.py` for exact shorthand such as `AITAH`, `WIBTAH`, `TLDR`, and `bc`.
- OpenAI then lightly polishes for audibility without over-explaining common Reddit notation like `I, 45 M`, and can add conservative Eleven v3 cues in the same call.
- Ask-mode comment turns are spoken as `{username} responds:` with usernames cleaned to sound better out loud.
- When the cleaned script clearly contains different speakers, the pipeline can request segmented output and alternate voices across segments.
- Duplicate prevention is based on the Reddit post ID when available plus a SHA-256 hash of the first 20 normalized characters of the spoken post text.
- ElevenLabs generates narration and alignment data in the same request, then the app turns those timings into SRT captions locally.
- Subtitle timings are lightly normalized before rendering so adjacent captions do not visually stack.
- Subtitles and narration are rendered in one pass so the final video keeps both overlays and audio.
- `videofetcher.py` can still be used to download source footage, but the main pipeline only needs local `.mp4` files in the video directory.
- Background clips now start from a random valid point in the source footage instead of always using the beginning, while still guaranteeing enough remaining runtime for the narration.
