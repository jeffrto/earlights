import subprocess
from dataclasses import dataclass
from pathlib import Path

from earlights.models import Marker

CORE_HALF_MS = 15_000
MARGIN_MS = 10_000


class AudioError(Exception):
    pass


@dataclass(frozen=True)
class Window:
    core_start_ms: int
    core_end_ms: int
    start_ms: int
    end_ms: int


def marker_window(marker: Marker, runtime_ms: int | None) -> Window:
    def clamp(ms: int) -> int:
        ms = max(0, ms)
        return ms if runtime_ms is None else min(ms, runtime_ms)

    start = clamp(marker.start_ms)
    if marker.end_ms is not None:
        core_start, core_end = start, clamp(marker.end_ms)
    else:
        core_start, core_end = clamp(start - CORE_HALF_MS), clamp(start + CORE_HALF_MS)
    return Window(
        core_start_ms=core_start,
        core_end_ms=core_end,
        start_ms=clamp(core_start - MARGIN_MS),
        end_ms=clamp(core_end + MARGIN_MS),
    )


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise AudioError(f"{args[0]} not found. Install ffmpeg.") from None
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise AudioError(f"{args[0]} failed: {detail}")
    return result.stdout


def audio_duration_ms(src: Path) -> int:
    out = _run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration"]
        + ["-of", "default=noprint_wrappers=1:nokey=1", str(src)]
    )
    try:
        return round(float(out.strip()) * 1000)
    except ValueError:
        raise AudioError(f"Could not read the duration of {src}.") from None


def cut_clip(src: Path, start_ms: int, end_ms: int, dest: Path) -> Path:
    if dest.exists():
        return dest
    if end_ms <= start_ms:
        raise AudioError(f"Empty audio range: {start_ms}-{end_ms} ms.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(f"{dest.stem}.part{dest.suffix}")
    try:
        _run(
            ["ffmpeg", "-y", "-loglevel", "error"]
            + ["-ss", f"{start_ms / 1000:.3f}", "-t", f"{(end_ms - start_ms) / 1000:.3f}"]
            + ["-i", str(src), "-vn", "-c:a", "copy", str(part)]
        )
    except AudioError:
        part.unlink(missing_ok=True)
        raise
    part.replace(dest)
    return dest
