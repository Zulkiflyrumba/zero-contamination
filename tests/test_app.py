from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_app_boots(tmp_path, monkeypatch):
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "a.db"))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception
