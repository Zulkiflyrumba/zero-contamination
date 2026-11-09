"""Data package (``.ctpack``): the whole database, photos and 3D models in one zip file.

Layout::

    manifest.json   format, data version, counts, SHA-256 of every file
    payload.json    same structure as ``db.export_payload`` but photos are relative paths
    photos/...      reference and finding photos
    models/<unit>/  3D model files of each unit (config.json is part of payload.json)

The HTML / Android app imports this file (Data Center > Import Data Package), so it carries the same data as
the web app without an app update.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from datetime import datetime

from core import db, models

FORMAT = "ctpack/1"
MAGIC = b"CTPKENC1"  # encrypted package: MAGIC + iterations(4) + salt(16) + iv(12) + AES-256-GCM(ciphertext + tag)
KDF_ITERS = 200_000


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build(path=None, password: str | None = None) -> tuple[bytes, dict]:
    """Return (package bytes, manifest). With ``password`` the package is encrypted (AES-256-GCM, PBKDF2-SHA256)."""
    files: dict[str, bytes] = {}

    def photo(rel: str) -> str:
        f = db.DATA / rel
        if f.exists():
            files[rel] = f.read_bytes()
        return rel

    payload = db.export_payload(path, photo_fn=photo)
    # drop references to photos that do not exist on disk
    for p in payload["parts"]:
        p["photos"] = [x for x in p["photos"] if x in files]
    payload["sample"] = {k: [x for x in v if x in files] for k, v in payload["sample"].items()}
    payload["models"] = models.manifest()
    for uid, cfg in payload["models"].items():
        for name in cfg.get("files", []):
            f = models.MODELS / uid / name
            if f.exists():
                files[f"models/{uid}/{name}"] = f.read_bytes()
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    files["payload.json"] = body
    hashes = {k: _sha(v) for k, v in sorted(files.items())}
    content = _sha("".join(f"{k}:{h}" for k, h in hashes.items()).encode())
    now = datetime.now().astimezone()
    manifest = {
        "format": FORMAT,
        "app": "contamination-tracker",
        "dataVersion": f"{now:%Y.%m.%d.%H%M}-{content[:6]}",
        "contentHash": content,
        "createdAt": now.isoformat(timespec="seconds"),
        "counts": {
            "units": len(payload["units"]),
            "parts": len(payload["parts"]),
            "history": sum(len(p["history"]) for p in payload["parts"]),
            "photos": sum(1 for k in files if k.startswith("photos/")),
            "models": len(payload["models"]),
            "cases": len(payload["cases"]),
            "inspections": len(payload["inspect"]),
            "operations": len(payload["ops"]),
        },
        "files": hashes,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for k, v in files.items():
            z.writestr(k, v)
    out = buf.getvalue()
    if password:
        out = encrypt(out, password)
        manifest["encrypted"] = True
    return out, manifest


def is_encrypted(data: bytes) -> bool:
    return data[: len(MAGIC)] == MAGIC


def _key(password: str, salt: bytes, iters: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters, dklen=32)


def encrypt(data: bytes, password: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt, iv = os.urandom(16), os.urandom(12)
    head = MAGIC + KDF_ITERS.to_bytes(4, "big") + salt + iv
    return head + AESGCM(_key(password, salt, KDF_ITERS)).encrypt(iv, data, head)


def decrypt(data: bytes, password: str) -> bytes:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    n = len(MAGIC)
    head, body = data[: n + 32], data[n + 32 :]
    iters, salt, iv = int.from_bytes(head[n : n + 4], "big"), head[n + 4 : n + 20], head[n + 20 : n + 32]
    try:
        return AESGCM(_key(password, salt, iters)).decrypt(iv, body, head)
    except InvalidTag as e:
        raise ValueError("Kata sandi salah atau file rusak.") from e


def read_manifest(data: bytes, password: str | None = None) -> dict:
    if is_encrypted(data):
        if not password:
            raise ValueError("Paket terkunci: kata sandi diperlukan.")
        data = decrypt(data, password)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        m = json.loads(z.read("manifest.json"))
    if m.get("format") != FORMAT:
        raise ValueError(f"Format paket tidak dikenal: {m.get('format')}")
    return m


def verify(data: bytes, password: str | None = None) -> dict:
    """Check every file against the manifest; return the manifest or raise ValueError."""
    if is_encrypted(data):
        data = decrypt(data, password or "")
    m = read_manifest(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name, h in m["files"].items():
            try:
                ok = _sha(z.read(name)) == h
            except KeyError:
                ok = False
            if not ok:
                raise ValueError(f"File rusak atau hilang di paket: {name}")
    return m


def filename(manifest: dict) -> str:
    return f"contamination-tracker-{manifest['dataVersion']}.ctpack"
