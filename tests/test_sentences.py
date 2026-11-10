from earlights.deepgram import Word
from earlights.sentences import extend_to_sentences


def words(text, step=1000):
    return [Word(w, i * step, i * step + step - 100) for i, w in enumerate(text.split())]


def test_extends_back_and_forward_to_sentence_end():
    ws = words("One two. Three four five six. Seven eight.")
    # core covers "four five" only
    assert extend_to_sentences(ws, 3000, 4500) == "Three four five six."


def test_core_spanning_two_sentences_keeps_both():
    ws = words("One two. Three four. Five six. Seven.")
    assert extend_to_sentences(ws, 3000, 4500) == "Three four. Five six."


def test_stops_at_list_bounds_without_terminator():
    ws = words("one two three four five")
    assert extend_to_sentences(ws, 2000, 2500) == "one two three four five"


def test_closing_quote_counts_as_terminator():
    ws = words('Antes. Ele disse." Depois veio mais texto. Fim.')
    assert extend_to_sentences(ws, 4000, 4500) == "Depois veio mais texto."


def test_question_and_ellipsis_end_sentences():
    ws = words("Is it? Yes it is… Maybe not! Done.")
    assert extend_to_sentences(ws, 3000, 3500) == "Yes it is…"


def test_empty_transcript_yields_empty_passage():
    assert extend_to_sentences([], 0, 30_000) == ""


def test_no_word_in_core_yields_empty():
    ws = words("One two. Three.")
    assert extend_to_sentences(ws, 60_000, 90_000) == ""
