# ContamTrack 3D

Platform pelacakan sumber kontaminasi **PIT / ROM** tambang: upload foto temuan (logam atau non-logam), lalu sistem
menampilkan peringkat part/unit yang paling mungkin menjadi sumber, simulasi 3D kondisi aktual dan restorasi,
serta **letak part sumber pada unit (3D skala unit)**.

## Fitur
- **Analisis temuan** dari 1 atau lebih foto (opsional: lokasi, tanggal, material, dimensi, marking).
  Skor gabungan: kemiripan visual, material, ukuran, marking, korelasi histori unit, dan kasus terkonfirmasi.
- **3D kondisi aktual → restorasi** (2.5D dari siluet foto dicocokkan ke foto referensi part): perkiraan sisa dan bagian hilang.
- **Lokasi source pada unit**: kamera bergerak dari part sumber ke seluruh unit (dump truck / excavator), mode X-ray,
  grid 1 m, dan figur manusia 1,75 m sebagai pembanding skala.
- **Database katalog hierarki** Unit → Sistem → Assembly → Part (HD 785-7, CAT 777, PC1250-8, PC2000-8, PC400-8,
  PC3000-6, EX1200-6, EX2500-6, CAT 390F, CAT 6015B), ekspor/impor CSV, tambah part dan foto referensi.
- **Kasus terkonfirmasi**: hasil investigasi tersimpan dan ikut menjadi pembanding pada analisis berikutnya.

## Menjalankan lokal
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
Tes: `pip install pytest && pytest -q`

## Deploy ke Streamlit Community Cloud
1. Push repo ini ke GitHub.
2. Buka share.streamlit.io, pilih **New app**, pilih repo dan branch, isi **Main file path** = `app.py`, lalu Deploy.
3. Atur siapa yang boleh mengakses di pengaturan **Sharing** aplikasi. Aplikasi ini **tidak punya login sendiri**,
   jadi siapa pun yang bisa membuka URL dapat mengubah database.

## Penting: penyimpanan data
- Database (SQLite) dan foto tersimpan di folder `kontaminasi_data/` (atau path dari variabel lingkungan `CONTAM_DATA_DIR`).
- Di Streamlit Community Cloud sistem file **bersifat sementara**: data hilang saat aplikasi di-reboot atau di-deploy ulang.
  Untuk pemakaian nyata, jalankan di server/VM dengan volume permanen (set `CONTAM_DATA_DIR`), atau pindahkan penyimpanan
  ke database dan object storage eksternal.
- `kasus_assets/` (foto kasus nyata perusahaan) sengaja masuk `.gitignore`. Foto lapangan bisa memuat logo, lokasi, dan
  personel, jadi jangan dipublikasikan di repo publik. Jika ingin ikut ter-deploy, gunakan repo **private**.

## Kualitas data
- Part number, dimensi, berat, dan material di katalog bawaan **indikatif** (kolom `verified` = 0) sampai dicocokkan dengan parts book OEM.
- Spesifikasi unit HD 785-7, CAT 777, PC1250-8, PC2000-8 bersumber dari brosur OEM/dealer; unit lain baru kelas bobot.
- Foto referensi bawaan adalah ilustrasi per kategori. Hasil akan jauh lebih baik dengan foto part asli dari banyak sudut.
- Model 3D unit dan part bersifat ilustratif (proporsi perkiraan), bukan CAD OEM.

## Struktur
```
app.py            # antarmuka Streamlit
core.py           # database, katalog, kemiripan foto, restorasi, lokasi pada unit (tanpa Streamlit)
tests/            # tes otomatis (dijalankan GitHub Actions)
.streamlit/       # konfigurasi tema
```
Tentukan lisensi sebelum repo dipublikasikan.
