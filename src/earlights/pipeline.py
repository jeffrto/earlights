import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from . import audible, audio, deepgram
from .align import find_passage
from .annotations import parse_annotations, parse_chapters
from .config import Config, require
from .epub import BookText, load_epub
from .markdown import format_time, render_markdown
from .models import BookInfo, Chapter, Marker, Passage
from .paths import cache_dir
from .sentences import extend_to_sentences
from .state import BookState, load_state, save_state

Mode = Literal["transcript", "epub", "ai", "auto"]

_ASIN = re.compile(r"[A-Z0-9]{10}")


class PipelineError(Exception):
    pass


@dataclass(frozen=True)
class Options:
    mode: Mode | None = None
    epub: Path | None = None
    language: str | None = None
    out: Path | None = None
    readwise: bool = False
    force: bool = False
    profile: str | None = None


def process_book(
    query: str,
    options: Options,
    config: Config,
    report: Callable[[str], None] = print,
) -> Path | None:
    api_key = require(config, "deepgram_api_key")
    if options.mode in ("ai", "auto") or options.readwise:
        raise PipelineError(
            "Only the transcript and epub modes are available: the rest is not implemented yet."
        )
    new_epub = load_epub(options.epub) if options.epub else None

    book = _find_book(query, options.profile)
    state = load_state(book.asin)
    epub_changed = False
    if options.epub:
        epub_path = str(options.epub.resolve())
        epub_changed = epub_path != state.epub_path
        state.epub_path = epub_path
        save_state(state)
    mode = options.mode or ("epub" if state.epub_path else "transcript")
    book_text = None
    if mode == "epub":
        if not state.epub_path:
            raise PipelineError("The epub mode needs the book: pass it with --epub.")
        book_text = new_epub or load_epub(Path(state.epub_path))

    report(f"{book.title} [{book.asin}]: fetching bookmarks and audio")
    cache = cache_dir(book.asin)
    files = audible.download_book(book.asin, cache, options.profile)
    markers = parse_annotations(_read_json(files.annotations))
    if not markers:
        report("This book has no bookmarks or clips.")
        return None
    chapters = _chapters(files.chapters)
    audio.check_decodable(files.audio)
    duration_ms = audio.audio_duration_ms(files.audio)
    markers = audio.merge_overlapping(markers, duration_ms)
    language = deepgram.deepgram_language(book.language, options.language)

    failed = 0
    for number, marker in enumerate(markers, 1):
        done = state.passages.get(marker.id)
        if done and done.mode == mode and not options.force and not epub_changed:
            continue
        report(f"[{number}/{len(markers)}] {format_time(marker.start_ms)}")
        try:
            words = _transcribe(marker, files.audio, duration_ms, cache, language, api_key, config)
        except deepgram.DeepgramAuthError:
            raise
        except (audio.AudioError, deepgram.DeepgramError) as exc:
            failed += 1
            report(f"Warning: marker at {format_time(marker.start_ms)} failed: {exc}")
            continue
        passage = _transcript_passage(marker, words, duration_ms, mode)
        if book_text and passage.text:
            found = _epub_text(book_text, marker, words, duration_ms)
            if found:
                passage = replace(passage, text=found, source="epub")
            else:
                at = format_time(marker.start_ms)
                report(f"Warning: marker at {at} not found in the EPUB, using the transcript.")
        state.passages[marker.id] = passage
        save_state(state)

    _drop_deleted(state, markers)
    if failed:
        plural = "marker" if failed == 1 else "markers"
        report(f"{failed} {plural} failed. Run the command again to retry.")
    if book_text:
        found = sum(p.source == "epub" for p in state.passages.values())
        report(f"{found}/{len(state.passages)} found in EPUB")

    out = options.out or Path(f"{_file_name(book.title) or book.asin}.md")
    out.write_text(render_markdown(book, markers, state.passages, chapters), encoding="utf-8")
    return out


def _find_book(query: str, profile: str | None) -> BookInfo:
    asin = query.strip().upper()
    if not _ASIN.fullmatch(asin):
        asin = audible.find_book(query, audible.list_library(profile)).asin
    return audible.get_book_info(asin, profile)


def _read_json(path: Path | None) -> dict:
    if path is None:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise PipelineError(f"Could not read {path}.") from None


def _chapters(path: Path | None) -> list[Chapter]:
    if path is None:
        return []
    try:
        return parse_chapters(_read_json(path))[0]
    except (KeyError, TypeError, ValueError):
        return []


def _transcribe(
    marker: Marker,
    src: Path,
    duration_ms: int,
    cache: Path,
    language: str,
    api_key: str,
    config: Config,
) -> list[deepgram.Word]:
    """Words of the marker window, with times relative to the whole book."""
    window = audio.marker_window(marker, duration_ms)
    name = f"{_safe(marker.id)}-{window.start_ms}-{window.end_ms}"
    model = config.deepgram_model
    cached = cache / "transcripts" / f"{name}-{_safe(language)}-{_safe(model)}.json"
    if cached.exists():
        data = json.loads(cached.read_text(encoding="utf-8"))
    else:
        clip = audio.cut_clip(src, window.start_ms, window.end_ms, cache / "clips" / f"{name}.flac")
        data = deepgram.fetch_transcript(clip, language, api_key, model)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return [
        replace(w, start_ms=w.start_ms + window.start_ms, end_ms=w.end_ms + window.start_ms)
        for w in deepgram.parse_words(data)
    ]


def _transcript_passage(
    marker: Marker, words: list[deepgram.Word], duration_ms: int, mode: str
) -> Passage:
    window = audio.marker_window(marker, duration_ms)
    text = extend_to_sentences(words, window.core_start_ms, window.core_end_ms)
    return Passage(
        marker_id=marker.id,
        text=text,
        source="transcript" if text else "none",
        mode=mode,
        transcript=" ".join(w.text for w in words),
    )


def _epub_text(
    book_text: BookText, marker: Marker, words: list[deepgram.Word], duration_ms: int
) -> str | None:
    """The passage as written in the book, located by the whole transcribed window."""
    window = audio.marker_window(marker, duration_ms)
    position = 0
    core_start = core_end = None
    for word in words:
        if word.end_ms >= window.core_start_ms and word.start_ms <= window.core_end_ms:
            if core_start is None:
                core_start = position
            core_end = position + len(word.text)
        position += len(word.text) + 1
    core = None if core_start is None else (core_start, core_end)
    ratio = marker.start_ms / duration_ms if duration_ms else None
    match = find_passage(book_text, " ".join(w.text for w in words), ratio, core)
    return book_text.text[match.start : match.end] if match else None


def _drop_deleted(state: BookState, markers: list[Marker]) -> None:
    current = {m.id for m in markers}
    deleted = [marker_id for marker_id in state.passages if marker_id not in current]
    if deleted:
        for marker_id in deleted:
            del state.passages[marker_id]
        save_state(state)


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def _file_name(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title)
    return re.sub(r"\s+", " ", cleaned).strip(" .")
