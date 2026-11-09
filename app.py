"""Contamination Tracker - Streamlit entry point.

Run locally:   streamlit run app.py
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import auth, db, theme, users

st.set_page_config(page_title="Contamination Tracker", page_icon="🛠️", layout="wide")


@st.cache_resource
def _init() -> bool:
    db.init_db()
    users.ensure_admin()
    return True


_init()
theme.inject()

if not auth.logged_in():
    auth.login_view()
    st.stop()

me = auth.current()
account = st.Page("views/account.py", title="Akun saya", icon=":material/manage_accounts:", url_path="akun")
if me.get("must_change"):  # forced password change before anything else
    st.navigation([account]).run()
    st.stop()

catalog_pages = {
    "tracker": st.Page("views/tracker.py", title="Tracker", icon=":material/search:", default=True),
    "parts3d": st.Page("views/parts3d.py", title="Galeri part 3D", icon=":material/view_in_ar:"),
    "catalog": st.Page("views/catalog.py", title="Katalog", icon=":material/inventory_2:"),
    "cases": st.Page("views/cases.py", title="Inspeksi & Kasus", icon=":material/fact_check:"),
    "users": st.Page("views/users.py", title="Pengguna", icon=":material/group:"),
    "about": st.Page("views/about.py", title="Tentang", icon=":material/info:"),
}
pages = [p for k, p in catalog_pages.items() if users.can(me.get("role", ""), k)] + [account]
with st.sidebar:
    st.caption(f'{me.get("name", "")} · {users.ROLE_LABEL.get(me.get("role", ""), "")}')
    if st.button("Keluar", icon=":material/logout:", use_container_width=True):
        auth.logout()
        st.rerun()
st.navigation(pages).run()
