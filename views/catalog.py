"""Catalog page: units, specs, parts (unit > system > assembly > part), photos, daily operations."""
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import auth, db, models, pack, theme, users

auth.require("catalog")

META = db.meta()
KINDS = list(META["kind_label"].keys())
theme.hero("Katalog unit dan part","Unit, sistem, assembly, part, foto referensi, dan model 3D unit.")
units = db.list_units()
by_id = {u["id"]: u for u in units}
tab_part, tab_unit, tab_photo, tab_model, tab_ops, tab_export = st.tabs(["Part", "Unit & spesifikasi", "Foto referensi", "Model 3D", "Operasi harian", "Ekspor"])

with tab_part:
    uid = st.selectbox("Unit", [u["id"] for u in units], format_func=lambda i: f'{by_id[i]["name"]} ({by_id[i]["kind"]})', key="cat_unit")
    rows = db.list_parts(uid)
    df = pd.DataFrame(rows, columns=db.PART_COLUMNS)
    df["fm"] = df["fm"].astype(bool)
    q = st.text_input("Cari (nama, sistem, assembly, nomor part)", key="cat_q")
    view = df
    if q:
        m = df[["name", "system", "asm", "part_no", "material"]].astype(str).agg(" ".join, axis=1).str.contains(q, case=False)
        view = df[m]
    st.caption(f"{len(view)} dari {len(df)} part. Kolom fm = kandidat kontaminan (ikut dianalisis). Ubah lalu tekan Simpan.")
    edited = st.data_editor(
        view, key=f"ed_{uid}_{q}", num_rows="dynamic" if not q else "fixed", hide_index=True, use_container_width=True,
        disabled=["id", "unit_id"],
        column_config={
            "id": st.column_config.TextColumn("ID", help="Kosongkan untuk part baru"),
            "unit_id": None, "name": "Part", "part_no": "No. part", "system": "Sistem", "asm": "Assembly",
            "kind": st.column_config.SelectboxColumn("Bentuk 3D", options=KINDS, required=True),
            "type": st.column_config.SelectboxColumn("Jenis", options=["metal", "nonmetal"], required=True),
            "material": "Material", "l": st.column_config.NumberColumn("P (mm)", min_value=1), "w": st.column_config.NumberColumn("L (mm)", min_value=1),
            "h": st.column_config.NumberColumn("T (mm)", min_value=1), "qty": st.column_config.NumberColumn("Jml", min_value=0, step=1),
            "fm": st.column_config.CheckboxColumn("Kandidat"), "incidents": st.column_config.NumberColumn("Kejadian 12 bln", min_value=0, step=1),
            "note": "Catatan kerusakan", "color": st.column_config.TextColumn("Warna"),
        },
    )
    if st.button("Simpan perubahan part", type="primary", disabled=bool(q)):
        res = db.save_parts(uid, edited.to_dict("records"))
        st.success(f'Tersimpan: {res["added"]} baru, {res["updated"]} diubah, {res["deleted"]} dihapus.')
        st.rerun()
    if q:
        st.info("Hapus pencarian untuk menambah atau menghapus baris.")

with tab_unit:
    udf = pd.DataFrame(units)[["id", "name", "maker", "kind", "fleet", "hm", "descr"]]
    ed = st.data_editor(udf, key="ed_units", num_rows="dynamic", hide_index=True, use_container_width=True,
                        column_config={"id": "ID", "name": "Model", "maker": "Pabrikan", "kind": "Jenis", "fleet": "Jumlah unit",
                                       "hm": "Rata-rata HM", "descr": "Keterangan"})
    if st.button("Simpan unit"):
        n = 0
        for r in ed.to_dict("records"):
            if str(r.get("name") or "").strip():
                r["id"] = (r.get("id") or str(r["name"]).lower().replace(" ", "").replace("-", ""))
                db.save_unit(r)
                n += 1
        st.success(f"{n} unit tersimpan.")
        st.rerun()
    st.divider()
    st.subheader("Spesifikasi unit")
    sid = st.selectbox("Unit", [u["id"] for u in units], format_func=lambda i: by_id[i]["name"], key="spec_unit")
    with db.connect() as con:
        spec = pd.DataFrame([dict(r) for r in con.execute("SELECT label, value, src FROM unit_spec WHERE unit_id=?", (sid,))],
                            columns=["label", "value", "src"])
    se = st.data_editor(spec, key=f"spec_{sid}", num_rows="dynamic", hide_index=True, use_container_width=True,
                        column_config={"label": "Parameter", "value": "Nilai",
                                       "src": st.column_config.SelectboxColumn("Sumber", options=["web", "indikatif", "parts book", "OEM"])})
    if st.button("Simpan spesifikasi"):
        with db.connect() as con:
            con.execute("DELETE FROM unit_spec WHERE unit_id=?", (sid,))
            for r in se.to_dict("records"):
                if str(r.get("label") or "").strip():
                    con.execute("INSERT OR REPLACE INTO unit_spec(unit_id,label,value,src) VALUES(?,?,?,?)",
                                (sid, r["label"], r.get("value") or "", r.get("src") or "indikatif"))
        st.success("Spesifikasi tersimpan.")

