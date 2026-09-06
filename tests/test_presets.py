from yoink.core.presets import PRESETS, TV_COMPATIBLE, get_preset


def test_tv_preset_matches_notebook():
    assert get_preset("TV Compatible").format == TV_COMPATIBLE
    assert "avc1" in PRESETS["TV Compatible"].format
    assert "m4a" in PRESETS["TV Compatible"].format


def test_unknown_preset_is_safe():
    assert get_preset("missing").name == "TV Compatible"
