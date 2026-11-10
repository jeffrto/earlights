from click.testing import CliRunner

from earlights.cli import main


def test_version():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "earlights" in result.output