with tab_photo:
    st.write("Foto referensi nyata (baru, aus, patah) membuat pencocokan lebih akurat daripada gambar otomatis.")
    puid = st.selectbox("Unit", [u["id"] for u in units], format_func=lambda i: by_id[i]["name"], key="ph_unit")
    plist = db.list_parts(puid)
    pid = st.selectbox("Part", [p["id"] for p in plist], format_func=lambda i: next(p["name"] for p in plist if p["id"] == i), key="ph_part")
    role = st.radio("Jenis foto", ["ref"], format_func=lambda r: "Referensi part", horizontal=True)
    files = st.file_uploader("Foto (JPG/PNG), beberapa sudut sekaligus", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="ph_files")
    if st.button("Simpan foto", disabled=not files):
        for f in files:
            db.add_photo(pid, f.getvalue(), role)
        st.success(f"{len(files)} foto disimpan.")
    with db.connect() as con:
        existing = [dict(r) for r in con.execute("SELECT file FROM photos WHERE part_id=? AND role='ref'", (pid,))]
    if existing:
        st.image([str(db.DATA / e["file"]) for e in existing if (db.DATA / e["file"]).exists()], width=150)

with tab_model:
    st.markdown("Unggah model 3D unit **sekali**. File disimpan di `static/models/<unit>/` dan dibaca semua pengguna. "
                "Di Streamlit Community Cloud disk tidak permanen, jadi commit folder itu ke GitHub agar model tetap ada.")
    mid = st.selectbox("Unit", [u["id"] for u in units], format_func=lambda i: by_id[i]["name"], key="mdl_unit")
    cfg = models.get(mid)
    if cfg:
        st.success(f'Model aktif: {cfg["file"]} ({len(cfg["files"])} file). Panjang {cfg["opts"]["len"]} m, sumbu atas {cfg["opts"]["up"]}, putar {cfg["opts"]["yaw"]} derajat.')
    else:
        st.info("Unit ini belum punya model. Yang tampil adalah model skematik.")
    ups = st.file_uploader("File .glb, .gltf, atau .dae beserta tekstur, atau satu .zip (RAR harus diekstrak dulu)",
                           accept_multiple_files=True, key=f"mdl_up_{mid}")
    c1, c2, c3 = st.columns(3)
    cur = (cfg or {}).get("opts", models.DEFAULT_OPTS)
    mlen = c1.number_input("Panjang unit (m)", 3.0, 40.0, float(cur["len"]), 0.1, key=f"mdl_len_{mid}")
    mup = c2.selectbox("Sumbu atas model", ["y", "z", "-z"], index=["y", "z", "-z"].index(cur["up"]), key=f"mdl_up2_{mid}")
    myaw = c3.selectbox("Putar arah depan", [0, 90, 180, 270], index=[0, 90, 180, 270].index(int(cur["yaw"])), key=f"mdl_yaw_{mid}")
    b1, b2, _ = st.columns([1, 1, 3])
    if b1.button("Simpan model", type="primary", disabled=not ups and not cfg):
        try:
            o = {"len": mlen, "up": mup, "yaw": myaw}
            if ups:
                models.save(mid, [(f.name, f.getvalue()) for f in ups], o)
            else:
                models.set_options(mid, opts=o)
            st.toast("Model tersimpan")
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
    if cfg and b2.button("Hapus model"):
        models.delete(mid)
        st.rerun()
    if cfg:
        st.subheader("Lokasi part pada model")
        st.caption("Isi koordinat meter (x kiri, y atas, z depan) dari hasil klik Set lokasi part di Tracker. Kunci: Sistem/Assembly, mis. Hoist/Hose Hoist.")
        arows = [{"kunci": k, "x": v[0], "y": v[1], "z": v[2]} for k, v in cfg["anch"].items()]
        aed = st.data_editor(pd.DataFrame(arows or [{"kunci": "", "x": 0.0, "y": 0.0, "z": 0.0}]), num_rows="dynamic",
                             hide_index=True, use_container_width=True, key=f"mdl_anch_{mid}")
        if st.button("Simpan lokasi part"):
            an = {str(r["kunci"]).strip(): [float(r["x"]), float(r["y"]), float(r["z"])]
                  for r in aed.to_dict("records") if str(r.get("kunci") or "").strip()}
            models.set_options(mid, anch=an)
            st.toast("Lokasi part tersimpan")

