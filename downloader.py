"""Download a video with yt-dlp, preferring 1080p MP4. Only use this on content you own or have rights to."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yt_dlp

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov"}


def download_video(url: str, work_dir: Path, on_progress: Callable[[float], None]) -> Path:
    def hook(status: dict) -> None:
        state = status.get("status")
        if state == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            if total:
                on_progress(min(status.get("downloaded_bytes", 0) / total, 1.0))
        elif state == "finished":
            on_progress(1.0)

    options = {
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(work_dir / "source.%(ext)s"),
        "noplaylist": True,
        "restrictfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    target = work_dir / "source.mp4"
    if target.exists():
        return target
    candidates = [p for p in work_dir.glob("source.*") if p.suffix.lower() in VIDEO_EXTS]
    if not candidates:
        raise RuntimeError("Download finished but no video file was produced.")
    return max(candidates, key=lambda p: p.stat().st_size)
