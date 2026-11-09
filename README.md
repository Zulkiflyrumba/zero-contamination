# Contamination Tracker

Platform untuk menelusuri sumber kontaminan logam dan non-logam di PIT dan ROM tambang batubara.
QC mengunggah foto temuan (satu atau banyak sudut), lalu sistem mengurutkan kandidat part dan unit
sumbernya, menampilkan rekonstruksi 3D, diagnostik, peringkat kemiripan, nomor lambung kandidat,
dan simulasi lokasi part di unit berskala besar.

## Fitur
- Basis data hierarkis Unit > Sistem > Assembly > Part (HD785-7, Cat 777G, PC200/400/1250/2000, D375A, GD825A, WA600) dengan spesifikasi, riwayat, dan foto referensi.
- Kecocokan visual di browser (siluet, rasio, warna, lubang, tekstur) digabung dengan ukuran, jenis, area, dan riwayat insiden.
- Mobile: tombol Ambil foto (kamera belakang) dan Galeri, ringkasan hasil di atas, bilah aksi tetap di bawah, dan iframe Streamlit mengikuti tinggi konten.
- Galeri part 3D (halaman Streamlit dan tab Basis Data): model 3D interaktif per part, foto referensi, riwayat.
- Simulasi lokasi part di unit. Model skematik bawaan, atau unggah model 3D sendiri (.glb, .gltf, .dae + tekstur, atau .zip) dan tempatkan titik part dengan klik.
- Konfirmasi atau koreksi hasil: foto temuan menjadi referensi part (di versi artifact/web mandiri).
- 114 komponen lapangan HD785-7 (depan, mesin kiri/kanan, sisi kiri, bawah vessel, atas deck, belakang) dari panduan OTD KPC-S 2010, lengkap dengan zona lokasi di model 3D. Database lama otomatis ikut menerima part baru ini.
- Kasus nyata HD785 #512 (hose clamp) sebagai contoh validasi.

## Model 3D unit (sekali unggah, tersimpan di repo)
Buka Katalog > Model 3D, pilih unit, unggah `.glb`/`.gltf`/`.dae` beserta tekstur (atau satu `.zip`), lalu Simpan. File masuk ke `static/models/<unit>/` dan dimuat otomatis oleh semua pengguna di halaman Tracker. Di Streamlit Community Cloud disk tidak permanen, jadi **commit folder `static/models/` ke GitHub**. Model HD785-7 sudah disertakan di `static/models/hd785/`; periksa lisensi model Sketchfab tersebut sebelum repo dipublikasikan. Tekstur PBR dipasang otomatis dari nama file (`NamaMaterial_albedo.jpg`, `_normal`, `_roughness`, `_metallic`).
Lokasi part pada model: klik "Set lokasi part" di Tracker untuk uji, lalu salin koordinat ke Katalog > Model 3D > Lokasi part agar permanen.

## Tampilan
Banner di bagian atas memakai foto `assets/hero.jpg`. Ganti file itu dengan foto lain (`.jpg` atau `.png`) bila perlu.

## Login

Default: username `qc`, password `123` (tanpa signup). Ganti lewat environment variable `CT_USER` / `CT_PASS` atau `st.secrets`. Ini hanya gerbang ringan untuk demo; di versi artifact pengecekan dilakukan di browser. Untuk produksi gunakan SSO/autentikasi server. Logo ada di `assets/logo.png`.

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

- Akurasi identifikasi bergantung pada foto referensi nyata. Gunakan tombol "Benar, simpan foto sebagai referensi" di versi artifact dan crop benda sebelum Lacak.

## Cocok 3D dan analisis kerusakan
Setelah Lacak sumber, benda pada foto dipisahkan dari latar (siluet), dibentuk menjadi model 3D relief berwarna foto, lalu dicocokkan ke model part utuh dari kandidat teratas. Mode **Cocokkan** menganimasikan overlay temuan ke referensi, mode **Kerusakan** menandai material hilang (merah) dan tonjolan (kuning) serta menampilkan persentase kerusakan per zona. Isi Ukuran (mm) agar skala benar; tanpa itu temuan dianggap sepanjang part utuh sehingga serpihan tampak lebih utuh. Kedalaman model temuan adalah perkiraan dan angka kerusakan berasal dari siluet foto, bukan pemindaian 3D; gunakan sebagai indikasi untuk dikonfirmasi tim QC.

