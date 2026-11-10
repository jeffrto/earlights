import pytest
from click.testing import CliRunner

from earlights import cli
from earlights.audible import AudibleError
from earlights.cli import main
from earlights.config import Config, ConfigError
from earlights.models import BookInfo
from earlights.pipeline import Options


def test_version():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "earlights" in result.output


def test_library_lists_books(monkeypatch):
    books = [BookInfo("B000FAKE01", "A Fake Book", ["Ann Author", "Bob Writer"])]
    seen = {}

    def fake_list(profile=None):
        seen["profile"] = profile
        return books

    monkeypatch.setattr("earlights.cli.list_library", fake_list)
    result = CliRunner().invoke(main, ["library", "--profile", "work"])
    assert result.exit_code == 0
    assert result.output == "B000FAKE01  A Fake Book — Ann Author, Bob Writer\n"
    assert seen["profile"] == "work"


def test_library_error_exits_1(monkeypatch):
    def boom(profile=None):
        raise AudibleError("auth expired")

    monkeypatch.setattr("earlights.cli.list_library", boom)
    result = CliRunner().invoke(main, ["library"])
    assert result.exit_code == 1
    assert "auth expired" in result.output


def test_process_passes_options(monkeypatch, tmp_path):
    seen = {}

    def fake(query, options, config, report):
        seen.update(query=query, options=options)
        report("working")
        return tmp_path / "book.md"

    monkeypatch.setattr(cli, "process_book", fake)
    monkeypatch.setattr(cli, "load_config", lambda: Config(deepgram_api_key="k"))
    result = CliRunner().invoke(
        main, ["process", "my book", "--lang", "pt-BR", "--force", "--out", str(tmp_path / "o.md")]
    )
    assert result.exit_code == 0
    assert "working" in result.output
    assert str(tmp_path / "book.md") in result.output
    assert seen["query"] == "my book"
    assert seen["options"] == Options(language="pt-BR", force=True, out=tmp_path / "o.md")


@pytest.mark.parametrize(
    "args", [["--mode", "epub"], ["--mode", "auto"], ["--epub", "x.epub"], ["--readwise"]]
)
def test_process_unimplemented_options(args, monkeypatch):
    monkeypatch.setattr(cli, "process_book", lambda *a, **k: 1 / 0)
    result = CliRunner().invoke(main, ["process", "book", *args])
    assert result.exit_code == 2
    assert "not implemented yet" in result.output


def test_process_reports_errors(monkeypatch):
    def fake(*args, **kwargs):
        raise ConfigError("Missing DEEPGRAM_API_KEY.")

    monkeypatch.setattr(cli, "process_book", fake)
    monkeypatch.setattr(cli, "load_config", lambda: Config())
    result = CliRunner().invoke(main, ["process", "book"])
    assert result.exit_code == 1
    assert "Error: Missing DEEPGRAM_API_KEY." in result.output


def test_process_without_bookmarks(monkeypatch):
    monkeypatch.setattr(cli, "process_book", lambda *a, **k: None)
    monkeypatch.setattr(cli, "load_config", lambda: Config())
    result = CliRunner().invoke(main, ["process", "book"])
    assert result.exit_code == 0
