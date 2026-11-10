import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def load(name: str) -> dict:
        return json.loads((FIXTURES / name).read_text())

    return load


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    from earlights import paths

    monkeypatch.setattr(paths, "user_cache_dir", lambda app: str(tmp_path / "cache"))
    monkeypatch.setattr(paths, "user_data_dir", lambda app: str(tmp_path / "data"))
    return tmp_path
