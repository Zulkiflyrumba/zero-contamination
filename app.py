"""ContamTrack 3D - antarmuka Streamlit. Jalankan: streamlit run app.py"""
import streamlit as st
import streamlit.components.v1 as components
from core import *  # noqa: F401,F403

def model_manager():
    c = db(); U = pd.read_sql("select model from units", c); c.close()
    with st.expander("🧊 Model 3D referensi unit (GLB) - unggah model sendiri"):
        m = st.selectbox("Unit", U.model, key="mm_unit"); mp = model_path(m)
        st.caption(f"Model saat ini: {os.path.basename(mp)} ({os.path.getsize(mp)/1e6:.1f} MB)" if mp else "Belum ada model 3D untuk unit ini (dipakai model sederhana).")
        up = st.file_uploader("Unggah model .glb", type=["glb"], key="mm_up")
        sc = st.number_input("Skala (meter per satuan model)", 0.01, 10.0, float(model_scale(m)), 0.01, key=f"mm_sc_{m}")
        if st.button("Simpan model / skala", key="mm_save"):
            try:
                if up is not None: save_model(m, up.getvalue())
                set_model_scale(m, sc); st.success("Tersimpan. Buka tab Analisis untuk melihat hasilnya.")
            except ValueError as e: st.error(str(e))
        st.caption("Konversi dari DAE/OBJ/FBX: lihat tools/dae_to_glb.py. Nama node pada model (mis. Ladle, Wheel1) dipakai untuk memetakan letak part; kalibrasi dengan klik pada viewer di tab Analisis.")

def catalog_view():
    c = db(); U = pd.read_sql("select * from units", c); K = pd.read_sql("select * from parts", c); c.close()
    st.subheader("📚 Katalog hierarki unit")
    m = st.selectbox("Unit", U.model, format_func=lambda x: f"{x} - {U.set_index('model').merek[x]}"); u = U[U.model == m].iloc[0]
    st.info(f"**{u.merek} {u.model}** ({u.tipe})  \n{u.spek}")
    D = K[K.unit_model == m].fillna({"sistem": "(belum dikelompokkan)", "assembly": "-"})
    st.caption(f"{len(D)} part | {D.sistem.nunique()} sistem. Part number, dimensi, berat, dan material di katalog ini INDIKATIF (verified=0) sampai dicocokkan dengan parts book OEM.")
    for sis, G in D.groupby("sistem"):
        with st.expander(f"{sis} ({len(G)} part)"):
            for asm, A in G.groupby("assembly"):
                st.markdown(f"**{asm}**"); st.dataframe(A[["part_name", "part_no", "material", "dim_mm", "weight_kg", "marking", "notes", "verified"]], hide_index=True, use_container_width=True)
    with st.expander("⬇️⬆️ Ekspor / impor CSV (untuk memperluas katalog)"):
        st.download_button("Unduh katalog (CSV)", K.drop(columns=["imgs"]).to_csv(index=False).encode("utf-8"), "katalog_part.csv", "text/csv")
        up = st.file_uploader("Impor CSV (kolom: unit_model, sistem, assembly, part_name, part_no, category, material, dim_mm, weight_kg, marking, notes)", type="csv")
        if up is not None and st.button("Impor ke database"):
            X = pd.read_csv(up).fillna(""); c = db(); n = 0
            for _, r in X.iterrows():
                if not r.get("unit_model") or not r.get("part_name") or c.execute("select 1 from parts where unit_model=? and part_name=?", (r["unit_model"], r["part_name"])).fetchone(): continue
                cat = r.get("category") if r.get("category") in CATS else "pin"
                c.execute("insert or ignore into units(model,merek,tipe,k,spek) values(?,?,?,?,?)", (r["unit_model"], "", "", 1, ""))
                c.execute("insert into parts(unit_model,part_name,part_no,category,material,dim_mm,weight_kg,marking,notes,imgs,sistem,assembly,verified) values(?,?,?,?,?,?,?,?,?,?,?,?,0)",
                          (r["unit_model"], r["part_name"], r.get("part_no", ""), cat, r.get("material", ""), float(r.get("dim_mm") or 0), float(r.get("weight_kg") or 0), r.get("marking", ""), r.get("notes", ""),
                           "|".join(os.path.join(IMG, f"cat_{cat}_{q}.png") for q in range(2)), r.get("sistem", ""), r.get("assembly", ""))); n += 1
            c.commit(); c.close(); st.success(f"{n} part diimpor.")

