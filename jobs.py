"""In-process job queue. A single worker thread keeps CPU-heavy renders from competing."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from core.models import JobSettings, MediaSource

log = logging.getLogger(__name__)
MAX_LOG_LINES = 500


@dataclass
class Job:
    id: str
    source: MediaSource
    settings: JobSettings
    created: float = field(default_factory=time.time)
    status: str = "queued"  # queued | running | done | failed
    stage: str = "Waiting in queue"
    progress: float = 0.0
    logs: list[str] = field(default_factory=list)
    clip_count: int = 0
    error: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def start(self) -> None:
        with self._lock:
            self.status = "running"
            self.stage = "Starting"
        self.log("Job started")

    def log(self, message: str) -> None:
        with self._lock:
            self.logs.append(f"{datetime.now():%H:%M:%S}  {message}")
            del self.logs[:-MAX_LOG_LINES]

    def update(self, stage: str | None = None, progress: float | None = None) -> None:
        with self._lock:
            if stage is not None:
                self.stage = stage
            if progress is not None:
                self.progress = max(0.0, min(1.0, progress))

    def finish(self, clip_count: int) -> None:
        with self._lock:
            self.status = "done"
            self.stage = "Done"
            self.progress = 1.0
            self.clip_count = clip_count
        self.log(f"Finished: {clip_count} clip(s) ready in the Library tab")

    def fail(self, message: str) -> None:
        with self._lock:
            self.status = "failed"
            self.stage = "Failed"
            self.error = message
        self.log(f"Error: {message}")

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "stage": self.stage,
                "progress": self.progress,
                "logs": list(self.logs),
                "clip_count": self.clip_count,
                "error": self.error,
            }


class JobManager:
    def __init__(self, workers: int = 1) -> None:
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="clip-job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, source: MediaSource, settings: JobSettings) -> str:
        job = Job(id=uuid.uuid4().hex[:12], source=source, settings=settings)
        with self._lock:
            self._jobs[job.id] = job
        self._pool.submit(self._execute, job)
        return job.id

    def get(self, job_id: str | None) -> Job | None:
        if job_id is None:
            return None
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, limit: int = 20) -> list[Job]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)
        return jobs[:limit]

    @staticmethod
    def _execute(job: Job) -> None:
        from core.pipeline import run_pipeline  # imported lazily to avoid a circular import

        try:
            run_pipeline(job)
        except Exception as exc:  # last-resort guard so a worker never dies silently
            log.exception("Job %s crashed", job.id)
            job.fail(str(exc))


JOBS = JobManager()
