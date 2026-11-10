import logging
from datetime import datetime

from earlights.annotations import chapter_at, parse_annotations, parse_chapters


def test_parse_annotations_kinds_and_order(load_fixture):
    markers = parse_annotations(load_fixture("annotations.json"))
    assert [m.kind for m in markers] == ["bookmark", "clip"]
    assert [m.start_ms for m in markers] == [60000, 120000]
    assert [m.id for m in markers] == ["bm-1", "clip-1"]
    assert markers[0].created == datetime(2026, 1, 2, 8, 15, 30, 123000)


def test_note_attached_to_bookmark(load_fixture):
    markers = parse_annotations(load_fixture("annotations.json"))
    assert markers[0].note == "my note"
    assert markers[0].end_ms is None


def test_clip_has_end_and_note(load_fixture):
    markers = parse_annotations(load_fixture("annotations.json"))
    assert markers[1].end_ms == 125000
    assert markers[1].note == "clip note"


def test_malformed_record_skipped(load_fixture, caplog):
    with caplog.at_level(logging.WARNING):
        markers = parse_annotations(load_fixture("annotations.json"))
    assert "bm-broken" not in [m.id for m in markers]
    assert any("malformed" in r.message for r in caplog.records)


def test_unpaired_note_becomes_bookmark():
    data = {
        "payload": {
            "records": [
                {
                    "type": "audible.note",
                    "startPosition": "9000",
                    "creationTime": "2026-01-02 08:16:00.0",
                    "text": "lonely",
                }
            ]
        }
    }
    (marker,) = parse_annotations(data)
    assert marker.kind == "bookmark"
    assert marker.note == "lonely"
    assert marker.id == "audible.note:9000"


def test_note_does_not_override_clip_note():
    data = {
        "payload": {
            "records": [
                {
                    "type": "audible.clip",
                    "annotationId": "c",
                    "startPosition": "1000",
                    "endPosition": "2000",
                    "creationTime": "2026-01-02 08:16:00.0",
                    "metadata": {"note": "from clip"},
                },
                {
                    "type": "audible.note",
                    "startPosition": "1000",
                    "creationTime": "2026-01-02 08:16:00.0",
                    "text": "from note",
                },
            ]
        }
    }
    (marker,) = parse_annotations(data)
    assert marker.note == "from clip"


def test_empty_payload():
    assert parse_annotations({}) == []
    assert parse_annotations({"payload": {"records": []}}) == []


def test_parse_chapters_and_runtime(load_fixture):
    chapters, runtime = parse_chapters(load_fixture("chapters.json"))
    assert runtime == 300000
    assert [c.title for c in chapters] == ["Opening", "Chapter 1", "Chapter 2"]
    assert chapters[1].start_ms == 50000
    assert chapters[1].length_ms == 100000


def test_chapter_at(load_fixture):
    chapters, _ = parse_chapters(load_fixture("chapters.json"))
    assert chapter_at(chapters, 200000).title == "Chapter 2"
    assert chapter_at(chapters, 50000).title == "Chapter 1"
    assert chapter_at(chapters, 999999).title == "Chapter 2"
    assert chapter_at([], 1000) is None


def test_note_html_entities_unescaped():
    data = {
        "payload": {
            "records": [
                {
                    "type": "audible.note",
                    "startPosition": "1000",
                    "creationTime": "2026-01-01 10:00:00.0",
                    "text": "inquieta&ccedil;&atilde;o &amp; busca",
                }
            ]
        }
    }
    assert parse_annotations(data)[0].note == "inquietação & busca"
