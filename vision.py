"""Find where the speaker is on screen so the vertical crop follows them."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

_CASCADE: cv2.CascadeClassifier | None = None


def _cascade() -> cv2.CascadeClassifier:
    global _CASCADE
    if _CASCADE is None:
        _CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    return _CASCADE


def detect_focus_x(video: Path, start: float, end: float, samples: int = 8) -> float:
    """Median horizontal position (0..1) of the largest face across sampled frames. Falls back to centre."""
    cap = cv2.VideoCapture(str(video))
    centres: list[float] = []
    try:
        for t in np.linspace(start, max(start, end - 0.1), samples):
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = _cascade().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
            if len(faces):
                x, _, w, _ = max(faces, key=lambda f: f[2] * f[3])
                centres.append((x + w / 2) / frame.shape[1])
    finally:
        cap.release()
    return float(np.median(centres)) if centres else 0.5
