from yoink.ui.assets import asset_path


def test_bundled_icon_assets_exist():
    assert asset_path("icons", "luna.ico").is_file()
    assert asset_path("icons", "main-icon-nobg.png").is_file()
