"""SQLite data layer.

The catalog (units, parts, specs, history) is seeded once from ``data/catalog.json``.
After that the database is the source of truth and is edited from the Streamlit pages.
Set ``CT_DB_PATH`` to move the database file (for example to a mounted volume).
"""
from __future__ import annotations

import base64
import io
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from core import cloud

LAST_SYNC_ERROR = [""]
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PHOTO_DIR = DATA / "photos"
SEED = DATA / "catalog.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS units(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, maker TEXT, kind TEXT, fleet INTEGER DEFAULT 0,
  hm TEXT, descr TEXT, ts REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS unit_spec(
  unit_id TEXT NOT NULL, label TEXT NOT NULL, value TEXT, src TEXT DEFAULT 'indikatif',
  PRIMARY KEY(unit_id, label));
CREATE TABLE IF NOT EXISTS parts(
  id TEXT PRIMARY KEY, unit_id TEXT NOT NULL, name TEXT NOT NULL, part_no TEXT DEFAULT '—',
  system TEXT DEFAULT 'Lainnya', asm TEXT DEFAULT 'Umum', kind TEXT DEFAULT 'bolt',
  type TEXT DEFAULT 'metal', material TEXT DEFAULT '—', l REAL DEFAULT 100, w REAL DEFAULT 100,
  h REAL DEFAULT 100, qty INTEGER DEFAULT 1, fm INTEGER DEFAULT 1, incidents INTEGER DEFAULT 0,
  note TEXT DEFAULT '', color TEXT DEFAULT '#5d636a');
CREATE INDEX IF NOT EXISTS idx_parts_unit ON parts(unit_id);
CREATE TABLE IF NOT EXISTS history(
  id INTEGER PRIMARY KEY AUTOINCREMENT, part_id TEXT NOT NULL, date TEXT, hm REAL, reason TEXT);
