import json
import subprocess
import tempfile
from pathlib import Path

from .annotations import parse_voucher
from .models import BookFiles, BookInfo


class AudibleError(Exception):
    pass


def _run(args: list[str], profile: str | None) -> subprocess.CompletedProcess:
    cmd = ["audible"]
    if profile:
        cmd += ["-P", profile]
    cmd += args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise AudibleError(
            "audible-cli not found. Install it and run `audible quickstart`."
        ) from None
    if result.returncode != 0:
        raise AudibleError(result.stderr.strip() or result.stdout.strip() or "audible failed")
    return result


def _runtime_ms(minutes) -> int | None:
    return int(minutes) * 60_000 if minutes is not None else None


def list_library(profile: str | None = None) -> list[BookInfo]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "library.json"
        _run(["library", "export", "-f", "json", "-o", str(out)], profile)
        items = json.loads(out.read_text())
    return [
        BookInfo(
            asin=item["asin"],
            title=item.get("title") or "",
            authors=[a.strip() for a in (item.get("authors") or "").split(",") if a.strip()],
            language=item.get("language"),
            runtime_ms=_runtime_ms(item.get("runtime_length_min")),
        )
        for item in items
    ]


def get_book_info(asin: str, profile: str | None = None) -> BookInfo:
    result = _run(
        ["api", f"1.0/library/{asin}", "-p", "response_groups=product_attrs,contributors,media"],
        profile,
    )
    try:
        item = json.loads(result.stdout)["item"]
    except (ValueError, KeyError) as exc:
        raise AudibleError(f"Unexpected response for {asin}: {exc!r}") from None
    return BookInfo(
        asin=asin,
        title=item.get("title") or "",
        authors=[a["name"] for a in item.get("authors") or []],
        language=item.get("language"),
        runtime_ms=_runtime_ms(item.get("runtime_length_min")),
    )


def _find_audio(asin: str, dest: Path) -> Path | None:
    for audio in sorted(dest.glob(f"{asin}-*.aaxc")):
        if audio.with_suffix(".voucher").exists():
            return audio
    return None


def download_book(asin: str, dest: Path, profile: str | None = None) -> BookFiles:
    dest.mkdir(parents=True, exist_ok=True)
    annotations = dest / f"{asin}-annotations.json"
    chapters = dest / f"{asin}-chapters.json"
    # audible-cli skips files that already exist, and annotations change between runs
    annotations.unlink(missing_ok=True)

    args = ["download", "-a", asin]
    if _find_audio(asin, dest) is None:
        args.append("--aaxc")
    args += ["--annotation", "--chapter", "--chapter-type", "flat"]
    args += ["-o", str(dest), "-f", "asin_only", "-y", "--no-progress"]
    result = _run(args, profile)

    audio = _find_audio(asin, dest)
    if audio is None:
        detail = (result.stderr.strip() or result.stdout.strip())[-2000:]
        raise AudibleError(f"Download of {asin} produced no audio file. {detail}".strip())
    try:
        key, iv = parse_voucher(json.loads(audio.with_suffix(".voucher").read_text()))
    except (ValueError, KeyError, TypeError) as exc:
        raise AudibleError(f"Could not read voucher for {asin}: {exc!r}") from None
    return BookFiles(
        audio=audio,
        key=key,
        iv=iv,
        annotations=annotations if annotations.exists() else None,
        chapters=chapters if chapters.exists() else None,
    )


def find_book(query: str, library: list[BookInfo]) -> BookInfo:
    needle = query.strip().casefold()
    for book in library:
        if book.asin.casefold() == needle:
            return book
    matches = [b for b in library if needle in b.title.casefold()]
    exact = [b for b in matches if b.title.casefold() == needle]
    if len(exact) == 1:
        return exact[0]
    if not matches:
        raise AudibleError(f"No book matches '{query}'. Run `earlights library` to list them.")
    if len(matches) > 1:
        listing = "\n".join(f"  {b.asin}  {b.title}" for b in matches)
        raise AudibleError(f"'{query}' matches more than one book, use the ASIN:\n{listing}")
    return matches[0]
