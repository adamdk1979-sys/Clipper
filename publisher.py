"""YouTube Data API v3: web OAuth flow, token storage, resumable uploads with scheduled publish times."""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from core import config

YOUTUBE_CATEGORY_PEOPLE_AND_BLOGS = "22"


class YouTubeAuthError(RuntimeError):
    """Raised when OAuth or uploading cannot proceed."""


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _flow() -> Flow:
    if not config.YOUTUBE_CLIENT_SECRETS.exists():
        raise YouTubeAuthError("client_secret.json was not found. See the README setup steps.")
    if config.APP_BASE_URL.startswith("http://localhost") or "127.0.0.1" in config.APP_BASE_URL:
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")  # allow http only for local testing
    return Flow.from_client_secrets_file(
        str(config.YOUTUBE_CLIENT_SECRETS),
        scopes=config.YOUTUBE_SCOPES,
        redirect_uri=config.APP_BASE_URL,
    )


def start_authorization() -> str:
    """Return the Google sign-in URL. The PKCE verifier is kept on disk, keyed by state."""
    state = secrets.token_urlsafe(24)
    flow = _flow()
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    pending = _read_json(config.OAUTH_PENDING_FILE, {})
    pending[state] = flow.code_verifier
    _write_json(config.OAUTH_PENDING_FILE, pending)
    return url


def finish_authorization(code: str, state: str) -> None:
    pending = _read_json(config.OAUTH_PENDING_FILE, {})
    if state not in pending:
        raise YouTubeAuthError("This sign-in link has expired. Please connect again.")
    verifier = pending.pop(state)
    _write_json(config.OAUTH_PENDING_FILE, pending)

    flow = _flow()
    flow.code_verifier = verifier
    flow.fetch_token(code=code)
    _save_credentials(flow.credentials)


def _save_credentials(creds: Credentials) -> None:
    config.YOUTUBE_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")


def load_credentials() -> Credentials | None:
    if not config.YOUTUBE_TOKEN_FILE.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(config.YOUTUBE_TOKEN_FILE), config.YOUTUBE_SCOPES)
    if not creds.valid and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
        except Exception:
            return None
    return creds if creds.valid else None


def is_connected() -> bool:
    return load_credentials() is not None


def disconnect() -> None:
    config.YOUTUBE_TOKEN_FILE.unlink(missing_ok=True)


def upload_video(
    path: Path,
    *,
    title: str,
    description: str,
    privacy: str = "private",
    publish_at: datetime | None = None,
    tags: list[str] | None = None,
) -> str:
    """Upload and return the YouTube video ID.

    When publish_at is given the video is uploaded as private and YouTube flips it public at that time.
    """
    creds = load_credentials()
    if creds is None:
        raise YouTubeAuthError("Not connected to YouTube.")

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    status: dict[str, Any] = {
        "selfDeclaredMadeForKids": False,
        "privacyStatus": "private" if publish_at else privacy,
    }
    if publish_at is not None:
        status["publishAt"] = publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags or ["Shorts"],
            "categoryId": YOUTUBE_CATEGORY_PEOPLE_AND_BLOGS,
        },
        "status": status,
    }
    media = MediaFileUpload(str(path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = request.next_chunk()
    return response["id"]
