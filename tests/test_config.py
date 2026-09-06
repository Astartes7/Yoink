import json

from yoink import config
from yoink.config import Settings


def test_default_geometry_is_compact():
    assert Settings().window_geometry == "720x480"


def _write_settings(tmp_path, monkeypatch, values):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    monkeypatch.setattr(config, "settings_path", lambda: path)


def test_load_settings_resets_quality_from_other_format(tmp_path, monkeypatch):
    _write_settings(
        tmp_path,
        monkeypatch,
        {"default_format": "Video", "default_quality": "320 kbps"},
    )
    assert config.load_settings().default_quality == "Best Available"


def test_load_settings_keeps_valid_quality(tmp_path, monkeypatch):
    _write_settings(
        tmp_path,
        monkeypatch,
        {"default_format": "Video", "default_quality": "1080p"},
    )
    assert config.load_settings().default_quality == "1080p"


def test_load_settings_clamps_workers(tmp_path, monkeypatch):
    _write_settings(tmp_path, monkeypatch, {"workers": 9})
    assert config.load_settings().workers == 4
    _write_settings(tmp_path, monkeypatch, {"workers": 0})
    assert config.load_settings().workers == 1
    _write_settings(tmp_path, monkeypatch, {"workers": "many"})
    assert config.load_settings().workers == 1


def test_load_settings_clamps_background_dim(tmp_path, monkeypatch):
    _write_settings(tmp_path, monkeypatch, {"background_dim": 300})
    assert config.load_settings().background_dim == 100
    _write_settings(tmp_path, monkeypatch, {"background_dim": "dark"})
    assert config.load_settings().background_dim == 78
