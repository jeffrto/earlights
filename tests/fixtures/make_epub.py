import zipfile
from html import escape
from pathlib import Path

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

NAV = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Contents</title></head>
<body><nav><ol><li><a href="text/ch1.xhtml">NAVIGATION ENTRY</a></li></ol></nav></body></html>"""

CHAPTERS = [
    (
        "The Lighthouse",
        [
            "The keeper climbed the narrow stairs every evening before the sun went down. "
            "He carried a small brass lamp and a tin of oil that smelled of the sea.",
            "From the top he could see the fishing boats coming home across the grey water. "
            "Ação, coragem e paciência were the three words painted above the door.",
        ],
    ),
    (
        "The Storm",
        [
            "On the ninth night of October the wind turned and the waves began to break "
            "over the rocks. Nobody in the village had seen a storm like that since the "
            "old bridge was washed away.",
            '"Light the lamp!" shouted the keeper. Nobody answered him, because the '
            "boy had already run down to the harbour to warn the others.",
        ],
    ),
    (
        "The Morning",
        [
            "When the morning came the sea was flat and quiet again. Seven boats were "
            "tied to the pier and the eighth was found two days later, drifting empty "
            "near the northern cliffs.",
        ],
    ),
]


def chapter_xhtml(title: str, paragraphs: list[str]) -> str:
    body = "".join(f"<p>{escape(p)}</p>\n" for p in paragraphs)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
        f"<title>{escape(title)}</title><style>p {{ margin: 0 }}</style></head>\n"
        f"<body><h1>{escape(title)}</h1>\n{body}</body></html>"
    )


def make_epub(path: Path, documents: list[str] | None = None) -> Path:
    """Write a synthetic EPUB. The manifest order differs from the spine order on purpose."""
    if documents is None:
        documents = [chapter_xhtml(title, paragraphs) for title, paragraphs in CHAPTERS]
    numbers = range(1, len(documents) + 1)
    manifest = "".join(
        f'<item id="c{i}" href="text/ch%20{i}.xhtml" media-type="application/xhtml+xml"/>'
        for i in reversed(numbers)
    )
    spine = "".join(f'<itemref idref="c{i}"/>' for i in numbers)
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        "<metadata/>"
        '<manifest><item id="nav" href="nav.xhtml" properties="nav" '
        f'media-type="application/xhtml+xml"/>{manifest}</manifest>'
        f'<spine><itemref idref="nav"/>{spine}</spine></package>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/nav.xhtml", NAV)
        for i, document in zip(numbers, documents, strict=True):
            archive.writestr(f"OEBPS/text/ch {i}.xhtml", document)
    return path
