import pytest

from earlights.epub import EpubError, load_epub, normalize, tokenize
from fixtures.make_epub import CHAPTERS, make_epub


def test_load_epub_spine_order_and_paragraphs(tmp_path):
    book = load_epub(make_epub(tmp_path / "book.epub"))

    expected = [p for _, paragraphs in CHAPTERS for p in paragraphs]
    assert book.text == "\n\n".join(expected)
    assert "NAVIGATION ENTRY" not in book.text
    assert "margin" not in book.text


def test_tokens_point_into_the_original_text(tmp_path):
    book = load_epub(make_epub(tmp_path / "book.epub"))

    token = next(t for t in book.tokens if t.norm == "acao")
    assert book.text[token.start : token.end] == "Ação"
    assert [t.norm for t in book.tokens[:4]] == ["the", "keeper", "climbed", "the"]


def test_inline_markup_and_line_breaks(tmp_path):
    xhtml = (
        "<html><body><div>Loose text<p>One <em>two</em>\n   three.</p>"
        "<p>Four<br/>five.</p></div></body></html>"
    )
    book = load_epub(make_epub(tmp_path / "book.epub", [xhtml]))
    assert book.text == "Loose text\n\nOne two three.\n\nFour five."


def test_headings_are_left_out(tmp_path):
    xhtml = (
        '<html><body><h2 title="1. One"></h2><h1><span>1. ONE</span></h1>'
        "<p>First.</p><h3>A section</h3><p>Second.</p></body></html>"
    )
    book = load_epub(make_epub(tmp_path / "book.epub", [xhtml]))
    assert book.text == "First.\n\nSecond."


def test_footnotes_and_their_references_are_left_out(tmp_path):
    xhtml = (
        '<html xmlns:epub="http://www.idpf.org/2007/ops"><body>'
        '<p>It began<a class="footnote-link" href="#n1">[1]</a> at dawn'
        '<sup><a href="#n2">2</a></sup> and ended<a epub:type="noteref" href="#n3">3</a> late.</p>'
        '<div class="footnotes footnote"><p>[<a href="#b1">1</a>] First note.</p></div>'
        '<aside epub:type="footnote" id="n3"><p>Third note.</p></aside>'
        '<p>See <a href="ch2.xhtml">the next chapter</a>.</p>'
        "</body></html>"
    )
    book = load_epub(make_epub(tmp_path / "book.epub", [xhtml]))
    assert book.text == "It began at dawn and ended late.\n\nSee the next chapter."


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
