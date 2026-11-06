"""Shared look and feel (soft sage palette, dark-green rail sidebar, hero banner)."""
import base64
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def _logo_uri() -> str:
    f = ASSETS / "logo.png"
    return "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode() if f.exists() else ""

CSS = """
<style>
:root{--ct-bg:#e7eee9;--ct-bg2:#f2f6f3;--ct-rail:#233f35;--ct-acc:#2f9a73;--ct-soft:#dff1e8;--ct-fg:#2a3a35;--ct-mut:#7d8e87;--ct-sh:0 10px 30px rgba(52,86,70,.10)}
html,body,.stApp{font-family:'Plus Jakarta Sans','Inter',system-ui,sans-serif;color:var(--ct-fg)}
.stApp{background:linear-gradient(160deg,var(--ct-bg),var(--ct-bg2)) fixed}
[data-testid="stHeader"]{background:transparent}
[data-testid="stToolbar"]{right:1rem}
.block-container{padding:1.2rem 2rem 3rem;max-width:1600px}
[data-testid="stSidebar"]{min-width:232px!important;width:232px!important}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#3f8f72 0%,#2c6b55 38%,#1f4a3c 72%,#16372c 100%);border-radius:0 30px 30px 0;box-shadow:var(--ct-sh)}
[data-testid="stSidebar"] *{color:#c9ddd3}
[data-testid="stSidebarNav"] a,[data-testid="stSidebarNavLink"]{border-radius:16px;padding:.55rem .8rem;margin:.15rem .4rem}
[data-testid="stSidebarNav"] a:hover,[data-testid="stSidebarNavLink"]:hover{background:rgba(255,255,255,.08)}
[data-testid="stSidebarNav"] a[aria-current="page"],[data-testid="stSidebarNavLink"][aria-current="page"]{background:rgba(255,255,255,.16)}
[data-testid="stSidebarNav"] a[aria-current="page"] *,[data-testid="stSidebarNavLink"][aria-current="page"] *{color:#fff!important;font-weight:600}
[data-testid="stSidebarCollapseButton"] button{color:#c9ddd3}
[data-testid="stVerticalBlockBorderWrapper"]{background:#fff;border:1px solid #dfe8e3!important;border-radius:22px!important;box-shadow:var(--ct-sh);padding:.4rem .6rem}
h1,h2,h3{letter-spacing:-.01em;color:var(--ct-fg)}
.stButton>button,.stDownloadButton>button,[data-testid="stBaseButton-secondary"],[data-testid="stBaseButton-primary"]{border-radius:999px;font-weight:600;border:0;background:var(--ct-soft);color:var(--ct-acc);padding:.5rem 1.2rem}
[data-testid="stBaseButton-primary"]{background:var(--ct-acc);color:#fff;box-shadow:0 8px 20px rgba(47,154,115,.3)}
.stTabs [data-baseweb="tab-list"]{gap:6px;background:#fff;border-radius:999px;padding:5px;box-shadow:var(--ct-sh);width:fit-content}
.stTabs [data-baseweb="tab"]{border-radius:999px;padding:.4rem 1rem;height:auto;color:var(--ct-mut)}
.stTabs [aria-selected="true"]{background:var(--ct-soft);color:var(--ct-acc);font-weight:600}
.stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none}
[data-baseweb="select"]>div,.stTextInput input,.stNumberInput input,.stTextArea textarea{border-radius:14px!important;background:#f2f6f3;border-color:transparent}
[data-testid="stDataFrame"],[data-testid="stDataEditor"]{border-radius:18px;overflow:hidden;box-shadow:var(--ct-sh)}
[data-testid="stFileUploaderDropzone"]{border-radius:18px;background:#f2f6f3}
[data-testid="stMetric"]{background:#fff;border-radius:20px;padding:14px 18px;box-shadow:var(--ct-sh)}
iframe{border:0;border-radius:28px}
.ct-hero{position:relative;overflow:hidden;border-radius:28px;box-shadow:var(--ct-sh);padding:30px 32px;min-height:170px;margin-bottom:1.2rem;color:#fff;display:flex;flex-direction:column;justify-content:flex-end;
 background:linear-gradient(100deg,rgba(18,46,36,.94) 0%,rgba(24,60,47,.62) 40%,rgba(24,60,47,.04) 100%),var(--hero) center 45%/cover no-repeat}
.ct-hero .lg{position:absolute;right:30px;top:24px;width:118px;height:34px;background:var(--logo) right center/contain no-repeat}
.ct-hero .eb{align-self:flex-start;font:600 11px 'Plus Jakarta Sans',sans-serif;letter-spacing:.08em;text-transform:uppercase;padding:4px 11px;border-radius:99px;background:rgba(255,255,255,.16);backdrop-filter:blur(6px);margin-bottom:10px;color:#fff}
.ct-hero h1{margin:0;color:#fff!important;font-size:28px;font-weight:700;padding:0}
.ct-hero p{margin:4px 0 0;color:rgba(255,255,255,.85);font-size:13px;max-width:520px}
</style>
"""


def _hero_uri() -> str:
    for name, mime in (("hero.jpg", "image/jpeg"), ("hero.png", "image/png"), ("hero.svg", "image/svg+xml")):
        f = ASSETS / name
        if f.exists():
            return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()
    return ""


def hero_data_uri() -> str:
    return _hero_uri()


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, eyebrow: str = "PIT · ROM · Foreign material") -> None:
    st.markdown(
        f'<div class="ct-hero" style="--hero:url({_hero_uri()});--logo:url({_logo_uri()})"><div class="lg"></div><span class="eb">{eyebrow}</span>'
        f"<h1>{title}</h1><p>{subtitle}</p></div>",
        unsafe_allow_html=True,
    )
