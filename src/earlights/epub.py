import posixpath
import re
import unicodedata
import warnings
import zipfile
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning
from lxml import etree

_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
_HTML_TYPES = frozenset({"application/xhtml+xml", "text/html"})
_SKIPPED = frozenset({"head", "nav", "script", "style", "template"})
_BLOCKS = frozenset(
    "address article aside blockquote body caption dd div dl dt figcaption figure footer "
    "h1 h2 h3 h4 h5 h6 header hr li main ol p pre section table td th tr ul".split()
)


class EpubError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Token:
    norm: str
    start: int
    end: int


@dataclass(frozen=True)
class BookText:
    """Text of the book in reading order, paragraphs separated by a blank line."""

    text: str
    tokens: list[Token]

    @cached_property
    def bigrams(self) -> dict[tuple[str, str], list[int]]:
        index: dict[tuple[str, str], list[int]] = {}
        norms = [t.norm for t in self.tokens]
        for position, pair in enumerate(zip(norms, norms[1:], strict=False)):
            index.setdefault(pair, []).append(position)
        return index


def normalize(word: str) -> str:
    decomposed = unicodedata.normalize("NFKD", word.casefold())
    return "".join(c for c in decomposed if c.isalnum())


def tokenize(text: str) -> list[Token]:
    tokens = []
    for found in _WORD.finditer(text):
        norm = normalize(found.group())
        if norm:
            tokens.append(Token(norm, found.start(), found.end()))
    return tokens


def load_epub(path: Path) -> BookText:
    paragraphs: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in _spine(archive):
                paragraphs += _paragraphs(archive.read(name))
    except FileNotFoundError:
        raise EpubError(f"EPUB not found: {path}") from None
    except (zipfile.BadZipFile, etree.LxmlError, KeyError, OSError):
        raise EpubError(f"{path} is not a valid EPUB.") from None
    text = "\n\n".join(paragraphs)
    tokens = tokenize(text)
    if not tokens:
        raise EpubError(f"No text found in {path}.")
    return BookText(text=text, tokens=tokens)


def _xml(data: bytes) -> etree._Element:
    return etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))


def _spine(archive: zipfile.ZipFile) -> list[str]:
    """Names of the content documents in reading order, without the navigation page."""
    container = _xml(archive.read("META-INF/container.xml"))
    opf_path = next(container.iter("{*}rootfile")).attrib["full-path"]
    package = _xml(archive.read(opf_path))
    items = {item.get("id"): item for item in package.iter("{*}item")}
    present = set(archive.namelist())
    names = []
    for ref in package.iter("{*}itemref"):
        item = items.get(ref.get("idref"))
        if item is None or item.get("media-type") not in _HTML_TYPES:
            continue
        if "nav" in (item.get("properties") or "").split():
            continue
        href = unquote((item.get("href") or "").split("#")[0])
        name = posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), href))
        if name in present:
            names.append(name)
    return names


def _paragraphs(markup: bytes) -> list[str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(markup, "lxml")
    paragraphs: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        text = " ".join("".join(buffer).replace("\xad", "").split())
        buffer.clear()
        if text:
            paragraphs.append(text)

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, Tag):
                if child.name in _SKIPPED:
                    continue
                if child.name == "br":
                    buffer.append(" ")
                elif child.name in _BLOCKS:
                    flush()
                    walk(child)
                    flush()
                else:
                    walk(child)
            elif type(child) is NavigableString:
                buffer.append(child)

    walk(soup.body or soup)
    flush()
    return paragraphs
