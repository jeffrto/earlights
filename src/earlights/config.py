import os
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path

from platformdirs import user_config_dir

ENV_VARS = {
    "deepgram_api_key": "DEEPGRAM_API_KEY",
    "gemini_api_key": "GEMINI_API_KEY",
    "readwise_token": "READWISE_TOKEN",
}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    deepgram_api_key: str | None = None
    gemini_api_key: str | None = None
    readwise_token: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    deepgram_model: str = "nova-3"


def default_path() -> Path:
    return Path(user_config_dir("earlights")) / "config.toml"


def load_config(path: Path | None = None) -> Config:
    path = path or default_path()
    values: dict[str, str] = {}
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            raise ConfigError(f"Could not read {path}: {exc}") from None
        for field in fields(Config):
            value = data.get(field.name)
            if isinstance(value, str) and value.strip():
                values[field.name] = value.strip()
    for name, env in ENV_VARS.items():
        value = os.environ.get(env, "").strip()
        if value:
            values[name] = value
    return replace(Config(), **values)


def require(config: Config, field: str) -> str:
    value = getattr(config, field)
    if not value:
        env = ENV_VARS[field]
        raise ConfigError(
            f"Missing {env}. Set the environment variable or add {field} to {default_path()}."
        )
    return value
