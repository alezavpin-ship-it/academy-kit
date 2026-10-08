"""Each role family's career path as its own CSV file, run by the family's champion.

    content/families/<family-id>.csv      (one per family; ACADEMY_FAMILIES names another folder)

    SkillId, Skill, Class, Title, Url, Kind, Provider, Status, Minutes, Notes

* Status = required (a class of the path: it counts for the learner's progress) | optional (recommended material, shown
  but not counted) | off (kept in the plan, hidden from learners). A champion switches classes on and off without losing
  them.
* Class = the order of the required classes inside the skill (1, 2, 3…).
* Url = https://… (Microsoft Learn, the vendor, Workday Learning, a SharePoint deck…) or a file uploaded to the academy
  (``file:<family>/<name>``, for example the champion's own PowerPoint), which learners download.

The files mirror catalog/materials.json (the learning paths of every skill) and the LearningPaths tab of the content
workbook: change any of them and the others follow. ``sync`` applies a family file edited in Excel (checked first; with a
problem nothing changes); ``refresh`` rewrites the files after the app changes the paths.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from pathlib import Path

from academy.catalog import load_materials, save_materials

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ["SkillId", "Skill", "Class", "Title", "Url", "Kind", "Provider", "Status", "Minutes", "Notes"]
REQUIRED, OPTIONAL, OFF = "required", "optional", "off"
STATUSES = [REQUIRED, OPTIONAL, OFF]
KINDS = ["module", "path", "course", "lab", "tutorial", "deck", "doc", "guide", "video", "exam"]
FILE_TYPES = ["pptx", "ppt", "pdf", "docx", "xlsx", "zip", "mp4"]
MAX_FILE_MB = 50  # the upload limit of Streamlit (server.maxUploadSize)


def folder() -> Path:
    from academy import workspace

    return Path(os.environ.get("ACADEMY_FAMILIES") or workspace.root() / "content" / "families")


def files_folder() -> Path:
    return folder().parent / "family_files"


def state_path() -> Path:
    from academy import workspace

    return Path(os.environ.get("ACADEMY_FAMILIES_STATE") or workspace.root() / "data" / "families_state.json")


# ------------------------------------------------------------------------------------------------ uploaded files
def safe_name(name: str) -> str:
    stem, dot, ext = Path(name).name.rpartition(".")
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "", stem or ext).strip(" .") or "file"
    return f"{stem}.{ext.lower()}" if dot else stem


def save_file(family_id: str, name: str, data: bytes) -> str:
    """Store a champion's file (deck, PDF…) and return the Url to put in the path: file:<family>/<name>."""
    ext = Path(name).suffix.lower().lstrip(".")
    if ext not in FILE_TYPES:
        raise ValueError(f"'{ext}' files are not accepted ({', '.join(FILE_TYPES)}).")
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise ValueError(f"the file is bigger than {MAX_FILE_MB} MB.")
    dest = files_folder() / family_id / safe_name(name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return f"file:{family_id}/{dest.name}"


def file_path(url: str) -> Path | None:
    """The local file of a file:<family>/<name> Url (None for web links or a missing file)."""
    if not str(url).startswith("file:"):
        return None
    rel = Path(str(url)[5:])
    if rel.is_absolute() or ".." in rel.parts:
        return None
    p = files_folder() / rel
    return p if p.exists() else None


# ------------------------------------------------------------------------------------------------ status of a class
def status_of(item: dict) -> str:
    """required / optional / off; without a written status, vendor steps are required and the rest optional."""
    s = str(item.get("status") or "").strip().lower()
    if s in STATUSES:
        return s
    from academy.route import STEP_KINDS

    return REQUIRED if item.get("kind") in STEP_KINDS else OPTIONAL


# ------------------------------------------------------------------------------------------------ CSV of one family
def rows(family_id: str, catalog, materials: dict[str, list[dict]]) -> list[dict]:
    from academy.route import class_order

    out = []
    for s in catalog.in_family(family_id):
        items = materials.get(s.id, [])
        steps = class_order(items)
        number = {id(m): n for n, m in enumerate(steps, start=1)}
        for m in steps + [m for m in items if m not in steps]:
            out.append({"SkillId": s.id, "Skill": s.name, "Class": number.get(id(m), m.get("order", "")), "Title": m.get("title", ""),
                        "Url": m.get("url", ""), "Kind": m.get("kind", ""), "Provider": m.get("provider", ""), "Status": status_of(m),
                        "Minutes": m.get("minutes", ""), "Notes": m.get("notes", "")})
    return out


def to_csv(family_rows: list[dict]) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\r\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(family_rows)
    return buf.getvalue().encode("utf-8-sig")


def export(family_id: str, catalog, materials: dict | None = None) -> bytes:
    return to_csv(rows(family_id, catalog, load_materials() if materials is None else materials))


def _int(v) -> int | None:
    try:
        return int(float(str(v).strip())) if str(v).strip() else None
    except ValueError:
        return None


def parse(raw: bytes, family_id: str, catalog) -> tuple[dict[str, list[dict]], list[str]]:
    """{skill id: items} for the family and the problems found (the skill may be written by id or by name)."""
    text = raw.decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    table = list(csv.DictReader(io.StringIO(text, newline=""), delimiter=";" if first.count(";") > first.count(",") else ","))
    if table and not {"Title", "Url"} <= set(table[0]):
        return {}, [f"Missing columns: Title and Url are required ({', '.join(COLUMNS)})."]
    skills = {s.id: s for s in catalog.in_family(family_id)}
    by_name = {s.name.strip().lower(): s.id for s in skills.values()}
    out: dict[str, list[dict]] = {sid: [] for sid in skills}
    problems = []
    for n, r in enumerate(table, start=2):
        r = {k: (v or "").strip() for k, v in r.items() if k}
        if not any(r.values()):
            continue
        tag = f"[{family_id} row {n}]"
        sid = r.get("SkillId") or by_name.get(r.get("Skill", "").lower(), "")
        if sid not in skills:
            problems.append(f"{tag} skill '{r.get('SkillId') or r.get('Skill')}' is not a skill of this family.")
            continue
        url, status, kind = r.get("Url", ""), (r.get("Status") or "").lower(), (r.get("Kind") or "").lower()
        if not r.get("Title") or not (url.startswith("https://") or url.startswith("file:")):
            problems.append(f"{tag} needs a Title and a Url (https://… or an uploaded file).")
            continue
        if status and status not in STATUSES:
            problems.append(f"{tag} Status must be required, optional or off.")
            continue
        if kind and kind not in KINDS:
            problems.append(f"{tag} Kind must be one of: {', '.join(KINDS)}.")
            continue
        item = {"title": r["Title"], "url": url, "kind": kind or "course", "provider": r.get("Provider") or "Champion"}
        if _int(r.get("Class")):
            item["order"] = _int(r["Class"])
        for key, col in (("status", "Status"), ("minutes", "Minutes"), ("notes", "Notes")):
            v = r.get(col, "").lower() if key == "status" else r.get(col, "")
            if v:
                item[key] = _int(v) if key == "minutes" and _int(v) is not None else v
        out[sid].append(item)
    return out, problems


def replace(family_id: str, new: dict[str, list[dict]], catalog, materials: dict | None = None) -> dict[str, list[dict]]:
    """materials.json with this family's skills replaced by ``new`` (other families untouched)."""
    mats = dict(load_materials() if materials is None else materials)
    for s in catalog.in_family(family_id):
        mats[s.id] = new.get(s.id, [])
    return mats


# ------------------------------------------------------------------------------------------------ files on disk, both ways
def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(st: dict) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, indent=1), encoding="utf-8")


