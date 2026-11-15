"""Render a 9:16 (1080x1920) MP4 with burned-in captions using FFmpeg."""
from __future__ import annotations

from pathlib import Path

from core import config
from core.ffmpeg_utils import run

TARGET_RATIO = 9 / 16
OUT_W, OUT_H = 1080, 1920


def _even(value: int) -> int:
    return value - (value % 2)


def crop_box(width: int, height: int, focus_x: float) -> tuple[int, int, int, int]:
    """Return (crop_w, crop_h, x, y) for a 9:16 window.

    For landscape sources the window slides horizontally, centred on focus_x (0..1).
    For portrait sources the full width is kept and the window is centred vertically.
    """
    if width / height > TARGET_RATIO:
        ch = _even(height)
        cw = _even(round(height * TARGET_RATIO))
        x = min(max(round(focus_x * width - cw / 2), 0), width - cw)
        return cw, ch, x, 0
    cw = _even(width)
    ch = _even(round(width / TARGET_RATIO))
    y = min(max(round((height - ch) / 2), 0), height - ch)
    return cw, ch, 0, y


def render_clip(source: Path, start: float, end: float, focus_x: float, clip_dir: Path) -> Path:
    """Expects captions.ass to already exist in clip_dir."""
    from core.ffmpeg_utils import probe

    info = probe(source)
    cw, ch, x, y = crop_box(info.width, info.height, focus_x)
    video_filter = (
        f"crop={cw}:{ch}:{x}:{y},"
        f"scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1,"
        "subtitles=filename=captions.ass"
    )
    output = clip_dir / "clip.mp4"
    run(
        [
            config.FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{end - start:.3f}",
            "-vf", video_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            str(output),
        ],
        cwd=clip_dir,  # lets the subtitles filter use a plain relative filename
    )
    return output
