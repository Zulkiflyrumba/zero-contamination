"""Admin: accounts, roles and the audit log."""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import auth, cloud, db, theme, users

auth.require("users")
me = auth.current()
theme.hero("Pengguna", "Akun per orang, peran, dan catatan aktivitas.")
st.caption("Admin: semua fitur. Operator QC: Tracker, Galeri, Inspeksi & Kasus. Viewer: Tracker dan Galeri saja.")
tab_u, tab_new, tab_log, tab_cloud = st.tabs(["Daftar pengguna", "Tambah / ubah", "Catatan aktivitas", "Cloud (Supabase)"])

with tab_u:
    df = pd.DataFrame(users.list_users())
    df["role"] = df["role"].map(users.ROLE_LABEL)
    df["active"] = df["active"].map({1: "aktif", 0: "nonaktif"})
    df["must_change"] = df["must_change"].map({1: "ya", 0: "tidak"})
    st.dataframe(df.rename(columns={"username": "Username", "name": "Nama", "role": "Peran", "active": "Status",
                                    "must_change": "Wajib ganti password", "created": "Dibuat"}), hide_index=True, use_container_width=True)

with tab_new:
    st.subheader("Tambah pengguna")
    with st.form("newu", clear_on_submit=True):
        c1, c2 = st.columns(2)
        un = c1.text_input("Username")
        nm = c2.text_input("Nama lengkap")
        c3, c4 = st.columns(2)
        rl = c3.selectbox("Peran", users.ROLES, format_func=users.ROLE_LABEL.get, index=1)
        pw = c4.text_input("Password awal", type="password", help="Pengguna wajib menggantinya saat login pertama.")
        if st.form_submit_button("Tambah", type="primary"):
            try:
                users.create_user(un, nm, rl, pw, by=me["username"])
                st.success(f"Pengguna {un.strip().lower()} dibuat. Sampaikan password awal lewat jalur aman.")
            except ValueError as e:
                st.error(str(e))
    st.subheader("Ubah pengguna")
    lst = users.list_users()
    sel = st.selectbox("Pengguna", [u["username"] for u in lst], key="u_sel")
    cur = next(u for u in lst if u["username"] == sel)
    c1, c2 = st.columns(2)
    nrole = c1.selectbox("Peran", users.ROLES, index=users.ROLES.index(cur["role"]), format_func=users.ROLE_LABEL.get, key=f"u_role_{sel}")
    nact = c2.toggle("Aktif", value=bool(cur["active"]), key=f"u_act_{sel}")
    if st.button("Simpan peran dan status"):
        try:
            users.update_user(sel, role=nrole, active=nact, by=me["username"])
            st.success("Tersimpan.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))
    with st.form(f"reset_{sel}", clear_on_submit=True):
        rp = st.text_input("Password sementara baru", type="password")
        if st.form_submit_button("Atur ulang password"):
            try:
                users.set_password(sel, rp, must_change=True, by=me["username"])
                st.success("Password diatur ulang. Pengguna wajib menggantinya saat login berikutnya.")
            except ValueError as e:
                st.error(str(e))

with tab_log:
    st.dataframe(pd.DataFrame(users.list_audit(300)).rename(columns={"ts": "Waktu", "user": "Pengguna", "action": "Aksi", "detail": "Keterangan"}),
                 hide_index=True, use_container_width=True)

with tab_cloud:
    if not cloud.enabled():
        st.info("Cloud belum aktif. Isi SUPABASE_URL dan SUPABASE_SERVICE_KEY di Secrets (lihat README), "
                "lalu jalankan supabase/schema.sql di Supabase.")
    else:
        with db.connect() as con:
            queued = cloud.pending(con)
        st.write(f"Terhubung ke `{cloud.url()}`. Perubahan menunggu dikirim: **{queued}**.")
        if db.LAST_SYNC_ERROR[0]:
            st.warning("Sinkronisasi terakhir gagal, akan dicoba lagi pada perubahan berikutnya: " + db.LAST_SYNC_ERROR[0])
        c1, c2 = st.columns(2)
        if c1.button("Tarik data terbaru dari cloud", use_container_width=True):
            try:
                n = db.cloud_pull()
                users.audit(auth.current().get("username", ""), "cloud_tarik", str(sum(n.values())) + " baris")
                st.success(f"Selesai: {n}")
            except cloud.CloudError as e:
                st.error(str(e))
        if c2.button("Kirim ulang semua data ke cloud", use_container_width=True):
            try:
                st.success(f"Terkirim: {db.cloud_push_all()} baris")
            except cloud.CloudError as e:
                st.error(str(e))
