"""Safe wrappers around the ffmpeg and ffprobe binaries."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from core import config
from core.models import VideoInfo


def run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip()[-800:]
        raise RuntimeError(f"{Path(cmd[0]).name} failed: {tail}")
    return proc.stdout


def probe(path: Path) -> VideoInfo:
    data = json.loads(run([
        config.FFPROBE_BIN, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]))
    stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if stream is None:
        raise RuntimeError("No video stream found in this file.")

    width, height = int(stream["width"]), int(stream["height"])
    rotation = abs(int(float(stream.get("tags", {}).get("rotate", 0) or 0)))
    for side_data in stream.get("side_data_list", []):
        if "rotation" in side_data:
            rotation = abs(int(side_data["rotation"]))
    if rotation % 180 == 90:  # phone footage shot in portrait
        width, height = height, width

    duration = float(data.get("format", {}).get("duration") or stream.get("duration") or 0)
    if duration <= 0:
        raise RuntimeError("Could not determine the video duration.")
    return VideoInfo(duration=duration, width=width, height=height)


def extract_audio(src: Path, dst: Path) -> Path:
    """Mono 16 kHz WAV, the format Whisper works best with."""
    run([
        config.FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst),
    ])
    return dst
