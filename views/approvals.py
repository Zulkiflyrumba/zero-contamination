"""Admin: review field data sent from the APK."""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import auth, cloud, submissions, theme, users

auth.require("approvals")
theme.hero("Persetujuan data lapangan", "Temuan, inspeksi, dan foto dari APK menunggu persetujuan sebelum masuk ke data utama.")

if not cloud.enabled():
    st.info("Fitur ini butuh Supabase. Isi SUPABASE_URL dan SUPABASE_SERVICE_KEY di Secrets.")
    st.stop()

me = auth.current().get("username", "")
try:
    pend = submissions.list_pending()
except cloud.CloudError as e:
    st.error(str(e))
    st.stop()

st.write(f"Menunggu persetujuan: **{len(pend)}**")
for s in pend:
    with st.container(border=True):
        st.write(submissions.describe(s))
        st.caption(f'Dikirim {str(s.get("created_at", ""))[:16].replace("T", " ")} · perangkat {str(s.get("device_id", ""))[:12]}')
        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("Setujui", key=f"ok_{s['id']}", type="primary"):
            try:
                msg = submissions.approve(s, me)
                users.audit(me, "setujui_kiriman", f'{s.get("kind")} {s["id"][:8]}')
                st.success(msg)
                st.rerun()
            except (ValueError, cloud.CloudError) as e:
                st.error(str(e))
        if c2.button("Tolak", key=f"no_{s['id']}"):
            submissions.reject(s, me)
            users.audit(me, "tolak_kiriman", f'{s.get("kind")} {s["id"][:8]}')
            st.rerun()

with st.expander("Riwayat keputusan terakhir"):
    for s in submissions.list_recent():
        st.write(f'{s.get("status")} · {submissions.describe(s)} · oleh {s.get("reviewed_by")}')
