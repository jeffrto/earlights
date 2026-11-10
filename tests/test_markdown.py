from datetime import datetime

from earlights.markdown import render_markdown
from earlights.models import BookInfo, Chapter, Marker, Passage

BOOK = BookInfo(asin="B000FAKE01", title="Fake Book", authors=["Ann Author", "Bob Writer"])
CHAPTERS = [Chapter("Intro", 0, 60_000), Chapter("Chapter 1", 60_000, 7_200_000)]


def marker(id, start_ms, note=None):
    return Marker(id, "bookmark", start_ms, None, note, datetime(2026, 1, 1))


def passage(id, text, source="transcript"):
    return Passage(marker_id=id, text=text, source=source, mode="transcript", transcript=text)


def test_render_order_chapter_note_and_empty():
    markers = [
        marker("a", 30_000),
        marker("b", 3_725_000, note="my note"),
        marker("c", 4_000_000),
        marker("d", 5_000_000),
    ]
    passages = {
        "a": passage("a", "First passage."),
        "b": passage("b", "Second passage."),
        "c": passage("c", "", source="none"),
    }

    assert render_markdown(BOOK, markers, passages, CHAPTERS) == (
        "# Fake Book\n"
        "*Ann Author, Bob Writer*\n"
        "\n"
        "## 00:00:30 · Intro\n"
        "\n"
        "> First passage.\n"
        "\n"
        "## 01:02:05 · Chapter 1\n"
        "\n"
        "> Second passage.\n"
        "\n"
        "**Note:** my note\n"
        "\n"
        "## 01:06:40 · Chapter 1\n"
        "\n"
        "> _(no speech detected)_\n"
    )


def test_source_line_for_non_transcript_passages():
    out = render_markdown(BOOK, [marker("a", 0)], {"a": passage("a", "Text.", "epub")}, CHAPTERS)
    assert out.endswith("> Text.\n\n<sub>source: epub</sub>\n")


def test_no_chapters_and_no_authors():
    book = BookInfo(asin="X", title="Solo", authors=[])
    out = render_markdown(book, [marker("a", 1000)], {"a": passage("a", "Text.")}, [])
    assert out == "# Solo\n\n## 00:00:01\n\n> Text.\n"


def test_multiline_text_stays_in_blockquote():
    out = render_markdown(BOOK, [marker("a", 0)], {"a": passage("a", "One.\n\nTwo.")}, [])
    assert "> One.\n>\n> Two.\n" in out
