"""One-time move to an English-only academy (earlier versions kept Spanish and English side by side).

``migrate()`` runs when the app starts and does nothing once everything is English:

* courses (packs/<id>/) and exams (exams/<id>/): the English translation (pack.en.json / exam.en.json) becomes the only file
  and the other languages are removed; videos in other languages are dropped from the course;
* the content workbook and the demand files get their English names.

Everything that is replaced or removed is copied first to data/content_backups/<date>-english/. Progress is kept: the
lessons and questions have the same ids in every language.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEVEL_EN = {"básico": "basic", "basico": "basic", "intermedio": "intermediate", "avanzado": "advanced"}
RENAMES = [("content/academia_contenido.xlsx", "content/academy_content.xlsx"), ("content/academia_contenido.csv", "content/academy_content.csv"),
           ("content/demanda_roles.csv", "content/demand_roles.csv"), ("content/demanda_historial", "content/demand_history"),
           ("content/demanda_roles_ejemplo.csv", "content/demand_roles_sample.csv"),
           ("content/demanda_roles_ejemplo_semana_anterior.csv", "content/demand_roles_sample_previous_week.csv"),
           ("catalog/ejemplo_upskilling_plan.xlsx", "catalog/sample_upskilling_plan.xlsx")]
# Spanish files replaced by an English one shipped with the app: removed (after a backup) once the English one is there
REPLACED = [("packs/_plantilla", "packs/_template"), ("Instalar componentes.bat", "Install components.bat"),
            ("content/demanda_roles_ejemplo.csv", "content/demand_roles_sample.csv"),
            ("content/demanda_roles_ejemplo_semana_anterior.csv", "content/demand_roles_sample_previous_week.csv"),
            ("catalog/ejemplo_upskilling_plan.xlsx", "catalog/sample_upskilling_plan.xlsx")]


def _backup(root: Path, stamp: str, path: Path) -> None:
    dest = root / "data" / "content_backups" / f"{stamp}-english" / path.relative_to(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        shutil.copytree(path, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(path, dest)


def _clean_pack(d: dict) -> dict:
    """Only English videos, English level names, language = en."""
    res = {k: r for k, r in d.get("resources", {}).items() if r.get("lang", "en") == "en"}
    for r in res.values():
        r["level"] = LEVEL_EN.get(r.get("level", ""), r.get("level", ""))
    for les in d.get("lessons", []):
        les.pop("vbd", None)
        les["resources"] = [k for k in les.get("resources", []) if k in res]
        notes = {k: v for k, v in les.get("resource_notes", {}).items() if k in res}
        if notes:
            les["resource_notes"] = notes
        else:
            les.pop("resource_notes", None)
    d["resources"] = res
    d.setdefault("meta", {})["language"] = "en"
    return d


def _folder(root: Path, folder: Path, name: str, stamp: str, clean) -> bool:
    """name = 'pack' or 'exam'. Returns True when something changed."""
    base, en = folder / f"{name}.json", folder / f"{name}.en.json"
    others = [p for p in folder.glob(f"{name}.*.json")]
    changed = False
    base_lang = ""
    if base.exists():
        try:
            data = json.loads(base.read_text(encoding="utf-8"))
            base_lang = data.get("meta", data).get("language", "")
        except ValueError:
            pass
    if en.exists():
        for p in [base] + others:
            if p.exists():
                _backup(root, stamp, p)
        if base_lang == "en":  # the main file is already the English one (a newer version was copied in): keep it
            en.unlink()
        else:
            en.replace(base)
        changed = True
    for p in folder.glob(f"{name}.*.json"):  # any other language left
        _backup(root, stamp, p)
        p.unlink()
        changed = True
    if base.exists():
        raw = base.read_text(encoding="utf-8")
        data = json.loads(raw)
        meta = data.get("meta", data)
        if meta.get("language", "en") != "en" and not changed:
            return changed  # a course that only exists in another language: kept as it is (translate it in the workbook)
        new = clean(data)
        text = json.dumps(new, ensure_ascii=False, indent=1) + "\n"
        if text != raw and json.loads(raw) != new:
            if not changed:
                _backup(root, stamp, base)
            base.write_text(text, encoding="utf-8")
            changed = True
    return changed


def _clean_exam(d: dict) -> dict:
    d.get("meta", d)["language"] = "en"
    return d


def migrate(root: Path | None = None) -> bool:
    """Returns True when something was converted (the caller clears its caches)."""
    root = root or ROOT
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    changed = False
    for kind, name, clean in (("packs", "pack", _clean_pack), ("exams", "exam", _clean_exam)):
        top = root / kind
        if top.is_dir():
            for folder in sorted(p for p in top.iterdir() if p.is_dir() and not p.name.startswith("_")):
                changed |= _folder(root, folder, name, stamp, clean)
    cat = root / "catalog" / "skills.json"
    if cat.exists():  # the catalog's own description (shown nowhere, but kept in English too)
        data = json.loads(cat.read_text(encoding="utf-8"))
        meta = data.get("meta", {})
        if any(ch in json.dumps(meta, ensure_ascii=False) for ch in "áéíóúñ«»"):
            _backup(root, stamp, cat)
            data["meta"] = {"title": "Skills catalog", "updated": meta.get("updated", ""),
                            "source": "Team gap report (skill families with Gap Volume and Role Impact Count).",
                            "note": "'champion' = who leads the family's upskilling (empty = to be assigned). This file is replaced when the "
                                    "content workbook is imported or the catalog is edited in the app."}
            cat.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed = True
    for old, new in REPLACED:
        o, n = root / old, root / new
        if o.exists() and n.exists():
            _backup(root, stamp, o)
            shutil.rmtree(o) if o.is_dir() else o.unlink()
            changed = True
    for old, new in RENAMES:
        o, n = root / old, root / new
        if o.exists() and not n.exists():
            o.replace(n)
            changed = True
    return changed
