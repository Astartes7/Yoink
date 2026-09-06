import json
from pathlib import Path


REQUIRED = {
    "bg",
    "surface",
    "surface_alt",
    "accent",
    "accent_hover",
    "text",
    "text_muted",
    "success",
    "warning",
    "danger",
    "border",
    "progress_fill",
    "progress_track",
}


class ThemeManager:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or Path(__file__).parent

    def available(self) -> list[str]:
        return sorted(path.name for path in self.directory.glob("*.json"))

    def load(self, name: str) -> dict:
        path = Path(name)
        if not path.is_absolute():
            path = self.directory / name
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = REQUIRED - data.keys()
        if missing:
            raise ValueError(f"Theme is missing: {', '.join(sorted(missing))}")
        return data
