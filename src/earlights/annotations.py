import logging
from dataclasses import replace
from datetime import datetime

from .models import Chapter, Marker

log = logging.getLogger(__name__)

_KINDS = {"audible.bookmark": "bookmark", "audible.clip": "clip"}
_NOTE = "audible.note"


def parse_annotations(data: dict) -> list[Marker]:
    records = (data.get("payload") or {}).get("records") or []
    markers: list[Marker] = []
    notes: list[Marker] = []
    for record in records:
        try:
            marker = _parse_record(record)
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            log.warning("skipping malformed annotation record: %r", exc)
            continue
        if marker is None:
            continue
        (notes if record["type"] == _NOTE else markers).append(marker)

    for note in notes:
        index = next((i for i, m in enumerate(markers) if m.start_ms == note.start_ms), None)
        if index is None:
            markers.append(note)
        elif not markers[index].note:
            markers[index] = replace(markers[index], note=note.note)

    return sorted(markers, key=lambda m: m.start_ms)


def _parse_record(record: dict) -> Marker | None:
    kind = record["type"]
    if kind != _NOTE and kind not in _KINDS:
        return None
    start = int(record["startPosition"])
    if kind == _NOTE:
        end = None
        note = record.get("text")
    else:
        end = int(record["endPosition"]) if kind == "audible.clip" else None
        note = (record.get("metadata") or {}).get("note")
    return Marker(
        id=record.get("annotationId") or f"{kind}:{start}",
        kind=_KINDS.get(kind, "bookmark"),
        start_ms=start,
        end_ms=end,
        note=note or None,
        created=_parse_time(record["creationTime"]),
    )


def _parse_time(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return datetime.fromisoformat(value)


def parse_chapters(data: dict) -> tuple[list[Chapter], int | None]:
    info = data["content_metadata"]["chapter_info"]
    chapters = [
        Chapter(title=c["title"], start_ms=int(c["start_offset_ms"]), length_ms=int(c["length_ms"]))
        for c in info.get("chapters", [])
    ]
    runtime = info.get("runtime_length_ms")
    return chapters, int(runtime) if runtime is not None else None


def chapter_at(chapters: list[Chapter], ms: int) -> Chapter | None:
    if not chapters:
        return None
    current = chapters[0]
    for chapter in chapters:
        if chapter.start_ms <= ms:
            current = chapter
    return current
