import os, sys, tempfile, datetime as dt
os.environ["CONTAM_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import core


def setup_module(_):
    core.init(); core.init()  # idempoten


def test_katalog_terisi():
    c = core.db()
    assert c.execute("select count(*) from parts").fetchone()[0] > 300
    assert c.execute("select count(*) from units").fetchone()[0] >= 12
    c.close()


def test_analisis_dan_restorasi():
    imgs = [core.make_img("clamp", 901, rust=True, rot=20)]
    R = core.analyse(imgs, "Tidak diketahui", 0, "", "Pit Selatan", dt.date.today())
    assert len(R) > 300 and R.Peluang.sum() == pytest.approx(100)
    assert "clamp" in R.head(10).cat.tolist()
    top = R.iloc[0]
    rs = core.restore(imgs, top.imgs.split("|"))
    assert rs and 0 <= rs["rem"] <= 1 and len(rs["data"]) > 1000


def test_lokasi_pada_unit():
    us = core.unit_scene("HD 785-7", "Hidrolik & Selang", "Selang & clamp", "Clamp selang hidrolik")
    assert us and us["cfg"]["pos"] == [0.5, 2.65, -1] and "__CFG__" not in us["html"]
    assert core.unit_scene("PC2000-8", "Bucket & GET", "Gigi & adapter", "Bucket tooth")["cfg"]["kind"] == "E"
    assert core.unit_scene("D155AX-6", None, None, "x") is None
