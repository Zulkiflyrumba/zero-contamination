"""Contamination Tracker - Streamlit entry point.

Run locally:   streamlit run app.py
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import auth, db, theme

st.set_page_config(page_title="Contamination Tracker", page_icon="🛠️", layout="wide")


@st.cache_resource
def _init() -> bool:
    db.init_db()
    return True


_init()
theme.inject()

if not auth.logged_in():
    auth.login_view()
    st.stop()

pages = [
    st.Page("views/tracker.py", title="Tracker", icon=":material/search:", default=True),
    st.Page("views/parts3d.py", title="Galeri part 3D", icon=":material/view_in_ar:"),
    st.Page("views/catalog.py", title="Katalog", icon=":material/inventory_2:"),
    st.Page("views/cases.py", title="Inspeksi & Kasus", icon=":material/fact_check:"),
    st.Page("views/about.py", title="Tentang", icon=":material/info:"),
]
with st.sidebar:
    if st.button("Keluar", icon=":material/logout:", use_container_width=True):
        auth.logout()
        st.rerun()
st.navigation(pages).run()
