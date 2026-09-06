from yoink.core.inspection import describe, media_entries


def test_describe_normalizes_optional_metadata():
    media = describe({"id": "abc", "title": "Example", "duration": 62})
    assert media["title"] == "Example"
    assert media["duration"] == "1:02"
    assert media["uploader"] == "Unknown uploader"


def test_media_entries_filters_missing_playlist_items():
    entries = media_entries({"entries": [{"id": "one"}, None, {"id": "two"}]})
    assert [entry["id"] for entry in entries] == ["one", "two"]
