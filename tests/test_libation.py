import subprocess

import pytest

from earlights import libation
from earlights.libation import LibationError, books_dir, find_audio, liberate

ASIN = "B000FAKE01"


class FakeRun:
    def __init__(self, handler=None, returncode=0, stdout="", stderr=""):
        self.calls = []
        self.kwargs = []
        self.handler = handler
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        self.kwargs.append(kwargs)
        stdout = self.handler(cmd) if self.handler else None
        return subprocess.CompletedProcess(cmd, self.returncode, stdout or self.stdout, self.stderr)


def make_book(books, name=f"A Fake Book [{ASIN}]", suffix=".m4b"):
    folder = books / f"A Fake Book [{ASIN}]"
    folder.mkdir(parents=True, exist_ok=True)
    audio = folder / f"{name}{suffix}"
    audio.write_bytes(b"audio")
    (folder / f"A Fake Book [{ASIN}].json").write_text("{}")
    return audio


def test_books_dir_parses_setting(monkeypatch):
    run = FakeRun(stdout='LibationCli v14\nBooks="/data/My Books"\n')
    monkeypatch.setattr(subprocess, "run", run)
    assert str(books_dir()) == "/data/My Books"
    assert run.calls == [["libationcli", "get-setting", "-b", "Books"]]
    assert run.kwargs[0]["stdin"] == subprocess.DEVNULL


def test_books_dir_unparseable_raises(monkeypatch):
    monkeypatch.setattr(subprocess, "run", FakeRun(stdout="nothing here"))
    with pytest.raises(LibationError, match="books folder"):
        books_dir()


def test_find_audio_by_asin(tmp_path):
    audio = make_book(tmp_path)
    other = tmp_path / "Other [B000FAKE02]"
    other.mkdir()
    (other / "Other [B000FAKE02].m4b").write_bytes(b"x")
    assert find_audio(ASIN, tmp_path) == audio
    assert find_audio("B000FAKE03", tmp_path) is None
    assert find_audio(ASIN, tmp_path / "missing") is None


def test_find_audio_split_files_raises(tmp_path):
    make_book(tmp_path, name=f"A Fake Book [{ASIN}] - 01 - One")
    make_book(tmp_path, name=f"A Fake Book [{ASIN}] - 02 - Two")
    with pytest.raises(LibationError, match="more than one"):
        find_audio(ASIN, tmp_path)


def test_liberate_runs_command_and_returns_file(tmp_path, monkeypatch):
    def handler(cmd):
        if cmd[1] == "get-setting":
            return f'Books="{tmp_path}"\n'
        make_book(tmp_path)

    run = FakeRun(handler)
    monkeypatch.setattr(subprocess, "run", run)

    audio = liberate(ASIN)

    assert ["libationcli", "liberate", ASIN] in run.calls
    assert audio == tmp_path / f"A Fake Book [{ASIN}]" / f"A Fake Book [{ASIN}].m4b"


def test_liberate_without_file_raises(tmp_path, monkeypatch):
    def handler(cmd):
        return f'Books="{tmp_path}"\n' if cmd[1] == "get-setting" else "some failure text"

    monkeypatch.setattr(subprocess, "run", FakeRun(handler))
    with pytest.raises(LibationError, match="some failure text"):
        liberate(ASIN)


def test_libation_error_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(subprocess, "run", FakeRun(returncode=1, stderr="boom"))
    with pytest.raises(LibationError, match="boom"):
        books_dir()


def test_libation_error_when_binary_missing(monkeypatch):
    def missing(cmd, **kwargs):
        raise FileNotFoundError("libationcli")

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(LibationError, match="libationcli not found"):
        books_dir()


def test_available(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert libation.available() is False
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/libationcli")
    assert libation.available() is True
