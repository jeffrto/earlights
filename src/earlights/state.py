import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .models import Passage
from .paths import data_dir


class StateError(Exception):
    pass


@dataclass
class BookState:
    asin: str
    epub_path: str | None = None
    passages: dict[str, Passage] = field(default_factory=dict)
    sent: set[str] = field(default_factory=set)


def state_path(asin: str) -> Path:
    return data_dir(asin) / "state.json"


def load_state(asin: str) -> BookState:
    path = state_path(asin)
    if not path.exists():
        return BookState(asin=asin)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return BookState(
            asin=asin,
            epub_path=data.get("epub_path"),
            passages={k: Passage(**v) for k, v in data.get("passages", {}).items()},
            sent=set(data.get("sent", [])),
        )
    except (ValueError, TypeError, AttributeError) as exc:
        raise StateError(
            f"Could not read {path} ({exc}). Delete it to process the book from scratch."
        ) from None


def save_state(state: BookState) -> None:
    path = state_path(state.asin)
    data = {
        "epub_path": state.epub_path,
        "passages": {k: asdict(v) for k, v in state.passages.items()},
        "sent": sorted(state.sent),
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
