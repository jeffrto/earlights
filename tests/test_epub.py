import pytest

from earlights.epub import EpubError, load_epub, normalize, tokenize
from fixtures.make_epub import CHAPTERS, make_epub


def test_load_epub_spine_order_and_paragraphs(tmp_path):
    book = load_epub(make_epub(tmp_path / "book.epub"))

    expected = []
    for title, paragraphs in CHAPTERS:
        expected += [title, *paragraphs]
    assert book.text == "\n\n".join(expected)
    assert "NAVIGATION ENTRY" not in book.text
    assert "margin" not in book.text


def test_tokens_point_into_the_original_text(tmp_path):
    book = load_epub(make_epub(tmp_path / "book.epub"))

    token = next(t for t in book.tokens if t.norm == "acao")
    assert book.text[token.start : token.end] == "Ação"
    assert [t.norm for t in book.tokens[:4]] == ["the", "lighthouse", "the", "keeper"]


def test_inline_markup_and_line_breaks(tmp_path):
    xhtml = (
        "<html><body><div>Loose text<p>One <em>two</em>\n   three.</p>"
        "<p>Four<br/>five.</p></div></body></html>"
    )
    book = load_epub(make_epub(tmp_path / "book.epub", [xhtml]))
    assert book.text == "Loose text\n\nOne two three.\n\nFour five."


def test_normalize_strips_accents_and_punct():
    assert normalize("Ação,") == "acao"
    assert normalize("“Don’t”") == "dont"
    assert normalize("—") == ""


def test_tokenize_splits_on_dashes_and_keeps_apostrophes():
    tokens = tokenize("Well-known—don't stop")
    assert [t.norm for t in tokens] == ["well", "known", "dont", "stop"]


def test_not_an_epub(tmp_path):
    path = tmp_path / "book.epub"
    path.write_text("not a zip")
    with pytest.raises(EpubError, match="not a valid EPUB"):
        load_epub(path)
    with pytest.raises(EpubError, match="not found"):
        load_epub(tmp_path / "missing.epub")
