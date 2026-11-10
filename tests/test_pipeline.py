import json
from pathlib import Path

import pytest

from earlights import audible, audio, deepgram
from earlights.audible import AudibleError
from earlights.config import Config, ConfigError
from earlights.deepgram import DeepgramAuthError, DeepgramError
from earlights.epub import EpubError
from earlights.models import BookFiles, BookInfo
from earlights.pipeline import Options, PipelineError, process_book
from earlights.state import load_state, save_state
from fixtures.make_epub import make_epub

ASIN = "B000FAKE01"
CONFIG = Config(deepgram_api_key="dg-key")


def record(id, start, type="audible.bookmark"):
    return {
        "type": type,
        "annotationId": id,
        "startPosition": str(start),
        "creationTime": "2026-01-01 10:00:00.0",
    }


def response(*words):
    items = [{"punctuated_word": w, "start": s, "end": e} for w, s, e in words]
    return {"results": {"channels": [{"alternatives": [{"words": items}]}]}}


SPEECH = response(
    ("Before.", 1.0, 1.5),
    ("Hello", 12.0, 12.5),
    ("there", 13.0, 13.5),
    ("world.", 14.0, 14.5),
    ("After.", 45.0, 45.5),
)


class Env:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.records = [record("m1", 60_000), record("m2", 300_000)]
        self.title = "Fake Book"
        self.language = "english"
        self.library_calls = 0
        self.cuts: list[tuple[int, int]] = []
        self.fetches: list[tuple[str, str, str, str]] = []
        self.fail_fetch: dict[int, Exception] = {}
        self.transcript = SPEECH
        self.transcripts: list[dict] = []
        self.reports: list[str] = []

    def info(self):
        return BookInfo(ASIN, self.title, ["Ann Author"], language=self.language)

    def list_library(self, profile=None):
        self.library_calls += 1
        return [self.info()]

    def get_book_info(self, asin, profile=None):
        if asin != ASIN:
            raise AudibleError("not in library")
        return self.info()

    def download_book(self, asin, dest, profile=None):
        annotations = None
        if self.records is not None:
            annotations = dest / f"{asin}-annotations.json"
            annotations.write_text(json.dumps({"payload": {"records": self.records}}))
        return BookFiles(audio=self.tmp_path / "book.m4b", annotations=annotations, chapters=None)

    def cut_clip(self, src, start_ms, end_ms, dest):
        if not dest.exists():
            self.cuts.append((start_ms, end_ms))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"clip")
        return dest

    def fetch_transcript(self, clip, language, api_key, model="nova-3", client=None):
        self.fetches.append((clip.name, language, api_key, model))
        error = self.fail_fetch.get(len(self.fetches))
        if error:
            raise error
        return self.transcripts.pop(0) if self.transcripts else self.transcript

    def run(self, query=ASIN, config=CONFIG, **options):
        options.setdefault("out", self.tmp_path / "out.md")
        return process_book(query, Options(**options), config, self.reports.append)


@pytest.fixture
def env(tmp_path, dirs, monkeypatch):
    env = Env(tmp_path)
    monkeypatch.setattr(audible, "list_library", env.list_library)
    monkeypatch.setattr(audible, "get_book_info", env.get_book_info)
    monkeypatch.setattr(audible, "download_book", env.download_book)
    monkeypatch.setattr(audio, "audio_duration_ms", lambda src: 600_000)
    monkeypatch.setattr(audio, "check_decodable", lambda src: None)
    monkeypatch.setattr(audio, "cut_clip", env.cut_clip)
    monkeypatch.setattr(deepgram, "fetch_transcript", env.fetch_transcript)
    return env


def test_process_writes_markdown_and_state(env):
    out = env.run()

    assert out == env.tmp_path / "out.md"
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Fake Book\n*Ann Author*\n\n## 00:01:00\n\n> Hello there world.\n")
    assert "## 00:05:00" in text
    assert env.cuts == [(35_000, 85_000), (275_000, 325_000)]
    assert [f[1:] for f in env.fetches] == [("en", "dg-key", "nova-3")] * 2
    passage = load_state(ASIN).passages["m1"]
    assert passage.text == "Hello there world."
    assert passage.transcript == "Before. Hello there world. After."
    assert (passage.source, passage.mode) == ("transcript", "transcript")
    assert env.library_calls == 0


