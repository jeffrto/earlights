import random
import time

import pytest

from earlights.align import candidates, extend_to_sentences_text, find_passage
from earlights.epub import BookText, load_epub, tokenize
from fixtures.make_epub import make_epub


def book_from(text: str) -> BookText:
    return BookText(text=text, tokens=tokenize(text))


@pytest.fixture
def book(tmp_path):
    return load_epub(make_epub(tmp_path / "book.epub"))


def synthetic_text(words: int, seed: int = 7) -> str:
    rng = random.Random(seed)
    letters = "abcdefghijklmnopqrstuvwxyz"
    vocabulary = ["".join(rng.choices(letters, k=rng.randint(2, 9))) for _ in range(6000)]
    sentences = []
    count = 0
    while count < words:
        size = rng.randint(6, 22)
        sentence = " ".join(rng.choices(vocabulary, k=size))
        sentences.append(sentence.capitalize() + ".")
        count += size
    paragraphs = [" ".join(sentences[i : i + 6]) for i in range(0, len(sentences), 6)]
    return "\n\n".join(paragraphs)


def spoken(text: str) -> str:
    return " ".join(t.norm for t in tokenize(text))


def test_find_exact_passage_extended_to_sentences(book):
    transcript = "nobody in the village had seen a storm like that since the old bridge"

    match = find_passage(book, transcript, None)

    assert book.text[match.start : match.end] == (
        "Nobody in the village had seen a storm like that since the old bridge was washed away."
    )
    assert match.score > 95


def test_find_with_transcription_errors():
    book = book_from(synthetic_text(3000))
    target = book.tokens[1200:1320]
    rng = random.Random(1)
    heard = [t.norm if rng.random() > 0.15 else "zzqx" for t in target]

    match = find_passage(book, " ".join(heard), None)

    assert match is not None
    # edges may be off by a word or two when the misheard words are at the ends
    assert match.start <= target[3].start
    assert match.end >= target[-4].end
    assert match.end - match.start < (target[-1].end - target[0].start) * 1.6


def test_returns_none_for_unrelated_text(book):
    transcript = (
        "quarterly revenue grew by twelve percent while operating margins "
        "declined because of higher logistics and marketing expenses"
    )
    assert find_passage(book, transcript, 0.5) is None
    assert find_passage(book, "", None) is None


def test_position_ratio_disambiguates_repeated_phrase():
    refrain = "The bells of the old harbour rang twice and then the whole town fell silent."
    filler = synthetic_text(4000)
    half = len(filler) // 2
    cut = filler.index("\n\n", half)
    text = f"{refrain}\n\n{filler[:cut]}\n\n{refrain}\n\n{filler[cut + 2 :]}\n\n{refrain}"
    book = book_from(text)
    starts = [i for i in range(len(text)) if text.startswith(refrain, i)]
    assert len(starts) == 3

    transcript = spoken(refrain)
    assert find_passage(book, transcript, 0.02).start == starts[0]
    assert find_passage(book, transcript, 0.5).start == starts[1]
    assert find_passage(book, transcript, 0.98).start == starts[2]


def test_falls_back_to_whole_book_when_ratio_is_wrong(book):
    transcript = "seven boats were tied to the pier and the eighth was found two days later"
    match = find_passage(book, transcript, 0.0)
    assert book.text[match.start : match.end].startswith("Seven boats were tied")


def test_match_text_is_literal_substring(book):
    match = find_passage(book, "acao coragem e paciencia were the three words painted", None)
    assert book.text[match.start : match.end] == (
        "Ação, coragem e paciência were the three words painted above the door."
    )


def test_core_limits_the_passage(book):
    transcript = (
        "he carried a small brass lamp and a tin of oil that smelled of the sea "
        "from the top he could see the fishing boats coming home across the grey water "
        "acao coragem e paciencia were the three words painted above the door"
    )
    core_start = transcript.index("fishing")
    core = (core_start, core_start + len("fishing boats"))

    match = find_passage(book, transcript, None, core=core)

    assert book.text[match.start : match.end] == (
        "From the top he could see the fishing boats coming home across the grey water."
    )


def test_large_book_performance():
    book = book_from(synthetic_text(150_000))
    target = book.tokens[100_000:100_130]
    transcript = " ".join(t.norm for t in target)

    started = time.perf_counter()
    match = find_passage(book, transcript, 0.2)
    elapsed = time.perf_counter() - started

    assert match is not None
    assert match.start <= target[0].start < target[-1].end <= match.end
    assert elapsed < 2


def test_candidates_are_literal_chunks_around_the_best_guesses():
    book = book_from(synthetic_text(5000))
    target = book.tokens[3000:3100]
    transcript = " ".join(t.norm for t in target)

    found = candidates(book, transcript, 0.6, n=3, size_words=600)

    assert 1 <= len(found) <= 3
    assert all(chunk in book.text for chunk in found)
    assert book.text[target[0].start : target[-1].end] in found[0]
    assert len(tokenize(found[0])) <= 600


def test_candidates_use_position_when_nothing_matches():
    book = book_from(synthetic_text(5000))
    found = candidates(book, "nothing in common with it", 0.5, n=3, size_words=200)
    assert len(found) == 1
    middle = book.tokens[len(book.tokens) // 2]
    assert book.text[middle.start : middle.end] in found[0]


@pytest.mark.parametrize(
    ("text", "inner", "expected"),
    [
        ("One two. Three four five. Six.", "four", "Three four five."),
        ("One two. Three four five", "four", "Three four five"),
        ("Title\n\nBody text here. More.", "text", "Body text here."),
        ("Heading without stop\n\nNext one.", "without", "Heading without stop"),
        ('"Go now!" he said. Then left.', "now", '"Go now!" he said.'),
        ('He said, "Stop." Then left. End.', "Then", "Then left."),
        ("Well... maybe not. Fine.", "maybe", "Well... maybe not."),
        ("We met Mr. Smith at noon. Bye.", "Smith", "We met Mr. Smith at noon."),
        ("First. Is it so? Yes!", "it", "Is it so?"),
    ],
)
def test_extend_to_sentences_text(text, inner, expected):
    start = text.index(inner)
    new_start, new_end = extend_to_sentences_text(text, start, start + len(inner))
    assert text[new_start:new_end] == expected
