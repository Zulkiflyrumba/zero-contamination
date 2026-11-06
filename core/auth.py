"""Simple login gate. Default demo account: qc / 123.

Change it with the environment variables CT_USER and CT_PASS (or Streamlit secrets of the same name).
This is a lightweight gate for an internal tool, not a replacement for real authentication.
"""
import base64
import contextlib
import hmac
import os
from pathlib import Path

import streamlit as st

LOGO = Path(__file__).resolve().parents[1] / "assets" / "logo.png"

CSS = """
<style>
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stToolbar"]{display:none!important}
.st-key-lg{max-width:880px;margin:7vh auto 0;background:#fff;border-radius:26px;box-shadow:0 24px 60px rgba(40,80,62,.18);overflow:hidden;padding:0!important;border:0!important}
.st-key-lg>div,.st-key-lg [data-testid="stHorizontalBlock"]{gap:0!important}
.st-key-lg [data-testid="stColumn"]{padding:0!important}
.lg-left{position:relative;overflow:hidden;min-height:500px;color:#fff;padding:34px;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;gap:8px;
 background:linear-gradient(150deg,#46b08a 0%,#2f9a73 45%,#1f6f55 100%)}
.lg-left::before{content:"";position:absolute;width:70px;height:70px;right:-14px;top:70px;background:rgba(255,255,255,.12);transform:rotate(45deg);border-radius:10px}
.lg-left::after{content:"";position:absolute;left:-60px;bottom:-60px;width:220px;height:220px;border-radius:50%;background:rgba(255,255,255,.09)}
.lg-logo{position:absolute;left:26px;top:24px;width:112px;height:32px;background:var(--logo) left center/contain no-repeat}
.lg-left h2{font:700 30px/1.15 'Plus Jakarta Sans',sans-serif;margin:0;color:#fff;padding:0}
.lg-left p{margin:0;color:rgba(255,255,255,.86);font-size:13.5px;max-width:260px}
.st-key-lgform{padding:44px 46px;min-height:500px;display:flex;flex-direction:column;justify-content:center}
.st-key-lgform h1{font-size:26px;color:#2f9a73;padding:0;margin:0 0 4px}
.st-key-lgform [data-testid="stFormSubmitButton"] button{width:100%;min-height:50px;letter-spacing:.1em;text-transform:uppercase;font-size:13px;background:#2f9a73;color:#fff;box-shadow:0 8px 20px rgba(47,154,115,.3)}
.st-key-lgform input{min-height:46px}
@media (max-width:760px){.lg-left{min-height:0;padding:70px 24px 28px}.lg-left h2{font-size:24px}.st-key-lgform{padding:26px 24px 30px;min-height:0}.st-key-lg{margin-top:3vh}}
</style>
"""


def _creds() -> tuple[str, str]:
    user = os.environ.get("CT_USER")
    pw = os.environ.get("CT_PASS")
    with contextlib.suppress(Exception):  # no secrets file
        user = user or st.secrets.get("CT_USER")
        pw = pw or st.secrets.get("CT_PASS")
    return user or "qc", pw or "123"


def _logo_uri() -> str:
    return "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode() if LOGO.exists() else ""


def logged_in() -> bool:
    return bool(st.session_state.get("ct_auth"))


def logout() -> None:
    st.session_state.pop("ct_auth", None)


def login_view() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    with st.container(key="lg"):
        left, right = st.columns(2, gap="small")
        with left:
            st.markdown(
                f'<div class="lg-left" style="--logo:url({_logo_uri()})"><div class="lg-logo"></div>'
                "<h2>Selamat datang</h2><p>Contamination Tracker. Telusuri sumber kontaminan di PIT dan ROM dari foto temuan.</p></div>",
                unsafe_allow_html=True,
            )
        with right, st.container(key="lgform"):
            st.markdown("# Masuk")
            st.caption("Gunakan akun tim QC.")
            with st.form("login", border=False):
                u = st.text_input("Username", placeholder="Username", label_visibility="collapsed")
                p = st.text_input("Password", placeholder="Password", type="password", label_visibility="collapsed")
                ok = st.form_submit_button("Login")
            if ok:
                cu, cp = _creds()
                if hmac.compare_digest(u.strip().lower().encode(), cu.lower().encode()) and hmac.compare_digest(p.encode(), cp.encode()):
                    st.session_state["ct_auth"] = True
                    st.rerun()
                st.error("Username atau password salah.")
