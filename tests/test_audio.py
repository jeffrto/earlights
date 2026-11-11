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
    merge_overlapping,
)
from earlights.models import Marker

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def make_marker(start_ms, end_ms=None, id="m1", note=None, created=datetime(2026, 1, 1)):
    kind = "clip" if end_ms is not None else "bookmark"
    return Marker(id=id, kind=kind, start_ms=start_ms, end_ms=end_ms, note=note, created=created)


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


def test_merge_keeps_separate_markers_untouched():
    markers = [make_marker(60_000, id="a"), make_marker(300_000, id="b")]
    assert merge_overlapping(markers, 600_000) == markers


def test_merge_clip_and_bookmark_at_the_same_position():
    clip = make_marker(100_000, 130_000, id="clip", created=datetime(2026, 1, 2))
    bookmark = make_marker(100_000, id="mark", created=datetime(2026, 1, 1))

    [merged] = merge_overlapping([clip, bookmark], 600_000)

    assert (merged.kind, merged.start_ms, merged.end_ms) == ("clip", 85_000, 130_000)
    assert merged.created == datetime(2026, 1, 1)
    window = marker_window(merged, 600_000)
    assert (window.core_start_ms, window.core_end_ms) == (85_000, 130_000)


def test_merge_chains_markers_and_stops_at_a_gap():
    markers = [
        make_marker(100_000, id="a"),
        make_marker(120_000, id="b"),
        make_marker(145_000, id="c"),
        make_marker(200_000, id="d"),
    ]

    merged = merge_overlapping(markers, 600_000)

    assert [(m.start_ms, m.end_ms) for m in merged] == [(85_000, 160_000), (200_000, None)]
    assert merged[1] == markers[3]


def test_merge_joins_notes_without_repeating():
    markers = [
        make_marker(100_000, id="a", note="first"),
        make_marker(105_000, id="b"),
        make_marker(110_000, id="c", note="second"),
        make_marker(112_000, id="d", note="first"),
    ]

    [merged] = merge_overlapping(markers, 600_000)

    assert merged.note == "first\n\nsecond"


def test_merged_id_changes_when_the_group_changes():
    a, b, c = (make_marker(100_000 + i * 5_000, id=name) for i, name in enumerate("abc"))

    [two] = merge_overlapping([a, b], 600_000)
    [three] = merge_overlapping([a, b, c], 600_000)
    [again] = merge_overlapping([b, a], 600_000)

    assert two.id.startswith("a+")
    assert two.id != three.id
    assert two.id == again.id
