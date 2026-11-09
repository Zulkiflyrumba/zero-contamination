"""Login with per-person accounts and roles (see core/users.py).

First start: one admin is created from CT_USER / CT_PASS (default qc / 123) and must change the password at first login.
"""
import base64
from pathlib import Path

import streamlit as st

from core import users

LOGO = Path(__file__).resolve().parents[1] / "assets" / "logo.png"

CSS = """
<style>
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stToolbar"]{display:none!important}
.st-key-lg{max-width:880px;margin:7vh auto 0;background:#fff;border-radius:26px;box-shadow:0 24px 60px rgba(40,80,62,.18);overflow:hidden;padding:0!important;border:0!important}
.st-key-lg>div,.st-key-lg [data-testid="stHorizontalBlock"]{gap:0!important}
.st-key-lg [data-testid="stColumn"]{padding:0!important}
.lg-left>*{margin-left:auto;margin-right:auto}
.lg-left{position:relative;overflow:hidden;min-height:500px;color:#fff;padding:34px;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;gap:8px;
 background:linear-gradient(150deg,#46b08a 0%,#2f9a73 45%,#1f6f55 100%)}
.lg-left::before{content:"";position:absolute;width:70px;height:70px;right:-14px;top:70px;background:rgba(255,255,255,.12);transform:rotate(45deg);border-radius:10px}
.lg-left::after{content:"";position:absolute;left:-60px;bottom:-60px;width:220px;height:220px;border-radius:50%;background:rgba(255,255,255,.09)}
.lg-logo{display:block;width:auto!important;height:20px!important;max-width:none!important;margin:0 auto 14px;flex:none}
.lg-left h2{font:700 22px/1.15 'Plus Jakarta Sans',sans-serif;margin:0;color:#fff;padding:0}
.lg-left p{margin:0;color:rgba(255,255,255,.86);font-size:12px;max-width:240px}
.st-key-lgform{padding:44px 46px;min-height:500px;display:flex;flex-direction:column;justify-content:center}
.st-key-lgform h1{font-size:20px;color:#2f9a73;padding:0;margin:0 0 4px}
.st-key-lgform [data-testid="stFormSubmitButton"] button{width:100%;min-height:50px;letter-spacing:.1em;text-transform:uppercase;font-size:12px;background:#2f9a73;color:#fff;box-shadow:0 8px 20px rgba(47,154,115,.3)}
.st-key-lgform,.st-key-lgform label,.st-key-lgform p{color:#1d2b25}
.st-key-lgform{background:#fff}
.st-key-lgform input{min-height:44px;font-size:14px!important;color:#3d4a44!important;-webkit-text-fill-color:#3d4a44!important;caret-color:#3d4a44;background:#fff!important;border:0!important}
.st-key-lgform [data-baseweb="input"],.st-key-lgform [data-baseweb="base-input"]{border:1px solid #cfd8d3!important;border-radius:12px!important}
.st-key-lgform [data-baseweb="input"] button,.st-key-lgform [data-baseweb="input"] svg{color:#3d4a44!important;fill:#3d4a44!important;background:#fff!important}
.st-key-lgform input::placeholder{color:#7b8c83!important;-webkit-text-fill-color:#7b8c83;opacity:1}
.st-key-lgform [data-baseweb="input"],.st-key-lgform [data-baseweb="base-input"]{background:#fff!important}
.st-key-lgform [data-testid="stFormSubmitButton"] button p{color:#fff!important}
.st-key-lgform [data-testid="InputInstructions"]{display:none}
@media (max-width:760px){.lg-left{min-height:0;padding:34px 24px 30px}.lg-left h2{font-size:19px}.st-key-lgform{padding:26px 24px 30px;min-height:0}.st-key-lg{margin-top:3vh}}
.st-key-lgform [data-baseweb="input"]{box-shadow:inset 0 0 0 1px #c3cfc8!important;border-radius:12px!important;overflow:hidden}
.st-key-lgform [data-baseweb="input"]:focus-within{box-shadow:inset 0 0 0 1.5px #2f9a73!important}
.st-key-lgform [data-testid="stTextInputRootElement"]{border:1px solid #c3cfc8!important;border-radius:12px!important;background:#fff!important;overflow:hidden}
.st-key-lgform [data-testid="stTextInputRootElement"]:focus-within{border-color:#2f9a73!important}
</style>
"""


def _logo_uri() -> str:
    return "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode() if LOGO.exists() else ""


def logged_in() -> bool:
    return bool(st.session_state.get("ct_auth"))


def current() -> dict:
    """The signed-in user ({username, name, role, must_change}); empty dict when signed out."""
    return st.session_state.get("ct_user") or {}


def logout() -> None:
    users.audit(current().get("username", ""), "logout")
    st.session_state.pop("ct_auth", None)
    st.session_state.pop("ct_user", None)


def require(page: str) -> None:
    """Stop the page when the signed-in role may not open it (the sidebar already hides it)."""
    if not users.can(current().get("role", ""), page):
        st.error("Anda tidak memiliki akses ke halaman ini.")
        st.stop()


def login_view() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    with st.container(key="lg"):
        left, right = st.columns(2, gap="small")
        with left:
            st.markdown(
                f'<div class="lg-left"><img class="lg-logo" alt="Adaro" src="{_logo_uri()}">'
                "<h2>Selamat datang</h2><p>Contamination Tracker. Telusuri sumber kontaminan di PIT dan ROM dari foto temuan.</p></div>",
                unsafe_allow_html=True,
            )
        with right, st.container(key="lgform"):
            st.markdown("# Masuk")
            st.caption("Gunakan akun tim QC.")
            with st.form("login", border=False):
                u = st.text_input("Username", placeholder="Username", label_visibility="collapsed")
                p = st.text_input("Password", placeholder="Password", type="password", label_visibility="collapsed")
                ok = st.form_submit_button("Login", use_container_width=True)
            if ok:
                user, msg = users.authenticate(u, p)
                if user:
                    st.session_state["ct_auth"] = True
                    st.session_state["ct_user"] = user
                    st.rerun()
                st.error(msg)
