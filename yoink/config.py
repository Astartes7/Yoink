import json
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_config_dir

from yoink.core.codecs import CODECS

VIDEO_QUALITIES = [
    "Best Available",
    "2160p",
    "1440p",
    "1080p",
    "720p",
    "480p",
    "360p",
]
AUDIO_QUALITIES = ["Best Available", "320 kbps", "256 kbps", "192 kbps", "128 kbps"]


@dataclass
class Settings:
    output_dir: str = str(Path.home() / "Downloads" / "Yoink")
    cookies_path: str = ""
    theme: str = "luna_night.json"
    codec: str = "Auto (Best)"
    workers: int = 1
    recode_mp4: bool = False
    window_geometry: str = "720x480"
    background_mode: str = "off"
    background_path: str = ""
    background_dim: int = 78
    default_format: str = "Video"
    default_quality: str = "Best Available"
    embed_metadata: bool = True
    embed_thumbnail: bool = False
    subtitles: bool = False
    filename_template: str = "%(title)s [%(id)s].%(ext)s"


def settings_path() -> Path:
    return Path(user_config_dir("Yoink")) / "settings.json"


def load_settings() -> Settings:
    path = settings_path()
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        if "codec" not in values and values.get("preset") == "TV Compatible":
            values["codec"] = "H.264 (TV Compatible)"
        if values.get("default_format") == "MP4":
            values["default_format"] = "Video"
        elif values.get("default_format") == "MP3":
            values["default_format"] = "Audio"
        settings = Settings(
            **{
                key: value
                for key, value in values.items()
                if key in Settings.__dataclass_fields__
            }
        )
        if settings.codec not in CODECS:
            settings.codec = "Auto (Best)"
        if settings.default_format not in {"Video", "Audio"}:
            settings.default_format = "Video"
        qualities = (
            VIDEO_QUALITIES if settings.default_format == "Video" else AUDIO_QUALITIES
        )
        if settings.default_quality not in qualities:
            settings.default_quality = "Best Available"
        try:
            settings.workers = min(4, max(1, int(settings.workers)))
        except (TypeError, ValueError):
            settings.workers = 1
        try:
            settings.background_dim = min(100, max(0, int(settings.background_dim)))
        except (TypeError, ValueError):
            settings.background_dim = 78
        return settings
    except (OSError, ValueError, TypeError):
        return Settings()


def save_settings(settings: Settings) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
