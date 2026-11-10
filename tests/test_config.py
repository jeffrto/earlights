import pytest

from earlights.config import Config, ConfigError, load_config, require

ENV = ("DEEPGRAM_API_KEY", "GEMINI_API_KEY", "READWISE_TOKEN")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


def test_missing_file_gives_defaults(tmp_path):
    config = load_config(tmp_path / "nope.toml")
    assert config.deepgram_api_key is None
    assert config.deepgram_model == "nova-3"


def test_reads_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('deepgram_api_key = "from-file"\ndeepgram_model = "nova-2"\n')
    config = load_config(path)
    assert config.deepgram_api_key == "from-file"
    assert config.deepgram_model == "nova-2"


def test_env_overrides_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('deepgram_api_key = "from-file"\nreadwise_token = "rw-file"\n')
    monkeypatch.setenv("DEEPGRAM_API_KEY", "from-env")
    config = load_config(path)
    assert config.deepgram_api_key == "from-env"
    assert config.readwise_token == "rw-file"


def test_empty_values_count_as_missing(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('gemini_api_key = ""\n')
    monkeypatch.setenv("DEEPGRAM_API_KEY", " ")
    config = load_config(path)
    assert config.gemini_api_key is None
    assert config.deepgram_api_key is None


def test_invalid_toml_raises(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("deepgram_api_key = \n")
    with pytest.raises(ConfigError, match="config.toml"):
        load_config(path)


def test_require_missing_raises():
    with pytest.raises(ConfigError, match="DEEPGRAM_API_KEY"):
        require(Config(), "deepgram_api_key")


def test_require_returns_value():
    assert require(Config(readwise_token="t"), "readwise_token") == "t"
