from typing import Any

from .presets import get_preset


def inspect_url(url: str, cookies_path: str | None = None) -> dict[str, Any]:
    """Extract metadata without downloading. Imports yt-dlp lazily for testability."""
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    if cookies_path:
        opts["cookiefile"] = cookies_path
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info


def compatibility(info: dict[str, Any], preset_name: str) -> bool | None:
    preset = get_preset(preset_name)
    if preset.kind != "video":
        return True
    formats = info.get("formats") or []
    has_avc = any((item.get("vcodec") or "").startswith("avc1") for item in formats)
    has_m4a = any(item.get("acodec") and item.get("ext") == "m4a" for item in formats)
    return has_avc and has_m4a if formats else None
