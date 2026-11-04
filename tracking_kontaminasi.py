"""ContamTrack 3D - platform tracking kontaminasi PIT/ROM.
Jalankan: pip install streamlit pillow numpy pandas
          streamlit run tracking_kontaminasi.py
"""
import streamlit as st, sqlite3, os, io, base64, math, datetime as dt
import numpy as np, pandas as pd
from PIL import Image, ImageDraw, ImageFilter
import streamlit.components.v1 as components

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kontaminasi_data")
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
    asp = (xs.ptp() + 1) / (ys.ptp() + 1) if len(xs) else 1
    return np.concatenate([h, o, [m.mean(), asp / (1 + asp)]])

def sim(f1, f2): return float(np.exp(-3 * np.abs(f1 - f2).sum() / 2))

def analyse(imgs, mat, size, mark, loc, day):
    c = db(); P = pd.read_sql("select * from parts", c); H = pd.read_sql("select * from history", c); C = pd.read_sql("select * from cases", c); c.close()
    fs = [feat(i) for i in imgs]; rows = []
    for _, p in P.iterrows():
        refs = [feat(Image.open(f)) for f in (p.imgs or "").split("|") if f and os.path.exists(f)]
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
                         Ukuran=sz, Marking=mk, Histori=hs, Kasus=ks, kn=kn, Skor=tot, note=p.notes, hn=hn, imgs=p.imgs))
    R = pd.DataFrame(rows).sort_values("Skor", ascending=False).reset_index(drop=True)
    e = np.exp(R.Skor * 10); R["Peluang"] = e / e.sum() * 100
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

# ---------- UI ----------
st.set_page_config(page_title="ContamTrack 3D", page_icon="🛰️", layout="wide"); init()
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
        st.session_state.res = analyse(imgs, mat, size, mark, loc, day); st.session_state.act = imgs
    if "res" in st.session_state:
        R = st.session_state.res; st.subheader("Peringkat kemiripan")
        st.dataframe(R.head(8)[["Unit", "Part", "PartNo", "Peluang", "Skor"]], hide_index=True, use_container_width=True,
                     column_config={"Peluang": st.column_config.ProgressColumn("Peluang (%)", min_value=0, max_value=100, format="%.0f%%"),
                                    "Skor": st.column_config.NumberColumn(format="%.2f")})
        top = R.head(5); sel = st.selectbox("Lihat diagnostik & 3D", top.index, format_func=lambda i: f"#{i+1} {R.Unit[i]} - {R.Part[i]}")
        r = R.loc[sel]; rs = restore(st.session_state.act, r.imgs.split("|")); g1, g2 = st.columns([3, 2])
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
    c = db(); P = pd.read_sql("select id,unit_model,part_name,part_no,category,material,dim_mm,weight_kg,marking,notes,imgs from parts", c); c.close()
    P["jml_foto"] = P.imgs.str.count(r"\|") + 1; st.dataframe(P.drop(columns="imgs"), hide_index=True, use_container_width=True)
    with st.expander("➕ Tambah part baru", expanded=False):
        f = st.columns(4); u = f[0].text_input("Unit/model"); pn = f[1].text_input("Nama part"); no = f[2].text_input("Part number"); ct = f[3].selectbox("Kategori 3D", CATS)
        g = st.columns(4); mt = g[0].text_input("Material"); dm = g[1].number_input("Dimensi (mm)", 0., 5000., 100.); wt = g[2].number_input("Berat (kg)", 0., 500., 1.); mk = g[3].text_input("Marking")
        nt = st.text_area("Keterangan / mode kerusakan"); ph = st.file_uploader("Foto part (banyak sudut)", accept_multiple_files=True, key="np")
        if st.button("Simpan part") and u and pn:
            c = db(); c.execute("insert into parts(unit_model,part_name,part_no,category,material,dim_mm,weight_kg,marking,notes,imgs) values(?,?,?,?,?,?,?,?,?,?)",
                                (u, pn, no, ct, mt, dm, wt, mk, nt, "|".join(save_uploads(ph, "new")))); c.commit(); c.close(); st.rerun()
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
