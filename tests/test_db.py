import io

from PIL import Image

from core import db


def test_seed(dbp):
    p = db.export_payload()
    assert len(p["units"]) == 9
    assert len(p["parts"]) >= 190
    assert any(c["builtin"] for c in p["cases"])
    assert "hd785" in p["spec"]


def test_save_and_delete_part(dbp):
    rows = db.list_parts("hd785")
    n = len(rows)
    new = {"name": "Test clamp", "kind": "clamp", "system": "Hoist", "asm": "Hose Hoist"}
    r = db.save_parts("hd785", rows + [new])
    assert r["added"] == 1 and r["deleted"] == 0
    assert len(db.list_parts("hd785")) == n + 1
    r = db.save_parts("hd785", rows)
    assert r["deleted"] == 1
    assert len(db.list_parts("hd785")) == n


def test_existing_ids_stable(dbp):
    ids = {p["id"] for p in db.list_parts()}
    assert {"p1", "p29"} <= ids


def test_history_inspection_case(dbp):
    db.add_history("p29", "2026-01-01", 1200, "ganti")
    db.set_inspection("HD785-512", "p29", "rusak", "2026-01-02")
    cid = db.add_case("2026-01-03", "PIT A", "hd785", "p29", "HD785-512", "uji")
    p = db.export_payload()
    assert any(h["reason"] == "ganti" for x in p["parts"] if x["id"] == "p29" for h in x["history"])
    assert p["inspect"]
    assert any(c["id"] == f"c{cid}" for c in p["cases"])
    db.delete_case(cid)
    assert not any(c["id"] == f"c{cid}" for c in db.export_payload()["cases"])


def test_add_photo(dbp):
    buf = io.BytesIO()
    Image.new("RGB", (900, 600), "gray").save(buf, "JPEG")
    name = db.add_photo("p29", buf.getvalue())
    assert name.endswith(".jpg")
    assert (db.PHOTO_DIR / name).exists()
