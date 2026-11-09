"""Field data sent by the APK (``field_submissions``). It waits for an admin to approve it.

The payloads come from phones, so they are treated as untrusted input: every field is type-checked and length
limited before it reaches the database, and nothing is executed or trusted as markup.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from core import cloud, db

KINDS = ("case", "inspection", "photo", "history")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PATH_RE = re.compile(r"^submissions/[0-9a-f-]{36}/[A-Za-z0-9._-]{1,80}$")


def _s(v, n: int = 200) -> str:
    if v is None:
        return ""
    if not isinstance(v, (str, int, float)):
        raise ValueError("Isi kiriman tidak valid.")  # noqa: TRY004
    return str(v).strip()[:n]


def _date(v) -> str:
    d = _s(v, 10)
    if not DATE_RE.match(d):
        raise ValueError("Tanggal harus berformat YYYY-MM-DD.")
    return d


def list_pending() -> list[dict]:
    return cloud.get_json("/rest/v1/field_submissions?status=eq.pending&order=created_at.asc&select=*")


def list_recent(n: int = 30) -> list[dict]:
    return cloud.get_json(f"/rest/v1/field_submissions?status=neq.pending&order=reviewed_at.desc&limit={int(n)}&select=*")


def describe(sub: dict) -> str:
    p = sub.get("payload") or {}
    k = sub.get("kind")
    if k == "case":
        return f'Kasus {_s(p.get("date"), 10)} · lambung {_s(p.get("no"), 20)} · part {_s(p.get("partId"), 20)} · {_s(p.get("loc"), 30)}'
    if k == "inspection":
        return f'Inspeksi lambung {_s(p.get("no"), 20)} · part {_s(p.get("partId"), 20)} · {_s(p.get("status"), 12)}'
    if k == "photo":
        return f'{len(p.get("files") or [])} foto referensi untuk part {_s(p.get("partId"), 20)}'
    if k == "history":
        return f'Riwayat part {_s(p.get("partId"), 20)} · {_s(p.get("date"), 10)} · {_s(p.get("reason"), 60)}'
    return str(k)


def _part_exists(pid: str) -> bool:
    return any(p["id"] == pid for p in db.list_parts())


def apply(sub: dict) -> str:
    """Write an approved submission into the database (and so to Supabase). Raises ValueError if invalid."""
    k, p = sub.get("kind"), sub.get("payload") or {}
    if k not in KINDS or not isinstance(p, dict):
        raise ValueError("Jenis kiriman tidak dikenal.")
    tag = f' [lapangan {_s(sub.get("device_id"), 12)}]'
    if k == "case":
        pid, no = _s(p.get("partId"), 40), _s(p.get("no"), 20)
        if not _part_exists(pid) or not no:
            raise ValueError("Part tidak ditemukan atau nomor lambung kosong.")
        unit = next(x["unit_id"] for x in db.list_parts() if x["id"] == pid)
        db.add_case(_date(p.get("date")), _s(p.get("loc"), 40), unit, pid, no, _s(p.get("note"), 500) + tag)
        return "kasus ditambahkan"
    if k == "inspection":
        pid, no, st = _s(p.get("partId"), 40), _s(p.get("no"), 20), _s(p.get("status"), 12)
        if not _part_exists(pid) or not no or st not in db.STATUSES:
            raise ValueError("Data inspeksi tidak valid.")
        db.set_inspection(no, pid, st, _date(p.get("date")), tag.strip())
        return "inspeksi dicatat"
    if k == "history":
        pid = _s(p.get("partId"), 40)
        if not _part_exists(pid):
            raise ValueError("Part tidak ditemukan.")
        try:
            hm = float(p.get("hm") or 0)
        except (TypeError, ValueError):
            raise ValueError("HM tidak valid.") from None
        db.add_history(pid, _date(p.get("date")), hm, _s(p.get("reason"), 200) or "—")
        return "riwayat ditambahkan"
    pid = _s(p.get("partId"), 40)
    files = p.get("files")
    if not _part_exists(pid) or not isinstance(files, list) or not 0 < len(files) <= 8:
        raise ValueError("Data foto tidak valid.")
    n = 0
    for path in files:
        if not isinstance(path, str) or not PATH_RE.match(path):
            raise ValueError("Path foto tidak valid.")
        blob = cloud.download_file(path)
        if not blob:
            raise ValueError("File foto tidak ditemukan di penyimpanan.")
        try:
            db.add_photo(pid, blob, "ref")  # re-encoded by Pillow, so a non-image fails here
        except (OSError, ValueError):
            raise ValueError("File foto bukan gambar yang valid.") from None
        n += 1
    return f"{n} foto ditambahkan"


def _stamp(sub_id: str, status: str, by: str) -> None:
    cloud.patch("field_submissions", {"id": sub_id},
                {"status": status, "reviewed_by": by, "reviewed_at": datetime.now(timezone.utc).isoformat()})


def approve(sub: dict, by: str) -> str:
    msg = apply(sub)
    _stamp(sub["id"], "approved", by)
    return msg


def reject(sub: dict, by: str) -> None:
    _stamp(sub["id"], "rejected", by)
