from typing import Any


def inspect_url(url: str, cookies_path: str | None = None) -> dict[str, Any]:
    """Extract metadata without downloading. Imports yt-dlp lazily for testability."""
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    if cookies_path:
        opts["cookiefile"] = cookies_path
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info
