"""Speech-to-text with faster-whisper, returning word-level timestamps."""
from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from faster_whisper import WhisperModel

from core import config
from core.models import Word


@lru_cache(maxsize=2)
def _model(size: str) -> WhisperModel:
    return WhisperModel(size, device="cpu", compute_type=config.WHISPER_COMPUTE)


def transcribe(
    audio_path: Path,
    *,
    model_size: str,
    language: str | None,
    on_progress: Callable[[float], None],
) -> list[Word]:
    model = _model(model_size)
    segments, info = model.transcribe(
        str(audio_path),
        language=language,  # None = auto-detect
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
    )
    duration = max(info.duration, 1.0)
    words: list[Word] = []
    for segment in segments:  # a generator: decoding happens as we iterate
        on_progress(min(segment.end / duration, 1.0))
        for item in segment.words or []:
            text = item.word.strip()
            if text:
                words.append(Word(float(item.start), float(item.end), text))
    on_progress(1.0)
    return words
