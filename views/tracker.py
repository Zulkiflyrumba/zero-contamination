"""Tracker page: embeds the 3D front end (photo analysis, reconstruction, unit location simulation)."""
import json
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import db

HTML = ROOT / "web" / "tracker.html"
WRAP = ('<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0">{}</body></html>')


@st.cache_data(show_spinner=False)
def _template() -> str:
    return HTML.read_text(encoding="utf-8")


def build_html(payload: dict) -> str:
    """Inject the database payload into the front end. ``</`` is escaped so JSON cannot close the script tag."""
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return WRAP.format(_template().replace("__CT_BOOT__", data))


st.title("Contamination Tracker")
st.caption("Unggah foto temuan kontaminan, lihat peringkat part dan unit sumber, lalu simulasikan lokasinya di unit 3D.")
payload = db.export_payload()
components.html(build_html(payload), height=1900, scrolling=True)
