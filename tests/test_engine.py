from yoink.core.engine import DownloadEngine, _final_filepath, _format_selector
from yoink.core.models import DownloadJob


def test_format_selector_applies_video_height():
    job = DownloadJob("https://example.com", "out", quality="1080p")
    assert "height<=1080" in _format_selector(job)


def test_format_selector_applies_selected_codec():
    job = DownloadJob(
        "https://example.com", "out", codec="VP9 (YouTube)", quality="1080p"
    )
    selector = _format_selector(job)
    assert "vcodec^=vp9" in selector
    assert "bestaudio[ext=webm]" in selector


def test_auto_selector_keeps_best_available_behavior():
    job = DownloadJob("https://example.com", "out")
    assert _format_selector(job) == "bestvideo*+bestaudio/best"


def test_format_selector_uses_source_audio():
    job = DownloadJob("https://example.com", "out", kind="audio", quality="192 kbps")
    assert _format_selector(job) == "bestaudio/best"


def test_download_job_uses_canonical_media_kinds():
    assert DownloadJob("https://example.com", "out", kind="video").kind == "video"
    assert DownloadJob("https://example.com", "out", kind="audio").kind == "audio"


def test_download_job_preserves_filename_template():
    job = DownloadJob(
        "https://example.com", "out", filename_template="%(uploader)s/%(title)s.%(ext)s"
    )
    assert job.filename_template == "%(uploader)s/%(title)s.%(ext)s"


def test_postprocessors_extract_audio_with_quality():
    job = DownloadJob("https://example.com", "out", kind="audio", quality="192 kbps")
    assert DownloadEngine._postprocessors(job) == [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        },
        {"key": "FFmpegMetadata"},
    ]


def test_postprocessors_combine_video_options_in_order():
    job = DownloadJob(
        "https://example.com",
        "out",
        recode_mp4=True,
        embed_metadata=True,
        embed_thumbnail=True,
        subtitles=True,
    )
    keys = [processor["key"] for processor in DownloadEngine._postprocessors(job)]
    assert keys == [
        "FFmpegVideoConvertor",
        "FFmpegEmbedSubtitle",
        "FFmpegMetadata",
        "EmbedThumbnail",
    ]


def test_postprocessors_empty_for_plain_video_without_metadata():
    job = DownloadJob("https://example.com", "out", embed_metadata=False)
    assert DownloadEngine._postprocessors(job) == []


class _FakeYdl:
    def __init__(self, prepared):
        self._prepared = prepared

    def prepare_filename(self, _info):
        return str(self._prepared)


def test_final_filepath_finds_merged_file_by_stem(tmp_path):
    # merged download: requested fragment is gone, container changed
    final = tmp_path / "Clip [abc123].mp4"
    final.write_bytes(b"x" * 16)
    ydl = _FakeYdl(tmp_path / "Clip [abc123].mkv")
    assert _final_filepath(ydl, {}, "video") == str(final)


def test_final_filepath_matches_stale_format_fragment_name(tmp_path):
    # requested path is a deleted format fragment: name.f137.mp4
    final = tmp_path / "Clip [abc123].mp4"
    final.write_bytes(b"x" * 16)
    fragment = str(tmp_path / "Clip [abc123].f137.mp4")
    info = {"requested_downloads": [{"filepath": fragment}]}
    ydl = _FakeYdl(fragment)
    assert _final_filepath(ydl, info, "video") == str(final)


def test_final_filepath_prefers_mp3_for_audio(tmp_path):
    (tmp_path / "Song [xyz].mp3").write_bytes(b"x")
    ydl = _FakeYdl(tmp_path / "Song [xyz].webm")
    assert _final_filepath(ydl, {}, "audio").endswith("Song [xyz].mp3")


def test_final_filepath_uses_existing_requested_download(tmp_path):
    target = tmp_path / "actual.mp4"
    target.write_bytes(b"x")
    info = {"requested_downloads": [{"filepath": str(target)}]}
    ydl = _FakeYdl(tmp_path / "prepared.mp4")
    assert _final_filepath(ydl, info, "video") == str(target)


def test_final_filepath_ignores_thumbnails_when_matching(tmp_path):
    (tmp_path / "Video [id].webp").write_bytes(b"x" * 4)
    final = tmp_path / "Video [id].mkv"
    final.write_bytes(b"x" * 8)
    ydl = _FakeYdl(tmp_path / "Video [id].webm")
    assert _final_filepath(ydl, {}, "video") == str(final)


def test_final_filepath_returns_fallback_when_nothing_exists(tmp_path):
    ydl = _FakeYdl(tmp_path / "missing.mp4")
    assert _final_filepath(ydl, {}, "video").endswith("missing.mp4")