CREATE TABLE IF NOT EXISTS photos(
  id INTEGER PRIMARY KEY AUTOINCREMENT, part_id TEXT NOT NULL, role TEXT NOT NULL, file TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inspections(
  lambung TEXT NOT NULL, part_id TEXT NOT NULL, status TEXT NOT NULL, date TEXT, note TEXT,
  PRIMARY KEY(lambung, part_id));
CREATE TABLE IF NOT EXISTS cases(
  id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, loc TEXT, unit_id TEXT, part_id TEXT,
  lambung TEXT, note TEXT, builtin INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS operations(
  date TEXT NOT NULL, lambung TEXT NOT NULL, area TEXT, PRIMARY KEY(date, lambung));
CREATE TABLE IF NOT EXISTS users(
  username TEXT PRIMARY KEY, name TEXT, role TEXT NOT NULL, pw_hash TEXT NOT NULL,
  active INTEGER DEFAULT 1, must_change INTEGER DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user TEXT, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS attempts(username TEXT NOT NULL, ts REAL NOT NULL);
"""

STATUSES = ["belum", "lengkap", "hilang", "rusak"]
PART_COLUMNS = ["id", "unit_id", "name", "part_no", "system", "asm", "kind", "type", "material",
                "l", "w", "h", "qty", "fm", "incidents", "note", "color"]


SEED_VERSION = 2


def db_path() -> Path:
    return Path(os.environ.get("CT_DB_PATH", DATA / "tracker.db"))


@contextmanager
def connect(path: str | Path | None = None):
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
        _flush(con)
    finally:
        con.close()


def _flush(con: sqlite3.Connection) -> None:
    """Best effort push to Supabase; a failure keeps the changes queued and is retried on the next write."""
    if not cloud.enabled():
        return
    try:
        if cloud.pending(con):
            cloud.flush(con, DATA)
            con.commit()
    except (cloud.CloudError, sqlite3.Error, OSError) as e:
        LAST_SYNC_ERROR[0] = str(e)
    else:
        LAST_SYNC_ERROR[0] = ""


def init_db(path: str | Path | None = None) -> None:
    """Create tables and seed the catalog on first run."""
    with connect(path) as con:
        con.executescript(SCHEMA + cloud.trigger_sql())
        if con.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 0 and cloud.enabled() and _try_pull(con):
            return
        if con.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 0 and SEED.exists():
            _seed(con)
            con.execute(f"PRAGMA user_version={SEED_VERSION}")
        elif con.execute("PRAGMA user_version").fetchone()[0] < SEED_VERSION and SEED.exists():
            _sync_new_parts(con)
            con.execute(f"PRAGMA user_version={SEED_VERSION}")


def _try_pull(con: sqlite3.Connection) -> bool:
    """Fresh local database: rebuild it from Supabase when the cloud already holds data."""
    try:
        if not cloud.remote_has_data():
            return False
        cloud.pull_all(con, DATA)
        return True
    except (cloud.CloudError, sqlite3.Error, OSError) as e:
        LAST_SYNC_ERROR[0] = str(e)
        return False


def cloud_pull(path=None) -> dict:
    """Manual: replace local data with the cloud copy (changes still queued locally are pushed first)."""
    with connect(path) as con:
        cloud.flush(con, DATA)
        return cloud.pull_all(con, DATA)


def cloud_push_all(path=None) -> int:
    with connect(path) as con:
        return cloud.push_all(con, DATA)


def _sync_new_parts(con: sqlite3.Connection) -> None:
    """Add seed parts that older databases do not have yet (never touches existing rows)."""
    cat = json.loads(SEED.read_text(encoding="utf-8"))
    for p in cat["parts"]:
        if con.execute("SELECT 1 FROM parts WHERE id=?", (p["id"],)).fetchone():
            continue
        con.execute(
            "INSERT INTO parts(id,unit_id,name,part_no,system,asm,kind,type,material,l,w,h,qty,fm,incidents,note,color)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p["id"], p["unitId"], p["name"], p.get("partNo", "—"), p.get("system", "Lainnya"),
             p.get("asm", "Umum"), p["kind"], p["type"], p.get("material", "—"), p["L"], p["W"], p["H"],
             p.get("qty", 1), 1 if p.get("fm", True) else 0, p.get("incidents", 0), p.get("note", ""),
             p.get("color", "#5d636a")))


def _seed(con: sqlite3.Connection) -> None:
    cat = json.loads(SEED.read_text(encoding="utf-8"))
    for u in cat["units"]:
        con.execute("INSERT OR REPLACE INTO units(id,name,maker,kind,fleet,hm,descr) VALUES(?,?,?,?,?,?,?)",
                    (u["id"], u["name"], u.get("maker", "Komatsu"), u["kind"], u.get("fleet", 0),
                     u.get("hm", ""), u.get("desc", "")))
    for uid, sp in cat["spec"].items():
        for label, value, src in sp["rows"]:
            con.execute("INSERT OR REPLACE INTO unit_spec(unit_id,label,value,src) VALUES(?,?,?,?)",
                        (uid, label, value, src))
    for p in cat["parts"]:
        con.execute(
            "INSERT OR REPLACE INTO parts(id,unit_id,name,part_no,system,asm,kind,type,material,l,w,h,qty,fm,incidents,note,color)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p["id"], p["unitId"], p["name"], p.get("partNo", "—"), p.get("system", "Lainnya"),
             p.get("asm", "Umum"), p["kind"], p["type"], p.get("material", "—"), p["L"], p["W"], p["H"],
             p.get("qty", 1), 1 if p.get("fm", True) else 0, p.get("incidents", 0), p.get("note", ""),
             p.get("color", "#5d636a")))
        for h in p.get("history", []):
            con.execute("INSERT INTO history(part_id,date,hm,reason) VALUES(?,?,?,?)",
                        (p["id"], h["date"], h["hm"], h["reason"]))
    for ph in cat.get("photos", []):
        con.execute("INSERT INTO photos(part_id,role,file) VALUES(?,?,?)", (ph["part_id"], ph["role"], ph["file"]))
    for c in cat.get("cases", []):
        con.execute("INSERT INTO cases(date,loc,unit_id,part_id,lambung,note,builtin) VALUES(?,?,?,?,?,?,1)",
                    (c["date"], c["loc"], c["unitId"], c["partId"], c["no"], c["note"]))


def meta() -> dict:
    cat = json.loads(SEED.read_text(encoding="utf-8"))
    return {"kind_label": cat["kind_label"], "fleet": cat["fleet"], "area_units": cat["area_units"]}


# ---------- units ----------
def list_units(path=None) -> list[dict]:
    with connect(path) as con:
        return [dict(r) for r in con.execute("SELECT * FROM units ORDER BY kind, name")]


def save_unit(u: dict, path=None) -> None:
    with connect(path) as con:
        con.execute("INSERT OR REPLACE INTO units(id,name,maker,kind,fleet,hm,descr) VALUES(?,?,?,?,?,?,?)",
                    (u["id"], u["name"], u.get("maker", ""), u.get("kind", "Unit"), int(u.get("fleet") or 0),
                     u.get("hm", ""), u.get("descr", "")))


# ---------- parts ----------
def list_parts(unit_id: str | None = None, path=None) -> list[dict]:
    q, args = "SELECT * FROM parts", ()
    if unit_id:
        q, args = q + " WHERE unit_id=?", (unit_id,)
    with connect(path) as con:
        return [dict(r) for r in con.execute(q + " ORDER BY unit_id, system, asm, name", args)]


def next_part_id(con: sqlite3.Connection) -> str:
    n = con.execute("SELECT COUNT(*) FROM parts WHERE id LIKE 'u%'").fetchone()[0]
    while True:
        n += 1
        pid = f"u{n:04d}"
        if not con.execute("SELECT 1 FROM parts WHERE id=?", (pid,)).fetchone():
            return pid


def save_parts(unit_id: str, rows: list[dict], path=None) -> dict:
    """Replace the parts of one unit with ``rows`` (insert, update and delete in one transaction)."""
    added = updated = 0
    with connect(path) as con:
        existing = {r["id"] for r in con.execute("SELECT id FROM parts WHERE unit_id=?", (unit_id,))}
        keep = set()
        for r in rows:
            if not str(r.get("name") or "").strip():
                continue
            pid = str(r.get("id") or "").strip()
            if not pid or pid == "None":
                pid = next_part_id(con)
            keep.add(pid)
            vals = (unit_id, str(r["name"]).strip(), r.get("part_no") or "—", r.get("system") or "Lainnya",
                    r.get("asm") or "Umum", r.get("kind") or "bolt", r.get("type") or "metal",
                    r.get("material") or "—", float(r.get("l") or 100), float(r.get("w") or 100),
                    float(r.get("h") or 100), int(r.get("qty") or 1), 1 if r.get("fm", True) else 0,
                    int(r.get("incidents") or 0), r.get("note") or "", r.get("color") or "#5d636a")
            if pid in existing:
                con.execute("UPDATE parts SET unit_id=?,name=?,part_no=?,system=?,asm=?,kind=?,type=?,material=?,"
                            "l=?,w=?,h=?,qty=?,fm=?,incidents=?,note=?,color=? WHERE id=?", vals + (pid,))
                updated += 1
            else:
                con.execute("INSERT INTO parts(unit_id,name,part_no,system,asm,kind,type,material,l,w,h,qty,fm,"
                            "incidents,note,color,id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", vals + (pid,))
                added += 1
        gone = existing - keep
        for pid in gone:
            con.execute("DELETE FROM parts WHERE id=?", (pid,))
            con.execute("DELETE FROM history WHERE part_id=?", (pid,))
            con.execute("DELETE FROM photos WHERE part_id=?", (pid,))
    return {"added": added, "updated": updated, "deleted": len(gone)}


def add_history(part_id: str, date: str, hm: float, reason: str, path=None) -> None:
    with connect(path) as con:
        con.execute("INSERT INTO history(part_id,date,hm,reason) VALUES(?,?,?,?)", (part_id, date, hm, reason))


def add_photo(part_id: str, data: bytes, role: str = "ref", path=None) -> str:
    """Save an uploaded photo (resized to max 480 px) and register it."""
    from PIL import Image

    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((480, 480))
    with connect(path) as con:
        n = con.execute("SELECT COUNT(*) FROM photos WHERE part_id=?", (part_id,)).fetchone()[0] + 1
        name = f"{part_id}_{role}{n}.jpg"
        im.save(PHOTO_DIR / name, quality=78)
        con.execute("INSERT INTO photos(part_id,role,file) VALUES(?,?,?)", (part_id, role, f"photos/{name}"))
    return name


# ---------- inspections, cases, operations ----------
def lambung_list(unit_id: str, fleet: dict | None = None, path=None) -> list[str]:
    fleet = fleet or meta()["fleet"]
    if unit_id in fleet:
        start, n = fleet[unit_id]
        return [str(start + i) for i in range(n)]
    with connect(path) as con:
        row = con.execute("SELECT fleet FROM units WHERE id=?", (unit_id,)).fetchone()
    return [str(900 + i) for i in range(min(40, (row["fleet"] if row else 0) or 0))]


def set_inspection(lambung: str, part_id: str, status: str, date: str = "", note: str = "", path=None) -> None:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with connect(path) as con:
        con.execute("INSERT OR REPLACE INTO inspections(lambung,part_id,status,date,note) VALUES(?,?,?,?,?)",
                    (str(lambung), part_id, status, date, note))


def list_inspections(path=None) -> list[dict]:
    with connect(path) as con:
        return [dict(r) for r in con.execute("SELECT * FROM inspections")]


def add_case(date: str, loc: str, unit_id: str, part_id: str, lambung: str, note: str = "", path=None) -> int:
    with connect(path) as con:
        cur = con.execute("INSERT INTO cases(date,loc,unit_id,part_id,lambung,note) VALUES(?,?,?,?,?,?)",
                          (date, loc, unit_id, part_id, str(lambung), note))
        return int(cur.lastrowid)


def list_cases(path=None) -> list[dict]:
    with connect(path) as con:
        return [dict(r) for r in con.execute("SELECT * FROM cases ORDER BY date DESC, id DESC")]


def delete_case(case_id: int, path=None) -> None:
    with connect(path) as con:
        con.execute("DELETE FROM cases WHERE id=? AND builtin=0", (case_id,))


def import_operations(rows: list[dict], path=None) -> int:
    n = 0
    with connect(path) as con:
        for r in rows:
            d, lb = str(r.get("date") or "").strip(), str(r.get("lambung") or "").strip()
            if d and lb:
                con.execute("INSERT OR REPLACE INTO operations(date,lambung,area) VALUES(?,?,?)",
                            (d, lb, str(r.get("area") or "")))
                n += 1
    return n


# ---------- payload for the front end ----------
def _b64(rel: str) -> str:
    return "data:image/jpeg;base64," + base64.b64encode((DATA / rel).read_bytes()).decode()


def export_payload(path=None, photo_fn=None) -> dict:
    """Whole database as one JSON-able dict. ``photo_fn(rel_path)`` turns a photo path into what is stored
    (default: an inline data URI; the data package stores the relative path instead)."""
    photo_fn = photo_fn or _b64
    m = meta()
    with connect(path) as con:
        units = [dict(r) for r in con.execute("SELECT * FROM units ORDER BY kind, name")]
        parts = [dict(r) for r in con.execute("SELECT * FROM parts")]
        hist: dict[str, list] = {}
        for h in con.execute("SELECT * FROM history ORDER BY date DESC"):
            hist.setdefault(h["part_id"], []).append({"date": h["date"], "hm": h["hm"], "reason": h["reason"]})
        photos: dict[str, list] = {}
        sample = {"find": [], "ref": []}
        for ph in con.execute("SELECT * FROM photos"):
            f = DATA / ph["file"]
            if not f.exists():
                continue
            if ph["role"] == "find":
                sample["find"].append(photo_fn(ph["file"]))
            else:
                photos.setdefault(ph["part_id"], []).append(photo_fn(ph["file"]))
        spec: dict[str, dict] = {}
        for s in con.execute("SELECT * FROM unit_spec"):
            spec.setdefault(s["unit_id"], {"src": "database", "rows": []})["rows"].append([s["label"], s["value"], s["src"]])
        inspect = {f'{r["lambung"]}|{r["part_id"]}': {"no": r["lambung"], "partId": r["part_id"], "status": r["status"],
                                                       "date": r["date"]} for r in con.execute("SELECT * FROM inspections")}
        cases = [{"id": f'c{r["id"]}', "builtin": bool(r["builtin"]), "date": r["date"], "loc": r["loc"], "partId": r["part_id"],
                  "unitId": r["unit_id"], "no": r["lambung"], "note": r["note"]} for r in con.execute("SELECT * FROM cases")]
        ops = {f'{r["lambung"]}|{r["date"]}': r["area"] for r in con.execute("SELECT * FROM operations")}
    jparts = [{"id": p["id"], "unitId": p["unit_id"], "name": p["name"], "partNo": p["part_no"], "system": p["system"],
               "asm": p["asm"], "kind": p["kind"], "type": p["type"], "material": p["material"], "L": p["l"], "W": p["w"],
               "H": p["h"], "qty": p["qty"], "fm": bool(p["fm"]), "incidents": p["incidents"], "note": p["note"],
               "color": p["color"], "history": hist.get(p["id"], []), "photos": photos.get(p["id"], []), "builtin": True}
              for p in parts]
    junits = [{"id": u["id"], "name": u["name"], "maker": u["maker"], "kind": u["kind"], "fleet": u["fleet"], "hm": u["hm"],
               "desc": u["descr"]} for u in units]
    return {"kind_label": m["kind_label"], "units": junits, "parts": jparts, "spec": spec, "fleet": m["fleet"],
            "area_units": m["area_units"], "cases": cases, "inspect": inspect, "ops": ops, "sample": sample}
