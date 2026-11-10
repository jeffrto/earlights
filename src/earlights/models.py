from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class BookInfo:
    asin: str
    title: str
    authors: list[str]
    language: str | None = None
    runtime_ms: int | None = None


@dataclass(frozen=True)
class Chapter:
    title: str
    start_ms: int
    length_ms: int


@dataclass(frozen=True)
class Marker:
    id: str
    kind: Literal["bookmark", "clip"]
    start_ms: int
    end_ms: int | None
    note: str | None
    created: datetime


@dataclass(frozen=True)
class BookFiles:
    audio: Path
    key: str | None
    iv: str | None
    annotations: Path | None
    chapters: Path | None
