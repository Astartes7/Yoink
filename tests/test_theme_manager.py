from pathlib import Path

from yoink.themes.manager import REQUIRED, ThemeManager


def test_bundled_themes_are_valid():
    manager = ThemeManager(Path("yoink/themes"))
    assert manager.available()
    for name in manager.available():
        assert REQUIRED <= manager.load(name).keys()


def test_luna_accent_text_is_black():
    theme = ThemeManager(Path("yoink/themes")).load("luna_night.json")
    assert theme["accent_text"] == "#000000"
