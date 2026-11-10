from click.testing import CliRunner

from earlights.audible import AudibleError
from earlights.cli import main
from earlights.models import BookInfo


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
