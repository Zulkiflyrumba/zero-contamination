"""Cloud sync against an in-memory fake of the Supabase REST + Storage API."""
import io
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest
from PIL import Image

from core import cloud, db, users


class Fake(BaseHTTPRequestHandler):
    tables: ClassVar[dict] = {}
    files: ClassVar[dict] = {}
    fail = False
    seen_keys: ClassVar[set] = set()

    def log_message(self, *a):
        pass

    def _send(self, code=200, body=b""):
        self.send_response(code)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def _handle(self, method):
        Fake.seen_keys.add(self.headers.get("apikey"))
        if Fake.fail:
            return self._send(500, b"boom")
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path.startswith("/storage/v1/object/ct-files/"):
            name = urllib.parse.unquote(u.path.split("/ct-files/", 1)[1])
            if method == "POST":
                Fake.files[name] = self._body()
                return self._send()
            return self._send(200, Fake.files[name]) if name in Fake.files else self._send(404)
        t = u.path.rsplit("/", 1)[1]
        tab = Fake.tables.setdefault(t, {})
        pk = cloud.pk(t)
        flt = {k: v[0] for k, v in q.items() if v[0].startswith(("eq.", "neq."))}

        def match(r):
            for c, v in flt.items():
                ok = str(r.get(c)) == v.split(".", 1)[1]
                if ok == v.startswith("neq."):
                    return False
            return True

        if method == "PATCH":
            for r in tab.values():
                if match(r):
                    r.update(json.loads(self._body()))
            return self._send(204)
        if method == "POST":
            for r in json.loads(self._body()):
                tab[tuple(r[c] for c in pk)] = r
            return self._send(201)
        if method == "DELETE":
            for k in [k for k, r in tab.items() if match(r)]:
                del tab[k]
            return self._send(204)
        rows = [r for r in tab.values() if match(r)]
        off, lim = int(q.get("offset", ["0"])[0]), int(q.get("limit", ["1000"])[0])
        return self._send(200, json.dumps(rows[off:off + lim]).encode())

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PATCH(self):
        self._handle("PATCH")

    def do_DELETE(self):
        self._handle("DELETE")


@pytest.fixture()
def fake(monkeypatch, tmp_path):
    Fake.tables, Fake.files, Fake.fail, Fake.seen_keys = {}, {}, False, set()
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("SUPABASE_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-secret")
    monkeypatch.delenv("CT_USER", raising=False)
    monkeypatch.delenv("CT_PASS", raising=False)
    monkeypatch.setattr(db, "PHOTO_DIR", tmp_path / "photos")
    monkeypatch.setattr(db, "DATA", tmp_path)  # photos are resolved against DATA
    yield srv
    srv.shutdown()


def test_disabled_without_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert not cloud.enabled()


def test_first_run_uploads_seed_then_changes_flow(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "a.db"))
    monkeypatch.setattr(db, "SEED", db.ROOT / "data" / "catalog.json")
    db.init_db()
    users.ensure_admin()
    assert len(Fake.tables["units"]) >= 6 and len(Fake.tables["parts"]) > 100
    assert "qc" in {k[0] for k in Fake.tables["users"]}
    assert Fake.seen_keys == {"service-secret"}
    db.add_case("2026-11-09", "ROM", "hd785", "p1", "512", "tes")
    assert any(r["note"] == "tes" for r in Fake.tables["cases"].values())
    with db.connect() as con:
        assert cloud.pending(con) == 0


def test_fresh_container_restores_everything(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "a.db"))
    db.init_db()
    users.ensure_admin()
    users.create_user("budi", "Budi", "operator", "rahasia123", by="qc")
    db.add_case("2026-11-09", "PIT", "hd785", "p1", "512", "dari cloud")
    n_parts = len(db.list_parts())
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "b.db"))  # new empty container
    db.init_db()
    assert len(db.list_parts()) == n_parts
    assert any(c["note"] == "dari cloud" for c in db.list_cases())
    assert users.authenticate("budi", "rahasia123")[0]["role"] == "operator"
    with db.connect() as con:
        assert cloud.pending(con) == 0


def test_delete_and_update_propagate(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "a.db"))
    db.init_db()
    cid = db.add_case("2026-11-09", "PIT", "hd785", "p1", "512", "hapus")
    db.delete_case(cid)
    assert not any(r["note"] == "hapus" for r in Fake.tables["cases"].values())


