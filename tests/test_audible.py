import json
import subprocess
from pathlib import Path

import pytest

from earlights import audible
from earlights.audible import AudibleError, download_book, find_book, get_book_info, list_library
from earlights.models import BookInfo

ASIN = "B000FAKE01"
FIXTURES = Path(__file__).parent / "fixtures"


class FakeRun:
    def __init__(self, handler=None, returncode=0, stdout="", stderr=""):
        self.calls: list[list[str]] = []
        self.handler = handler
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self.handler:
            self.handler(cmd)
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, self.stderr)


def fake_download(cmd):
    dest = Path(cmd[cmd.index("-o") + 1])
    if "--aaxc" in cmd:
        (dest / f"{ASIN}-AAX_44_128.aaxc").write_bytes(b"audio")
        (dest / f"{ASIN}-AAX_44_128.voucher").write_text((FIXTURES / "voucher.json").read_text())
    (dest / f"{ASIN}-annotations.json").write_text('{"fresh": true}')
    (dest / f"{ASIN}-chapters.json").write_text("{}")


def test_download_book_command_and_files(tmp_path, monkeypatch):
    run = FakeRun(fake_download)
    monkeypatch.setattr(subprocess, "run", run)

    files = download_book(ASIN, tmp_path, profile="work")

    assert run.calls == [
        [
            "audible", "-P", "work", "download", "-a", ASIN, "--aaxc",
            "--annotation", "--chapter", "--chapter-type", "flat",
            "-o", str(tmp_path), "-f", "asin_only", "-y", "--no-progress",
        ]
    ]  # fmt: skip
    assert files.audio == tmp_path / f"{ASIN}-AAX_44_128.aaxc"
    assert files.key == "00112233445566778899aabbccddeeff"
    assert files.iv == "ffeeddccbbaa99887766554433221100"
    assert files.annotations == tmp_path / f"{ASIN}-annotations.json"
    assert files.chapters == tmp_path / f"{ASIN}-chapters.json"


def test_download_skips_audio_when_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", FakeRun(fake_download))
    download_book(ASIN, tmp_path)
    (tmp_path / f"{ASIN}-annotations.json").write_text('{"fresh": false}')

    run = FakeRun(fake_download)
    monkeypatch.setattr(subprocess, "run", run)
    files = download_book(ASIN, tmp_path)

    assert len(run.calls) == 1
    assert "--aaxc" not in run.calls[0]
    assert "--annotation" in run.calls[0]
    assert files.audio.read_bytes() == b"audio"
    assert json.loads(files.annotations.read_text()) == {"fresh": True}


def test_download_without_annotations_file(tmp_path, monkeypatch):
    def handler(cmd):
        fake_download(cmd)
        (tmp_path / f"{ASIN}-annotations.json").unlink()

    monkeypatch.setattr(subprocess, "run", FakeRun(handler))
    assert download_book(ASIN, tmp_path).annotations is None


def test_download_raises_when_audio_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", FakeRun(stdout="nothing to download"))
    with pytest.raises(AudibleError, match="nothing to download"):
        download_book(ASIN, tmp_path)


def test_audible_error_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(subprocess, "run", FakeRun(returncode=1, stderr="auth expired\n"))
    with pytest.raises(AudibleError, match="auth expired"):
        list_library()


def test_audible_error_when_binary_missing(monkeypatch):
    def missing(cmd, **kwargs):
        raise FileNotFoundError("audible")

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(AudibleError, match="audible-cli not found"):
        list_library()


def test_list_library_parses_export(monkeypatch):
    def handler(cmd):
        out = Path(cmd[cmd.index("-o") + 1])
        out.write_text(
            json.dumps(
                [
                    {
                        "asin": ASIN,
                        "title": "A Fake Book",
                        "authors": "Ann Author, Bob Writer",
                        "runtime_length_min": 5,
                    },
                    {"asin": "B000FAKE02", "title": "Other", "authors": None},
                ]
            )
        )

    run = FakeRun(handler)
    monkeypatch.setattr(subprocess, "run", run)

    books = list_library()

    assert run.calls[0][:5] == ["audible", "library", "export", "-f", "json"]
    assert books[0] == BookInfo(ASIN, "A Fake Book", ["Ann Author", "Bob Writer"], None, 300000)
    assert books[1].authors == []
    assert books[1].runtime_ms is None


def test_get_book_info(monkeypatch):
    payload = {
        "item": {
            "asin": ASIN,
            "title": "A Fake Book",
            "authors": [{"name": "Ann Author"}, {"name": "Bob Writer"}],
            "language": "english",
            "runtime_length_min": 5,
        }
    }
    run = FakeRun(stdout=json.dumps(payload))
    monkeypatch.setattr(subprocess, "run", run)

    info = get_book_info(ASIN)

    assert run.calls == [
        [
            "audible", "api", f"1.0/library/{ASIN}",
            "-p", "response_groups=product_attrs,contributors,media",
        ]
    ]  # fmt: skip
    assert info == BookInfo(ASIN, "A Fake Book", ["Ann Author", "Bob Writer"], "english", 300000)


LIBRARY = [
    BookInfo("B000FAKE01", "The Long Road", ["A"]),
    BookInfo("B000FAKE02", "The Long Road Home", ["B"]),
    BookInfo("B000FAKE03", "Short Stories", ["C"]),
]


def test_find_book_by_asin_and_partial_title():
    assert find_book("b000fake02", LIBRARY).asin == "B000FAKE02"
    assert find_book("short", LIBRARY).asin == "B000FAKE03"
    assert find_book("the long road", LIBRARY).asin == "B000FAKE01"


def test_find_book_ambiguous_raises():
    with pytest.raises(AudibleError, match="(?s)B000FAKE01.*B000FAKE02"):
        find_book("long", LIBRARY)


def test_find_book_not_found_raises():
    with pytest.raises(AudibleError, match="No book"):
        find_book("missing", LIBRARY)


def test_module_never_imports_audible_cli():
    assert "audible_cli" not in Path(audible.__file__).read_text()