# ---------- UI ----------
st.set_page_config(page_title="ContamTrack 3D", page_icon="🛰️", layout="wide")
st.cache_resource(show_spinner="Menyiapkan database...")(init)()
st.title("🛰️ ContamTrack 3D")
st.caption("Tracking sumber kontaminasi PIT / ROM dari foto temuan, database part & histori unit")
t1, t2, t3, t4 = st.tabs(["🔎 Analisis Temuan", "🗄️ Database Part", "📜 Histori Unit", "✅ Kasus Terkonfirmasi"])

with t1:
    a, b = st.columns([1, 1])
    with a:
        src = st.radio("Sumber foto", ["Upload foto (boleh banyak sudut)", "Foto contoh (dummy)"], horizontal=True)
        imgs = []
        if src.startswith("Upload"):
            imgs = [Image.open(f).convert("RGB") for f in st.file_uploader("Foto temuan", type=["jpg", "jpeg", "png"], accept_multiple_files=True) or []]
        else:
            dc = st.selectbox("Jenis temuan contoh", CATS, index=0)
            imgs = [make_img(dc, 901 + k, rust=True, rot=k * 40) for k in range(3)]
            if st.checkbox("Simulasikan bagian patah", True):
                for i in imgs: ImageDraw.Draw(i).polygon([(0, 0), (256, 0), (256, 110), (0, 60)], fill=(225, 225, 228))
        if imgs: st.image(imgs, width=110, caption=[f"Sudut {i+1}" for i in range(len(imgs))])
    with b:
        loc = st.text_input("Lokasi temuan", "Pit Selatan Blok B4"); day = st.date_input("Tanggal temuan", dt.date.today())
        with st.expander("Keterangan tambahan (opsional, makin lengkap makin akurat)"):
            c1, c2 = st.columns(2); mat = c1.selectbox("Jenis material", list(MATS)); size = c2.number_input("Dimensi terbesar (mm)", 0, 3000, 0)
            mark = st.text_input("Marking / part number terbaca")
    if st.button("🚀 Analisis sumber kontaminasi", type="primary", disabled=not imgs):
        st.session_state.res = analyse(imgs, mat, size, mark, loc, day); st.session_state.act = imgs; st.session_state.rcache = {}
    if "res" in st.session_state:
        R = st.session_state.res; st.subheader("Peringkat kemiripan")
        G = R.head(15).groupby("Part").agg(Peluang=("Peluang", "sum"), Unit=("Unit", lambda x: ", ".join(x))).sort_values("Peluang", ascending=False).head(5).reset_index()
        st.caption("Ringkasan per jenis part (unit yang memakai part serupa). Foto menyempitkan sampai tipe part & model unit; nomor lambung ditentukan dari histori/inspeksi.")
        st.dataframe(G, hide_index=True, use_container_width=True, column_config={"Peluang": st.column_config.NumberColumn("Peluang gabungan (%)", format="%.0f")})
        st.dataframe(R.head(8)[["Unit", "Part", "PartNo", "Peluang", "Skor"]], hide_index=True, use_container_width=True,
                     column_config={"Peluang": st.column_config.ProgressColumn("Peluang (%)", min_value=0, max_value=100, format="%.0f%%"),
                                    "Skor": st.column_config.NumberColumn(format="%.2f")})
        top = R.head(5); sel = st.selectbox("Lihat diagnostik & 3D", top.index, format_func=lambda i: f"#{i+1} {R.Unit[i]} - {R.Part[i]}")
        r = R.loc[sel]; rc = st.session_state.setdefault("rcache", {})
        if sel not in rc: rc[sel] = restore(st.session_state.act, r.imgs.split("|"))
        rs = rc[sel]; g1, g2 = st.columns([3, 2])
        with g1: components.html(HTML.replace("__CAT__", r.cat).replace("__D__", rs["data"] if rs else ""), height=450)
        with g2:
            st.markdown(f"### {r.Unit} - {r.Part}"); st.caption(f"Part No: {r.PartNo}")
            if rs:
                st.progress(float(rs["rem"]), text=f"Sisa part (estimasi): ~{rs['rem']*100:.0f}% | hilang ~{rs['miss']*100:.0f}% | kecocokan bentuk {rs['iou']*100:.0f}%")
                if rs["iou"] < .4: st.warning("Kecocokan bentuk rendah: kandidat ini mungkin bukan sumbernya, atau foto kurang jelas.")
            for k in ["Visual", "Material", "Ukuran", "Marking", "Histori", "Kasus"]: st.progress(float(r[k]), text=f"{k}: {r[k]*100:.0f}%")
            st.markdown(f"**Diagnostik:** {r.note}\n\n**Korelasi histori:** {r.hn}\n\n**Kasus serupa:** {r.kn or "Belum ada kasus terkonfirmasi yang mirip."}")
            st.info(f"Tindak lanjut: cek work order & kondisi {r.Part} pada unit {r.Unit}, verifikasi area kerja unit pada tanggal temuan.")
            st.image([f for f in r.imgs.split("|") if os.path.exists(f)], width=110, caption="Foto referensi")
        st.markdown("---"); st.subheader("📍 Lokasi source pada unit (simulasi skala unit)")
        us = unit_scene(r.Unit, r.Sistem, r.Assembly, r.Part)
        if us:
            st.success(f"Letak part: {us['desc']}"); components.html(us["html"], height=540)
            st.caption("Klik **Simulasi part → unit**: kamera bergerak dari part sumber ke seluruh unit. Aktifkan **X-ray** untuk melihat part yang tertutup bodi. Grid = 1 m, tinggi figur = 1,75 m; proporsi model unit ilustratif.")
            if us["has_model"]:
                if st.session_state.pop("anch_ok", False): st.success("Lokasi tersimpan untuk part ini.")
                with st.expander("🎯 Kalibrasi letak part pada model (klik pada model 3D)"):
                    st.caption("Klik titik yang benar pada model, salin teks di kotak kanan-bawah viewer (format Node|fx|fy|fz), tempel di bawah, lalu simpan.")
                    sp = st.text_input("Hasil klik", key="anch_spec")
                    if st.button("Simpan sebagai lokasi part ini", key="anch_save"):
                        if set_anchor(r.Unit, r.Sistem, r.Assembly, sp): st.session_state.anch_ok = True; st.rerun()
                        else: st.error("Format salah atau part belum punya sistem/assembly.")
        else: st.info("Model 3D unit belum tersedia untuk tipe unit ini (saat ini: dump truck dan excavator).")
        with st.expander("✅ Konfirmasi sumber & simpan sebagai kasus"):
            cu = st.text_input("No. lambung unit sumber", key="cu"); cn_ = st.text_area("Catatan investigasi", key="cn"); ci = st.file_uploader("Foto investigasi (opsional)", accept_multiple_files=True, key="ci")
            if st.button("Simpan kasus terkonfirmasi") and cu:
                fa = []
                for i, im in enumerate(st.session_state.act):
                    p_ = os.path.join(IMG, f"case_{dt.datetime.now():%H%M%S%f}_{i}.png"); im.convert("RGB").save(p_); fa.append(p_)
                c = db(); c.execute("insert into cases(date,location,unit_cn,unit_model,part_name,category,material,size_mm,notes,imgs_find,imgs_src) values(?,?,?,?,?,?,?,?,?,?,?)",
                                    (day.isoformat(), loc, cu, r.Unit, r.Part, r.cat, "", size, cn_, "|".join(fa), "|".join(save_uploads(ci, "inv")))); c.commit(); c.close(); st.success("Kasus tersimpan di tab Kasus Terkonfirmasi.")
        st.caption("Kemiripan visual memakai fitur ringan (warna, orientasi tepi, bentuk). 3D aktual & restorasi adalah 2.5D dari siluet foto yang dicocokkan ke foto referensi part di database (bukan scan 3D sungguhan).")

