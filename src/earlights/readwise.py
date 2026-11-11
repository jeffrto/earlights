import time
from collections.abc import Callable

import httpx

from .models import BookInfo, Marker, Passage

URL = "https://readwise.io/api/v2/highlights/"
TIMEOUT = 60
BATCH_SIZE = 100
MAX_LENGTH = 8191
MAX_TRIES = 5
DEFAULT_WAIT = 60


class ReadwiseError(Exception):
    pass


def build_highlight(book: BookInfo, marker: Marker, passage: Passage) -> dict:
    highlight = {
        "text": passage.text[:MAX_LENGTH],
        "title": book.title,
        "category": "books",
        "source_type": "earlights",
        "location": marker.start_ms // 1000,
        "location_type": "time_offset",
        "highlighted_at": marker.created.isoformat(),
    }
    if book.authors:
        highlight["author"] = ", ".join(book.authors)
    if marker.note:
        highlight["note"] = marker.note[:MAX_LENGTH]
    return highlight


def send_highlights(
    highlights: list[dict],
    token: str,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    if client is None:
        with httpx.Client() as owned:
            return send_highlights(highlights, token, owned, sleep)
    for start in range(0, len(highlights), BATCH_SIZE):
        _send_batch(highlights[start : start + BATCH_SIZE], token, client, sleep)


def _send_batch(
    batch: list[dict], token: str, client: httpx.Client, sleep: Callable[[float], None]
) -> None:
    for attempt in range(1, MAX_TRIES + 1):
        try:
            response = client.post(
                URL,
                json={"highlights": batch},
                headers={"Authorization": f"Token {token}"},
                timeout=TIMEOUT,
            )
        except httpx.TransportError as exc:
            raise ReadwiseError(f"Could not reach Readwise: {exc!r}") from None
        if response.status_code != 429:
            break
        if attempt < MAX_TRIES:
            sleep(_retry_after(response))
    else:
        raise ReadwiseError("Readwise rate limit: still refusing after 5 tries. Try again later.")
    if response.status_code in (401, 403):
        raise ReadwiseError("Readwise rejected the token. Check READWISE_TOKEN.")
    if not response.is_success:
        raise ReadwiseError(f"Readwise error {response.status_code}: {response.text[:500]}")


def _retry_after(response: httpx.Response) -> int:
    try:
        return max(0, int(response.headers["Retry-After"]))
    except (KeyError, ValueError):
        return DEFAULT_WAIT
