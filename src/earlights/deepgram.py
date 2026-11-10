import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

URL = "https://api.deepgram.com/v1/listen"
TIMEOUT = 120
LANGUAGES = {
    "english": "en",
    "portuguese": "pt-BR",
    "spanish": "es",
    "german": "de",
    "french": "fr",
    "italian": "it",
    "japanese": "ja",
}


class DeepgramError(Exception):
    pass


class DeepgramAuthError(DeepgramError):
    """The account cannot be used at all, so retrying other clips is pointless."""


@dataclass(frozen=True)
class Word:
    text: str
    start_ms: int
    end_ms: int


def deepgram_language(audible_language: str | None, override: str | None) -> str:
    if override:
        return override
    code = LANGUAGES.get((audible_language or "").strip().casefold())
    if code is None:
        log.warning(
            "unknown book language %r, letting Deepgram detect it (use --lang to set it)",
            audible_language,
        )
        return "multi"
    return code


def fetch_transcript(
    audio: Path,
    language: str,
    api_key: str,
    model: str = "nova-3",
    client: httpx.Client | None = None,
) -> dict:
    if client is None:
        with httpx.Client() as owned:
            return fetch_transcript(audio, language, api_key, model, owned)
    request = {
        "params": {
            "model": model,
            "language": language,
            "smart_format": "true",
            "punctuate": "true",
        },
        "headers": {"Authorization": f"Token {api_key}", "Content-Type": "audio/mp4"},
        "content": audio.read_bytes(),
        "timeout": TIMEOUT,
    }
    for attempt in (1, 2):
        try:
            response = client.post(URL, **request)
        except httpx.TransportError as exc:
            if attempt == 1:
                continue
            raise DeepgramError(f"Could not reach Deepgram: {exc!r}") from None
        if response.status_code >= 500 and attempt == 1:
            continue
        break
    if response.status_code in (401, 403):
        raise DeepgramAuthError("Deepgram rejected the API key. Check DEEPGRAM_API_KEY.")
    if response.status_code == 402:
        raise DeepgramAuthError("Deepgram refused the request: the account has no credits left.")
    if response.status_code != 200:
        raise DeepgramError(f"Deepgram error {response.status_code}: {_detail(response)}")
    try:
        return response.json()
    except ValueError:
        raise DeepgramError("Deepgram returned an invalid response.") from None


def _detail(response: httpx.Response) -> str:
    try:
        return str(response.json()["err_msg"])
    except (ValueError, KeyError, TypeError):
        return response.text[:200]


def parse_words(data: dict) -> list[Word]:
    try:
        words = data["results"]["channels"][0]["alternatives"][0].get("words") or []
        return [
            Word(
                text=w.get("punctuated_word") or w["word"],
                start_ms=round(float(w["start"]) * 1000),
                end_ms=round(float(w["end"]) * 1000),
            )
            for w in words
        ]
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise DeepgramError("Deepgram returned an unexpected response.") from None


def transcribe(
    audio: Path,
    language: str,
    api_key: str,
    model: str = "nova-3",
    client: httpx.Client | None = None,
) -> list[Word]:
    return parse_words(fetch_transcript(audio, language, api_key, model, client))
