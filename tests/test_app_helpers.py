from yoink.ui.app import APP_VERSION, _valid_timestamp


def test_app_version_is_v1_1():
    assert APP_VERSION == "v1.1"


def test_valid_timestamp_accepts_common_forms():
    assert _valid_timestamp("")
    assert _valid_timestamp("   ")
    assert _valid_timestamp("90")
    assert _valid_timestamp("1:30")
    assert _valid_timestamp("1:30:45")
    assert _valid_timestamp("0:00.5")


def test_valid_timestamp_rejects_bad_values():
    assert not _valid_timestamp("inf")
    assert not _valid_timestamp("nan")
    assert not _valid_timestamp("-1:00")
    assert not _valid_timestamp("1:99")
    assert not _valid_timestamp("1:2:3:4")
    assert not _valid_timestamp("abc")
