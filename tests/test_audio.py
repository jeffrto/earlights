import shutil
import subprocess
from datetime import datetime

import pytest

from earlights import audio
from earlights.audio import (
    AudioError,
    audio_duration_ms,
    check_decodable,
    cut_clip,
    marker_window,
)
from earlights.models import Marker

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def make_marker(start_ms, end_ms=None):
    kind = "clip" if end_ms is not None else "bookmark"
    return Marker(
        id="m1",
        kind=kind,
        start_ms=start_ms,
        end_ms=end_ms,
        note=None,
        created=datetime(2026, 1, 1),
    )


@pytest.fixture
def sine(tmp_path):
    path = tmp_path / "sine.m4a"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi"]
        + ["-i", "sine=frequency=440:duration=60", "-c:a", "aac", str(path)],
        check=True,
    )
    return path


def test_window_bookmark():
    window = marker_window(make_marker(60_000), 600_000)
    assert (window.core_start_ms, window.core_end_ms) == (45_000, 75_000)
    assert (window.start_ms, window.end_ms) == (35_000, 85_000)


def test_window_clip_uses_own_range():
    window = marker_window(make_marker(100_000, 140_000), 600_000)
    assert (window.core_start_ms, window.core_end_ms) == (100_000, 140_000)
    assert (window.start_ms, window.end_ms) == (90_000, 150_000)


def test_window_clamped_to_book_bounds():
    start = marker_window(make_marker(5_000), 600_000)
    assert (start.core_start_ms, start.start_ms) == (0, 0)
    end = marker_window(make_marker(595_000), 600_000)
    assert (end.core_end_ms, end.end_ms) == (600_000, 600_000)


def test_window_without_runtime_is_not_clamped_at_the_end():
    window = marker_window(make_marker(595_000), None)
    assert window.end_ms == 620_000


def test_window_marker_past_the_end_stays_inside_the_book():
    window = marker_window(make_marker(650_000), 600_000)
    assert window.start_ms < window.end_ms == 600_000


@needs_ffmpeg
def test_audio_duration(sine):
    assert audio_duration_ms(sine) == pytest.approx(60_000, abs=500)


@needs_ffmpeg
def test_cut_clip_duration(sine, tmp_path):
    dest = cut_clip(sine, 10_000, 20_000, tmp_path / "clips" / "clip.flac")
    assert dest.exists()
    assert audio_duration_ms(dest) == pytest.approx(10_000, abs=500)


def probe(path, entries):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", entries, "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split()


@needs_ffmpeg
def test_cut_clip_is_reencoded_to_mono_flac(sine, tmp_path):
    dest = cut_clip(sine, 10_000, 20_000, tmp_path / "clip.flac")
    assert probe(dest, "stream=codec_name,channels") == ["flac,1"]


@needs_ffmpeg
def test_check_decodable_accepts_plain_aac(sine):
    check_decodable(sine)


def test_check_decodable_rejects_xhe_aac(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "_run", lambda args: "xHE-AAC\n")
    with pytest.raises(AudioError, match="xHE-AAC"):
        check_decodable(tmp_path / "book.m4b")


@needs_ffmpeg
def test_cut_clip_cached(sine, tmp_path, monkeypatch):
    dest = cut_clip(sine, 10_000, 20_000, tmp_path / "clip.flac")

    def fail(*args, **kwargs):
        raise AssertionError("ffmpeg should not run again")

    monkeypatch.setattr(audio.subprocess, "run", fail)
    assert cut_clip(sine, 10_000, 20_000, dest) == dest


@needs_ffmpeg
def test_cut_clip_failure_leaves_no_file(tmp_path):
    dest = tmp_path / "clip.flac"
    with pytest.raises(AudioError):
        cut_clip(tmp_path / "missing.m4b", 0, 1_000, dest)
    assert not dest.exists()


def test_cut_clip_rejects_empty_range(tmp_path):
    with pytest.raises(AudioError):
        cut_clip(tmp_path / "a.m4b", 5_000, 5_000, tmp_path / "clip.flac")


def test_missing_ffmpeg(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(audio.subprocess, "run", missing)
    with pytest.raises(AudioError, match="ffmpeg"):
        cut_clip(tmp_path / "a.m4b", 0, 1_000, tmp_path / "clip.flac")
