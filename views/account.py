"""Own account: change password (forced when the password is still the default one)."""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import auth, theme, users

me = auth.current()
theme.hero("Akun saya", "Ganti password dan lihat peran Anda.")
if me.get("must_change"):
    st.warning("Password Anda masih password awal. Ganti dulu sebelum memakai aplikasi.")
st.write(f'**{me.get("name")}** · username `{me.get("username")}` · peran **{users.ROLE_LABEL.get(me.get("role"), "")}**')
with st.form("chpw", border=True):
    old = st.text_input("Password sekarang", type="password")
    new = st.text_input("Password baru", type="password", help=f"Minimal {users.MIN_LEN} karakter, gabungan huruf dan angka.")
    new2 = st.text_input("Ulangi password baru", type="password")
    go = st.form_submit_button("Simpan password", type="primary")
if go:
    u, _ = users.authenticate(me["username"], old)
    if not u:
        st.error("Password sekarang salah.")
    elif new != new2:
        st.error("Password baru dan ulangannya tidak sama.")
    elif old == new:
        st.error("Password baru harus berbeda dari yang lama.")
    else:
        try:
            users.set_password(me["username"], new, must_change=False, by=me["username"])
        except ValueError as e:
            st.error(str(e))
        else:
            st.session_state["ct_user"] = {**me, "must_change": False}
            st.success("Password diganti.")
            st.rerun()
