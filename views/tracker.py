"""Tracker page: embeds the 3D front end (photo analysis, reconstruction, unit location simulation)."""
import sys
from pathlib import Path

import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.embed import build_html, make_payload

components.html(build_html(make_payload("tracker")), height=1900, scrolling=True)
