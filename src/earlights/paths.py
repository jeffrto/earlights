from pathlib import Path

from platformdirs import user_cache_dir, user_data_dir

APP = "earlights"


def cache_dir(asin: str) -> Path:
    return _ensure(Path(user_cache_dir(APP)) / asin)


def data_dir(asin: str) -> Path:
    return _ensure(Path(user_data_dir(APP)) / asin)


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
