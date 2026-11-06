"""Gallery of parts with an interactive 3D view, filtered by unit / system / assembly."""
import sys
from pathlib import Path

import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import theme
from core.embed import build_html, make_payload

theme.hero("Galeri part 3D", "Pilih unit, cari part, lalu buka detailnya untuk melihat model 3D, foto referensi, dan riwayat.")
components.html(build_html(make_payload("database")), height=1500, scrolling=True)