def test_process_finds_book_by_title(env):
    assert env.run("fake") is not None
    assert env.library_calls == 1


def test_process_unknown_title(env):
    with pytest.raises(AudibleError):
        env.run("nothing like it")


def test_process_fails_fast_without_deepgram_key(env, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("no external call expected")

    monkeypatch.setattr(audible, "list_library", boom)
    monkeypatch.setattr(audible, "get_book_info", boom)
    monkeypatch.setattr(audible, "download_book", boom)
    with pytest.raises(ConfigError, match="DEEPGRAM_API_KEY"):
        env.run(config=Config())


def test_unimplemented_mode_fails_before_any_call(env, monkeypatch):
    monkeypatch.setattr(audible, "get_book_info", lambda *a, **k: 1 / 0)
    with pytest.raises(PipelineError, match="not implemented"):
        env.run(mode="ai")
    with pytest.raises(PipelineError, match="not implemented"):
        env.run(mode="auto")


def test_state_saved_per_marker(env):
    env.fail_fetch[2] = DeepgramError("boom")

    out = env.run()

    assert list(load_state(ASIN).passages) == ["m1"]
    assert "## 00:05:00" not in out.read_text()
    assert any("00:05:00" in r and "boom" in r for r in env.reports)
    assert any("1 marker failed" in r for r in env.reports)

    env.run()
    assert list(load_state(ASIN).passages) == ["m1", "m2"]
    assert len(env.fetches) == 3


def test_auth_error_stops_the_run(env):
    env.fail_fetch[1] = DeepgramAuthError("bad key")
    with pytest.raises(DeepgramAuthError):
        env.run()
    assert len(env.fetches) == 1


def test_process_skips_done_markers(env):
    env.run()
    env.run()
    assert len(env.fetches) == 2
    assert len(env.cuts) == 2


def test_process_force_reprocesses(env):
    env.run()
    state = load_state(ASIN)
    state.passages["m1"] = state.passages["m1"].__class__(
        marker_id="m1", text="stale", source="transcript", mode="transcript", transcript="stale"
    )
    save_state(state)

    env.run()
    assert load_state(ASIN).passages["m1"].text == "stale"

    env.run(force=True)
    assert load_state(ASIN).passages["m1"].text == "Hello there world."
    assert len(env.fetches) == 2


def test_new_marker_only_processes_the_new_one(env):
    env.run()
    env.records.append(record("m3", 400_000))
    out = env.run()
    assert len(env.fetches) == 3
    assert "## 00:06:40" in out.read_text()


def test_deleted_marker_removed_from_state(env):
    env.run()
    env.records.pop()
    out = env.run()
    assert list(load_state(ASIN).passages) == ["m1"]
    assert "## 00:05:00" not in out.read_text()


def test_empty_transcript_gives_none_passage(env):
    env.transcript = response()
    out = env.run()
    passage = load_state(ASIN).passages["m1"]
    assert (passage.text, passage.source) == ("", "none")
    assert "_(no speech detected)_" in out.read_text()


def test_language_override(env):
    env.run(language="pt-BR")
    assert env.fetches[0][1] == "pt-BR"


def test_language_change_transcribes_again(env):
    env.run()
    env.run(language="pt-BR", force=True)
    assert len(env.fetches) == 4


def test_no_bookmarks_returns_none(env):
    env.records = None
    assert env.run() is None
    env.records = []
    assert env.run() is None
    assert not (env.tmp_path / "out.md").exists()


def test_default_output_name_is_sanitized(env, monkeypatch):
    work = env.tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    env.title = 'Fake: Book / "One"?'
    out = env.run(out=None)
    assert out == Path("Fake Book One.md")
    assert (work / "Fake Book One.md").exists()


def test_marker_ids_are_safe_file_names(env):
    env.records = [record(None, 60_000)]
    env.run()
    names = [p.name for p in (env.tmp_path / "cache" / ASIN / "clips").iterdir()]
    assert names == ["audible.bookmark_60000-35000-85000.flac"]


def test_undecodable_audio_stops_before_any_clip(env, monkeypatch):
    def reject(src):
        raise audio.AudioError("xHE-AAC")

    monkeypatch.setattr(audio, "check_decodable", reject)
    with pytest.raises(audio.AudioError):
        env.run()
    assert env.cuts == []


def spoken(text, start, step=0.4):
    return [(w, start + i * step, start + i * step + 0.3) for i, w in enumerate(text.split())]


# Marker m1 is at 60 s and its clip starts at 35 s: the core is 10 s to 40 s of the clip.
STORM = response(
    *spoken("were the three words painted above the door. The Storm.", 2.0),
    *spoken(
        "On the 9th night of October the wind turned and the waves began to brake over "
        "the rocks. Nobody in the village had seen a storm like that since the old bridge "
        "was washed away.",
        12.0,
    ),
    *spoken("Light the lamp shouted the keeper. Nobody answered him because the boy", 42.0),
)


@pytest.fixture
def epub(tmp_path):
    return make_epub(tmp_path / "book.epub")


def test_epub_mode_uses_the_book_text(env, epub):
    env.records = [record("m1", 60_000)]
    env.transcript = STORM

    out = env.run(epub=epub)

    state = load_state(ASIN)
    passage = state.passages["m1"]
    assert (passage.source, passage.mode) == ("epub", "epub")
    assert passage.text.startswith("On the ninth night of October the wind turned")
    assert passage.text.endswith("the old bridge was washed away.")
    assert "9th" in passage.transcript
    assert state.epub_path == str(epub.resolve())
    assert "<sub>source: epub</sub>" in out.read_text()
    assert "1/1 found in EPUB" in env.reports


def test_pipeline_epub_fallback_to_transcript(env, epub):
    env.transcripts = [STORM, SPEECH]

    out = env.run(mode="epub", epub=epub)

    passages = load_state(ASIN).passages
    assert passages["m1"].source == "epub"
    assert (passages["m2"].source, passages["m2"].mode) == ("transcript", "epub")
    assert passages["m2"].text == "Hello there world."
    assert any("00:05:00" in r and "not found in the EPUB" in r for r in env.reports)
    assert "1/2 found in EPUB" in env.reports
    assert "<sub>source: transcript</sub>" in out.read_text()


def test_epub_is_remembered_and_reprocesses_transcript_passages(env, epub):
    env.records = [record("m1", 60_000)]
    env.transcript = STORM
    env.run()
    assert load_state(ASIN).passages["m1"].source == "transcript"

    env.run(epub=epub, mode="transcript")
    assert load_state(ASIN).passages["m1"].source == "transcript"

    env.run()
    assert load_state(ASIN).passages["m1"].source == "epub"
    assert len(env.fetches) == 1


def test_new_epub_reprocesses_everything(env, epub, tmp_path):
    env.records = [record("m1", 60_000)]
    env.transcript = STORM
    unrelated = "<html><body><p>Unrelated words.</p></body></html>"
    other = make_epub(tmp_path / "other.epub", [unrelated])
    env.run(epub=other)
    assert load_state(ASIN).passages["m1"].source == "transcript"

    env.run(epub=epub)
    assert load_state(ASIN).passages["m1"].source == "epub"


def test_epub_mode_without_epub(env):
    with pytest.raises(PipelineError, match="--epub"):
        env.run(mode="epub")
    assert env.fetches == []


def test_bad_epub_fails_before_the_download(env, tmp_path, monkeypatch):
    monkeypatch.setattr(audible, "download_book", lambda *a, **k: 1 / 0)
    bad = tmp_path / "bad.epub"
    bad.write_text("nope")
    with pytest.raises(EpubError):
        env.run(epub=bad)
    with pytest.raises(EpubError):
        env.run(epub=tmp_path / "missing.epub")


def test_no_speech_marker_stays_none_in_epub_mode(env, epub):
    env.transcript = response()
    env.run(epub=epub)
    assert load_state(ASIN).passages["m1"].source == "none"
    assert "0/2 found in EPUB" in env.reports
