from dataclasses import dataclass


TV_COMPATIBLE = (
    "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/best[vcodec^=avc1]/best"
)


@dataclass(frozen=True)
class Preset:
    name: str
    format: str
    kind: str = "video"
    max_height: int | None = None


PRESETS = {
    "TV Compatible": Preset("TV Compatible", TV_COMPATIBLE, max_height=1080),
    "Best Available": Preset("Best Available", "bestvideo*+bestaudio/best"),
    "720p": Preset(
        "720p", "bestvideo[height<=720]+bestaudio/best[height<=720]", max_height=720
    ),
    "480p": Preset(
        "480p", "bestvideo[height<=480]+bestaudio/best[height<=480]", max_height=480
    ),
    "Audio (m4a)": Preset("Audio (m4a)", "bestaudio[ext=m4a]/bestaudio", kind="audio"),
}


def get_preset(name: str) -> Preset:
    return PRESETS.get(name, PRESETS["TV Compatible"])
