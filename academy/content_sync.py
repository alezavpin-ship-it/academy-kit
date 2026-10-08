"""The content file: one Excel workbook in the app folder, one tab per section, that holds every course, video, learning
path, the skills catalog and the practice definition.

    content/academy_content.xlsx         (or the file named by ACADEMY_CONTENT)

(The first version used a single CSV, content/academy_content.csv; if that file is found it is read one last time and
replaced by the workbook.)

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
CONTENT_FILE = ROOT / "content" / "academy_content.xlsx"
STATE_FILE = ROOT / "data" / "content_state.json"


def content_path() -> Path:
    return Path(os.environ.get("ACADEMY_CONTENT") or CONTENT_FILE)


def state_path() -> Path:
    return Path(os.environ.get("ACADEMY_CONTENT_STATE") or STATE_FILE)


def _schema() -> list[str]:
    """The tables and columns of the workbook: when they change (a new app version), the file is rewritten."""
    return [f"{name}:{','.join(cols)}" for name, cols in content.SHEETS.items()]


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


def _migrate() -> None:
    """content/academy_content.csv (one CSV) -> content/academy_content.xlsx (one tab per section)."""
    old, new = content_path().with_suffix(".csv"), content_path()
    if new.suffix.lower() != ".xlsx" or new.exists() or not old.exists():
        return
    st = _state()
    raw = old.read_bytes()
    if st.get("sha256") != _digest(raw):  # edited by hand since the app last wrote it: apply it first, if it is right
        result = content.read(raw)
        if not result["problems"]:
            content.apply(result)
    refresh()
    old.replace(old.with_name(old.stem + " (old).csv"))


def sync() -> dict:
    """Bring the app up to date with the content file. Returns {"status": none | same | applied | problems | locked, ...}."""
    p = content_path()
    try:
        _migrate()
    except OSError:
        pass
    if not p.exists():
        return {"status": "none", "file": str(p)}
    try:
        raw = p.read_bytes()
    except OSError:  # open in Excel with an exclusive lock
        return {"status": "locked", "file": str(p)}
    digest, st = _digest(raw), _state()
    if st.get("sha256") == digest:
        if not st.get("problems") and st.get("tables") != _schema():
            return refresh() | {"status": "same"}  # the app gained tables since the file was written: add them (the user has not edited it)
        return {"status": "problems" if st.get("problems") else "same", "file": str(p), "problems": st.get("problems", [])}
    result = content.read(raw)
    if result["problems"]:
        _save_state(sha256=digest, problems=result["problems"][:200], tables=_schema())
        return {"status": "problems", "file": str(p), "problems": result["problems"]}
    content.apply(result)
    _save_state(sha256=digest, problems=[], tables=_schema())
    return {"status": "applied", "file": str(p), "summary": result["summary"]}


def refresh() -> dict:
    """Rewrite the content file from the app's current data. Returns {"status": written | locked, "file": ...}."""
    p = content_path()
    raw = content.export_bytes() if p.suffix.lower() == ".xlsx" else content.csv_bytes(content.export_csv())
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    except OSError:  # the file is open in Excel: the app's data is saved; the file is rewritten the next time
        return {"status": "locked", "file": str(p)}
    _save_state(sha256=_digest(raw), problems=[], tables=_schema())
    return {"status": "written", "file": str(p)}
