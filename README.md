# Contamination Tracker

Platform untuk menelusuri sumber kontaminan logam dan non-logam di PIT dan ROM tambang batubara.
QC mengunggah foto temuan (satu atau banyak sudut), lalu sistem mengurutkan kandidat part dan unit
sumbernya, menampilkan rekonstruksi 3D, diagnostik, peringkat kemiripan, nomor lambung kandidat,
dan simulasi lokasi part di unit berskala besar.

## Fitur
- Basis data hierarkis Unit > Sistem > Assembly > Part (HD785-7, Cat 777G, PC200/400/1250/2000, D375A, GD825A, WA600) dengan spesifikasi, riwayat, dan foto referensi.
- Kecocokan visual di browser (siluet, rasio, warna, lubang, tekstur) digabung dengan ukuran, jenis, area, dan riwayat insiden.
- Simulasi lokasi part di unit. Model skematik bawaan, atau unggah model 3D sendiri (.glb, .gltf, .dae + tekstur, atau .zip) dan tempatkan titik part dengan klik.
- Konfirmasi atau koreksi hasil: foto temuan menjadi referensi part (di versi artifact/web mandiri).
- Kasus nyata HD785 #512 (hose clamp) sebagai contoh validasi.

## Jalankan lokal
```bash
pip install -r requirements.txt
streamlit run app.py
```
Database SQLite dibuat otomatis dari `data/catalog.json`. Ubah lokasinya dengan `CT_DB_PATH`.

## Deploy
1. Push ke GitHub.
2. Streamlit Community Cloud: New app, pilih repo, main file `app.py`.
3. Catatan: disk Community Cloud tidak permanen, jadi edit di Katalog hilang saat app restart. Untuk data tetap, jalankan lewat Docker dengan volume (`docker build -t ct . && docker run -p 8501:8501 -v ct-data:/data ct`) atau ganti `core/db.py` ke database eksternal.

## Struktur
`app.py` (navigasi), `core/db.py` (SQLite), `views/` (halaman), `web/tracker.html` (mesin analisis 3D dan simulasi, satu file HTML), `data/catalog.json` (seed).

## Batasan yang perlu diketahui
- Hasil adalah peringkat kandidat untuk dikonfirmasi tim QC, bukan kepastian. Part yang mirip bentuknya di beberapa unit sering sulit dibedakan hanya dari foto.
- Akurasi naik jika foto referensi nyata ditambahkan per part.
- Spesifikasi bertanda "web" berasal dari sumber publik, bertanda "indikatif" belum terverifikasi. Cat 777G dipakai untuk "HD 777" karena Komatsu tidak memiliki HD777.
- Nomor lambung dan area operasi pada data bawaan adalah data dummy. Impor data operasi nyata di halaman Katalog.
- Posisi part di unit memakai peta zona, bukan CAD. Cek dengan parts book.
- Embed Streamlit bersifat baca-saja untuk umpan balik. Model 3D unggahan tersimpan di browser pengguna.
