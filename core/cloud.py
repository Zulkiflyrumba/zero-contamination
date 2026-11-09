"""Supabase sync (optional).

SQLite stays the working copy. Every change is recorded by triggers in ``_outbox`` and pushed to Supabase
(PostgREST + Storage) with the **service key**, which only ever lives on the server (env vars or Streamlit
secrets). When the local database is empty (a fresh Streamlit container) it is rebuilt from Supabase.
Nothing here runs unless ``SUPABASE_URL`` and ``SUPABASE_SERVICE_KEY`` are set.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# table -> primary key columns. ``attempts`` (login lockout) stays local on purpose.
TABLES: dict[str, list[str]] = {
    "units": ["id"],
    "unit_spec": ["unit_id", "label"],
    "parts": ["id"],
    "history": ["id"],
    "photos": ["id"],
    "inspections": ["lambung", "part_id"],
    "cases": ["id"],
    "operations": ["date", "lambung"],
    "users": ["username"],
    "audit": ["id"],
}
EXTRA_PK = {"meta": ["key"], "field_submissions": ["id"]}
BUCKET = "ct-files"
BATCH = 400
PAGE = 1000


class CloudError(RuntimeError):
    pass


def _cfg(name: str) -> str:
    v = os.environ.get(name, "")
    if not v:
        try:  # Streamlit secrets, when running inside Streamlit
            import streamlit as st

            v = str(st.secrets.get(name, "") or "")
        except Exception:  # noqa: BLE001 - st.secrets raises several types when no secrets file exists
            v = ""
    return v.strip()


def url() -> str:
    return _cfg("SUPABASE_URL").rstrip("/")


def enabled() -> bool:
    return bool(url() and _cfg("SUPABASE_SERVICE_KEY"))


def _req(method: str, path: str, body: bytes | None = None, headers: dict | None = None, timeout: int = 30):
    key = _cfg("SUPABASE_SERVICE_KEY")
    h = {"apikey": key}
    if not key.startswith("sb_"):  # new-style sb_secret_ keys are not JWTs and go in apikey only
        h["Authorization"] = f"Bearer {key}"
    h.update(headers or {})
    r = urllib.request.Request(url() + path, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        raise CloudError(f"{method} {path.split('?')[0]} -> {e.code} {e.read()[:200]!r}") from e
    except urllib.error.URLError as e:
        raise CloudError(f"Tidak bisa menghubungi Supabase: {e.reason}") from e


def _json(rows) -> bytes:
    return json.dumps(rows, ensure_ascii=False).encode()


def pk(table: str) -> list[str]:
    return TABLES.get(table) or EXTRA_PK[table]


def upsert(table: str, rows: list[dict]) -> None:
    on = ",".join(pk(table))
    for i in range(0, len(rows), BATCH):
        _req("POST", f"/rest/v1/{table}?on_conflict={on}", _json(rows[i:i + BATCH]),
             {"Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"})


def delete(table: str, key: dict) -> None:
    q = "&".join(f"{k}=eq.{urllib.parse.quote(str(v), safe='')}" for k, v in key.items())
    _req("DELETE", f"/rest/v1/{table}?{q}", None, {"Prefer": "return=minimal"})


def fetch(table: str) -> list[dict]:
    out: list[dict] = []
    while True:
        _, raw = _req("GET", f"/rest/v1/{table}?select=*&order={','.join(TABLES[table])}&limit={PAGE}&offset={len(out)}")
        page = json.loads(raw or b"[]")
        out += page
        if len(page) < PAGE:
            return out


def get_json(path: str):
    return json.loads(_req("GET", path)[1] or b"[]")


def patch(table: str, match: dict, fields: dict) -> None:
    q = "&".join(f"{k}=eq.{urllib.parse.quote(str(v), safe='')}" for k, v in match.items())
    _req("PATCH", f"/rest/v1/{table}?{q}", _json(fields), {"Content-Type": "application/json", "Prefer": "return=minimal"})


def set_meta(key: str, value: str) -> None:
    upsert("meta", [{"key": key, "value": value}])


def get_meta(key: str) -> str | None:
    rows = get_json(f"/rest/v1/meta?key=eq.{urllib.parse.quote(key, safe='')}&select=value")
    return rows[0]["value"] if rows else None


def bump_version() -> str:
    """New data version: the APK compares it with the one it holds to know an update exists."""
    v = datetime.now(timezone.utc).strftime("%Y.%m.%d.%H%M%S")
    set_meta("data_version", v)
    return v


def publish_static(force: bool = False) -> None:
    """Catalog metadata and 3D model files for the APK (models are uploaded only when they changed)."""
    from core import db, models

    set_meta("catalog_meta", json.dumps(db.meta(), ensure_ascii=False, separators=(",", ":")))
    man = models.manifest()
    set_meta("models", json.dumps(man, ensure_ascii=False, separators=(",", ":")))
    sig = hashlib.sha256(json.dumps(
        [(u, n, (models.MODELS / u / n).stat().st_size) for u, c in man.items() for n in c.get("files", [])
         if (models.MODELS / u / n).exists()]).encode()).hexdigest()[:16]
    if force or get_meta("models_sig") != sig:
        for u, c in man.items():
            for n in c.get("files", []):
                f = models.MODELS / u / n
                if f.exists():
                    upload_file(f"models/{u}/{n}", f.read_bytes(), mimetypes.guess_type(n)[0] or "application/octet-stream")
        set_meta("models_sig", sig)


def remote_has_data() -> bool:
    _, raw = _req("GET", "/rest/v1/units?select=id&limit=1")
    return bool(json.loads(raw or b"[]"))


# ---------- files (Storage) ----------
def _obj(path: str) -> str:
    return f"/storage/v1/object/{BUCKET}/" + urllib.parse.quote(path)


def upload_file(path: str, data: bytes, ctype: str = "image/jpeg") -> None:
    _req("POST", _obj(path), data, {"Content-Type": ctype, "x-upsert": "true"})


def download_file(path: str) -> bytes | None:
    try:
        return _req("GET", _obj(path))[1]
    except CloudError:
        return None


# ---------- outbox / pull (SQLite side) ----------
def trigger_sql() -> str:
    """Triggers that record every change in ``_outbox``."""
    out = ["CREATE TABLE IF NOT EXISTS _outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, tbl TEXT NOT NULL, key TEXT NOT NULL);"]
    for t, pk in TABLES.items():
        new = ",".join(f"'{c}',NEW.{c}" for c in pk)
        old = ",".join(f"'{c}',OLD.{c}" for c in pk)
        out.append(f"CREATE TRIGGER IF NOT EXISTS ob_{t}_i AFTER INSERT ON {t} BEGIN "
                   f"INSERT INTO _outbox(tbl,key) VALUES('{t}',json_object({new})); END;")
        out.append(f"CREATE TRIGGER IF NOT EXISTS ob_{t}_u AFTER UPDATE ON {t} BEGIN "
                   f"INSERT INTO _outbox(tbl,key) VALUES('{t}',json_object({new})); END;")
        out.append(f"CREATE TRIGGER IF NOT EXISTS ob_{t}_d AFTER DELETE ON {t} BEGIN "
                   f"INSERT INTO _outbox(tbl,key) VALUES('{t}',json_object({old})); END;")
    return "\n".join(out)


def pending(con) -> int:
    return con.execute("SELECT COUNT(*) FROM _outbox").fetchone()[0]


def flush(con, data_dir: Path) -> int:
    """Push queued changes. Rows are re-read from SQLite, so only the final state of each key is sent."""
    rows = con.execute("SELECT id,tbl,key FROM _outbox ORDER BY id").fetchall()
    if not rows:
        return 0
    last: dict[tuple[str, str], int] = {}
    for r in rows:
        last[(r["tbl"], r["key"])] = r["id"]
    ups: dict[str, list[dict]] = {}
    for tbl, key in last:
        k = json.loads(key)
        where = " AND ".join(f"{c}=?" for c in TABLES[tbl])
        row = con.execute(f"SELECT * FROM {tbl} WHERE {where}", [k[c] for c in TABLES[tbl]]).fetchone()
        if row is None:
            delete(tbl, k)
        else:
            ups.setdefault(tbl, []).append(dict(row))
    for tbl, items in ups.items():
        if tbl == "photos":
            for it in items:
                f = data_dir / it["file"]
                if f.exists():
                    upload_file(it["file"], f.read_bytes())
        upsert(tbl, items)
    con.execute("DELETE FROM _outbox WHERE id<=?", (rows[-1]["id"],))
    bump_version()
    return len(last)


def push_all(con, data_dir: Path) -> int:
    """Queue every row (first upload, or a manual full re-push) and flush."""
    for t, pk in TABLES.items():
        cols = ",".join(pk)
        for r in con.execute(f"SELECT {cols} FROM {t}").fetchall():
            con.execute("INSERT INTO _outbox(tbl,key) VALUES(?,?)", (t, json.dumps(dict(r))))
    return flush(con, data_dir)


def pull_all(con, data_dir: Path) -> dict:
    """Replace local tables with the cloud copy and fetch photo files that are missing locally."""
    counts: dict[str, int] = {}
    for t in TABLES:
        rows = fetch(t)
        counts[t] = len(rows)
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        con.execute(f"DELETE FROM {t}")
        for r in rows:
            use = [c for c in cols if c in r]
            con.execute(f"INSERT INTO {t}({','.join(use)}) VALUES({','.join('?' * len(use))})", [r[c] for c in use])
    con.execute("DELETE FROM _outbox")
    for r in con.execute("SELECT file FROM photos").fetchall():
        f = data_dir / r["file"]
        if not f.exists():
            blob = download_file(r["file"])
            if blob:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(blob)
    return counts
