import io
import json
import zipfile

import pytest

from core import db, pack


def test_build_and_verify(dbp):
    data, man = pack.build()
    assert man["format"] == pack.FORMAT
    assert man["counts"]["units"] == 9 and man["counts"]["parts"] >= 300
    assert pack.verify(data)["dataVersion"] == man["dataVersion"]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        pay = json.loads(z.read("payload.json"))
        names = set(z.namelist())
    assert {"manifest.json", "payload.json"} <= names
    # photos are stored as files, not inline data URIs
    for p in pay["parts"]:
        for ph in p["photos"]:
            assert ph in names and not ph.startswith("data:")


def test_version_changes_with_data(dbp):
    _, m1 = pack.build()
    db.add_history("p29", "2026-02-02", 100, "ganti baru")
    _, m2 = pack.build()
    assert m1["contentHash"] != m2["contentHash"]


def test_verify_detects_corruption(dbp):
    data, _ = pack.build()
    bad = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zi, zipfile.ZipFile(bad, "w") as zo:
        for n in zi.namelist():
            b = zi.read(n)
            zo.writestr(n, b + b" " if n == "payload.json" else b)
    with pytest.raises(ValueError):
        pack.verify(bad.getvalue())
