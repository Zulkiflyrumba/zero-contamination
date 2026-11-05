import io
import zipfile

import pytest

from core import models


def test_manifest_has_hd785():
    m = models.manifest()
    assert "hd785" in m and m["hd785"]["file"] == "model.dae"
    assert all(f for f in m["hd785"]["files"])


def test_save_zip_and_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "MODELS", tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("model/model.dae", "<x/>")
        z.writestr("model/textures/a_albedo.jpg", "x")
    cfg = models.save("u1", [("m.zip", buf.getvalue())], {"len": 8})
    assert cfg["file"] == "model.dae" and "a_albedo.jpg" in cfg["files"] and cfg["opts"]["len"] == 8
    models.set_options("u1", anch={"A/B": [1, 2, 3]})
    assert models.get("u1")["anch"]["A/B"] == [1, 2, 3]
    models.delete("u1")
    assert models.get("u1") is None


def test_save_requires_model_file(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "MODELS", tmp_path)
    with pytest.raises(ValueError):
        models.save("u1", [("a.jpg", b"x")], {})
