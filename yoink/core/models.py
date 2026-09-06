from dataclasses import dataclass, field
from enum import Enum
from threading import Event, Lock
from typing import Optional


class JobStatus(str, Enum):
    QUEUED = "queued"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadJob:
    url: str
    output_dir: str
    preset: str = "TV Compatible"
    start: Optional[str] = None
    end: Optional[str] = None
    cookies_path: Optional[str] = None
    recode_mp4: bool = False
    id: str = field(default_factory=lambda: "job-" + __import__("uuid").uuid4().hex[:8])
    title: str = "Waiting for media information"
    duration: Optional[float] = None
    status: JobStatus = JobStatus.QUEUED
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    filename: str = ""
    error: str = ""
    compatible: Optional[bool] = None
    cancel_requested: Event = field(default_factory=Event, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def update(self, **values) -> None:
        with self._lock:
            for key, value in values.items():
                setattr(self, key, value)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                key: getattr(self, key)
                for key in (
                    "id",
                    "url",
                    "title",
                    "status",
                    "percent",
                    "speed",
                    "eta",
                    "filename",
                    "error",
                    "compatible",
                )
            }

    def cancel(self) -> None:
        self.cancel_requested.set()
