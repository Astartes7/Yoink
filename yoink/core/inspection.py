from typing import Any

from .precheck import inspect_url


def media_entries(info: dict[str, Any]) -> list[dict[str, Any]]:
    entries = info.get("entries")
    if entries:
        return [item for item in entries if item]
    return [info]


def describe(info: dict[str, Any]) -> dict[str, Any]:
    duration = info.get("duration")
    return {
        "url": info.get("webpage_url")
        or info.get("original_url")
        or info.get("url", ""),
        "title": info.get("title") or "Untitled media",
        "uploader": info.get("uploader") or info.get("channel") or "Unknown uploader",
        "duration": _duration(duration),
        "duration_seconds": float(duration) if duration else None,
        "source": info.get("extractor_key")
        or info.get("extractor")
        or "Unknown source",
        "thumbnail": info.get("thumbnail") or "",
        "id": info.get("id") or "",
        "info": info,
    }


def _duration(value: float | None) -> str:
    if not value:
        return "Duration unavailable"
    seconds = int(value)
    return (
        f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"
        if seconds >= 3600
        else f"{seconds // 60}:{seconds % 60:02}"
    )


def inspect_urls(urls: list[str], cookies_path: str = "") -> list[dict[str, Any]]:
    results = []
    for url in urls:
        info = inspect_url(url, cookies_path or None)
        results.extend(describe(entry) for entry in media_entries(info))
    return results
