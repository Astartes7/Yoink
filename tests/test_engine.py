from yoink.core.engine import DownloadEngine, _format_selector
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
