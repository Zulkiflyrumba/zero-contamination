"""Builds the HTML of the 3D front end with the database payload injected."""
import json
from pathlib import Path

import streamlit as st

from core import db, models, theme

ROOT = Path(__file__).resolve().parents[1]
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


def make_payload(view: str = "tracker") -> dict:
    payload = db.export_payload()
    payload["models"] = models.manifest()
    payload["view"] = view
    if any((ROOT / "assets" / n).exists() for n in ("hero.jpg", "hero.png")):
        uri = theme.hero_data_uri()
        if uri:
            payload["hero"] = uri
    return payload
