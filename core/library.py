"""Read finished-job manifests from disk so the library survives restarts."""
from __future__ import annotations

import json

from core import config


def load_library() -> list[dict]:
    items: list[dict] = []
    for path in config.CLIP_DIR.glob("*/manifest.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data["job_id"] = path.parent.name
        items.append(data)
    return sorted(items, key=lambda d: d.get("created", ""), reverse=True)


def mark_published(job_id: str, index: int, youtube_id: str) -> None:
    path = config.CLIP_DIR / job_id / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for clip in data["clips"]:
        if clip["index"] == index:
            clip["youtube_id"] = youtube_id
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
