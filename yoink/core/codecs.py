from dataclasses import dataclass


@dataclass(frozen=True)
class Codec:
    name: str
    video_prefix: str | None
    audio_selector: str
    container: str


CODECS = {
    "Auto (Best)": Codec("Auto (Best)", None, "bestaudio/best", "mp4"),
    "H.264 (TV Compatible)": Codec(
        "H.264 (TV Compatible)", "avc1", "bestaudio[ext=m4a]", "mp4"
    ),
    "H.265 (HEVC)": Codec("H.265 (HEVC)", "hvc1", "bestaudio[ext=m4a]", "mp4"),
    "VP9 (YouTube)": Codec("VP9 (YouTube)", "vp9", "bestaudio[ext=webm]", "mkv"),
    "AV1 (Newest)": Codec("AV1 (Newest)", "av01", "bestaudio[ext=webm]", "mkv"),
}


def get_codec(name: str) -> Codec:
    return CODECS.get(name, CODECS["Auto (Best)"])
