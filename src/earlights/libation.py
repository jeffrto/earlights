import re
import shutil
import subprocess
from pathlib import Path

AUDIO_SUFFIXES = {".m4b", ".m4a", ".mp3"}


class LibationError(Exception):
    pass


def available() -> bool:
    return shutil.which("libationcli") is not None


def _run(args: list[str]) -> subprocess.CompletedProcess:
    try:
        # stdin is closed because some libationcli commands wait for a key press
        result = subprocess.run(
            ["libationcli", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL
        )
    except FileNotFoundError:
        raise LibationError("libationcli not found. Install Libation and sign in.") from None
    if result.returncode != 0:
        raise LibationError(result.stderr.strip() or result.stdout.strip() or "libationcli failed")
    return result


def books_dir() -> Path:
    output = _run(["get-setting", "-b", "Books"]).stdout
    match = re.search(r'^Books="?(.+?)"?\s*$', output, re.MULTILINE)
    if not match:
        raise LibationError("Could not read the books folder from Libation settings.")
    return Path(match.group(1))


def find_audio(asin: str, books: Path) -> Path | None:
    if not books.is_dir():
        return None
    tag = f"[{asin}]"
    found = sorted(
        p for p in books.rglob("*") if p.suffix.lower() in AUDIO_SUFFIXES and tag in p.name
    )
    if len(found) > 1:
        raise LibationError(
            f"Libation has more than one audio file for {asin}. "
            "Books split by chapter are not supported."
        )
    return found[0] if found else None


def liberate(asin: str) -> Path:
    result = _run(["liberate", asin])
    audio = find_audio(asin, books_dir())
    if audio is None:
        detail = (result.stdout.strip() or result.stderr.strip())[-2000:]
        raise LibationError(f"Libation did not produce an audio file for {asin}. {detail}".strip())
    return audio
