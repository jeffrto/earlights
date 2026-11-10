import json

import pytest

from earlights.models import Passage
from earlights.state import BookState, StateError, load_state, save_state

ASIN = "B000FAKE01"


def test_missing_state_is_empty(dirs):
    state = load_state(ASIN)
    assert state == BookState(asin=ASIN)
    assert state.passages == {} and state.sent == set() and state.epub_path is None


def test_roundtrip(dirs):
    state = BookState(asin=ASIN, epub_path="/books/a.epub")
    state.passages["m1"] = Passage(
        marker_id="m1", text="Olá, mundo.", source="transcript", mode="transcript", transcript="x"
    )
    state.sent.add("m1")

    save_state(state)

    assert load_state(ASIN) == state
    folder = dirs / "data" / ASIN
    assert [p.name for p in folder.iterdir()] == ["state.json"]
    assert "Olá" in (folder / "state.json").read_text(encoding="utf-8")


def test_corrupt_state_raises(dirs):
    path = dirs / "data" / ASIN / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    with pytest.raises(StateError, match="state.json"):
        load_state(ASIN)


def test_wrong_shape_raises(dirs):
    path = dirs / "data" / ASIN / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"passages": {"m1": {"text": "x"}}}))
    with pytest.raises(StateError):
        load_state(ASIN)
