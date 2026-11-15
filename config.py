"""Central configuration, read from environment variables (a .env file is loaded automatically)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DOWNLOAD_DIR = DATA_DIR / "downloads"
CLIP_DIR = DATA_DIR / "clips"
YOUTUBE_TOKEN_FILE = DATA_DIR / "youtube_token.json"
OAUTH_PENDING_FILE = DATA_DIR / "oauth_pending.json"

for _dir in (UPLOAD_DIR, DOWNLOAD_DIR, CLIP_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

APP_PASSWORD = os.getenv("APP_PASSWORD", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8501")
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "UTC")

# OAuth client file from Google Cloud. Hosts without a file system for secrets can pass
# the JSON contents in YOUTUBE_CLIENT_SECRETS_JSON instead (e.g. Hugging Face Space secrets).
YOUTUBE_CLIENT_SECRETS = Path(os.getenv("YOUTUBE_CLIENT_SECRETS", BASE_DIR / "client_secret.json"))
_inline_secrets = os.getenv("YOUTUBE_CLIENT_SECRETS_JSON")
if _inline_secrets:
    YOUTUBE_CLIENT_SECRETS = DATA_DIR / "client_secret.json"
    YOUTUBE_CLIENT_SECRETS.write_text(_inline_secrets, encoding="utf-8")

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "int8")
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN = os.getenv("FFPROBE_BIN", "ffprobe")
