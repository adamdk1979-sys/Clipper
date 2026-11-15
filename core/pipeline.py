"""End-to-end processing: download -> audio -> transcript -> highlights -> rendered clips."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from core import config
from core.captions import build_ass
from core.downloader import download_video
from core.ffmpeg_utils import extract_audio, probe
from core.highlights import find_highlights
from core.renderer import render_clip
from core.transcriber import transcribe
from core.vision import detect_focus_x

if TYPE_CHECKING:
    from core.jobs import Job

log = logging.getLogger(__name__)


def make_title(words) -> str:
    text = " ".join(w.text for w in words[:10]).strip(" .,!?;:")
    if len(text) > 70:
        text = text[:70].rsplit(" ", 1)[0]
    return text[:1].upper() + text[1:] if text else "Highlight"


def run_pipeline(job: "Job") -> None:
    job.start()
    source, settings = job.source, job.settings
    work_dir = config.DOWNLOAD_DIR / job.id
    out_dir = config.CLIP_DIR / job.id

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        job.update("Downloading source", 0.02)
        if source.kind == "url":
            job.log(f"Downloading {source.value}")
            video = download_video(
                source.value, work_dir,
                on_progress=lambda f: job.update(progress=0.02 + 0.13 * f),
            )
        else:
            video = Path(source.value)

        info = probe(video)
        job.log(f"Source is {info.width}x{info.height}, {info.duration / 60:.1f} min")

        job.update("Extracting audio", 0.16)
        audio = extract_audio(video, work_dir / "audio.wav")

        job.update("Transcribing speech", 0.18)
        words = transcribe(
            audio,
            model_size=settings.model_size,
            language=settings.language,
            on_progress=lambda f: job.update(progress=0.18 + 0.37 * f),
        )
        job.log(f"Transcribed {len(words)} words")
        if not words:
            raise RuntimeError("No speech was detected in this video.")

        job.update("Finding highlights", 0.57)
        highlights = find_highlights(words, settings)
        if not highlights:
            raise RuntimeError("No highlight windows found. Try a longer video or a different clip length.")
        job.log(f"Selected {len(highlights)} highlight(s)")

        clips: list[dict] = []
        total = len(highlights)
        for index, highlight in enumerate(highlights, start=1):
            job.update(f"Rendering clip {index}/{total}", 0.60 + 0.38 * (index - 1) / total)
            clip_dir = out_dir / f"clip_{index:02d}"
            clip_dir.mkdir(exist_ok=True)

            focus = detect_focus_x(video, highlight.start, highlight.end) if settings.face_crop else 0.5
            ass = build_ass(highlight.words, highlight.start, highlight.end, settings.caption_style)
            (clip_dir / "captions.ass").write_text(ass, encoding="utf-8")
            rendered = render_clip(video, highlight.start, highlight.end, focus, clip_dir)

            title = make_title(highlight.words)
            clips.append({
                "index": index,
                "path": str(rendered),
                "title": title,
                "description": f"{title}\n\n#Shorts",
                "start": round(highlight.start, 2),
                "end": round(highlight.end, 2),
                "score": highlight.score,
                "youtube_id": None,
            })
            job.log(f"Clip {index} ready ({highlight.end - highlight.start:.0f}s): {title}")

        manifest = {
            "created": datetime.now().isoformat(timespec="seconds"),
            "source_label": source.label,
            "clips": clips,
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        job.finish(len(clips))
    except Exception as exc:
        log.exception("Pipeline failed for job %s", job.id)
        job.fail(str(exc))
    finally:
        # The full-length download is large and no longer needed once clips are rendered.
        shutil.rmtree(work_dir, ignore_errors=True)
