import json
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_config_dir


@dataclass
class Settings:
    output_dir: str = str(Path.home() / "Downloads" / "Yoink")
    cookies_path: str = ""
    theme: str = "yoink_forest.json"
    preset: str = "TV Compatible"
    workers: int = 1
    recode_mp4: bool = False
    window_geometry: str = "1100x720"


def settings_path() -> Path:
    return Path(user_config_dir("Yoink")) / "settings.json"


def load_settings() -> Settings:
    path = settings_path()
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        return Settings(
            **{
                key: value
                for key, value in values.items()
                if key in Settings.__dataclass_fields__
            }
        )
    except (OSError, ValueError, TypeError):
        return Settings()


def save_settings(settings: Settings) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
