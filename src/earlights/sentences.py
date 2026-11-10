import re

from .deepgram import Word

SENTENCE_END = re.compile(r"[.!?…][\"'”’»)]*$")


def extend_to_sentences(words: list[Word], core_start_ms: int, core_end_ms: int) -> str:
    core = [
        i for i, w in enumerate(words) if w.end_ms >= core_start_ms and w.start_ms <= core_end_ms
    ]
    if not core:
        return ""
    first, last = core[0], core[-1]
    while first > 0 and not SENTENCE_END.search(words[first - 1].text):
        first -= 1
    while last < len(words) - 1 and not SENTENCE_END.search(words[last].text):
        last += 1
    return " ".join(w.text for w in words[first : last + 1])
