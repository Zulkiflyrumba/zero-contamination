from pathlib import Path

import pytest
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


def test_forced_password_change_then_admin_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "c.db"))
    monkeypatch.delenv("CT_USER", raising=False)
    monkeypatch.delenv("CT_PASS", raising=False)
    st.cache_resource.clear()
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.text_input[0].set_value("qc")
    at.text_input[1].set_value("123")
    at.button[0].click().run()
    assert at.session_state["ct_user"]["must_change"] and not at.exception
    assert any("password awal" in w.value for w in at.warning)
    at.text_input[0].set_value("123")
    at.text_input[1].set_value("kuat12345")
    at.text_input[2].set_value("kuat12345")
    at.button[0].click().run()
    assert not at.session_state["ct_user"]["must_change"] and not at.exception
    for page in ("views/users.py", "views/catalog.py", "views/cases.py"):
        at.switch_page(page).run()
        assert not at.exception, page


def test_viewer_blocked_from_admin_pages(tmp_path, monkeypatch):
    from core import users

    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "d.db"))
    st.cache_resource.clear()
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    users.create_user("tamu", "Tamu", "viewer", "rahasia123")
    users.set_password("tamu", "rahasia123", must_change=False)
    at.text_input[0].set_value("tamu")
    at.text_input[1].set_value("rahasia123")
    at.button[0].click().run()
    assert at.session_state["ct_user"]["role"] == "viewer"
    for page in ("views/catalog.py", "views/users.py", "views/cases.py"):  # pages are not even registered for a viewer
        with pytest.raises(ValueError):
            at.switch_page(page)
    # defence in depth: opening the page script directly is refused too
    page = AppTest.from_file(str(ROOT / "views" / "catalog.py"), default_timeout=60)
    page.session_state["ct_user"] = {"username": "tamu", "name": "Tamu", "role": "viewer", "must_change": False}
    page.run()
    assert any("tidak memiliki akses" in e.value for e in page.error)
