import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import theme

theme.hero("Tentang","Cara kerja, batasan, dan sumber data platform ini.")
st.markdown(
    """
**Contamination Tracker** membantu tim QC menelusuri sumber kontaminan logam dan non-logam di PIT dan ROM.

1. **Tracker**: unggah foto temuan, lihat peringkat kemiripan part dan unit, rekonstruksi 3D, dan simulasi lokasi part di unit.
2. **Katalog**: unit, spesifikasi, dan part dalam hierarki Unit > Sistem > Assembly > Part. Tambah foto referensi nyata.
3. **Inspeksi & Kasus**: status inspeksi per nomor lambung dan riwayat kasus.

**Batasan**: pencocokan visual memakai fitur sederhana (siluet, warna, tekstur, lubang) dan hasilnya berupa kandidat berperingkat
untuk dikonfirmasi tim QC. Model 3D unit adalah skema, bukan CAD. Spesifikasi bertanda *indikatif* perlu diverifikasi dengan parts book.
"""
)
