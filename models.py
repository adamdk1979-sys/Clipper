"""Shared immutable data types passed between pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Highlight:
    start: float
    end: float
    score: float
    words: list[Word]


@dataclass(frozen=True)
class VideoInfo:
    duration: float
    width: int
    height: int


@dataclass(frozen=True)
class JobSettings:
    min_duration: int = 30
    max_duration: int = 60
    num_clips: int = 5
    caption_style: str = "bold_pop"
    language: str | None = None
    model_size: str = "small"
    face_crop: bool = True


@dataclass(frozen=True)
class MediaSource:
    kind: str   # "url" or "file"
    value: str  # the URL or the saved file path
    label: str  # human-readable name shown in the UI