def refresh(catalog, materials: dict | None = None, keep: set[str] | None = None) -> None:
    """Rewrite every family file from the current paths (after the app or the workbook changed them). ``keep``: families
    whose file has unapplied edits with problems (left as the champion wrote them, so they can fix them)."""
    if not catalog:
        return
    mats = load_materials() if materials is None else materials
    old = _state()
    st = {f: old[f] for f in (keep or set()) if f in old}
    for fam in catalog.families:
        if fam.id in (keep or set()):
            continue
        raw = export(fam.id, catalog, mats)
        p = folder() / f"{fam.id}.csv"
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
        except OSError:  # open in Excel: written next time
            continue
        st[fam.id] = _digest(raw)
    _save_state(st)


def sync(catalog) -> dict:
    """Apply the family files edited by hand since the app last wrote them. Returns {"applied": [...], "problems": {fam: [...]}}."""
    out: dict = {"applied": [], "problems": {}}
    if not catalog:
        return out
    st = _state()
    if not st:  # first run: write the files
        refresh(catalog)
        return out
    mats = load_materials()
    changed = False
    for fam in catalog.families:
        p = folder() / f"{fam.id}.csv"
        if not p.exists():
            continue
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if st.get(fam.id) == _digest(raw):
            continue
        new, problems = parse(raw, fam.id, catalog)
        if problems:
            out["problems"][fam.id] = problems
            continue
        mats = replace(fam.id, new, catalog, mats)
        out["applied"].append(fam.id)
        changed = True
    if changed:
        save_materials(mats)
        refresh(catalog, mats, keep=set(out["problems"]))
    return out
