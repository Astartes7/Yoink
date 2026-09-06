from yoink.core.codecs import CODECS, get_codec


def test_all_codec_options_are_available():
    assert list(CODECS) == [
        "Auto (Best)",
        "H.264 (TV Compatible)",
        "H.265 (HEVC)",
        "VP9 (YouTube)",
        "AV1 (Newest)",
    ]


def test_codec_containers_match_playback_strategy():
    assert get_codec("H.264 (TV Compatible)").container == "mp4"
    assert get_codec("H.265 (HEVC)").container == "mp4"
    assert get_codec("VP9 (YouTube)").container == "mkv"
    assert get_codec("AV1 (Newest)").container == "mkv"


def test_unknown_codec_falls_back_to_auto():
    assert get_codec("missing").name == "Auto (Best)"
