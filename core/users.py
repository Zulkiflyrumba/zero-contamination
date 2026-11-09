"""Accounts, roles, lockout and audit log (all in the SQLite database).

Roles
  admin     everything, including Katalog (master data), Pengguna and data package export
  operator  Tracker, Galeri, Inspeksi & Kasus
  viewer    Tracker and Galeri (read only)

On first start (no users yet) one admin is created from CT_USER / CT_PASS (default qc / 123). That account must
change its password at first login when it still uses the default password.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime

from core import db

ROLES = ["admin", "operator", "viewer"]
ROLE_LABEL = {"admin": "Admin", "operator": "Operator QC", "viewer": "Viewer"}
PAGES = {  # page key -> roles allowed
    "tracker": ROLES,
    "parts3d": ROLES,
    "cases": ["admin", "operator"],
    "approvals": ["admin"],
    "catalog": ["admin"],
    "users": ["admin"],
    "about": ROLES,
}
ITERS = 260_000
MAX_FAILS, WINDOW = 5, 300  # lock a username for 5 minutes after 5 wrong passwords
MIN_LEN = 8


def hash_pw(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITERS)
    return f"pbkdf2${ITERS}${salt.hex()}${h.hex()}"


def verify_pw(pw: str, stored: str) -> bool:
    try:
        _, it, salt, h = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(calc, bytes.fromhex(h))
    except (ValueError, TypeError):
        return False


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def audit(user: str, action: str, detail: str = "", path=None) -> None:
    with db.connect(path) as con:
        con.execute("INSERT INTO audit(ts,user,action,detail) VALUES(?,?,?,?)", (_now(), user or "-", action, detail))


def list_audit(limit: int = 200, path=None) -> list[dict]:
    with db.connect(path) as con:
        return [dict(r) for r in con.execute("SELECT ts,user,action,detail FROM audit ORDER BY id DESC LIMIT ?", (limit,))]


def seed_creds() -> tuple[str, str]:
    user, pw = os.environ.get("CT_USER"), os.environ.get("CT_PASS")
    with contextlib.suppress(Exception):  # no Streamlit secrets file
        import streamlit as st

        user = user or st.secrets.get("CT_USER")
        pw = pw or st.secrets.get("CT_PASS")
    return (user or "qc").strip().lower(), pw or "123"


def ensure_admin(path=None) -> None:
    with db.connect(path) as con:
        if con.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return
        u, pw = seed_creds()
        default = pw == "123" or len(pw) < MIN_LEN
        con.execute("INSERT INTO users(username,name,role,pw_hash,active,must_change,created) VALUES(?,?,?,?,1,?,?)",
                    (u, u.upper(), "admin", hash_pw(pw), 1 if default else 0, _now()))


def _locked(con, username: str) -> int:
    """Seconds left of the lockout, 0 when not locked."""
    con.execute("DELETE FROM attempts WHERE ts < ?", (time.time() - WINDOW,))
    rows = [r["ts"] for r in con.execute("SELECT ts FROM attempts WHERE username=? ORDER BY ts", (username,))]
    return int(rows[0] + WINDOW - time.time()) + 1 if len(rows) >= MAX_FAILS else 0


def authenticate(username: str, pw: str, path=None) -> tuple[dict | None, str]:
    """Return (user dict, "") or (None, message). Same message for unknown user and wrong password."""
    u = (username or "").strip().lower()
    with db.connect(path) as con:
        left = _locked(con, u)
        if left:
            return None, f"Terlalu banyak percobaan. Coba lagi dalam {max(1, left // 60 + (1 if left % 60 else 0))} menit."
        row = con.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        stored = row["pw_hash"] if row else hash_pw("x", b"\0" * 16)  # constant work for unknown users
        ok = verify_pw(pw or "", stored) and row is not None and row["active"]
        if not ok:
            con.execute("INSERT INTO attempts(username,ts) VALUES(?,?)", (u, time.time()))
            con.execute("INSERT INTO audit(ts,user,action,detail) VALUES(?,?,?,?)", (_now(), u, "login_gagal", ""))
            return None, "Username atau password salah."
        con.execute("DELETE FROM attempts WHERE username=?", (u,))
        con.execute("INSERT INTO audit(ts,user,action,detail) VALUES(?,?,?,?)", (_now(), u, "login", ""))
        return {"username": row["username"], "name": row["name"] or row["username"], "role": row["role"],
                "must_change": bool(row["must_change"])}, ""


def get_user(username: str, path=None) -> dict | None:
    with db.connect(path) as con:
        r = con.execute("SELECT username,name,role,active,must_change,created FROM users WHERE username=?", (username,)).fetchone()
    return dict(r) if r else None


def list_users(path=None) -> list[dict]:
    with db.connect(path) as con:
        return [dict(r) for r in con.execute("SELECT username,name,role,active,must_change,created FROM users ORDER BY username")]


def check_password(pw: str, username: str = "") -> str:
    if len(pw) < MIN_LEN:
        return f"Password minimal {MIN_LEN} karakter."
    if username and pw.lower() == username.lower():
        return "Password tidak boleh sama dengan username."
    if pw.isdigit() or pw.isalpha():
        return "Gabungkan huruf dan angka."
    return ""


def create_user(username: str, name: str, role: str, pw: str, by: str = "", path=None) -> None:
    u = username.strip().lower()
    if not u or not u.replace(".", "").replace("_", "").replace("-", "").isalnum():
        raise ValueError("Username hanya huruf, angka, titik, garis bawah, atau strip.")
    if role not in ROLES:
        raise ValueError("Peran tidak dikenal.")
    if msg := check_password(pw, u):
        raise ValueError(msg)
    with db.connect(path) as con:
        if con.execute("SELECT 1 FROM users WHERE username=?", (u,)).fetchone():
            raise ValueError("Username sudah dipakai.")
        con.execute("INSERT INTO users(username,name,role,pw_hash,active,must_change,created) VALUES(?,?,?,?,1,1,?)",
                    (u, name.strip() or u, role, hash_pw(pw), _now()))
    audit(by, "user_dibuat", f"{u} ({role})", path)


def _admins_left(con, excluding: str) -> int:
    return con.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND username<>?", (excluding,)).fetchone()[0]


def update_user(username: str, role: str | None = None, active: bool | None = None, name: str | None = None,
                by: str = "", path=None) -> None:
    with db.connect(path) as con:
        cur = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not cur:
            raise ValueError("Pengguna tidak ditemukan.")
        new_role = role or cur["role"]
        new_active = cur["active"] if active is None else int(active)
        if cur["role"] == "admin" and cur["active"] and (new_role != "admin" or not new_active) and _admins_left(con, username) == 0:
            raise ValueError("Harus ada minimal satu admin aktif.")
        if new_role not in ROLES:
            raise ValueError("Peran tidak dikenal.")
        con.execute("UPDATE users SET role=?, active=?, name=? WHERE username=?",
                    (new_role, new_active, cur["name"] if name is None else name, username))
    audit(by, "user_diubah", f"{username}: peran={new_role} aktif={bool(new_active)}", path)


def set_password(username: str, pw: str, must_change: bool = False, by: str = "", path=None) -> None:
    if msg := check_password(pw, username):
        raise ValueError(msg)
    with db.connect(path) as con:
        n = con.execute("UPDATE users SET pw_hash=?, must_change=? WHERE username=?", (hash_pw(pw), int(must_change), username)).rowcount
    if not n:
        raise ValueError("Pengguna tidak ditemukan.")
    audit(by or username, "password_diganti", username, path)


def can(role: str, page: str) -> bool:
    return role in PAGES.get(page, [])
