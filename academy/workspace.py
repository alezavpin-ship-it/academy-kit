"""Practices: each practice of the organization (Microsoft Cloud Security, PPM…) is its own space in the app, with its
own courses, role families and skills, learning paths, demand, study material, news sources and content workbook.

    catalog/practices.csv                 the list of practices (global; ACADEMY_PRACTICES names another file)
        Id, Name, Description, Active
    <the app folder>                      the first practice (the one the app always had): catalog/, content/, packs/, exams/
    practices/<id>/                       every other practice, with the same folders

What is global: the people directory (catalog/people.csv, with the practice of each person), the owners, the progress
database (data/academy.db) and the app's settings. A person belongs to one practice; global owners see and run every
practice, a practice's owners only theirs.

The practice in use is chosen once per run of the page (``use``), before anything reads a file: every path of the app
(catalog, content, packs, exams…) asks ``root()`` for the folder of that practice. It is kept per session thread, so two
people working on different practices at the same time never mix their files.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ["Id", "Name", "Description", "Active"]
_current: ContextVar[str] = ContextVar("academy_practice", default="")


@dataclass(frozen=True)
class Practice:
    id: str
    name: str
    description: str = ""
    active: bool = True

    def row(self) -> list[str]:
        return [self.id, self.name, self.description, "yes" if self.active else "no"]


def registry_path() -> Path:
    return Path(os.environ.get("ACADEMY_PRACTICES") or ROOT / "catalog" / "practices.csv")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:40]


def _first() -> Practice:
    """The practice the app always had (the app folder), named after its practice definition."""
    name = ""
    p = ROOT / "catalog" / "practice.json"
    try:
        name = json.loads(p.read_text(encoding="utf-8")).get("name", "") if p.exists() else ""
    except ValueError:
        pass
    name = name or "Main practice"
    return Practice(slug(name) or "main", name)


def parse(raw: bytes) -> tuple[list[Practice], list[str]]:
    text = raw.decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    rows = list(csv.DictReader(io.StringIO(text, newline=""), delimiter=";" if first.count(";") > first.count(",") else ","))
    out, problems, seen = [], [], set()
    for n, r in enumerate(rows, start=2):
        name = (r.get("Name") or "").strip()
        pid = slug(r.get("Id") or name)
        if not name and not pid:
            continue
        if not name or not pid:
            problems.append(f"[practices row {n}] needs a Name.")
            continue
        if pid in seen:
            problems.append(f"[practices row {n}] the id '{pid}' is repeated.")
            continue
        seen.add(pid)
        out.append(Practice(pid, name, (r.get("Description") or "").strip(),
                            (r.get("Active") or "yes").strip().lower() not in ("no", "n", "false", "0")))
    return out, problems


def to_csv(items: list[Practice]) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(COLUMNS)
    w.writerows(p.row() for p in items)
    return buf.getvalue().encode("utf-8-sig")


_cache: dict[str, tuple[float, list[Practice]]] = {}


def load() -> list[Practice]:
    """Every practice, the first one (the app folder) always first. Read again only when the file changes."""
    p = registry_path()
    stamp = p.stat().st_mtime_ns if p.exists() else -1
    hit = _cache.get(str(p))
    if hit and hit[0] == stamp:
        return list(hit[1])
    items = (parse(p.read_bytes())[0] if p.exists() else []) or [_first()]
    _cache[str(p)] = (stamp, items)
    return list(items)


def save(items: list[Practice]) -> Path:
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(to_csv(items))
    return p


def default_id() -> str:
    return load()[0].id


def find(pid: str) -> Practice | None:
    return next((p for p in load() if p.id == pid), None)


# ------------------------------------------------------------------------------------------------ the practice in use
def use(pid: str | None) -> str:
    """Work on this practice for the rest of the run (an unknown id falls back to the first practice). Returns the id."""
    ids = [p.id for p in load()]
    pid = pid if pid in ids else ids[0]
    _current.set(pid)
    return pid


def current() -> str:
    return _current.get() or default_id()


def root(pid: str | None = None) -> Path:
    """The folder of a practice: the app folder for the first one, practices/<id>/ for the rest."""
    pid = pid or current()
    return ROOT if pid == default_id() else practices_dir() / pid


def practices_dir() -> Path:
    """Where the practices after the first one live (ACADEMY_PRACTICES_DIR names another folder)."""
    return Path(os.environ.get("ACADEMY_PRACTICES_DIR") or ROOT / "practices")


# ------------------------------------------------------------------------------------------------ a new practice
def create(name: str, description: str = "", pid: str = "") -> Practice:
    """Add a practice and its folder, ready to fill: an empty catalog and paths, the practice definition, the news sources
    of the first practice as a start, an empty study bank and a first course to fill in ✏️ Edit mode."""
    items = load()
    if not registry_path().exists():
        items = [items[0]]  # the first practice is written down too
    pid = slug(pid or name)
    if not name.strip() or not pid:
        raise ValueError("A practice needs a name.")
    if any(p.id == pid for p in items):
        raise ValueError(f"There is already a practice with the id '{pid}'.")
    new = Practice(pid, name.strip(), description.strip())
    base = practices_dir() / pid
    (base / "catalog").mkdir(parents=True, exist_ok=True)
    for sub in ("content", "packs", "exams", "data", "export"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    today = __import__("datetime").date.today().isoformat()
    files = {
        base / "catalog" / "skills.json": {"meta": {"title": f"{new.name} skills catalog", "updated": today}, "families": [], "skills": []},
        base / "catalog" / "materials.json": {},
        base / "catalog" / "practice.json": {"name": new.name, "description": new.description, "skills": [], "roles": []},
    }
    for f, data in files.items():
        if not f.exists():
            f.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    news_src = ROOT / "catalog" / "news_sources.csv"
    if news_src.exists() and not (base / "catalog" / "news_sources.csv").exists():
        (base / "catalog" / "news_sources.csv").write_bytes(news_src.read_bytes())
    if not (base / "catalog" / "study_material.csv").exists():
        (base / "catalog" / "study_material.csv").write_text("Title,Url,Source,Category,Theme,Kind,Level,SkillId,Notes\r\n", encoding="utf-8-sig")
    starter = base / "packs" / pid / "pack.json"
    if not starter.exists():
        starter.parent.mkdir(parents=True, exist_ok=True)
        ranks = json.loads((ROOT / "packs" / "_template" / "pack.json").read_text(encoding="utf-8"))["meta"]["ranks"]
        first = next((ROOT / "packs").glob("*/pack.json"), None) if (ROOT / "packs").is_dir() else None
        if first is not None:  # the rank names of the first practice's course, instead of the template's placeholders
            try:
                ranks = json.loads(first.read_text(encoding="utf-8"))["meta"]["ranks"]
            except (ValueError, KeyError):
                pass
        pack = {"meta": {"id": pid, "title": f"{new.name} Practice", "language": "en", "version": "0.1", "updated": today,
                         "subtitle": f"The courses of the {new.name} practice. Owners add the lessons in ✏️ Edit mode or in the content workbook.",
                         "disclaimer": "", "ranks": ranks},
                "levels": ["Fundamentals"], "roles": {}, "topics": {}, "lessons": [], "glossary": [], "resources": {}}
        starter.write_text(json.dumps(pack, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    save(items + [new])
    return new


def update(items: list[Practice]) -> Path:
    """Save names, descriptions and Active of the existing practices (ids and folders never change)."""
    known = {p.id for p in load()}
    unknown = [p.id for p in items if p.id not in known]
    if unknown:
        raise ValueError(f"Unknown practice id(s): {', '.join(unknown)}. Add new practices with «Add a practice».")
    if not any(p.active for p in items):
        raise ValueError("At least one practice must stay active.")
    return save(items)
