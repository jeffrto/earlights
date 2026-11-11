import json
from datetime import datetime

import httpx
import pytest

from earlights.models import BookInfo, Marker, Passage
from earlights.readwise import URL, ReadwiseError, build_highlight, send_highlights

BOOK = BookInfo("B000FAKE01", "Fake Book", ["Ann Author", "Bob Writer"])


def marker(note=None):
    return Marker("m1", "bookmark", 61_900, None, note, datetime(2026, 1, 2, 10, 30, 0))


def passage(text="Hello there world."):
    return Passage("m1", text, "transcript", "transcript", text)


def sent_batches(httpx_mock):
    return [json.loads(r.content)["highlights"] for r in httpx_mock.get_requests()]


def test_build_highlight_fields():
    assert build_highlight(BOOK, marker(), passage()) == {
        "text": "Hello there world.",
        "title": "Fake Book",
        "author": "Ann Author, Bob Writer",
        "category": "books",
        "source_type": "earlights",
        "location": 61,
        "location_type": "time_offset",
        "highlighted_at": "2026-01-02T10:30:00",
    }


def test_build_highlight_includes_the_note():
    assert build_highlight(BOOK, marker("my note"), passage())["note"] == "my note"


def test_build_highlight_cuts_long_text():
    highlight = build_highlight(BOOK, marker("n" * 9000), passage("x" * 9000))
    assert len(highlight["text"]) == 8191
    assert len(highlight["note"]) == 8191


def test_build_highlight_without_author():
    assert "author" not in build_highlight(BookInfo("A", "T", []), marker(), passage())


def test_send_batches_of_100(httpx_mock):
    httpx_mock.add_response(url=URL, method="POST", json=[], is_reusable=True)

    send_highlights([{"text": str(n)} for n in range(250)], "tok")

    assert [len(batch) for batch in sent_batches(httpx_mock)] == [100, 100, 50]
    assert httpx_mock.get_requests()[0].headers["Authorization"] == "Token tok"


def test_send_nothing_makes_no_request(httpx_mock):
    send_highlights([], "tok")
    assert httpx_mock.get_requests() == []


def test_retry_after_on_429(httpx_mock):
    httpx_mock.add_response(status_code=429, headers={"Retry-After": "3"})
    httpx_mock.add_response(status_code=429)
    httpx_mock.add_response(json=[])
    waits = []

    send_highlights([{"text": "a"}], "tok", sleep=waits.append)

    assert waits == [3, 60]
    assert len(httpx_mock.get_requests()) == 3


def test_gives_up_after_five_429(httpx_mock):
    httpx_mock.add_response(status_code=429, headers={"Retry-After": "1"}, is_reusable=True)

    with pytest.raises(ReadwiseError, match="rate limit"):
        send_highlights([{"text": "a"}], "tok", sleep=lambda seconds: None)

    assert len(httpx_mock.get_requests()) == 5


def test_error_raises_with_body(httpx_mock):
    httpx_mock.add_response(status_code=400, text='{"text": ["too long"]}')

    with pytest.raises(ReadwiseError, match=r"400.*too long"):
        send_highlights([{"text": "a"}], "tok")


def test_bad_token(httpx_mock):
    httpx_mock.add_response(status_code=401, text="Invalid token")

    with pytest.raises(ReadwiseError, match="READWISE_TOKEN"):
        send_highlights([{"text": "a"}], "tok")


def test_network_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("down"))

    with pytest.raises(ReadwiseError, match="Could not reach Readwise"):
        send_highlights([{"text": "a"}], "tok")
