"""Heuristic highlight picker.

Scores candidate windows of the transcript for speech density, emphasis (questions and
exclamations), hook language in the opening seconds, and pacing (long silences are penalised).
Windows are chosen greedily so that clips never overlap.
"""
from __future__ import annotations

import re

from core.models import Highlight, JobSettings, Word

ENDINGS = (".", "?", "!")
HOOK_TERMS = (
    "secret", "never", "nobody", "truth", "mistake", "biggest", "wrong", "crazy", "insane",
    "shocking", "why", "how", "stop", "wait", "actually", "believe", "worst", "best",
    "real", "money", "you need", "here's the thing", "the problem",
)
_HOOK_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in HOOK_TERMS) + r")\b", re.IGNORECASE)
TARGET_WORDS_PER_SECOND = 2.8
MIN_GAP_BETWEEN_CLIPS = 1.5
MAX_CANDIDATE_STARTS = 4000


def _score(words: list[Word], text: str) -> float:
    duration = max(words[-1].end - words[0].start, 0.1)
    density = max(0.0, 1.0 - abs(len(words) / duration - TARGET_WORDS_PER_SECOND) / TARGET_WORDS_PER_SECOND)
    max_gap = max((b.start - a.end for a, b in zip(words, words[1:])), default=0.0)
    silence_penalty = 0.25 if max_gap > 1.2 else 0.0
    emphasis = min(text.count("?") + text.count("!"), 3) / 3
    hook_in_opening = 1.0 if _HOOK_RE.search(" ".join(w.text for w in words[:10])) else 0.0
    keywords = min(len(_HOOK_RE.findall(text)), 3) / 3
    return 0.35 * density + 0.20 * emphasis + 0.25 * hook_in_opening + 0.20 * keywords - silence_penalty


def find_highlights(words: list[Word], settings: JobSettings) -> list[Highlight]:
    n = len(words)
    if n == 0:
        return []
    low, high = settings.min_duration, settings.max_duration
    stride = max(1, n // MAX_CANDIDATE_STARTS)

    candidates: list[tuple[float, int, int]] = []
    for i in range(0, n, stride):
        t0 = words[i].start
        j = i
        while j < n and words[j].end - t0 <= high:
            j += 1
        for k in range(i, j):
            if words[k].end - t0 < low:
                continue
            # Only end windows on sentence boundaries, or at the longest allowed length.
            if not (words[k].text.endswith(ENDINGS) or k == j - 1):
                continue
            window = words[i : k + 1]
            text = " ".join(w.text for w in window)
            candidates.append((_score(window, text), i, k))

    candidates.sort(reverse=True)
    picked: list[tuple[float, float, float, int, int]] = []
    for score, i, k in candidates:
        if len(picked) >= settings.num_clips:
            break
        start, end = words[i].start, words[k].end
        if any(start < p[1] + MIN_GAP_BETWEEN_CLIPS and end > p[0] - MIN_GAP_BETWEEN_CLIPS for p in picked):
            continue
        picked.append((start, end, score, i, k))

    picked.sort(key=lambda p: p[0])
    return [
        Highlight(start=s, end=e, score=round(sc, 3), words=words[i : k + 1])
        for s, e, sc, i, k in picked
    ]
