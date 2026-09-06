from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from typing import Callable

from .models import DownloadJob, JobStatus
from .presets import get_preset


def _timestamp(value: str | None) -> float | str | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return value


class DownloadEngine:
    def __init__(self, ffmpeg_location: str | None = None, workers: int = 1):
        self.ffmpeg_location = ffmpeg_location
        self.jobs: Queue[DownloadJob | None] = Queue()
        self._stop = Event()
        self._threads = [
            Thread(target=self._consume, daemon=True, name=f"yoink-worker-{i}")
            for i in range(max(1, workers))
        ]
        for thread in self._threads:
            thread.start()

    def submit(self, job: DownloadJob) -> None:
        self.jobs.put(job)

    def shutdown(self) -> None:
        self._stop.set()
        for _ in self._threads:
            self.jobs.put(None)

    def _consume(self) -> None:
        while not self._stop.is_set():
            try:
                job = self.jobs.get(timeout=0.2)
            except Empty:
                continue
            if job is None:
                return
            self._download(job)

    def _download(self, job: DownloadJob) -> None:
        try:
            import yt_dlp

            job.update(status=JobStatus.DOWNLOADING, error="")
            preset = get_preset(job.preset)
            opts = {
                "format": preset.format,
                "outtmpl": str(Path(job.output_dir) / "%(title)s [%(id)s].%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [self._hook(job)],
                "merge_output_format": "mp4" if preset.kind == "video" else None,
            }
            opts = {key: value for key, value in opts.items() if value is not None}
            if self.ffmpeg_location:
                opts["ffmpeg_location"] = self.ffmpeg_location
            if job.cookies_path:
                opts["cookiefile"] = job.cookies_path
            if job.start or job.end:
                opts["download_ranges"] = yt_dlp.utils.download_range_func(
                    None,
                    [(_timestamp(job.start) or 0, _timestamp(job.end) or float("inf"))],
                )
                opts["force_keyframes_at_cuts"] = True
            if job.recode_mp4 and preset.kind == "video":
                opts["postprocessors"] = [
                    {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
                ]
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(job.url, download=True)
                job.update(
                    title=info.get("title") or job.title,
                    status=JobStatus.COMPLETE,
                    percent=100.0,
                )
        except Exception as exc:
            if job.cancel_requested.is_set():
                job.update(status=JobStatus.CANCELLED, error="Cancelled")
            else:
                job.update(status=JobStatus.FAILED, error=str(exc))

    @staticmethod
    def _hook(job: DownloadJob) -> Callable[[dict], None]:
        def hook(data: dict) -> None:
            if job.cancel_requested.is_set():
                import yt_dlp

                raise yt_dlp.utils.DownloadCancelled()
            status = data.get("status")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                downloaded = data.get("downloaded_bytes", 0)
                percent = downloaded / total * 100 if total else 0
                job.update(
                    percent=percent,
                    speed=data.get("speed_str", ""),
                    eta=data.get("eta_str", ""),
                    filename=data.get("filename", ""),
                    status=JobStatus.DOWNLOADING,
                )
            elif status == "finished":
                job.update(
                    percent=100.0,
                    status=JobStatus.PROCESSING,
                    filename=data.get("filename", ""),
                )

        return hook