with t2:
    catalog_view()
    model_manager()
    c = db(); P = pd.read_sql("select id,unit_model,part_name,part_no,category,material,dim_mm,weight_kg,marking,notes,imgs from parts", c); c.close()
    P["jml_foto"] = P.imgs.str.count(r"\|") + 1; st.expander("📋 Semua part (tabel datar)").dataframe(P.drop(columns="imgs"), hide_index=True, use_container_width=True)
    with st.expander("➕ Tambah part baru", expanded=False):
        f = st.columns(4); u = f[0].text_input("Unit/model"); pn = f[1].text_input("Nama part"); no = f[2].text_input("Part number"); ct = f[3].selectbox("Kategori 3D", CATS)
        g = st.columns(4); mt = g[0].text_input("Material"); dm = g[1].number_input("Dimensi (mm)", 0., 5000., 100.); wt = g[2].number_input("Berat (kg)", 0., 500., 1.); mk = g[3].text_input("Marking")
        sy = st.text_input("Sistem (mis. Bak & Liner)"); asm = st.text_input("Assembly (mis. Liner & wear plate)"); nt = st.text_area("Keterangan / mode kerusakan"); ph = st.file_uploader("Foto part (banyak sudut)", accept_multiple_files=True, key="np")
        if st.button("Simpan part") and u and pn:
            c = db(); c.execute("insert into parts(unit_model,part_name,part_no,category,material,dim_mm,weight_kg,marking,notes,imgs) values(?,?,?,?,?,?,?,?,?,?)",
                                (u, pn, no, ct, mt, dm, wt, mk, nt, "|".join(save_uploads(ph, "new")))); c.execute("update parts set sistem=?, assembly=? where id=last_insert_rowid()", (sy, asm)); c.commit(); c.close(); st.rerun()
    with st.expander("🖼️ Tambah foto ke part yang sudah ada"):
        pid = st.selectbox("Part", P.id, format_func=lambda i: f"{P.set_index('id').unit_model[i]} - {P.set_index('id').part_name[i]}")
        ph = st.file_uploader("Foto tambahan", accept_multiple_files=True, key="ep")
        if st.button("Tambahkan foto") and ph:
            c = db(); old = c.execute("select imgs from parts where id=?", (int(pid),)).fetchone()[0]
            c.execute("update parts set imgs=? where id=?", ("|".join([x for x in [old] if x] + save_uploads(ph, "add")), int(pid))); c.commit(); c.close(); st.rerun()

