import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import db


@pytest.fixture()
def dbp(tmp_path, monkeypatch):
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(db, "PHOTO_DIR", tmp_path / "photos")
    db.init_db()
    return tmp_path / "t.db"
