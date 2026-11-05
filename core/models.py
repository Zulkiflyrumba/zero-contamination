"""Custom 3D unit models stored in the repo (static/models/<unit_id>/).

Streamlit static serving exposes ``static/`` at ``/app/static/``; the front end fetches the files from there,
so a model uploaded once (and committed to git) is available to every visitor.
"""
import io
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "static" / "models"
EXTS = (".glb", ".gltf", ".dae")
DEFAULT_OPTS = {"len": 10.4, "up": "y", "yaw": 0}


def _cfg_path(unit_id: str) -> Path:
    return MODELS / unit_id / "config.json"


def get(unit_id: str) -> dict | None:
    p = _cfg_path(unit_id)
    if not p.exists():
        return None
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg.setdefault("opts", dict(DEFAULT_OPTS))
    cfg.setdefault("anch", {})
    return cfg


def manifest() -> dict:
    out = {}
    if MODELS.exists():
        for d in sorted(MODELS.iterdir()):
            cfg = get(d.name) if d.is_dir() else None
            if cfg:
                out[d.name] = cfg
    return out


def save(unit_id: str, uploads: list[tuple[str, bytes]], opts: dict) -> dict:
    """Replace the model of a unit. ``uploads`` are (filename, bytes); a .zip is unpacked (folders are flattened)."""
    files: dict[str, bytes] = {}
    for name, data in uploads:
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for info in z.infolist():
                    if info.is_dir() or "__MACOSX" in info.filename:
                        continue
                    files[Path(info.filename).name] = z.read(info)
        else:
            files[Path(name).name] = data
    main = next((n for n in files if n.lower().endswith(EXTS)), None)
    if not main:
        raise ValueError("Tidak ada file .glb, .gltf atau .dae. File RAR harus diekstrak dulu.")
    old = get(unit_id)
    d = MODELS / unit_id
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for n, b in files.items():
        (d / n).write_bytes(b)
    cfg = {"file": main, "files": sorted(files), "opts": {**DEFAULT_OPTS, **opts}, "anch": (old or {}).get("anch", {})}
    _cfg_path(unit_id).write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    return cfg


def set_options(unit_id: str, opts: dict | None = None, anch: dict | None = None) -> None:
    cfg = get(unit_id)
    if not cfg:
        raise ValueError("Unit belum punya model.")
    if opts:
        cfg["opts"] = {**cfg["opts"], **opts}
    if anch is not None:
        cfg["anch"] = anch
    _cfg_path(unit_id).write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def delete(unit_id: str) -> None:
    d = MODELS / unit_id
    if d.exists():
        shutil.rmtree(d)
