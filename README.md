# Clip Studio

A self-hosted tool that turns your own long recordings into captioned 9:16 vertical shorts, then publishes or schedules them to YouTube.

**Pipeline:** yt-dlp download (or upload) → FFmpeg audio extraction → faster-whisper transcription with word timestamps → heuristic highlight scoring → face-aware 9:16 crop → word-highlighted captions burned in with FFmpeg → optional YouTube upload with `publishAt` scheduling.

Only process videos you own or have rights to. Downloading others' content may breach YouTube's terms and copyright law.

## Project layout

```
clip_studio/
├── app.py                  Streamlit UI (Input, Settings, Processing, Library)
├── core/
│   ├── config.py           Environment-driven settings
│   ├── models.py           Shared dataclasses
│   ├── jobs.py             Background job queue with logs and progress
│   ├── pipeline.py         End-to-end orchestration
│   ├── downloader.py       yt-dlp wrapper
│   ├── ffmpeg_utils.py     ffprobe / ffmpeg helpers
│   ├── transcriber.py      faster-whisper wrapper
│   ├── highlights.py       Highlight scoring and selection
│   ├── captions.py         ASS caption builder (word highlighting, styles)
│   ├── renderer.py         9:16 crop and final encode
│   ├── vision.py           OpenCV face detection for crop focus
│   ├── library.py          Manifest reader/writer
│   └── publisher.py        YouTube OAuth and resumable upload
├── tests/test_core.py
├── Dockerfile
├── .streamlit/config.toml
└── .env.example
```

## 1. Run locally

Requirements: Python 3.11+ and FFmpeg (`brew install ffmpeg`, `sudo apt install ffmpeg`, or the Windows build from ffmpeg.org).

```bash
cd clip_studio
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # then edit APP_PASSWORD
pytest -q                                           # optional sanity check
streamlit run app.py
```

Open http://localhost:8501. Leave `APP_PASSWORD` empty for purely local use.

## 2. Google Cloud setup (for auto-publishing)

1. Go to console.cloud.google.com, create a project, and enable **YouTube Data API v3**.
2. **Google Auth Platform → Audience:** choose *External*, add your own Google account as a **test user**.
3. **Clients → Create client → Web application.** Under *Authorized redirect URIs* add your app URL exactly as it appears in `APP_BASE_URL`, with no trailing slash, for example `https://your-host.example`.
4. Download the JSON and save it as `client_secret.json` in the project root (or paste its contents into `YOUTUBE_CLIENT_SECRETS_JSON`).
5. In the app, open **Library → Connect YouTube** and approve access once.

Quota: each upload costs about 1,600 units against a default 10,000-unit daily budget, so expect around six uploads per day.

## 3. Host it free and use it from your phone

### Option A (recommended): your own PC over Tailscale
Processing is heavy, so running on a machine you already own is fastest and free. Nothing is exposed to the public internet.

1. Install Tailscale on your PC and on your phone, and sign in to the same account.
2. Run the app on the PC: `streamlit run app.py --server.address 0.0.0.0`
3. Expose it over HTTPS on your tailnet: `tailscale serve --bg 8501`. This gives you a URL like `https://your-pc.your-tailnet.ts.net`.
4. Set `APP_BASE_URL` to that URL, add it as the redirect URI in Google Cloud, and set `APP_PASSWORD`.
5. On your phone, open the URL (Tailscale must be connected). In Safari or Chrome choose **Share → Add to Home Screen** for an app-like icon.

### Option B: Hugging Face Spaces (public URL, free CPU)
1. Create a Space, choose SDK **Docker**, and upload this folder. Put this front matter at the top of the Space's README:
   ```
   ---
   title: Clip Studio
   sdk: docker
   app_port: 7860
   ---
   ```
2. In **Settings → Variables and secrets**, add secrets `APP_PASSWORD` and `YOUTUBE_CLIENT_SECRETS_JSON` (the whole JSON), plus variables `APP_BASE_URL=https://<user>-<space>.hf.space` and `APP_TIMEZONE`.
3. Add that same `APP_BASE_URL` as the redirect URI in Google Cloud.

Caveats for the free tier: the Space sleeps after inactivity, the disk is wiped on restart (clips and the YouTube token are lost, so download or publish promptly and reconnect if needed), and the CPU is slower, so use the `base` or `tiny` model for long videos.

## Operational notes

- **Unverified API projects** are forced to private uploads until Google audits the project. Scheduling still works, and the video goes public at the scheduled time.
- **Uploaded source files** are kept in `data/uploads`. Delete them periodically to save disk space.
- **Highlight selection** is a transparent heuristic (speech density, questions and exclamations, hook words, pacing). It can be replaced with an LLM scorer in `core/highlights.py` without touching the rest of the pipeline.
- **MoviePy was replaced with direct FFmpeg.** The FFmpeg `subtitles` filter is faster, has no ImageMagick dependency, and renders captions more reliably.
