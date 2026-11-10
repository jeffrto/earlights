from .annotations import chapter_at
from .models import BookInfo, Chapter, Marker, Passage

NO_SPEECH = "_(no speech detected)_"


def format_time(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def render_markdown(
    book: BookInfo,
    markers: list[Marker],
    passages: dict[str, Passage],
    chapters: list[Chapter],
) -> str:
    header = f"# {book.title}"
    if book.authors:
        header += f"\n*{', '.join(book.authors)}*"
    blocks = [header]
    for marker in markers:
        passage = passages.get(marker.id)
        if passage is None:
            continue
        chapter = chapter_at(chapters, marker.start_ms)
        heading = f"## {format_time(marker.start_ms)}"
        if chapter and chapter.title:
            heading += f" · {chapter.title}"
        blocks.append(heading)
        blocks.append(_quote(passage.text) if passage.source != "none" else f"> {NO_SPEECH}")
        if marker.note:
            blocks.append(f"**Note:** {marker.note}")
        fallback = passage.source == "transcript" and passage.mode != "transcript"
        if passage.source in ("epub", "ai") or fallback:
            blocks.append(f"<sub>source: {passage.source}</sub>")
    return "\n\n".join(blocks) + "\n"
