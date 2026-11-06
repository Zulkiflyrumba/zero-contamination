"""Contamination Tracker - Streamlit entry point.

Run locally:   streamlit run app.py
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import db, theme

st.set_page_config(page_title="Contamination Tracker", page_icon="", layout="wide")


@st.cache_resource
def _init() -> bool:
    db.init_db()
    return True


_init()
theme.inject()

pages = [
    st.Page("views/tracker.py", title="Tracker", icon=":material/search:", default=True),
    st.Page("views/catalog.py", title="Katalog", icon=":material/inventory_2:"),
    st.Page("views/cases.py", title="Inspeksi & Kasus", icon=":material/fact_check:"),
    st.Page("views/about.py", title="Tentang", icon=":material/info:"),
]
st.navigation(pages).run()