def test_outage_keeps_queue_and_retries(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "a.db"))
    db.init_db()
    Fake.fail = True
    db.add_case("2026-11-09", "PIT", "hd785", "p1", "512", "offline")
    assert db.LAST_SYNC_ERROR[0]
    with db.connect() as con:
        pass
    assert not any(r["note"] == "offline" for r in Fake.tables["cases"].values())
    Fake.fail = False
    with db.connect() as con:
        con.execute("SELECT 1")
        assert cloud.pending(con) > 0
    db.add_case("2026-11-09", "PIT", "hd785", "p1", "513", "online")
    notes = {r["note"] for r in Fake.tables["cases"].values()}
    assert {"offline", "online"} <= notes and db.LAST_SYNC_ERROR[0] == ""


def test_photo_files_roundtrip(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "a.db"))
    db.init_db()
    pid = db.list_parts()[0]["id"]
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "red").save(buf, "JPEG")
    monkeypatch.setattr(db, "PHOTO_DIR", tmp_path / "photos")
    name = db.add_photo(pid, buf.getvalue())
    assert f"photos/{name}" in Fake.files
    (tmp_path / "photos" / name).unlink()
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "c.db"))
    db.init_db()
    assert (tmp_path / "photos" / name).exists()


def _sub(kind, payload, sid="11111111-1111-1111-1111-111111111111", device="hp-lapangan"):
    Fake.tables.setdefault("field_submissions", {})[(sid,)] = {
        "id": sid, "device_id": device, "kind": kind, "payload": payload, "status": "pending",
        "created_at": "2026-11-09T10:00:00Z"}
    return Fake.tables["field_submissions"][(sid,)]


def test_version_and_static_published(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "a.db"))
    db.init_db()
    meta = {k[0]: r["value"] for k, r in Fake.tables["meta"].items()}
    assert meta["data_version"] and json.loads(meta["catalog_meta"])["fleet"]
    v1 = meta["data_version"]
    import time

    time.sleep(1.1)
    db.add_case("2026-11-09", "PIT", "hd785", "p1", "512", "x")
    assert Fake.tables["meta"][("data_version",)]["value"] > v1


def test_approve_case_and_inspection(fake, tmp_path, monkeypatch):
    from core import submissions as sm

    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "a.db"))
    db.init_db()
    pid = db.list_parts()[0]["id"]
    s1 = _sub("case", {"date": "2026-11-09", "loc": "ROM", "partId": pid, "no": "512", "note": "<b>x</b>"})
    assert sm.list_pending()[0]["id"] == s1["id"]
    sm.approve(s1, "qc")
    assert any("<b>x</b>" in c["note"] and "hp-lapangan" in c["note"] for c in db.list_cases())
    assert s1["status"] == "approved" and s1["reviewed_by"] == "qc" and not sm.list_pending()
    s2 = _sub("inspection", {"date": "2026-11-09", "partId": pid, "no": "512", "status": "rusak"}, sid="2" * 8 + "-2222-2222-2222-222222222222")
    sm.approve(s2, "qc")
    assert any(r["status"] == "rusak" and r["lambung"] == "512" for r in db.list_inspections())


def test_invalid_submissions_rejected(fake, tmp_path, monkeypatch):
    from core import submissions as sm

    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "a.db"))
    db.init_db()
    pid = db.list_parts()[0]["id"]
    bad = [
        _sub("case", {"date": "kemarin", "loc": "ROM", "partId": pid, "no": "1"}),
        _sub("case", {"date": "2026-11-09", "partId": "tidak-ada", "no": "1"}),
        _sub("inspection", {"date": "2026-11-09", "partId": pid, "no": "1", "status": "hancur"}),
        _sub("history", {"date": "2026-11-09", "partId": pid, "hm": {"x": 1}}),
        _sub("photo", {"partId": pid, "files": ["../../etc/passwd"]}),
        _sub("photo", {"partId": pid, "files": []}),
        _sub("bom", {}),
    ]
    for b in bad:
        with pytest.raises(ValueError):
            sm.apply(b)
    assert not db.list_cases()[-1]["note"].startswith("[lapangan")


def test_approve_photo_from_storage(fake, tmp_path, monkeypatch):
    from core import submissions as sm

    monkeypatch.setenv("CT_DB_PATH", str(tmp_path / "a.db"))
    db.init_db()
    pid = db.list_parts()[0]["id"]
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), "blue").save(buf, "JPEG")
    path = "submissions/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/f1.jpg"
    Fake.files[path] = buf.getvalue()
    sm.approve(_sub("photo", {"partId": pid, "files": [path]}), "qc")
    assert any(f"photos/{pid}_ref" in k for k in Fake.files)
    Fake.files["submissions/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/bad.jpg"] = b"bukan gambar"
    with pytest.raises(ValueError):
        sm.apply(_sub("photo", {"partId": pid, "files": ["submissions/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/bad.jpg"]}))