with t3:
    c = db(); H = pd.read_sql("select * from history order by date desc", c); c.close(); st.dataframe(H, hide_index=True, use_container_width=True)
    with st.expander("➕ Tambah kejadian"):
        f = st.columns(3); d = f[0].date_input("Tanggal", dt.date.today(), key="hd"); cn = f[1].text_input("No. lambung unit"); um = f[2].text_input("Model unit", key="hm")
        f = st.columns(3); pn = f[0].text_input("Nama part (sesuai database)", key="hp"); ev = f[1].text_input("Kejadian"); ar = f[2].text_input("Area")
        if st.button("Simpan kejadian") and um and pn:
            c = db(); c.execute("insert into history(date,unit_cn,unit_model,part_name,event,area) values(?,?,?,?,?,?)", (d.isoformat(), cn, um, pn, ev, ar)); c.commit(); c.close(); st.rerun()

with t4:
    c = db(); K = pd.read_sql("select * from cases order by date desc", c); c.close()
    if K.empty: st.info("Belum ada kasus terkonfirmasi. Simpan dari tab Analisis setelah sumber terbukti.")
    for _, k in K.iterrows():
        with st.expander(f"{k.date} | {k.unit_cn} | {k.part_name}", expanded=True):
            st.write(f"**Lokasi:** {k.location}  \n**Catatan:** {k.notes}")
            ca, cb = st.columns(2)
            fa = [f for f in (k.imgs_find or "").split("|") if f and os.path.exists(f)]; fb = [f for f in (k.imgs_src or "").split("|") if f and os.path.exists(f)]
            if fa: ca.image(fa, width=240, caption="Temuan")
            if fb: cb.image(fb, width=240, caption="Sumber / investigasi")
