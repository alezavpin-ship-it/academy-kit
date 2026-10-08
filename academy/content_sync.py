"""The content file: one CSV in the app folder that holds every course, video, learning path and the skills catalog.

    content/academia_contenido.csv      (or the file named by ACADEMY_CONTENT)

Edit it in Excel, save it, reopen the app: ``sync`` notices the change, checks the whole file and, only if it is right,
rewrites the app's data (packs/, catalog/). With problems nothing changes and the app keeps the last good content.
``refresh`` goes the other way: after the app itself changes content (skills map, family courses, an import), it rewrites
the file so the file is always the current content.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from academy import content_xlsx as content

ROOT = Path(__file__).resolve().parents[1]
CONTENT_FILE = ROOT / "content" / "academia_contenido.csv"
STATE_FILE = ROOT / "data" / "content_state.json"


def content_path() -> Path:
    return Path(os.environ.get("ACADEMY_CONTENT") or CONTENT_FILE)


def state_path() -> Path:
    return Path(os.environ.get("ACADEMY_CONTENT_STATE") or STATE_FILE)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(**kw) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(kw, ensure_ascii=False, indent=1), encoding="utf-8")


def sync() -> dict:
    """Bring the app up to date with the content file. Returns {"status": none | same | applied | problems | locked, ...}."""
    p = content_path()
    if not p.exists():
        return {"status": "none", "file": str(p)}
    try:
        raw = p.read_bytes()
    except OSError:  # open in Excel with an exclusive lock
        return {"status": "locked", "file": str(p)}
    digest, st = _digest(raw), _state()
    if st.get("sha256") == digest:
        if not st.get("problems") and st.get("tables") != list(content.SHEETS):
            return refresh() | {"status": "same"}  # the app gained tables since the file was written: add them (the user has not edited it)
        return {"status": "problems" if st.get("problems") else "same", "file": str(p), "problems": st.get("problems", [])}
    result = content.read(raw)
    if result["problems"]:
        _save_state(sha256=digest, problems=result["problems"][:200], tables=list(content.SHEETS))
        return {"status": "problems", "file": str(p), "problems": result["problems"]}
    content.apply(result)
    _save_state(sha256=digest, problems=[], tables=list(content.SHEETS))
    return {"status": "applied", "file": str(p), "summary": result["summary"]}


def refresh() -> dict:
    """Rewrite the content file from the app's current data. Returns {"status": written | locked, "file": ...}."""
    p = content_path()
    raw = content.csv_bytes(content.export_csv())
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    except OSError:  # the file is open in Excel: the app's data is saved; the file is rewritten the next time
        return {"status": "locked", "file": str(p)}
    _save_state(sha256=_digest(raw), problems=[], tables=list(content.SHEETS))
    return {"status": "written", "file": str(p)}