## Paket data untuk aplikasi HTML / Android
Katalog > Ekspor > **Siapkan paket data** membuat satu file `.ctpack` (zip): `manifest.json` (versi data dan SHA-256 tiap file), `payload.json`, `photos/` dan `models/`. Di aplikasi HTML / Android buka **Data Center > Import Data Package**; data, foto, dan model 3D terpasang tanpa memperbarui aplikasi. Versi data berbentuk `tahun.bulan.tanggal.jam-hash`, jadi paket yang isinya sama tidak diimpor dua kali. Data lokal yang ditambah di aplikasi tetap dipertahankan. Sinkronisasi langsung ke server (tombol Check for Updates) adalah tahap berikutnya dan memakai format paket yang sama.

## Keamanan: akun per orang dan paket terkunci

- Login awal `qc` / `123` (atau dari `CT_USER` / `CT_PASS`) bersifat admin dan **wajib ganti password** saat masuk pertama. Di server, set `CT_USER`/`CT_PASS` lewat secrets, jangan di repo.
- Peran: **admin** (semua fitur, kelola pengguna, ekspor paket), **operator** (Tracker, Galeri, Inspeksi & Kasus), **viewer** (Tracker dan Galeri).
- Password minimal 8 karakter, huruf dan angka. Salah 5 kali dalam 5 menit mengunci sementara. Semua login, perubahan akun, dan ekspor tercatat di Catatan aktivitas.
- Paket `.ctpack` bisa dikunci kata sandi (AES-256-GCM, PBKDF2 200 ribu iterasi). Bagikan kata sandi lewat jalur terpisah dari filenya. Data yang sudah diimpor tersimpan tidak terenkripsi di perangkat.
- Pakai HTTPS atau VPN, repo dan app private.

## Supabase (data terpusat)

1. Buat proyek Supabase (region terdekat, atas nama tim). Di **SQL Editor** jalankan `supabase/schema.sql`. Skrip ini membuat tabel, mengaktifkan RLS di semua tabel, dan membuat bucket privat `ct-files`.
2. Isi `SUPABASE_URL` dan `SUPABASE_SERVICE_KEY` (service_role) di Secrets Streamlit, lihat `.streamlit/secrets.toml.example`. Kunci ini hanya untuk server; jangan masukkan ke repo atau APK.
3. Jalankan app. Saat pertama kali, katalog diunggah ke Supabase. Kalau server restart dengan disk kosong, data dipulihkan dari Supabase.
4. Setiap perubahan (kasus, inspeksi, part, foto, akun, catatan aktivitas) dicatat lewat trigger dan dikirim ke Supabase. Kalau koneksi gagal, perubahan tetap antre dan dikirim pada perubahan berikutnya.
5. Admin dapat memantau status, menarik data terbaru, atau mengirim ulang semua data di halaman **Pengguna > Cloud (Supabase)**.

## Sinkronisasi APK dengan Supabase

1. Jalankan ulang `supabase/schema.sql` (aman diulang). Skrip ini menambah tabel `meta` dan izin unggah foto lapangan.
2. Buat akun APK di Supabase: **Authentication > Users > Add user** (email dan password, centang auto confirm). Satu akun per orang.
3. Di APK: **Data Center > Sinkronisasi cloud**. Isi alamat server dan kunci **publishable** (bukan secret), lalu login.
4. **Check for Updates** membandingkan versi data. **Tarik pembaruan** mengunduh data, foto, dan model 3D (yang sudah diunduh tidak diunduh ulang).
5. Data yang dibuat di APK (kasus, inspeksi, foto referensi, riwayat) masuk antrean **Pending Sync** dan dikirim otomatis saat online, atau lewat tombol Kirim antrean. Isi kiriman hanya sampai ke tabel `field_submissions`.
6. Admin menyetujui atau menolak kiriman di halaman **Persetujuan** di Streamlit. Yang disetujui masuk ke data utama dan terbawa ke semua APK pada penarikan berikutnya.

Catatan: data lokal APK yang sudah dikirim tetap tampil di perangkat itu bersama data hasil tarikan, jadi satu kasus bisa terlihat ganda sampai data lokalnya dihapus. Paket `.ctpack` tetap bisa dipakai sebagai cadangan tanpa internet.
