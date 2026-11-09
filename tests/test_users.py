import time

import pytest

from core import db, pack, users


@pytest.fixture()
def clean(dbp, monkeypatch):
    monkeypatch.delenv("CT_USER", raising=False)
    monkeypatch.delenv("CT_PASS", raising=False)
    users.ensure_admin()
    return dbp


def test_seed_admin_must_change(clean):
    u, msg = users.authenticate("QC ", "123")
    assert u and u["role"] == "admin" and u["must_change"] and not msg


def test_wrong_password_and_unknown_user_same_message(clean):
    _, m1 = users.authenticate("qc", "salah")
    _, m2 = users.authenticate("tidakada", "salah")
    assert m1 == m2 == "Username atau password salah."


def test_lockout_after_five_failures(clean):
    for _ in range(users.MAX_FAILS):
        users.authenticate("qc", "salah")
    u, msg = users.authenticate("qc", "123")
    assert u is None and "Terlalu banyak" in msg
    with db.connect() as con:  # age the attempts past the window
        con.execute("UPDATE attempts SET ts=?", (time.time() - users.WINDOW - 5,))
    assert users.authenticate("qc", "123")[0]


def test_create_user_rules(clean):
    users.create_user("Budi.QC", "Budi", "operator", "rahasia123", by="qc")
    assert users.authenticate("budi.qc", "rahasia123")[0]["must_change"]
    with pytest.raises(ValueError):
        users.create_user("budi.qc", "x", "viewer", "rahasia123")  # duplicate
    with pytest.raises(ValueError):
        users.create_user("sari", "Sari", "viewer", "12345678")  # digits only
    with pytest.raises(ValueError):
        users.create_user("sari", "Sari", "boss", "rahasia123")  # unknown role


def test_inactive_user_cannot_login(clean):
    users.create_user("andi", "Andi", "viewer", "rahasia123")
    users.update_user("andi", active=False)
    assert users.authenticate("andi", "rahasia123")[0] is None


def test_last_admin_protected(clean):
    with pytest.raises(ValueError):
        users.update_user("qc", role="operator")
    with pytest.raises(ValueError):
        users.update_user("qc", active=False)
    users.create_user("adm2", "Admin 2", "admin", "rahasia123")
    users.update_user("qc", role="operator")


def test_change_password_clears_flag(clean):
    users.set_password("qc", "baru12345", must_change=False)
    u, _ = users.authenticate("qc", "baru12345")
    assert u and not u["must_change"]
    assert users.authenticate("qc", "123")[0] is None


def test_roles_pages():
    assert users.can("admin", "catalog") and not users.can("operator", "catalog")
    assert users.can("operator", "cases") and not users.can("viewer", "cases")
    assert users.can("viewer", "tracker") and not users.can("viewer", "users")


def test_audit_records(clean):
    users.authenticate("qc", "salah")
    users.authenticate("qc", "123")
    acts = [a["action"] for a in users.list_audit()]
    assert "login_gagal" in acts and "login" in acts


def test_pack_encrypted_roundtrip(dbp):
    data, man = pack.build(password="rahasia123")
    assert man["encrypted"] and pack.is_encrypted(data)
    assert pack.verify(data, "rahasia123")["dataVersion"] == man["dataVersion"]
    with pytest.raises(ValueError):
        pack.verify(data, "salah")
    with pytest.raises(ValueError):
        pack.read_manifest(data)  # no password
    assert b"payload.json" not in data  # file names are not visible in the ciphertext
