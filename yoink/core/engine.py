from collections.abc import Callable
from glob import escape as _glob_escape
from pathlib import Path
import re
from queue import Empty, Queue
from threading import Event, Thread

from .codecs import get_codec
from .models import DownloadJob, JobStatus


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

            job.update(status=JobStatus.PREPARING, error="")
            codec = get_codec(job.codec)
            format_selector = _format_selector(job)
            opts = {
                "format": format_selector,
                "outtmpl": str(Path(job.output_dir) / job.filename_template),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [self._hook(job)],
                "merge_output_format": codec.container if job.kind == "video" else None,
            }
            opts = {key: value for key, value in opts.items() if value is not None}
            postprocessors = self._postprocessors(job)
            if postprocessors:
                opts["postprocessors"] = postprocessors
            if job.embed_thumbnail:
                opts["writethumbnail"] = True
            if job.subtitles and job.kind == "video":
                opts["writesubtitles"] = True
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
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(job.url, download=True)
                job.update(
                    title=info.get("title") or job.title,
                    status=JobStatus.COMPLETE,
                    percent=100.0,
                    filename=_final_filepath(ydl, info, job.kind),
                )
        except Exception as exc:  # noqa: BLE001 - worker must never die silently
            if job.cancel_requested.is_set():
                job.update(status=JobStatus.CANCELLED, error="Cancelled")
            else:
                job.update(status=JobStatus.FAILED, error=str(exc))

    @staticmethod
    def _postprocessors(job: DownloadJob) -> list[dict]:
        processors: list[dict] = []
        if job.kind == "audio":
            processor = {"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}
            if job.quality != "Best Available":
                processor["preferredquality"] = job.quality.split()[0]
            processors.append(processor)
        if job.recode_mp4 and job.kind == "video":
            processors.append({"key": "FFmpegVideoConvertor", "preferedformat": "mp4"})
        if job.subtitles and job.kind == "video":
            processors.append({"key": "FFmpegEmbedSubtitle"})
        if job.embed_metadata:
            processors.append({"key": "FFmpegMetadata"})
        if job.embed_thumbnail:
            processors.append({"key": "EmbedThumbnail"})
        return processors

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


_FINAL_IGNORE_SUFFIXES = {
    ".part",
    ".ytdl",
    ".tmp",
    ".crdownload",
    ".webp",
    ".jpg",
    ".jpeg",
    ".png",
    ".url",
    ".json",
}
_FINAL_MEDIA_SUFFIXES = {
    ".mp4",
    ".mkv",
    ".webm",
    ".mov",
    ".avi",
    ".flv",
    ".ts",
    ".mp3",
    ".m4a",
    ".opus",
    ".ogg",
    ".wav",
    ".aac",
    ".flac",
}


def _core_stem(path: Path) -> str:
    """Stem with yt-dlp format-fragment suffixes removed (name.f137)."""
    return re.sub(r"\.f\d+$", "", path.stem)


def _final_filepath(ydl, info, kind: str) -> str:
    """Best-effort path to the file that exists after post-processing.

    Merging/recoding deletes the requested fragment files, and audio
    extraction changes the extension, so every candidate is checked for
    existence and matched against sibling media files by name stem.
    """
    try:
        candidates = []
        requested = info.get("requested_downloads") or []
        if requested:
            candidates.append(requested[0].get("filepath", ""))
        try:
            prepared = ydl.prepare_filename(info)
        except Exception:
            prepared = ""
        if prepared:
            candidates.append(prepared)
        fallback = candidates[0] if candidates else ""
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if kind == "audio":
                mp3 = path.with_suffix(".mp3")
                if mp3.exists():
                    return str(mp3)
            if path.exists() and path.suffix.lower() not in _FINAL_IGNORE_SUFFIXES:
                return str(path)
            if path.parent.is_dir():
                matches = [
                    p
                    for p in path.parent.glob(_glob_escape(_core_stem(path)) + ".*")
                    if p.suffix.lower() in _FINAL_MEDIA_SUFFIXES
                ]
                if matches:
                    matches.sort(
                        key=lambda p: (
                            p.suffix.lower() not in {".mp4", ".mp3"},
                            -p.stat().st_size,
                        )
                    )
                    return str(matches[0])
        return fallback
    except Exception:
        return ""


def _format_selector(job: DownloadJob) -> str:
    if job.kind == "audio":
        return "bestaudio/best"

    codec = get_codec(job.codec)
    if job.quality == "Best Available" and codec.video_prefix is None:
        return "bestvideo*+bestaudio/best"
    video_filter = ""
    if codec.video_prefix:
        video_filter = f"[vcodec^={codec.video_prefix}]"
    height_filter = ""
    if job.quality != "Best Available":
        height = job.quality.removesuffix("p")
        height_filter = f"[height<={height}]"
    video = f"bestvideo{height_filter}{video_filter}"
    audio = codec.audio_selector
    fallback = f"best{height_filter}{video_filter}"
    return f"{video}+{audio}/{fallback}/best{height_filter}"