with tab_ops:
    st.write("Data dispatch dipakai untuk menentukan nomor lambung yang beroperasi di area pada tanggal temuan. "
             "Tanpa data ini, aplikasi memakai penempatan dummy.")
    st.code("date,lambung,area\n2026-10-30,512,PIT Tutupan A", language="csv")
    up = st.file_uploader("Unggah CSV operasi harian", type=["csv"], key="ops_csv")
    if up is not None and st.button("Impor operasi"):
        d = pd.read_csv(up, dtype=str).fillna("")
        st.success(f'{db.import_operations(d.to_dict("records"))} baris diimpor.')
    with db.connect() as con:
        n = con.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
    st.caption(f"{n} baris operasi tersimpan.")

with tab_export:
    st.subheader("Paket data untuk aplikasi HTML / Android")
    st.caption("Satu file .ctpack berisi seluruh data (unit, part, riwayat, inspeksi, kasus, operasi), foto referensi, dan model 3D. "
               "Di aplikasi HTML / Android buka Data Center lalu Import Data Package. Aplikasi tidak perlu diperbarui.")
    pk_pw = st.text_input("Kata sandi paket (opsional, disarankan)", type="password", key="pk_pw",
                          help="Paket berisi seluruh data. Dengan kata sandi, isinya tidak terbaca bila file terkirim ke orang yang salah. Sampaikan kata sandi lewat jalur terpisah.")
    if st.button("Siapkan paket data", key="pk_build"):
        with st.spinner("Menyusun paket..."):
            st.session_state["pk"] = pack.build(password=pk_pw or None)
        users.audit(auth.current().get("username", ""), "paket_data_dibuat",
                    f'{st.session_state["pk"][1]["dataVersion"]} {"terkunci" if pk_pw else "TANPA kata sandi"}')
    if "pk" in st.session_state:
        pk_bytes, pk_man = st.session_state["pk"]
        c = pk_man["counts"]
        st.success(f'Versi data {pk_man["dataVersion"]} · {c["units"]} unit · {c["parts"]} part · {c["history"]} riwayat · '
                   f'{c["photos"]} foto · {c["models"]} model 3D · {len(pk_bytes) / 1e6:.1f} MB · '
                   f'{"dikunci dengan kata sandi" if pk_man.get("encrypted") else "tanpa kata sandi"}')
        st.download_button("Unduh paket data (.ctpack)", pk_bytes, pack.filename(pk_man), "application/zip", key="pk_dl")
    st.divider()
    allp = pd.DataFrame(db.list_parts())
    st.download_button("Unduh semua part (CSV)", allp.to_csv(index=False).encode("utf-8"), f"parts-{datetime.now().astimezone().date()}.csv", "text/csv")
    st.download_button("Unduh payload JSON (untuk front end)", json.dumps(db.export_payload(), ensure_ascii=False).encode("utf-8"),
                       f"payload-{datetime.now().astimezone().date()}.json", "application/json")
