"""Inspection records per fleet number (nomor lambung) and the contamination case log."""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import db, theme

META = db.meta()
theme.hero("Inspeksi dan kasus","Status part per nomor lambung dan catatan temuan yang sudah ditelusuri.")
units = db.list_units()
by_id = {u["id"]: u for u in units}
t_ins, t_case = st.tabs(["Inspeksi per nomor lambung", "Riwayat kasus"])

with t_ins:
    uid = st.selectbox("Unit", [u["id"] for u in units], format_func=lambda i: by_id[i]["name"], key="ins_unit")
    cand = [p for p in db.list_parts(uid) if p["fm"]]
    pid = st.selectbox("Part", [p["id"] for p in cand], format_func=lambda i: next(f'{p["name"]} ({p["system"]})' for p in cand if p["id"] == i), key="ins_part")
    nos = db.lambung_list(uid, META["fleet"])
    cur = {r["lambung"]: r for r in db.list_inspections() if r["part_id"] == pid}
    df = pd.DataFrame([{"lambung": n, "status": cur.get(n, {}).get("status", "belum"), "catatan": cur.get(n, {}).get("note", "")} for n in nos])
    ed = st.data_editor(df, hide_index=True, use_container_width=True, disabled=["lambung"], key=f"ins_{uid}_{pid}",
                        column_config={"lambung": "No. lambung",
                                       "status": st.column_config.SelectboxColumn("Status", options=db.STATUSES, required=True),
                                       "catatan": "Catatan"})
    if st.button("Simpan inspeksi", type="primary"):
        n = 0
        for r in ed.to_dict("records"):
            old = cur.get(r["lambung"], {})
            if r["status"] != old.get("status", "belum") or (r["catatan"] or "") != (old.get("note") or ""):
                db.set_inspection(r["lambung"], pid, r["status"], str(datetime.now().astimezone().date()), r["catatan"] or "")
                n += 1
        st.success(f"{n} perubahan disimpan.")

with t_case:
    cases = db.list_cases()
    parts = {p["id"]: p for p in db.list_parts()}
    if cases:
        st.dataframe(pd.DataFrame([{"ID": c["id"], "Tanggal": c["date"], "Lokasi": c["loc"], "Unit": by_id.get(c["unit_id"], {}).get("name", c["unit_id"]),
                                    "No. lambung": c["lambung"], "Part": parts.get(c["part_id"], {}).get("name", c["part_id"]),
                                    "Catatan": c["note"], "Kasus asli": bool(c["builtin"])} for c in cases]), hide_index=True, use_container_width=True)
    with st.form("new_case", clear_on_submit=True):
        st.subheader("Catat kasus baru")
        c1, c2 = st.columns(2)
        d = c1.date_input("Tanggal temuan", datetime.now().astimezone().date())
        loc = c2.selectbox("Lokasi", list(META["area_units"].keys()))
        uid2 = c1.selectbox("Unit sumber", [u["id"] for u in units], format_func=lambda i: by_id[i]["name"])
        plist = [p for p in parts.values() if p["unit_id"] == uid2]
        pid2 = c2.selectbox("Part", [p["id"] for p in plist], format_func=lambda i: parts[i]["name"]) if plist else None
        lb = c1.text_input("Nomor lambung")
        note = st.text_area("Catatan penelusuran")
        if st.form_submit_button("Simpan kasus", type="primary"):
            if pid2 and lb.strip():
                db.add_case(str(d), loc, uid2, pid2, lb.strip(), note)
                st.success("Kasus tersimpan.")
                st.rerun()
            else:
                st.error("Pilih part dan isi nomor lambung.")
    own = [c for c in cases if not c["builtin"]]
    if own:
        did = st.selectbox("Hapus kasus (hanya yang dibuat di aplikasi)", [c["id"] for c in own])
        if st.button("Hapus kasus"):
            db.delete_case(did)
            st.rerun()
