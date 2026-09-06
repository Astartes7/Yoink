import uuid
from dataclasses import dataclass, field
from enum import Enum
from threading import Event, Lock


class JobStatus(str, Enum):
    QUEUED = "queued"
    CHECKING = "checking"
    PREPARING = "preparing"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    MERGING = "merging"
    CONVERTING = "converting"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadJob:
    url: str
    output_dir: str
    codec: str = "Auto (Best)"
    start: str | None = None
    end: str | None = None
    cookies_path: str | None = None
    recode_mp4: bool = False
    kind: str = "video"
    quality: str = "Best Available"
    thumbnail: str = ""
    uploader: str = ""
    source: str = ""
    size: str = ""
    filename_template: str = "%(title)s [%(id)s].%(ext)s"
    embed_metadata: bool = True
    embed_thumbnail: bool = False
    subtitles: bool = False
    id: str = field(default_factory=lambda: "job-" + uuid.uuid4().hex[:8])
    title: str = "Waiting for media information"
    duration: float | None = None
    status: JobStatus = JobStatus.QUEUED
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    filename: str = ""
    error: str = ""
    compatible: bool | None = None
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
                    "kind",
                    "quality",
                    "thumbnail",
                    "uploader",
                    "source",
                    "size",
                )
            }

    def cancel(self) -> None:
        self.cancel_requested.set()
