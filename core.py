"""ContamTrack 3D - logika inti (database, katalog, kemiripan foto, restorasi 3D, lokasi pada unit). Tanpa dependensi Streamlit."""
import sqlite3, os, io, base64, math, json, datetime as dt
from functools import lru_cache
import numpy as np, pandas as pd
from PIL import Image, ImageDraw, ImageFilter

BASE = os.environ.get("CONTAM_DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "kontaminasi_data")
IMG = os.path.join(BASE, "img"); DB = os.path.join(BASE, "db.sqlite")
os.makedirs(IMG, exist_ok=True)
CATS = ["tooth", "adapter", "cutting_edge", "bolt", "track_shoe", "liner", "hose", "pin", "clamp"]
MATS = {"Tidak diketahui": None, "Baja / besi": ["baja", "hardox", "scm", "steel"],
        "Baja tahan aus (Hardox)": ["hardox"], "Karet / hose": ["karet"], "Plastik / non-logam": ["plastik", "poly"]}

# ---------- gambar dummy ----------
def make_img(cat, seed, rust=False, rot=0):
    rng = np.random.RandomState(seed); bg = (225, 225, 228)
    im = Image.new("RGB", (256, 256), bg); d = ImageDraw.Draw(im)
    c = (150, 105, 70) if rust else (110, 118, 128); c2 = tuple(int(v * .7) for v in c)
    if cat == "tooth": d.polygon([(128, 30), (190, 205), (66, 205)], fill=c); d.rectangle((60, 205, 196, 235), fill=c2)
    elif cat == "adapter": d.rectangle((50, 110, 206, 220), fill=c); d.polygon([(128, 40), (190, 110), (66, 110)], fill=c2)
    elif cat == "cutting_edge": d.rectangle((20, 115, 236, 145), fill=c); d.rectangle((20, 145, 236, 160), fill=c2)
    elif cat == "bolt": d.polygon([(88, 40), (168, 40), (190, 70), (168, 100), (88, 100), (66, 70)], fill=c); d.rectangle((112, 100, 144, 225), fill=c2)
    elif cat == "track_shoe":
        d.rectangle((30, 90, 226, 170), fill=c)
        for y in (105, 128, 150): d.rectangle((30, y, 226, y + 8), fill=c2)
    elif cat == "liner":
        d.rectangle((25, 60, 231, 200), fill=c)
        for x in range(50, 220, 40): d.ellipse((x, 120, x + 14, 134), fill=c2)
    elif cat == "hose": d.arc((40, 40, 216, 216), 200, 20, fill=c, width=26)
    elif cat == "clamp":
        d.polygon([(25, 100), (231, 100), (231, 115), (200, 160), (56, 160), (25, 115)], fill=c); d.rectangle((95, 60, 161, 165), fill=c2)
        d.ellipse((113, 72, 143, 100), fill=bg); d.ellipse((113, 122, 143, 150), fill=bg)
    else: d.rectangle((30, 105, 226, 150), fill=c); d.ellipse((190, 90, 236, 165), fill=c2)
    im = im.rotate(rot, fillcolor=bg)
    a = np.clip(np.asarray(im, float) + rng.normal(0, 9, (256, 256, 3)), 0, 255).astype("uint8")
    return Image.fromarray(a)

SEED = [  # unit, part, no, cat, material, dim_mm, kg, marking, notes
 ("HD 785-7", "Liner bak", "785-LNR-01", "liner", "Hardox 450", 600, 38, "HX450", "Aus & patah di sudut bak; sering lepas pada baut countersunk."),
 ("HD 785-7", "Wheel nut M30", "09244-02", "bolt", "Baja 10.9", 70, .4, "10.9", "Lepas akibat torsi kurang; hub roda."),
 ("HD 785-7", "Hydraulic hose 1in", "07000-HS", "hose", "Karet + kawat", 400, 1.2, "1SN", "Sobek akibat abrasi; potongan kerap terbawa material."),
 ("HD 785-7", "Tailgate pin", "785-PIN-07", "pin", "SCM440", 150, 6, "SCM440", "Aus/patah pada pin engsel."),
 ("PC1250-8", "Bucket tooth", "208-70-14152", "tooth", "Baja paduan", 350, 18, "14152", "Patah saat digging batuan keras."),
 ("PC1250-8", "Tooth adapter", "208-70-14170", "adapter", "Baja cor", 300, 22, "14170", "Retak pada nose adapter."),
 ("PC1250-8", "Side cutter", "208-70-14210", "cutting_edge", "Hardox 500", 800, 30, "HX500", "Aus & pecah di ujung."),
 ("PC1250-8", "Bucket pin", "208-70-pin", "pin", "SCM440", 200, 9, "SCM440", "Pin lepas karena retainer rusak."),
 ("PC2000-8", "Bucket tooth", "21N-70-21150", "tooth", "Baja paduan", 520, 41, "21150", "Tooth besar; patah pada pangkal."),
 ("PC2000-8", "Track shoe bolt", "21N-32-bolt", "bolt", "Baja 12.9", 90, .7, "12.9", "Kendur dan lepas di area crawler."),
 ("D155AX-6", "Track shoe", "14X-32-11010", "track_shoe", "Baja paduan", 500, 55, "14X", "Retak pada grouser."),
 ("D155AX-6", "Cutting edge", "175-71-21330", "cutting_edge", "Hardox 450", 1200, 65, "175-71", "Patah sebagian di blade."),
 ("WA600-6", "Bucket tooth", "423-847-1110", "tooth", "Baja paduan", 300, 12, "1110", "Patah di loading ROM."),
 ("WA600-6", "Cutting edge bolt M24", "01643-32", "bolt", "Baja 10.9", 90, .5, "10.9", "Lepas bersama segmen cutting edge."),
]

def db(): return sqlite3.connect(DB)

# ---------- katalog hierarki (data indikatif; isi/verifikasi dari parts book OEM) ----------
UNITS = """HD 785-7|Komatsu|Dump truck rigid|T|1|HD785|Mesin Komatsu SAA12V140E-3; daya 895 kW gross / 879 kW net (1.200 / 1.178 HP); payload nominal 91,7 t; berat kosong sekitar 72 t; GVW sekitar 163,8 t; bak heaped sekitar 60 m3
CAT 777|Caterpillar|Dump truck rigid|T|0.98|C777|Seri 777 (asumsi: "HD 777" = Cat 777E/F/G, verifikasi seri di site); 777G: mesin Cat C32 ACERT, sekitar 765 kW gross / 704 kW net; payload nominal sekitar 90 t (kelas 100 ton); target gross sekitar 164,7 t; bak sekitar 60-64 m3
PC1250-8|Komatsu|Excavator|E|0.6|PC1250|Mesin Komatsu SAA6D170E-5; 514 kW gross / 502 kW net (688 / 672 HP); berat operasi sekitar 106,5-116,6 t (backhoe); bucket 3,4-6,7 m3 (backhoe)
PC2000-8|Komatsu|Excavator|E|1|PC2000|Mesin Komatsu SAA12V140E-3; 728 kW gross (976 HP); berat operasi sekitar 200-204 t (backhoe); bucket 12-13,7 m3; boom 8,7 m, arm 3,9 m; bobot bucket sekitar 9,7 t; shoe 810 mm
PC400-8|Komatsu|Excavator|E|0.25|PC400|Kelas sekitar 40 t (verifikasi dengan spesifikasi OEM)
PC3000-6|Komatsu|Excavator|E|1.25|PC3000|Kelas sekitar 250 t (verifikasi dengan spesifikasi OEM)
EX1200-6|Hitachi|Excavator|E|0.65|EX1200|Kelas sekitar 110-120 t (verifikasi dengan spesifikasi OEM)
EX2500-6|Hitachi|Excavator|E|1.15|EX2500|Kelas sekitar 250 t (verifikasi dengan spesifikasi OEM)
CAT 390F|Caterpillar|Excavator|E|0.5|C390|Kelas sekitar 90 t (verifikasi dengan spesifikasi OEM)
CAT 6015B|Caterpillar|Excavator|E|0.65|C6015|Kelas sekitar 130 t (verifikasi dengan spesifikasi OEM)
D155AX-6|Komatsu|Bulldozer|O|1|D155|(spesifikasi belum diisi)
WA600-6|Komatsu|Wheel loader|O|1|WA600|(spesifikasi belum diisi)"""
TRUCK = """Bak & Liner|Liner & wear plate|Liner bak|liner|Hardox 450|600|38|HX450|Aus & patah di sudut bak; sering lepas pada baut countersunk.
Bak & Liner|Liner & wear plate|Wear plate lantai bak|liner|Hardox 400|800|45|HX400|Aus; potongan pelat bisa lepas dan terbawa material.
Bak & Liner|Liner & wear plate|Liner sisi bak|liner|Hardox 450|700|40|HX450|Patah di sambungan las.
Bak & Liner|Baut & pengencang|Baut liner countersunk|bolt|Baja 10.9|60|0.3|10.9|Kendur dan lepas akibat benturan material.
Bak & Liner|Baut & pengencang|Mur baut liner|bolt|Baja 10.9|45|0.1|10.9|Lepas bersama baut.
Bak & Liner|Engsel & pin|Tailgate pin|pin|SCM440|150|6|SCM440|Aus/patah pada pin engsel.
Bak & Liner|Engsel & pin|Pin engsel bak|pin|SCM440|180|8|SCM440|Aus pada engsel belakang bak.
Bak & Liner|Engsel & pin|Bushing engsel bak|pin|Baja paduan|120|2||Aus; sering lepas dari dudukan.
Bak & Liner|Karet & bantalan|Body pad karet|hose|Karet|250|2.5||Aus; potongan karet terbawa ke ROM (non-logam).
Hidrolik & Selang|Hoist cylinder|Pin hoist cylinder|pin|SCM440|150|6|SCM440|Aus/lepas pada dudukan silinder.
Hidrolik & Selang|Selang & clamp|Hydraulic hose 1in|hose|Karet + kawat|400|1.2|1SN|Sobek akibat abrasi; potongan kerap terbawa material.
Hidrolik & Selang|Selang & clamp|Clamp selang hidrolik|clamp|Baja galvanis|250|1.5||Clamp penjepit bundel selang di bawah bak; lepas/patah akibat getaran dan baut kendur.
Hidrolik & Selang|Selang & clamp|Baut clamp selang|bolt|Baja galvanis|50|0.1||Kendur akibat getaran.
Hidrolik & Selang|Selang & clamp|Pelindung selang (hose guard)|hose|Karet / spiral|600|0.8||Aus dan lepas.
Hidrolik & Selang|Selang & clamp|Bracket selang|clamp|Baja galvanis|200|0.8||Patah akibat getaran.
Hidrolik & Selang|Steering & rem|Pin steering cylinder|pin|SCM440|100|3|SCM440|Aus.
Hidrolik & Selang|Steering & rem|Brake hose|hose|Karet + kawat|500|1||Sobek/abrasi.
Roda & Ban|Roda|Wheel nut M30|bolt|Baja 10.9|70|0.4|10.9|Lepas akibat torsi kurang; hub roda.
Roda & Ban|Roda|Wheel stud|bolt|Baja 10.9|150|0.8|10.9|Patah atau lepas.
Roda & Ban|Rim|Lock ring rim|hose|Baja|900|12||Terlepas saat ban dilepas/dipasang.
Roda & Ban|Ban|Potongan ban (karet)|hose|Karet|500|2||Serpihan ban (non-logam).
Suspensi & Rangka|Suspensi|Pin strut suspensi|pin|SCM440|160|7|SCM440|Aus.
Suspensi & Rangka|Suspensi|Bushing suspensi|pin|Baja paduan|100|2||Aus.
Suspensi & Rangka|Pelindung|Belly guard|liner|Baja|1000|35||Patah/lepas.
Suspensi & Rangka|Pelindung|Fender / splash guard|liner|Baja / FRP|900|15||Retak dan lepas.
Suspensi & Rangka|Tangga & railing|Step plate anti-slip|liner|Baja|500|6||Lepas.
Suspensi & Rangka|Tangga & railing|Handrail & bracket|clamp|Baja|400|3||Patah.
Suspensi & Rangka|Baut|Baut rangka M24|bolt|Baja 10.9|90|0.5|10.9|Kendur.
Mesin & Penggerak|Pendingin|Fan guard|liner|Baja|800|5||Patah akibat getaran.
Mesin & Penggerak|Pendingin|Clamp radiator hose|clamp|Baja tahan karat|120|0.2||Lepas.
Mesin & Penggerak|Pendingin|Radiator hose|hose|Karet silikon|400|2||Sobek.
Mesin & Penggerak|Belt|V-belt|hose|Karet|1500|0.5||Putus (non-logam).
Mesin & Penggerak|Driveshaft|Driveshaft guard|liner|Baja|700|10||Patah.
Mesin & Penggerak|Driveshaft|Baut flange driveshaft|bolt|Baja 12.9|70|0.4|12.9|Lepas.
Kabin & Elektrikal|Kaca & lampu|Spion & rangka|liner|Kaca + plastik|300|1||Pecah (non-logam).
Kabin & Elektrikal|Kaca & lampu|Cover lampu|liner|Plastik|250|0.5||Pecah (non-logam).
Kabin & Elektrikal|Kabel|Clamp harness kabel|clamp|Nylon / baja|60|0.05||Lepas.
Kabin & Elektrikal|Panel|Panel plastik / cover|liner|Plastik|400|0.5||Pecah (non-logam)."""
EXC = """Bucket & GET|Gigi & adapter|Bucket tooth|tooth|Baja paduan|350|18||Patah saat digging batuan keras.
Bucket & GET|Gigi & adapter|Tooth adapter|adapter|Baja cor|300|22||Retak pada nose adapter.
Bucket & GET|Gigi & adapter|Pin & retainer gigi|pin|Baja paduan|180|1.5||Lepas; sering ikut tooth hilang.
Bucket & GET|Pelindung bucket|Shroud adapter|adapter|Baja cor|300|6||Patah atau aus.
Bucket & GET|Pelindung bucket|Wing shroud|adapter|Baja cor|350|9||Patah atau aus.
Bucket & GET|Pelindung bucket|Side cutter|cutting_edge|Hardox 500|800|30|HX500|Aus & pecah di ujung.
Bucket & GET|Pelindung bucket|Lip / cutting edge bucket|cutting_edge|Hardox 450|1200|60|HX450|Patah sebagian.
Bucket & GET|Pelindung bucket|Wear plate bucket|liner|Hardox 400|600|25|HX400|Aus dan lepas.
Bucket & GET|Sambungan|Bucket pin|pin|SCM440|200|9|SCM440|Pin lepas karena retainer rusak.
Bucket & GET|Sambungan|Bushing bucket|pin|Baja paduan|160|5||Aus.
Bucket & GET|Sambungan|Baut & mur bucket|bolt|Baja 10.9|80|0.4|10.9|Kendur dan lepas.
Boom & Arm|Pin & bushing|Pin boom / arm|pin|SCM440|250|25|SCM440|Aus.
Boom & Arm|Pin & bushing|Bushing boom / arm|pin|Baja paduan|180|6||Aus.
Boom & Arm|Pelindung|Pelindung silinder|liner|Baja|800|20||Patah.
Boom & Arm|Grease & selang|Clamp grease line|clamp|Baja galvanis|150|0.5||Lepas.
Boom & Arm|Grease & selang|Hydraulic hose boom/arm|hose|Karet + kawat|800|2.5||Sobek.
Boom & Arm|Grease & selang|Clamp selang boom/arm|clamp|Baja galvanis|200|1.2||Mirip clamp selang unit lain; cek bentuk dan jumlah lubang.
Undercarriage|Track|Track shoe|track_shoe|Baja paduan|800|120||Retak pada grouser.
Undercarriage|Track|Track shoe bolt|bolt|Baja 12.9|90|0.7|12.9|Kendur dan lepas di area crawler.
Undercarriage|Track|Mur track shoe|bolt|Baja 12.9|60|0.3|12.9|Lepas.
Undercarriage|Track|Pin track|pin|Baja paduan|300|15||Aus.
Undercarriage|Track|Bushing track|pin|Baja paduan|200|10||Aus.
Undercarriage|Roller & guard|Track roller (potongan)|pin|Baja paduan|400|80||Pecah.
Undercarriage|Roller & guard|Track guard|liner|Baja|900|40||Patah.
Upper Structure|Panel & tangga|Panel pintu / hood|liner|Baja / plastik|900|20||Lepas.
Upper Structure|Panel & tangga|Step plate / handrail|liner|Baja|500|6||Patah.
Upper Structure|Counterweight|Baut counterweight|bolt|Baja 12.9|120|1.5|12.9|Kendur.
Upper Structure|Mesin & pendingin|Fan guard|liner|Baja|800|5||Patah.
Upper Structure|Mesin & pendingin|Clamp radiator hose|clamp|Baja tahan karat|120|0.2||Lepas.
Upper Structure|Kabin & kabel|Kaca kabin / spion|liner|Kaca + plastik|400|2||Pecah (non-logam).
Upper Structure|Kabin & kabel|Clamp harness kabel|clamp|Nylon / baja|60|0.05||Lepas."""

def seed_catalog(c):
    c.execute("create table if not exists meta(k text primary key, v text)")
    c.execute("create table if not exists units(model text primary key, merek text, tipe text, k real, spek text)")
    have = [r[1] for r in c.execute("pragma table_info(parts)")]
    for col, typ in (("sistem", "text"), ("assembly", "text"), ("verified", "integer default 0")):
        if col not in have: c.execute(f"alter table parts add column {col} {typ}")
    if c.execute("select 1 from meta where k='catalog_v1'").fetchone(): return
    imgs = {}
    for j, cat in enumerate(CATS):
        fs = []
        for q in range(2):
            f = os.path.join(IMG, f"cat_{cat}_{q}.png"); make_img(cat, 500 + j * 3 + q, rust=q == 1, rot=q * 35).save(f); fs.append(f)
        imgs[cat] = "|".join(fs)
    for ln in UNITS.strip().splitlines():
        m, mrk, tp, fam, k, code, spek = ln.split("|"); k = float(k)
        c.execute("insert or replace into units values(?,?,?,?,?)", (m, mrk, tp, k, spek))
        if fam == "O": continue
        for i, l2 in enumerate((TRUCK if fam == "T" else EXC).strip().splitlines()):
            sis, asm, nm, cat, mat, dim, kg, mk2, nt = (l2.split("|") + [""] * 9)[:9]; dim, kg = float(dim), float(kg)
            kk = k if dim >= 150 else k ** .3
            r = c.execute("select id from parts where unit_model=? and part_name=?", (m, nm)).fetchone()
            if r: c.execute("update parts set sistem=?, assembly=? where id=?", (sis, asm, r[0])); continue
            c.execute("insert into parts(unit_model,part_name,part_no,category,material,dim_mm,weight_kg,marking,notes,imgs,sistem,assembly,verified) values(?,?,?,?,?,?,?,?,?,?,?,?,0)",
                      (m, nm, f"{code}-{i+1:03d}", cat, mat, round(dim * kk ** .8), round(kg * kk ** 2.4, 2), mk2, nt, imgs[cat], sis, asm))
    c.execute("insert into meta values('catalog_v1','1')")

@lru_cache(maxsize=None)
def ref_feat(f): return feat(Image.open(f))

ASSET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kasus_assets")

def seed_extra(c):
    c.execute("create table if not exists cases(id integer primary key autoincrement, date text, location text, unit_cn text, unit_model text, part_name text, category text, material text, size_mm real, notes text, imgs_find text, imgs_src text)")
    if not c.execute("select 1 from parts where category='clamp'").fetchone():
        fs = []
        for k in range(2):
            f = os.path.join(IMG, f"seed_clamp_{k}.png"); make_img("clamp", 77 + k, rust=k == 1, rot=k * 25).save(f); fs.append(f)
        c.execute("insert into parts(unit_model,part_name,part_no,category,material,dim_mm,weight_kg,marking,notes,imgs) values(?,?,?,?,?,?,?,?,?,?)",
                  ("HD 785-7", "Clamp selang hidrolik", "785-CLP-01", "clamp", "Baja galvanis", 250, 1.5, "", "Clamp penjepit bundel selang di bawah bak; lepas/patah akibat getaran dan baut kendur.", "|".join(fs)))
    src = [os.path.join(ASSET, n) for n in ("temuan_1.png", "unit_512.jpg", "investigasi.jpg")]
    if all(os.path.exists(x) for x in src) and not c.execute("select 1 from cases").fetchone():
        fs = []
        for n, x in zip(("temuan", "unit", "invest"), src):
            f = os.path.join(IMG, f"case1_{n}.png"); Image.open(x).convert("RGB").save(f); fs.append(f)
        c.execute("insert into cases(date,location,unit_cn,unit_model,part_name,category,material,size_mm,notes,imgs_find,imgs_src) values(?,?,?,?,?,?,?,?,?,?,?)",
                  ("2026-10-30", "Jobsite (hasil investigasi)", "HD 785 - 512", "HD 785-7", "Clamp selang hidrolik", "clamp", "Baja galvanis", 0,
                   "Potongan clamp (pelat melengkung + blok 2 lubang) ditemukan sebagai kontaminan logam; investigasi menelusuri asalnya ke clamp bundel selang di bawah bak unit HD 785 no. 512.",
                   fs[0], "|".join(fs[1:])))
    seed_catalog(c)
    c.commit()

def init():
    c = db()
    c.executescript("""create table if not exists parts(id integer primary key autoincrement, unit_model text, part_name text,
      part_no text, category text, material text, dim_mm real, weight_kg real, marking text, notes text, imgs text);
      create table if not exists history(id integer primary key autoincrement, date text, unit_cn text, unit_model text,
      part_name text, event text, area text);""")
    if c.execute("select count(*) from parts").fetchone()[0] == 0:
        for i, s in enumerate(SEED, 1):
            fs = []
            for k in range(2):
                f = os.path.join(IMG, f"seed_{i}_{k}.png"); make_img(s[3], i * 7 + k, rust=k == 1, rot=k * 35).save(f); fs.append(f)
            c.execute("insert into parts(unit_model,part_name,part_no,category,material,dim_mm,weight_kg,marking,notes,imgs) values(?,?,?,?,?,?,?,?,?,?)", (*s, "|".join(fs)))
        t = dt.date.today(); H = [(1, "EX-1250-03", "PC1250-8", "Bucket tooth", "Tooth hilang/patah saat loading", "Pit Selatan Blok B4"),
             (3, "HD-785-12", "HD 785-7", "Liner bak", "Liner bak lepas & patah", "Pit Utara Blok A2"),
             (2, "EX-2000-01", "PC2000-8", "Track shoe bolt", "Baut track shoe hilang", "Pit Selatan Blok B2"),
             (6, "HD-785-07", "HD 785-7", "Hydraulic hose 1in", "Hose sobek, ganti darurat", "ROM Stockpile 2"),
             (9, "WL-600-02", "WA600-6", "Bucket tooth", "Tooth patah di ROM", "ROM Stockpile 1"),
             (20, "DZ-155-05", "D155AX-6", "Cutting edge", "Cutting edge diganti (segmen patah)", "Disposal Timur")]
        for d, *r in H: c.execute("insert into history(date,unit_cn,unit_model,part_name,event,area) values(?,?,?,?,?,?)", ((t - dt.timedelta(days=d)).isoformat(), *r))
    seed_extra(c); c.close()

# ---------- kemiripan visual (ringan: histogram warna + orientasi tepi + bentuk) ----------
def feat(im):
    a = np.asarray(im.convert("RGB").resize((64, 64)), float); g = a.mean(2)
    h = np.concatenate([np.histogram(a[..., k], bins=8, range=(0, 255))[0] / 4096. for k in range(3)]) / 3
    gy, gx = np.gradient(g); o = np.histogram(np.arctan2(gy, gx) % math.pi, bins=8, weights=np.hypot(gx, gy), range=(0, math.pi))[0]
    o = o / (o.sum() + 1e-9); m = np.abs(g - np.median(g)) > 18; ys, xs = np.where(m)
    asp = (np.ptp(xs) + 1) / (np.ptp(ys) + 1) if len(xs) else 1
    return np.concatenate([h, o, [m.mean(), asp / (1 + asp)]])

def sim(f1, f2): return float(np.exp(-3 * np.abs(f1 - f2).sum() / 2))

def analyse(imgs, mat, size, mark, loc, day):
    c = db(); P = pd.read_sql("select * from parts", c); H = pd.read_sql("select * from history", c); C = pd.read_sql("select * from cases", c); c.close()
    fs = [feat(i) for i in imgs]; rows = []
    for _, p in P.iterrows():
        refs = [ref_feat(f) for f in (p.imgs or "").split("|") if f and os.path.exists(f)]
        vis = float(np.mean([max(sim(f, r) for r in refs) for f in fs])) if refs else 0.
        keys = MATS[mat]; ms = .5 if not keys else float(any(k in str(p.material).lower() for k in keys))
        sz = .5 if not size else float(math.exp(-abs(math.log(size / max(p.dim_mm, 1)))))
        mk = .5 if not mark else float(mark.lower() in f"{p.marking} {p.part_no}".lower())
        hs, hn = 0., "Tidak ada kejadian terkait di histori."
        for _, h in H[(H.unit_model == p.unit_model) & (H.part_name == p.part_name)].iterrows():
            dd = abs((day - dt.date.fromisoformat(h.date)).days)
            if dd <= 14:
                s = .5 + (.5 if loc and any(w in h.area.lower() for w in loc.lower().split() if len(w) > 2) else 0)
                if s > hs: hs, hn = s, f"{h.unit_cn}: {h.event} ({h.date}, {h.area})."
        ks, kn = 0., ""
        for _, k in C[(C.unit_model == p.unit_model) & (C.part_name == p.part_name)].iterrows():
            kf = [feat(Image.open(f)) for f in (k.imgs_find or "").split("|") if f and os.path.exists(f)]
            if kf:
                v = float(np.mean([max(sim(f, g) for g in kf) for f in fs]))
                if v > ks: ks, kn = v, f"Kasus {k.date} - unit {k.unit_cn}: {k.notes}"
        tot = .35 * vis + .15 * ms + .1 * sz + .08 * mk + .1 * hs + .22 * ks
        rows.append(dict(id=p.id, Unit=p.unit_model, Part=p.part_name, PartNo=p.part_no, cat=p.category, Visual=vis, Material=ms,
                         Ukuran=sz, Marking=mk, Histori=hs, Kasus=ks, kn=kn, Sistem=p.sistem, Assembly=p.assembly, Skor=tot, note=p.notes, hn=hn, imgs=p.imgs))
    R = pd.DataFrame(rows).sort_values("Skor", ascending=False).reset_index(drop=True)
    e = np.exp(R.Skor * 25); R["Peluang"] = e / e.sum() * 100
    return R

# ---------- 3D aktual -> restorasi (2.5D dari siluet foto vs foto referensi database) ----------
def silhouette(im, n=96):
    a = np.asarray(im.convert("RGB").resize((160, 160)), float)
    bg = np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]), 0)
    m = Image.fromarray(((np.linalg.norm(a - bg, axis=2) > 40) * 255).astype("uint8")).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(5))
    m = np.asarray(m) > 127; ys, xs = np.where(m)
    if len(xs) < 50: return np.zeros((n, n), bool)
    c = Image.fromarray(m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype("uint8") * 255)
    k = n * .9 / max(c.size); c = c.resize((max(1, int(c.size[0] * k)), max(1, int(c.size[1] * k))))
    o = Image.new("L", (n, n)); o.paste(c, ((n - c.size[0]) // 2, (n - c.size[1]) // 2)); return np.asarray(o) > 127

def fit(A, Rm):  # cari rotasi/skala/geser terbaik agar siluet temuan menempel di part utuh
    best = (-1., A); Ai = Image.fromarray(A.astype("uint8") * 255)
    for rot in (-30, -15, 0, 15, 30):
        for sc in (.35, .5, .65, .8, 1.):
            k = max(8, int(96 * sc)); o = Image.new("L", (96, 96)); o.paste(Ai.rotate(rot).resize((k, k)), ((96 - k) // 2, (96 - k) // 2)); o = np.asarray(o) > 127
            for dx in range(-12, 13, 6):
                for dy in range(-12, 13, 6):
                    x = np.roll(np.roll(o, dx, 1), dy, 0); u = (x | Rm).sum()
                    if u and (x & Rm).sum() / u > best[0]: best = ((x & Rm).sum() / u, x)
    return best

def blur(m, r=4): return np.asarray(Image.fromarray(m.astype("uint8") * 255).filter(ImageFilter.GaussianBlur(r)), float) / 255

def restore(acts, refs):
    Rs = [silhouette(Image.open(f)) for f in refs if os.path.exists(f)]; best = None
    for im in acts:
        A = silhouette(im)
        if A.sum() < 50: continue
        for Rm in Rs:
            iou, x = fit(A, Rm)
            if best is None or iou > best[0]: best = (iou, x, Rm)
    if best is None: return None
    iou, A, Rm = best; n = max(Rm.sum(), 1)
    raw = np.concatenate([blur(A).ravel() * 255, blur(A | Rm).ravel() * 255, (Rm & ~A).ravel() * 1, A.ravel() * 1]).astype("uint8").tobytes()
    return dict(iou=iou, rem=(A & Rm).sum() / n, miss=(Rm & ~A).sum() / n, data=base64.b64encode(raw).decode())

# ---------- viewer 3D ----------
HTML = """<div style="position:relative"><canvas id=c style="width:100%;height:430px;display:block;border-radius:12px"></canvas>
<div id=lbl style="position:absolute;top:8px;left:10px;font:12px sans-serif;color:#7fe"></div>
<div style="position:absolute;bottom:8px;left:8px;font:12px sans-serif">
<button onclick="mode=0;set()">Hologram</button> <button onclick="mode=1;set()">Solid</button> <button onclick="mode=2;set()">Realistis</button>
<button onclick="play()">&#9654; Simulasi</button> <button onclick="view=0;set()">Model part</button> <button onclick="view=1;TT=0;set()">3D aktual</button> <button onclick="view=1;TT=1;set()">Restorasi</button></div></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script><script>
const D="__D__",CAT="__CAT__",cv=document.getElementById('c'),lbl=document.getElementById('lbl'),W=cv.clientWidth,H=430;
const r=new THREE.WebGLRenderer({canvas:cv,antialias:true});r.setSize(W,H,false);
const s=new THREE.Scene();s.background=new THREE.Color(0x0b1220);
const cam=new THREE.PerspectiveCamera(45,W/H,.1,100);cam.position.set(0,2.5,7.5);cam.lookAt(0,0,0);
s.add(new THREE.AmbientLight(0xffffff,.55));const L=new THREE.DirectionalLight(0xffffff,1);L.position.set(5,8,5);s.add(L);
const L2=new THREE.PointLight(0xffaa55,.9);L2.position.set(-5,2,-3);s.add(L2);
const gr=new THREE.GridHelper(12,24,0x1f6feb,0x16324f);gr.position.y=-1.8;s.add(gr);
const nc=document.createElement('canvas');nc.width=nc.height=128;const nx=nc.getContext('2d');
for(let i=0;i<5000;i++){nx.fillStyle='hsl(0,0%,'+Math.random()*100+'%)';nx.fillRect(Math.random()*128,Math.random()*128,3,3)}
const bump=new THREE.CanvasTexture(nc);bump.wrapS=bump.wrapT=THREE.RepeatWrapping;
const M=[new THREE.MeshBasicMaterial({color:0x33ddff,wireframe:true}),
 new THREE.MeshStandardMaterial({color:0x8a97a6,metalness:.2,roughness:.6,flatShading:true}),
 new THREE.MeshStandardMaterial({color:0x9a8f86,metalness:.85,roughness:.38,bumpMap:bump,bumpScale:.8})];
M.forEach(m=>m.side=THREE.DoubleSide);function build(c){const g=new THREE.Group();
 const A=(geo,x=0,y=0,z=0,rz=0)=>{const m=new THREE.Mesh(geo,M[0]);m.position.set(x,y,z);m.rotation.z=rz;g.add(m);return m};
 if(c=='tooth'){A(new THREE.ConeGeometry(1.2,3.5,4),0,.4,0).scale.z=.6;A(new THREE.BoxGeometry(2,.8,1.4),0,-1.6,0)}
 else if(c=='adapter'){A(new THREE.BoxGeometry(2.6,1.4,2),0,-.7,0);A(new THREE.ConeGeometry(1,2,4),0,.9,0)}
 else if(c=='cutting_edge'){A(new THREE.BoxGeometry(6,.35,1.2));A(new THREE.BoxGeometry(6,.3,.5),0,-.3,.6)}
 else if(c=='bolt'){A(new THREE.CylinderGeometry(.5,.5,3,24),0,-.5,0);A(new THREE.CylinderGeometry(.9,.9,.6,6),0,1.3,0)}
 else if(c=='track_shoe'){A(new THREE.BoxGeometry(4,.3,1.6));for(let i=-1;i<=1;i++)A(new THREE.BoxGeometry(4,.35,.2),0,.3,i*.5)}
 else if(c=='liner'){A(new THREE.BoxGeometry(5,.25,3));for(let i=0;i<6;i++)A(new THREE.CylinderGeometry(.15,.15,.3,12),-2+i*.8,.2,0)}
 else if(c=='clamp'){A(new THREE.CylinderGeometry(2.4,2.4,3.2,40,1,true,0,Math.PI),0,0,0).rotation.z=-Math.PI/2;A(new THREE.BoxGeometry(2,1.4,1.1),0,-1.6,0);[-.5,.5].forEach(x=>A(new THREE.TorusGeometry(.32,.09,10,24),x,-.88,0).rotation.x=Math.PI/2)}
 else if(c=='hose'){A(new THREE.TorusGeometry(2,.25,16,48,4.2))}
 else{A(new THREE.CylinderGeometry(.6,.6,4.5,32),0,0,0,Math.PI/2);A(new THREE.CylinderGeometry(.9,.9,.5,32),2,0,0,Math.PI/2)}
 return g}
let mode=0,view=D?1:0,rel=null,T=0,TT=0,u=null,Z=null;const part=build(CAT);s.add(part);
function set(){part.visible=view==0;part.traverse(o=>{if(o.isMesh)o.material=M[mode]});
 if(rel){rel.visible=view==1;rel.material=Z[mode];upd()}
 lbl.textContent=['Hologram scan','Solid model','Realistic render'][mode]+' | '+(view?(TT?'Restorasi: merah = bagian hilang':'3D kondisi aktual'):'Model part kandidat')}
function play(){if(view==1&&rel){T=0;TT=1;mode=1;set();setTimeout(()=>{mode=2;set()},3800)}else{mode=0;set();setTimeout(()=>{mode=1;set()},1600);setTimeout(()=>{mode=2;set()},3200)}}
if(D){const b=atob(D);u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);
 const geo=new THREE.PlaneGeometry(6,6,95,95);geo.setAttribute('color',new THREE.BufferAttribute(new Float32Array(9216*3),3));
 Z=[new THREE.MeshBasicMaterial({vertexColors:true,wireframe:true}),new THREE.MeshStandardMaterial({vertexColors:true,metalness:.2,roughness:.6}),
  new THREE.MeshStandardMaterial({vertexColors:true,metalness:.8,roughness:.4,bumpMap:bump,bumpScale:.8})];
 rel=new THREE.Mesh(geo,Z[0]);rel.rotation.x=-Math.PI/2.4;rel.visible=false;s.add(rel);set()}
function upd(){if(!rel)return;const g=rel.geometry,p=g.attributes.position,c=g.attributes.color;
 for(let i=0;i<9216;i++){const a=u[i]/255,f=u[9216+i]/255,m=u[18432+i],q=u[27648+i];p.setZ(i,(a+(f-a)*T)*1.8);
  let x=.06,y=.1,z=.16;
  if(q||m){const k=.5+.1*((i*7)%5)/5,rd=m?(mode==2?1-T:1):0;x=k+(.95-k)*rd;y=k+(.15-k)*rd;z=k+(.12-k)*rd}
  else if(f>.08){x=y=z=.3}
  c.setXYZ(i,x,y,z)}
 p.needsUpdate=true;c.needsUpdate=true;g.computeVertexNormals()}
let drag=false,lx=0,ry=.6;cv.onmousedown=e=>{drag=true;lx=e.clientX};onmouseup=()=>drag=false;
onmousemove=e=>{if(drag){ry+=(e.clientX-lx)*.01;lx=e.clientX}};
(function a(){requestAnimationFrame(a);if(rel&&view==1&&Math.abs(TT-T)>.002){T+=(TT-T)*.04;upd()}if(!drag)ry+=.004;part.rotation.y=ry;if(rel)rel.rotation.z=ry;r.render(s,cam)})();
set();play();</script>"""

def uri(im):
    b = io.BytesIO(); im.convert("RGB").resize((128, 128)).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

def save_uploads(files, tag):
    out = []
    for i, f in enumerate(files or []):
        p = os.path.join(IMG, f"u_{tag}_{dt.datetime.now():%H%M%S%f}_{i}.png"); Image.open(f).convert("RGB").save(p); out.append(p)
    return out

# ---------- lokasi source pada unit (3D skala unit) ----------
LOC_T = {("Bak & Liner", "Liner & wear plate"): (-1.5, 3.7, 0, "lantai dan dinding dalam bak"), ("Bak & Liner", "Baut & pengencang"): (-2, 3.7, 1.2, "baut pengikat liner di dalam bak"),
 ("Bak & Liner", "Engsel & pin"): (-5, 3.3, 1.8, "engsel belakang bak"), ("Bak & Liner", "Karet & bantalan"): (-3, 3, 1.2, "bantalan karet antara bak dan rangka"),
 ("Hidrolik & Selang", "Hoist cylinder"): (-2, 3.2, 1.2, "dudukan silinder angkat bak"), ("Hidrolik & Selang", "Selang & clamp"): (.5, 2.65, -1, "di bawah bak, pada bundel selang antara rel rangka (sisi operator)"),
 ("Hidrolik & Selang", "Steering & rem"): (3.8, 2.2, 2.2, "area gardan depan"), ("Roda & Ban", "Roda"): (-3.2, 1.7, 3.1, "hub roda belakang"), ("Roda & Ban", "Rim"): (3.6, 1.7, 2.5, "rim roda depan"),
 ("Roda & Ban", "Ban"): (-3.2, 1.7, -3.1, "ban belakang sisi operator"), ("Suspensi & Rangka", "Suspensi"): (3.6, 2.3, 1.6, "strut suspensi depan"), ("Suspensi & Rangka", "Pelindung"): (0, 1.7, 0, "bagian bawah rangka"),
 ("Suspensi & Rangka", "Tangga & railing"): (4.3, 1.8, -2.8, "tangga akses depan sisi operator"), ("Suspensi & Rangka", "Baut"): (-1, 2.3, 1.1, "sambungan rangka"),
 ("Mesin & Penggerak", "Pendingin"): (5.4, 3, 0, "radiator dan kipas di depan"), ("Mesin & Penggerak", "Belt"): (4.6, 3, .6, "ruang mesin bagian depan"), ("Mesin & Penggerak", "Driveshaft"): (.5, 1.9, 0, "poros penggerak di bawah rangka"),
 ("Kabin & Elektrikal", "Kaca & lampu"): (3, 4.9, -2.9, "kabin sisi operator"), ("Kabin & Elektrikal", "Kabel"): (3.2, 3.4, -1, "harness di bawah kabin"), ("Kabin & Elektrikal", "Panel"): (3.6, 4.2, -2.9, "panel kabin")}
LOC_E = {("Bucket & GET", "Gigi & adapter"): (13.1, 1.3, .7, "ujung depan bucket (gigi)"), ("Bucket & GET", "Pelindung bucket"): (12.4, 1.2, 1.5, "tepi dan sisi bucket"), ("Bucket & GET", "Sambungan"): (11.2, 3.1, 0, "sambungan bucket dengan arm"),
 ("Boom & Arm", "Pin & bushing"): (7.2, 6.3, 0, "sambungan boom-arm"), ("Boom & Arm", "Pelindung"): (5, 5.5, .7, "silinder boom"), ("Boom & Arm", "Grease & selang"): (4, 4.8, .7, "jalur selang di sepanjang boom"),
 ("Undercarriage", "Track"): (1, .9, 3.6, "pelat track bagian luar"), ("Undercarriage", "Roller & guard"): (-1.5, .7, 3.6, "roller dan guard undercarriage"),
 ("Upper Structure", "Panel & tangga"): (-.5, 3.9, 2.8, "panel samping upper structure"), ("Upper Structure", "Counterweight"): (-4, 3, 0, "counterweight belakang"),
 ("Upper Structure", "Mesin & pendingin"): (-2.2, 3.9, 1.2, "ruang mesin"), ("Upper Structure", "Kabin & kabel"): (1.9, 4.9, -2, "kabin operator")}

UNIT_HTML = """<div style="position:relative"><canvas id=c style="width:100%;height:520px;display:block;border-radius:12px;touch-action:none"></canvas>
<div style="position:absolute;top:8px;left:10px;font:12px sans-serif;color:#7fe">Simulasi part &rarr; unit | geser = putar, scroll = zoom</div>
<div style="position:absolute;bottom:8px;left:8px;font:12px sans-serif;display:flex;gap:4px;flex-wrap:wrap">
<button onclick="play()">&#9654; Simulasi part &rarr; unit</button><button onclick="go('part')">Fokus part</button><button onclick="go('unit')">Tampak unit</button><button onclick="xr=!xr;paint()">X-ray</button></div></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script><script>
const CFG=__CFG__,cv=document.getElementById('c'),W=cv.clientWidth,H=520,SC=CFG.sc;
const r=new THREE.WebGLRenderer({canvas:cv,antialias:true});r.setSize(W,H,false);
const s=new THREE.Scene();s.background=new THREE.Color(0x0b1220);s.fog=new THREE.Fog(0x0b1220,70,170);
const cam=new THREE.PerspectiveCamera(45,W/H,.1,300);
s.add(new THREE.AmbientLight(0xffffff,.65));const L=new THREE.DirectionalLight(0xffffff,.9);L.position.set(20,30,15);s.add(L);
s.add(new THREE.GridHelper(80,80,0x1f6feb,0x16324f));
let xr=false;const U=new THREE.Group(),xm=[];U.scale.setScalar(SC);s.add(U);
function mat(c,m,ro){const k=new THREE.MeshStandardMaterial({color:c,metalness:m,roughness:ro,transparent:true});xm.push(k);return k}
const P=mat(CFG.col,.2,.55),D=mat(0x222a33,.1,.9),G=mat(0x8a97a6,.6,.4),K=mat(0x9ad7ff,.1,.2);
function paint(){xm.forEach(k=>{k.opacity=xr?.2:1;k.depthWrite=!xr})}
function B(w,h,d,x,y,z,m){const o=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),m||P);o.position.set(x,y,z);U.add(o);return o}
function Cy(rt,h,x,y,z,m,ax){const o=new THREE.Mesh(new THREE.CylinderGeometry(rt,rt,h,24),m||D);o.position.set(x,y,z);if(ax=='z')o.rotation.x=Math.PI/2;if(ax=='x')o.rotation.z=Math.PI/2;U.add(o);return o}
function beam(a,b,t,m){const dx=b[0]-a[0],dy=b[1]-a[1],o=new THREE.Mesh(new THREE.BoxGeometry(Math.hypot(dx,dy),t,t*1.2),m||P);o.position.set((a[0]+b[0])/2,(a[1]+b[1])/2,a[2]);o.rotation.z=Math.atan2(dy,dx);U.add(o);return o}
function tag(t,sz){const c=document.createElement('canvas');c.width=640;c.height=96;const x=c.getContext('2d');x.fillStyle='rgba(11,18,32,.8)';x.fillRect(0,8,640,76);x.font='bold 30px sans-serif';x.fillStyle='#fff';x.fillText(t,14,58);
 const sp=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(c),transparent:true,depthTest:false}));sp.scale.set(sz||9,sz?sz*.15:1.35,1);sp.renderOrder=12;return sp}
function truck(){
 [[3.6,2.5],[3.6,-2.5],[-3.2,1.5],[-3.2,2.6],[-3.2,-1.5],[-3.2,-2.6]].forEach(w=>Cy(1.7,1,w[0],1.7,w[1],D,'z'));
 B(10,.7,2.4,0,2.3,0,G);B(2.6,1.3,3.4,4.2,3,0);B(.15,1.1,2.8,5.55,3,0,D);
 B(2,2,1.8,3,4.3,-1.9);B(.1,1,1.5,4.02,4.6,-1.9,K);B(3.4,.3,5.6,4.6,5.8,0);
 B(8.4,.3,5.6,-1,3.5,0);B(8.4,1.9,.25,-1,4.5,2.7);B(8.4,1.9,.25,-1,4.5,-2.7);B(.3,2.2,5.6,3.1,4.6,0);
 Cy(.22,2.4,-2,3.2,1.2);Cy(.22,2.4,-2,3.2,-1.2);Cy(.12,4.2,.5,2.65,-1,D,'x');B(.35,.5,.5,.5,2.65,-1,G);B(.1,2.6,.6,4.3,1.4,-2.8,G)}
function exc(){
 [2.9,-2.9].forEach(z=>{B(8.2,1.4,1.3,0,.9,z,D);Cy(.9,1.3,4.1,.9,z,G,'z');Cy(.9,1.3,-4.1,.9,z,G,'z');B(8.2,.2,1.4,0,.15,z,G)});
 B(5.6,.8,4.8,0,1.7,0,G);B(7,1.6,5.4,-.4,2.9,0);B(1.6,2.1,5.2,-4,3,0,G);B(2.2,2.2,2,1.9,4.7,-1.8);B(.1,1.3,1.7,3.02,4.9,-1.8,K);
 beam([2.6,3.2,0],[7.2,6.3,0],.9);beam([7.2,6.3,0],[11.2,3.2,0],.7);beam([2.4,3.2,.8],[5.3,5.7,.8],.3,G);beam([5.9,6.4,.8],[8.7,5.2,.8],.3,G);
 B(2.2,1.8,3.4,12,2,0);for(let i=-2;i<=2;i++){const t=new THREE.Mesh(new THREE.ConeGeometry(.22,.8,4),G);t.position.set(13.4,1.3,i*.7);t.rotation.z=-Math.PI/2;U.add(t)}}
function human(x,z){const g=new THREE.Group(),m=new THREE.MeshStandardMaterial({color:0xff7a00}),n=new THREE.MeshStandardMaterial({color:0x334155});
 [-.12,.12].forEach(a=>{const l=new THREE.Mesh(new THREE.CylinderGeometry(.09,.09,.85),n);l.position.set(0,.43,a);g.add(l)});
 const t=new THREE.Mesh(new THREE.CylinderGeometry(.2,.2,.65),m);t.position.y=1.17;g.add(t);
 const h=new THREE.Mesh(new THREE.SphereGeometry(.13,16,16),new THREE.MeshStandardMaterial({color:0xe0b090}));h.position.y=1.62;g.add(h);
 g.position.set(x,0,z);s.add(g);const tg=tag('Orang 1,75 m',4);tg.position.set(x,2.3,z);s.add(tg)}
CFG.kind=='T'?truck():exc();human(CFG.hx,CFG.hz);paint();
const M=new THREE.Group(),rm=new THREE.MeshBasicMaterial({color:0xff2d2d,transparent:true,depthTest:false});
const core=new THREE.Mesh(new THREE.SphereGeometry(.3,20,20),rm);core.renderOrder=11;M.add(core);
const ringm=new THREE.MeshBasicMaterial({color:0xff2d2d,side:THREE.DoubleSide,transparent:true,depthTest:false}),ring=new THREE.Mesh(new THREE.RingGeometry(.5,.62,40),ringm);ring.rotation.x=-Math.PI/2;ring.renderOrder=11;M.add(ring);
const pole=new THREE.Mesh(new THREE.CylinderGeometry(.03,.03,6),new THREE.MeshBasicMaterial({color:0xff2d2d,depthTest:false}));pole.position.y=3;pole.renderOrder=11;M.add(pole);
const lab=tag('\\u25B6 '+CFG.lbl);lab.position.y=6.8;M.add(lab);M.position.set(CFG.pos[0],CFG.pos[1],CFG.pos[2]);U.add(M);
const V={part:{t:CFG.pos.map(v=>v*SC),r:Math.max(4.5,7*SC),th:CFG.pos[2]>=0?Math.PI/2:-Math.PI/2,ph:1.15},unit:{t:[CFG.cx*SC,3*SC,0],r:CFG.R*SC,th:.9,ph:1.1}};
let cur=JSON.parse(JSON.stringify(V.unit)),anim=null,drag=false,lx=0,ly=0;
function start(b,d){const a=JSON.parse(JSON.stringify(cur));a.th=b.th+(((a.th-b.th+Math.PI)%(2*Math.PI))+2*Math.PI)%(2*Math.PI)-Math.PI;anim={a:a,b:b,t0:performance.now(),d:d}}
function go(n){start(V[n],2400)}
function play(){anim=null;xr=true;paint();cur=JSON.parse(JSON.stringify(V.part));setTimeout(()=>start(V.unit,4500),1200);setTimeout(()=>{xr=false;paint()},6200)}
function down(e){drag=true;anim=null;const p=e.touches?e.touches[0]:e;lx=p.clientX;ly=p.clientY}
function move(e){if(!drag)return;const p=e.touches?e.touches[0]:e;cur.th-=(p.clientX-lx)*.008;cur.ph=Math.min(1.5,Math.max(.15,cur.ph-(p.clientY-ly)*.006));lx=p.clientX;ly=p.clientY}
cv.addEventListener('mousedown',down);cv.addEventListener('touchstart',down,{passive:true});addEventListener('mouseup',()=>{drag=false});addEventListener('touchend',()=>{drag=false});
addEventListener('mousemove',move);addEventListener('touchmove',move,{passive:true});
cv.addEventListener('wheel',e=>{e.preventDefault();cur.r=Math.max(2,Math.min(120,cur.r*(1+e.deltaY*.001)))},{passive:false});
(function a(){requestAnimationFrame(a);const t=performance.now();
 if(anim){let k=Math.min(1,(t-anim.t0)/anim.d);k=k*k*(3-2*k);['th','ph','r'].forEach(f=>{cur[f]=anim.a[f]+(anim.b[f]-anim.a[f])*k});cur.t=anim.a.t.map((v,i)=>v+(anim.b.t[i]-v)*k);if(k>=1)anim=null}
 else if(!drag)cur.th+=.002;
 const q=(t/800)%1;core.scale.setScalar(1+.2*Math.sin(t/180));ring.scale.setScalar(1+q*2);ringm.opacity=1-q;
 cam.position.set(cur.t[0]+cur.r*Math.sin(cur.ph)*Math.cos(cur.th),cur.t[1]+cur.r*Math.cos(cur.ph),cur.t[2]+cur.r*Math.sin(cur.ph)*Math.sin(cur.th));
 cam.lookAt(cur.t[0],cur.t[1],cur.t[2]);r.render(s,cam)})();
play();</script>"""

def unit_scene(unit_model, sistem, assembly, part_name):
    c = db(); u = c.execute("select merek,tipe,k from units where model=?", (unit_model,)).fetchone(); c.close()
    if not u: return None
    merek, tipe, k = u; tp = (tipe or "").lower(); kind = "T" if "truck" in tp else "E" if "excavator" in tp else None
    if kind is None: return None
    sistem = sistem if isinstance(sistem, str) else ""; assembly = assembly if isinstance(assembly, str) else ""
    T = LOC_T if kind == "T" else LOC_E
    hit = T.get((sistem, assembly)) or next((v for (a, b), v in T.items() if a == sistem), None) or (0, 3, 0, "pusat unit (lokasi detail belum dipetakan)")
    col = {"Komatsu": "#f2b705", "Caterpillar": "#ffc20e", "Hitachi": "#ff8c1a"}.get(merek, "#e0b000")
    cfg = dict(kind=kind, pos=list(hit[:3]), lbl=str(part_name)[:34], sc=1.0 if kind == "T" else round(max(.55, k ** .3), 2), col=col,
               R=24 if kind == "T" else 30, cx=.5 if kind == "T" else 3, hx=7.2 if kind == "T" else 6, hz=-1.5 if kind == "T" else 4.5)
    return dict(cfg=cfg, desc=f"{sistem or '(sistem belum dipetakan)'} > {assembly or '-'}: {hit[3]}", html=UNIT_HTML.replace("__CFG__", json.dumps(cfg)))
