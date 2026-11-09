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
        pk = cloud.TABLES[t]
        if method == "POST":
            for r in json.loads(self._body()):
                tab[tuple(r[c] for c in pk)] = r
            return self._send(201)
        if method == "DELETE":
            want = {k: v[0][3:] for k, v in q.items()}
            for k in [k for k, r in tab.items() if all(str(r[c]) == v for c, v in want.items())]:
                del tab[k]
            return self._send(204)
        rows = list(tab.values())
        off, lim = int(q.get("offset", ["0"])[0]), int(q.get("limit", ["1000"])[0])
        return self._send(200, json.dumps(rows[off:off + lim]).encode())

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

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
