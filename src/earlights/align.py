import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from itertools import accumulate

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from .epub import BookText, Token, tokenize

MATCH_THRESHOLD = 80.0

_BAND = 0.15
_BIN = 32
_MAX_SEED_HITS = 200
_TRIES = 3
_MIN_WORDS = 4
_SENTENCE_END = re.compile(r"[.!?…]+[\"'”’»)\]]*(?=\s|$)")
_ABBREVIATIONS = frozenset({"dr", "dra", "jr", "mr", "mrs", "ms", "prof", "sr", "sra", "st"})


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    score: float


def find_passage(
    book: BookText,
    transcript: str,
    position_ratio: float | None,
    core: tuple[int, int] | None = None,
) -> Match | None:
    """Locate the transcript in the book.

    `core` is a character span of the transcript: when given, only the book text
    that corresponds to it is returned, extended to whole sentences.
    """
    query = tokenize(transcript)
    if len(query) < _MIN_WORDS:
        return None
    norms = [t.norm for t in query]
    guesses = _guesses(book, norms)
    near = [g for g in guesses if _in_band(book, g, position_ratio)]
    tried: set[int] = set()
    for group in (near[:_TRIES], guesses[:_TRIES]):
        spans = [_locate(book, norms, g) for g in group if g not in tried]
        tried.update(group)
        if not spans:
            continue
        score, first, last = max(spans, key=lambda span: span[0])
        if score < MATCH_THRESHOLD:
            continue
        if core is not None:
            first, last = _project(book, query, core, first, last)
        start, end = extend_to_sentences_text(
            book.text, book.tokens[first].start, book.tokens[last].end
        )
        return Match(start=start, end=end, score=score)
    return None


def candidates(
    book: BookText,
    transcript: str,
    position_ratio: float | None,
    n: int = 3,
    size_words: int = 600,
) -> list[str]:
    """Chunks of the book where the transcript most likely is, best guess first."""
    norms = [t.norm for t in tokenize(transcript)]
    guesses = _guesses(book, norms)
    near = [g for g in guesses if _in_band(book, g, position_ratio)]
    centers = [g + _BIN + len(norms) // 2 for g in near + [g for g in guesses if g not in near]]
    if position_ratio is not None:
        centers.append(int(position_ratio * len(book.tokens)))
    total = len(book.tokens)
    size = min(size_words, total)
    taken: list[int] = []
    chunks = []
    for center in centers:
        lo = max(0, min(center - size // 2, total - size))
        if any(abs(lo - other) < size for other in taken):
            continue
        taken.append(lo)
        chunks.append(book.text[book.tokens[lo].start : book.tokens[lo + size - 1].end])
        if len(chunks) == n:
            break
    return chunks


def extend_to_sentences_text(text: str, start: int, end: int) -> tuple[int, int]:
    paragraph_start = text.rfind("\n\n", 0, start) + 2
    if paragraph_start < 2:
        paragraph_start = 0
    paragraph_end = text.find("\n\n", end)
    if paragraph_end < 0:
        paragraph_end = len(text)

    new_start = paragraph_start
    for found in _SENTENCE_END.finditer(text, paragraph_start, start):
        if found.end() < start and _is_boundary(text, found, paragraph_end):
            new_start = found.end()
    while new_start < start and text[new_start].isspace():
        new_start += 1

    new_end = paragraph_end
    for found in _SENTENCE_END.finditer(text, end, paragraph_end):
        if _is_boundary(text, found, paragraph_end):
            new_end = found.end()
            break
    return new_start, new_end


def _is_boundary(text: str, found: re.Match[str], paragraph_end: int) -> bool:
    if found.group().startswith(".") and not found.group().startswith(".."):
        word = re.search(r"[^\W\d_]+$", text[max(0, found.start() - 5) : found.start()])
        if word and word.group().casefold() in _ABBREVIATIONS:
            return False
    following = found.end()
    while following < paragraph_end and text[following].isspace():
        following += 1
    return following >= paragraph_end or not text[following].islower()


def _guesses(book: BookText, norms: list[str]) -> list[int]:
    """Token positions where the transcript may start, most likely first.

    Each word pair shared with the book votes for the offset between both texts.
    """
    votes: dict[int, float] = {}
    for i, pair in enumerate(zip(norms, norms[1:], strict=False)):
        positions = book.bigrams.get(pair, ())
        if not positions or len(positions) > _MAX_SEED_HITS:
            continue
        weight = 1 / len(positions)
        for position in positions:
            bin_ = (position - i) // _BIN
            votes[bin_] = votes.get(bin_, 0.0) + weight
    merged = {b: v + votes.get(b + 1, 0.0) for b, v in votes.items()}
    ranked = sorted(merged, key=lambda b: (-merged[b], b))
    guesses: list[int] = []
    chosen: set[int] = set()
    for bin_ in ranked:
        if merged[bin_] < merged[ranked[0]] / 10:
            break
        if bin_ - 1 in chosen or bin_ + 1 in chosen:
            continue
        chosen.add(bin_)
        guesses.append(max(0, bin_ * _BIN))
    return guesses


def _in_band(book: BookText, guess: int, position_ratio: float | None) -> bool:
    if position_ratio is None:
        return False
    return abs(guess / len(book.tokens) - position_ratio) <= _BAND


def _locate(book: BookText, norms: list[str], guess: int) -> tuple[float, int, int]:
    """Score and first/last book token of the transcript around a guess."""
    pad = _BIN + len(norms) // 4
    lo = max(0, guess - pad)
    hi = min(len(book.tokens), guess + 2 * _BIN + len(norms) + pad)
    window = [t.norm for t in book.tokens[lo:hi]]
    offsets = list(accumulate((len(norm) + 1 for norm in window), initial=0))
    found = fuzz.partial_ratio_alignment(" ".join(norms), " ".join(window))
    first = bisect_right(offsets, found.dest_start) - 1
    last = max(first, bisect_left(offsets, found.dest_end) - 1)
    return found.score, lo + first, lo + min(last, len(window) - 1)


def _project(
    book: BookText, query: list[Token], core: tuple[int, int], first: int, last: int
) -> tuple[int, int]:
    """Book tokens that correspond to the core of the transcript."""
    inside = [i for i, t in enumerate(query) if t.end > core[0] and t.start < core[1]]
    if not inside:
        return first, last
    core_first, core_last = inside[0], inside[-1]
    span = [t.norm for t in book.tokens[first : last + 1]]
    new_first, new_last = 0, len(span) - 1
    for op in Levenshtein.opcodes([t.norm for t in query], span):
        if op.tag == "insert":
            continue
        paired = op.tag != "delete"
        if op.src_start <= core_first < op.src_end:
            new_first = op.dest_start + (core_first - op.src_start if paired else 0)
        if op.src_start <= core_last < op.src_end:
            new_last = op.dest_start + (core_last - op.src_start if paired else -1)
    new_first = min(max(new_first, 0), len(span) - 1)
    new_last = min(max(new_last, new_first), len(span) - 1)
    return first + new_first, first + new_last
