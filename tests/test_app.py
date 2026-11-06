from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_app_boots(tmp_path, monkeypatch):
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "a.db"))
    st.cache_resource.clear()
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception


def test_login_gate_and_login(tmp_path, monkeypatch):
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "b.db"))
    monkeypatch.delenv("CT_USER", raising=False)
    monkeypatch.delenv("CT_PASS", raising=False)
    st.cache_resource.clear()
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception and len(at.text_input) == 2
    at.text_input[0].set_value("qc")
    at.text_input[1].set_value("salah")
    at.button[0].click().run()
    assert at.error
    at.text_input[1].set_value("123")
    at.button[0].click().run()
    assert at.session_state["ct_auth"] is True and not at.exception
