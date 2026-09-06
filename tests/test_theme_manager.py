from pathlib import Path

from yoink.themes.manager import REQUIRED, ThemeManager


def test_bundled_themes_are_valid():
    manager = ThemeManager(Path("yoink/themes"))
    assert manager.available()
    for name in manager.available():
        assert REQUIRED <= manager.load(name).keys()
