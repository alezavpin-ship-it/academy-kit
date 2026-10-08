"""The course content as an Excel workbook: export everything, edit it in Excel, import it back.

One workbook holds every course (pack) in every language, plus the learning paths (vendor training) of the skills catalog:

    Cursos           one row per course and language (title, subtitle, version…)
    Niveles          the levels of each course, in order
    Rangos           the ranks and the points each one needs
    Temas            the topics of the video library
    Roles            the roles and the skills each one needs
    Lecciones        one row per lesson: level, title, summary, key points, practice link, skills
    Preguntas        the 3 check questions of each lesson (options A-D and the correct letter)
    VBD              the value-based deliverable of each lesson
    Recursos         the videos and links (title, URL, channel, language, topic…)
    LeccionRecursos  which videos each lesson shows, in order
    Glosario         terms and definitions
    Familias         the main skill families (editable): gap, roles affected, champion
    Skills           the skills of each family, each with its technology / vendor (Microsoft, AWS, GCP, Cisco, IBM…) and category
    LearningPaths    the career path of each skill: class 1, class 2… from any source (Microsoft Learn, the vendor's free
                     training, the company's own portal such as Workday Learning)

    Practica         the practice the academy serves: its name and description (one row)
    PracticaSkills   the skills / technologies of the practice as the demand writes them: term, aliases, the catalog skill
                     and family it maps to, vendor and scope (core | third-party | emerging). Anything else is «outside».
    PracticaRoles    the role titles the practice can staff, with aliases

Structure: skill family -> vendor -> skill -> classes in order. Another practice (ServiceNow, SAP…) reuses the academy by
replacing the catalog and practice tables.

The same content also travels as ONE CSV file (``export_csv``): every row starts with the column ``Tabla`` (the sheet it
belongs to) and uses the columns of that sheet; filter by ``Tabla`` in Excel to work on one table at a time.

Rows are tied by PackId + Lang (+ LessonId / ResourceKey). The same course in two languages must keep the same lesson
ids, in the same order, with the same correct answers, because progress is shared between languages.

``export_bytes`` builds the workbook; ``read`` parses one into pack dictionaries and reports every problem found;
``apply`` writes the files (after a backup). Nothing is written while there are problems.
"""

from __future__ import annotations

import io
import json
import shutil
from datetime import datetime
from pathlib import Path

import csv

from academy.catalog import (Catalog, Family, Skill, catalog_path, load_catalog, load_materials, materials_path, save_catalog, save_materials,
                             validate_catalog, validate_materials)
from academy.catalog import vendor_of
from academy.pack import PACKS_DIR, _parse, validate
from academy.practice import Practice, RoleTerm, Term, load_practice, practice_path, save_practice, scope_of
from academy.route import class_order

MAX_POINTS, MAX_CRITERIA = 8, 6
LETTERS = "ABCD"
SHEETS: dict[str, list[str]] = {
    "Cursos": ["PackId", "Lang", "Title", "Subtitle", "Disclaimer", "Version", "Updated"],
    "Niveles": ["PackId", "Lang", "SortOrder", "Level"],
    "Rangos": ["PackId", "Lang", "Name", "Points", "Emoji", "Color", "Image"],
    "Temas": ["PackId", "Lang", "TopicId", "Name"],
    "Roles": ["PackId", "Lang", "Role", "Skills"],
    "Lecciones": ["PackId", "Lang", "LessonId", "Level", "Title", "Summary"] + [f"Point{i}" for i in range(1, MAX_POINTS + 1)]
                 + ["PracticeLabel", "PracticeUrl", "Skills", "CatalogSkills"],
    "Preguntas": ["PackId", "Lang", "LessonId", "SortOrder", "Question", "OptionA", "OptionB", "OptionC", "OptionD", "AnswerLetter", "Why"],
    "VBD": ["PackId", "Lang", "LessonId", "Deliverable"] + [f"DoneWhen{i}" for i in range(1, MAX_CRITERIA + 1)]
           + ["Value", "WhereLabel", "WhereUrl"],
    "Recursos": ["PackId", "Lang", "ResourceKey", "Title", "Url", "Channel", "VideoLang", "TopicId", "Kind", "Level", "Who", "Verified", "Why"],
    "LeccionRecursos": ["PackId", "Lang", "LessonId", "SortOrder", "ResourceKey", "Note"],
    "Glosario": ["PackId", "Lang", "Term", "Category", "Definition"],
    "Familias": ["FamilyId", "Name", "GapVolume", "RoleImpact", "Champion", "ChampionEmail"],
    "Skills": ["SkillId", "Name", "FamilyId", "Vendor", "Category", "Confirmed", "Severity", "Target", "ImpactedRoles"],
    "LearningPaths": ["SkillId", "Family", "Vendor", "Skill", "Class", "Title", "Url", "Kind", "Provider", "Verified"],
    "Practica": ["Name", "Description"],
    "PracticaSkills": ["Term", "Aliases", "SkillId", "FamilyId", "Vendor", "Scope"],
    "PracticaRoles": ["RoleTitle", "Aliases", "Scope"],
}
OPTIONAL = {"Familias", "Skills", "Practica", "PracticaSkills", "PracticaRoles"}  # files made before the catalog was included keep working: the catalog on disk stays
TABLE = "Tabla"  # first column of the single CSV: the sheet each row belongs to
_KEYS = ["PackId", "Lang", "LessonId", "ResourceKey", "FamilyId", "SkillId", "SortOrder"]  # the columns that tie rows together go first
CSV_COLUMNS = [TABLE] + _KEYS + [c for c in dict.fromkeys(c for cols in SHEETS.values() for c in cols) if c not in _KEYS]
README = [
    "Academia - Cloud · contenido de los cursos / course content",
    "",
    "ES · Edita las hojas y vuelve a importar el archivo en la app (pestaña Equipo → Contenido de la academia) o con",
    "     python tools/content.py import <archivo.xlsx | archivo.csv>",
    "EN · Edit the sheets and import the file back in the app (Team tab → Academy content) or with the command above.",
    "",
    "Reglas / Rules",
    "1. No cambies los nombres de las hojas ni de las columnas. · Do not rename sheets or columns.",
    "2. PackId + Lang identifican el curso y su idioma (es / en). · PackId + Lang identify the course and its language.",
    "3. Cada lección necesita 3 preguntas con 4 opciones distintas y AnswerLetter = A, B, C o D.",
    "   Each lesson needs 3 questions with 4 distinct options and AnswerLetter = A, B, C or D.",
    "4. Cada lección necesita al menos 2 videos (LeccionRecursos) de 2 canales distintos, y un VBD con 3 criterios o más.",
    "   Each lesson needs at least 2 videos (LeccionRecursos) from 2 different channels, and a VBD with 3 criteria or more.",
    "5. El mismo curso en dos idiomas lleva las mismas lecciones, en el mismo orden y con la misma respuesta correcta.",
    "   The same course in two languages keeps the same lessons, in the same order, with the same correct answer.",
    "6. Kind en Recursos: video | playlist | link. Los videos deben ser de YouTube; todo lo demás es link.",
    "   Kind in Recursos: video | playlist | link. Videos must be YouTube; anything else is a link.",
    "7. LearningPaths: Kind = path | module | course | lab | tutorial cuenta como paso de la ruta; doc | guide | video es consulta.",
    "   LearningPaths: Kind = path | module | course | lab | tutorial counts as a route step; doc | guide | video is reference.",
    "8. Para añadir un idioma, copia las filas del curso y cambia Lang. · To add a language, copy the course rows and change Lang.",
    "9. Familias y Skills son el catálogo de skills: FamilyId y SkillId son los identificadores que usan Lecciones (CatalogSkills) y LearningPaths.",
    "   Familias and Skills are the skills catalog: FamilyId and SkillId are the ids used by Lecciones (CatalogSkills) and LearningPaths.",
    "10. Estructura: Familia -> Vendor (Microsoft, AWS, GCP, Cisco, IBM...) -> Skill -> clases. En Skills escribe Vendor y, si quieres, Category.",
    "    Structure: Family -> Vendor (Microsoft, AWS, GCP, Cisco, IBM...) -> Skill -> classes. In Skills write Vendor and, optionally, Category.",
    "12. Practica, PracticaSkills y PracticaRoles definen la práctica para el análisis de demanda: Term es el skill como lo escribe la demanda,",
    "    Aliases sus otros nombres (separados por ;), Scope = core | third-party | emerging. Lo que no aparezca ahí cuenta como fuera de la práctica.",
    "    Practica, PracticaSkills and PracticaRoles define the practice for the demand analysis: Term is the skill as the demand writes it,",
    "    Aliases its other names (separated by ;), Scope = core | third-party | emerging. Anything not listed counts as outside the practice.",
    "11. LearningPaths es la ruta de carrera de cada skill: Class = 1, 2, 3... es el orden de las clases; Provider es la fuente",
    "    (Microsoft Learn, el fabricante, Workday Learning...). Las columnas Family, Vendor y Skill son informativas: se toman de Skills.",
    "    LearningPaths is each skill's career path: Class = 1, 2, 3... is the order of the classes; Provider is the source",
    "    (Microsoft Learn, the vendor, Workday Learning...). The Family, Vendor and Skill columns are informative: they come from Skills.",
    "",
    "Al importar, la app revisa todo y no guarda nada si encuentra un problema; antes de guardar hace un respaldo.",
    "On import the app checks everything and saves nothing if it finds a problem; it makes a backup before saving.",
]


# ------------------------------------------------------------------------------------------------ files on disk
def pack_files(packs_dir: Path | None = None) -> list[Path]:
    """Every pack file: packs/<id>/pack.json and its translations pack.<lang>.json (template folders excluded)."""
    root = packs_dir or PACKS_DIR
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        if (d / "pack.json").exists():
            out += [d / "pack.json"] + sorted(d.glob("pack.*.json"))
    return out


def load_all(packs_dir: Path | None = None) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in pack_files(packs_dir)]


# ------------------------------------------------------------------------------------------------ export
def _rows(packs: list[dict], materials: dict[str, list[dict]], catalog, practice=None) -> dict[str, list[list]]:
    out: dict[str, list[list]] = {k: [] for k in SHEETS}
    practice = load_practice() if practice is None else practice
    if practice.name or practice.skills or practice.roles:
        out["Practica"] = [[practice.name, practice.description]]
        out["PracticaSkills"] = [[t.term, "; ".join(t.aliases), t.skill_id, t.family, t.vendor, t.scope] for t in practice.skills]
        out["PracticaRoles"] = [[r.title, "; ".join(r.aliases), r.scope] for r in practice.roles]
    for d in packs:
        m = d["meta"]
        key = [m["id"], m.get("language", "es")]
        out["Cursos"].append(key + [m.get("title", ""), m.get("subtitle", ""), m.get("disclaimer", ""), str(m.get("version", "")),
                                    str(m.get("updated", ""))])
        out["Niveles"] += [key + [i, lv] for i, lv in enumerate(d.get("levels", []), start=1)]
        out["Rangos"] += [key + [r["name"], r["points"], r.get("emoji", ""), r.get("color", ""), r.get("image", "")] for r in m.get("ranks", [])]
        out["Temas"] += [key + [k, v] for k, v in d.get("topics", {}).items()]
        out["Roles"] += [key + [k, "; ".join(v)] for k, v in d.get("roles", {}).items()]
        for les in d["lessons"]:
            lk = key + [les["id"]]
            pts = list(les.get("points", []))[:MAX_POINTS]
            pr = les.get("practice") or {}
            out["Lecciones"].append(lk + [les["level"], les["title"], les["summary"]] + pts + [""] * (MAX_POINTS - len(pts))
                                    + [pr.get("label", ""), pr.get("url", ""), "; ".join(les.get("skills", [])),
                                       "; ".join(les.get("catalog_skills", []))])
            for n, q in enumerate(les.get("quiz", []), start=1):
                opts = (list(q["options"]) + [""] * 4)[:4]
                out["Preguntas"].append(lk + [n, q["q"]] + opts + [LETTERS[q["answer"]] if 0 <= q["answer"] < 4 else "", q["why"]])
            v = les.get("vbd")
            if v:
                crit = list(v.get("done_when", []))[:MAX_CRITERIA]
                wh = v.get("where") or {}
                out["VBD"].append(lk + [v["deliverable"]] + crit + [""] * (MAX_CRITERIA - len(crit))
                                  + [v.get("value", ""), wh.get("label", ""), wh.get("url", "")])
            notes = les.get("resource_notes") or {}
            out["LeccionRecursos"] += [lk + [n, rk, notes.get(rk, "")] for n, rk in enumerate(les.get("resources", []), start=1)]
        for rk, r in d.get("resources", {}).items():
            out["Recursos"].append(key + [rk, r["title"], r["url"], r["channel"], r.get("lang", key[1]), r.get("topic", ""),
                                          r.get("kind", "video"), r.get("level", ""), r.get("who", ""), r.get("verified", ""), r.get("why", "")])
        out["Glosario"] += [key + [g["term"], g.get("category", ""), g["definition"]] for g in d.get("glossary", [])]
    if catalog:
        out["Familias"] = [[f.id, f.name, f.gap_volume, f.role_impact, f.champion, f.champion_email] for f in catalog.families]
        out["Skills"] = [[x.id, x.name, x.family, vendor_of(x, materials), x.category, "yes" if x.confirmed else "no", x.severity, x.target,
                          x.impacted_roles] for x in catalog.skills]
    # learning paths in the order of the structure: family -> vendor -> skill -> class 1, 2, 3… -> reference material
    fam_name = {f.id: f.name for f in catalog.families} if catalog else {}
    known = {x.id: x for x in catalog.skills} if catalog else {}
    fam_pos = {f.id: n for n, f in enumerate(catalog.families)} if catalog else {}

    def place(sid: str):
        x = known.get(sid)
        return (fam_pos.get(x.family, 999), vendor_of(x, materials) != "Microsoft", vendor_of(x, materials), x.name) if x else (9999, True, "", sid)

    for sid in sorted(materials, key=place):
        x = known.get(sid)
        head = [sid, fam_name.get(x.family, "") if x else "", vendor_of(x, materials) if x else "", x.name if x else ""]
        steps = class_order(materials[sid])
        for n, i in enumerate(steps, start=1):
            out["LearningPaths"].append(head + [n, i.get("title", ""), i.get("url", ""), i.get("kind", ""), i.get("provider", ""), i.get("verified", "")])
        for i in materials[sid]:
            if i not in steps:
                out["LearningPaths"].append(head + ["", i.get("title", ""), i.get("url", ""), i.get("kind", ""), i.get("provider", ""),
                                                    i.get("verified", "")])
    return out


def export_bytes(packs: list[dict] | None = None, materials: dict | None = None, catalog=None) -> bytes:
    """The workbook with everything on disk (or with the given packs / materials)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    packs = load_all() if packs is None else packs
    materials = load_materials() if materials is None else materials
    catalog = catalog if catalog is not None else load_catalog()
    rows = _rows(packs, materials, catalog)
    wb = Workbook()
    ws = wb.active
    ws.title = "LEEME"
    for line in README:
        ws.append([line])
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width = 130
    wide = {"Summary", "Question", "Why", "Deliverable", "Value", "Definition", "Title", "Subtitle", "Disclaimer", "Url", "Note", "Description",
            "Aliases", "Term"}
    for name, cols in SHEETS.items():
        ws = wb.create_sheet(name)
        ws.append(cols)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="1C1C1E")
            cell.fill = PatternFill("solid", fgColor="FF5800")
        for r in rows[name]:
            ws.append(r)
        for n, col in enumerate(cols, start=1):
            long = col in wide or col.startswith(("Point", "DoneWhen", "Option"))
            ws.column_dimensions[get_column_letter(n)].width = 46 if long else 18
            if long:
                for cell in ws[get_column_letter(n)][1:]:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "D2" if name not in ("LearningPaths", "Cursos", "Familias", "Skills", "Practica", "PracticaSkills", "PracticaRoles") else "B2"
        ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_csv(packs: list[dict] | None = None, materials: dict | None = None, catalog=None) -> str:
    """Everything in ONE CSV: the column ``Tabla`` says which table a row belongs to; the rest are that table's columns."""
    packs = load_all() if packs is None else packs
    materials = load_materials() if materials is None else materials
    catalog = catalog if catalog is not None else load_catalog()
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(CSV_COLUMNS)
    for name, rows in _rows(packs, materials, catalog).items():
        cols = SHEETS[name]
        for r in rows:
            rec = dict(zip(cols, r))
            w.writerow([name] + ["" if rec.get(c) is None else rec.get(c, "") for c in CSV_COLUMNS[1:]])
    return buf.getvalue()


def csv_bytes(text: str) -> bytes:
    """With the mark Excel needs to open accents correctly."""
    return text.encode("utf-8-sig")


# ------------------------------------------------------------------------------------------------ import
def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, datetime):
        return v.date().isoformat()
    return str(v).strip()


def _list(v) -> list[str]:
    return [x.strip() for x in _text(v).replace(",", ";").split(";") if x.strip()]


def _sheet(wb, name: str, problems: list[str]) -> list[dict]:
    """Rows of a sheet as dictionaries keyed by its header; reports missing sheets and columns."""
    if name not in wb.sheetnames:
        problems.append(f"Falta la hoja «{name}». · Sheet \"{name}\" is missing.")
        return []
    it = wb[name].iter_rows(values_only=True)
    head = [_text(h) for h in next(it, [])]
    missing = [c for c in SHEETS[name] if c not in head]
    if missing:
        problems.append(f"[{name}] faltan columnas · missing columns: {', '.join(missing)}.")
        return []
    out = []
    for n, row in enumerate(it, start=2):
        rec = dict(zip(head, row))
        if any(_text(v) for v in row):
            rec["_row"] = n
            out.append(rec)
    return out


def _yes(v) -> bool:
    return _text(v).lower() not in ("no", "false", "falso", "0", "n")


def _int(v) -> int | None:
    try:
        return int(float(_text(v))) if _text(v) else None
    except ValueError:
        return None


def _load_csv(raw: bytes, problems: list[str]) -> dict[str, list[dict]]:
    """Rows of the single CSV grouped by table. Accepts comma or semicolon (what Excel writes depends on the regional settings)."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")  # Excel's «CSV (delimitado por comas)» in Windows
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") > first.count(",") else ("\t" if first.count("\t") > first.count(",") else ",")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
    data: dict[str, list[dict]] = {name: [] for name in SHEETS}
    if not rows or TABLE not in [h.strip() for h in rows[0]]:
        problems.append(f"El CSV no tiene la columna «{TABLE}» en la primera fila. · The CSV has no \"{TABLE}\" column in its first row.")
        return data
    head = [h.strip() for h in rows[0]]
    for name, cols in SHEETS.items():
        missing = [c for c in cols if c not in head]
        if missing and name not in OPTIONAL:
            problems.append(f"[{name}] faltan columnas · missing columns: {', '.join(missing)}.")
    for n, row in enumerate(rows[1:], start=2):
        rec = dict(zip(head, row))
        name = _text(rec.get(TABLE))
        if not any(_text(v) for v in row):
            continue
        if name not in SHEETS:
            problems.append(f"[fila {n}] {TABLE} = '{name}' no es una tabla conocida · is not a known table ({', '.join(SHEETS)}).")
            continue
        out = {c: rec.get(c, "") for c in SHEETS[name]}
        out["_row"] = n
        data[name].append(out)
    return data


def _catalog(data: dict, previous, problems: list[str]):
    """The skills catalog from the Familias / Skills tables; the one on disk when the file does not carry them."""
    if not data["Familias"] and not data["Skills"]:
        return previous, False
    old = {s.id: s for s in previous.skills} if previous else {}
    fams = [Family(_text(f["FamilyId"]), _text(f["Name"]), _int(f["GapVolume"]), _int(f["RoleImpact"]), _text(f["Champion"]),
                   _text(f["ChampionEmail"])) for f in data["Familias"]]
    skills = []
    for x in data["Skills"]:
        sid = _text(x["SkillId"])
        skills.append(Skill(sid, _text(x["Name"]), _text(x["FamilyId"]), _yes(x["Confirmed"]), _text(x["Severity"]), _text(x["Target"]),
                            _int(x["ImpactedRoles"]), list(old[sid].roles) if sid in old else [],  # role names never travel in the file
                            _text(x.get("Vendor")), _text(x.get("Category"))))
    for f in fams:
        if not f.id or not f.name:
            problems.append("[Familias] hay una fila sin FamilyId o sin Name. · a row has no FamilyId or no Name.")
    for x in skills:
        if not x.id or not x.name:
            problems.append("[Skills] hay una fila sin SkillId o sin Name. · a row has no SkillId or no Name.")
    cat = Catalog(fams, skills)
    problems += [f"[catálogo · catalog] {e}" for e in validate_catalog(cat)]
    return cat, True


def read(source, catalog=None) -> dict:
    """Parse a content file: the Excel workbook or the single CSV (bytes, a path or a file-like object).

    Returns {"packs": {(id, lang): dict}, "materials": {...}, "catalog": Catalog | None, "problems": [...], "summary": [...]}.
    ``problems`` lists everything that must be fixed in the file before it can be applied (empty = ready)."""
    from openpyxl import load_workbook

    problems: list[str] = []
    if isinstance(source, (str, Path)):
        raw = Path(source).read_bytes()
    else:
        raw = source if isinstance(source, (bytes, bytearray)) else source.read()
    if raw[:2] == b"PK":  # an .xlsx is a zip
        try:
            wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except Exception as e:  # damaged, password protected…
            return {"packs": {}, "materials": {}, "catalog": None, "new_catalog": False,
                    "problems": [f"No pude abrir el archivo · could not open the file: {e}"], "summary": [], "learning_paths": 0}
        data = {name: ([] if name in OPTIONAL and name not in wb.sheetnames else _sheet(wb, name, problems)) for name in SHEETS}
    else:
        data = _load_csv(bytes(raw), problems)
    catalog = catalog if catalog is not None else load_catalog()
    catalog, new_catalog = _catalog(data, catalog, problems)

    def of(name: str, key: tuple) -> list[dict]:
        return [r for r in data[name] if (_text(r["PackId"]), _text(r["Lang"])) == key]

    packs: dict[tuple, dict] = {}
    for c in data["Cursos"]:
        key = (_text(c["PackId"]), _text(c["Lang"]))
        tag = f"[{key[0]} · {key[1]}]"
        if not all(key):
            problems.append(f"[Cursos fila {c['_row']}] falta PackId o Lang. · PackId or Lang is missing.")
            continue
        if key in packs:
            problems.append(f"{tag} está repetido en Cursos. · is repeated in Cursos.")
            continue
        ranks = []
        for r in of("Rangos", key):
            try:
                rank = {"name": _text(r["Name"]), "points": int(float(_text(r["Points"]) or 0)), "emoji": _text(r["Emoji"]), "color": _text(r["Color"])}
            except ValueError:
                problems.append(f"{tag} [Rangos fila {r['_row']}] Points debe ser un número. · Points must be a number.")
                continue
            if _text(r.get("Image")):
                rank["image"] = _text(r["Image"])
            ranks.append(rank)
        meta = {"id": key[0], "title": _text(c["Title"]), "subtitle": _text(c["Subtitle"]), "language": key[1], "version": _text(c["Version"]) or "1.0",
                "updated": _text(c["Updated"]), "disclaimer": _text(c["Disclaimer"]), "ranks": ranks}
        levels = [_text(r["Level"]) for r in sorted(of("Niveles", key), key=lambda r: float(_text(r["SortOrder"]) or 0))]
        quiz_rows, vbd_rows, lr_rows = of("Preguntas", key), of("VBD", key), of("LeccionRecursos", key)
        lessons = []
        for r in of("Lecciones", key):
            lid = _text(r["LessonId"])
            les = {"id": lid, "level": _text(r["Level"]), "title": _text(r["Title"]), "summary": _text(r["Summary"]),
                   "points": [p for p in (_text(r.get(f"Point{i}")) for i in range(1, MAX_POINTS + 1)) if p],
                   "skills": _list(r["Skills"]), "catalog_skills": _list(r["CatalogSkills"])}
            practice = {k: v for k, v in (("label", _text(r["PracticeLabel"])), ("url", _text(r["PracticeUrl"]))) if v}
            if practice:
                les["practice"] = practice
            quiz = []
            for q in sorted((x for x in quiz_rows if _text(x["LessonId"]) == lid), key=lambda x: float(_text(x["SortOrder"]) or 0)):
                letter = _text(q["AnswerLetter"]).upper()
                if letter not in LETTERS or not letter:
                    problems.append(f"{tag} [Preguntas fila {q['_row']}] AnswerLetter debe ser A, B, C o D. · AnswerLetter must be A, B, C or D.")
                    letter = "A"
                quiz.append({"q": _text(q["Question"]), "options": [_text(q[f"Option{x}"]) for x in LETTERS], "answer": LETTERS.index(letter),
                             "why": _text(q["Why"])})
            les["quiz"] = quiz
            v = next((x for x in vbd_rows if _text(x["LessonId"]) == lid), None)
            if v:
                vbd = {"deliverable": _text(v["Deliverable"]),
                       "done_when": [d for d in (_text(v.get(f"DoneWhen{i}")) for i in range(1, MAX_CRITERIA + 1)) if d], "value": _text(v["Value"])}
                where = {k: x for k, x in (("label", _text(v["WhereLabel"])), ("url", _text(v["WhereUrl"]))) if x}
                if where:
                    vbd["where"] = where
                les["vbd"] = vbd
            mine = sorted((x for x in lr_rows if _text(x["LessonId"]) == lid), key=lambda x: float(_text(x["SortOrder"]) or 0))
            les["resources"] = [_text(x["ResourceKey"]) for x in mine]
            notes = {_text(x["ResourceKey"]): _text(x["Note"]) for x in mine if _text(x["Note"])}
            if notes:
                les["resource_notes"] = notes
            lessons.append(les)
        known = {les["id"] for les in lessons}
        for name in ("Preguntas", "VBD", "LeccionRecursos"):
            for x in of(name, key):
                if _text(x["LessonId"]) not in known:
                    problems.append(f"{tag} [{name} fila {x['_row']}] la lección '{_text(x['LessonId'])}' no está en Lecciones. · lesson not in Lecciones.")
        resources = {}
        for r in of("Recursos", key):
            rk = _text(r["ResourceKey"])
            if rk in resources:
                problems.append(f"{tag} [Recursos fila {r['_row']}] ResourceKey '{rk}' repetido. · repeated ResourceKey.")
            resources[rk] = {"title": _text(r["Title"]), "url": _text(r["Url"]), "channel": _text(r["Channel"]), "lang": _text(r["VideoLang"]) or key[1],
                             "topic": _text(r["TopicId"]), "why": _text(r["Why"]), "kind": _text(r["Kind"]) or "video",
                             "level": _text(r["Level"]) or "básico", "who": _text(r["Who"]), "verified": _text(r["Verified"])}
        pack = {"meta": meta, "levels": levels, "roles": {_text(r["Role"]): _list(r["Skills"]) for r in of("Roles", key)},
                "topics": {_text(r["TopicId"]): _text(r["Name"]) for r in of("Temas", key)}, "lessons": lessons,
                "glossary": [{"term": _text(g["Term"]), "category": _text(g["Category"]), "definition": _text(g["Definition"])} for g in of("Glosario", key)],
                "resources": resources}
        packs[key] = pack
        if not ranks:
            problems.append(f"{tag} no tiene rangos en la hoja Rangos. · has no ranks in the Rangos sheet.")
        else:
            try:
                problems += [f"{tag} {e}" for e in validate(_parse(pack), catalog)]
            except Exception as e:  # a structural hole the checks above did not name
                problems.append(f"{tag} contenido incompleto · incomplete content: {e}")
    # the same course in two languages must mirror: same lessons in the same order, same correct answers
    for pid in sorted({k[0] for k in packs}):
        versions = [packs[k] for k in packs if k[0] == pid]
        base = versions[0]
        shape = [(les["id"], [q["answer"] for q in les["quiz"]]) for les in base["lessons"]]
        for other in versions[1:]:
            if [(les["id"], [q["answer"] for q in les["quiz"]]) for les in other["lessons"]] != shape:
                problems.append(f"[{pid}] los idiomas {base['meta']['language']} y {other['meta']['language']} no coinciden en lecciones, orden o "
                                "respuesta correcta. · the languages do not match in lessons, order or correct answer.")
            if len(other["levels"]) != len(base["levels"]):
                problems.append(f"[{pid}] los idiomas no tienen el mismo número de niveles. · the languages do not have the same number of levels.")
    if not packs:
        problems.append("La hoja Cursos no tiene ningún curso. · The Cursos sheet has no course.")
    materials: dict[str, list[dict]] = {}
    for r in sorted(data["LearningPaths"], key=lambda r: (_int(r.get("Class")) is None, _int(r.get("Class")) or 0)):  # stable: class 1, 2, 3…
        item = {"title": _text(r["Title"]), "url": _text(r["Url"]), "kind": _text(r["Kind"]), "provider": _text(r["Provider"]),
                "verified": _text(r["Verified"])}
        item = {k: v for k, v in item.items() if v}
        if _int(r.get("Class")):
            item["order"] = _int(r["Class"])
        materials.setdefault(_text(r["SkillId"]), []).append(item)
    problems += validate_materials(materials, catalog)
    summary = [{"PackId": k[0], "Lang": k[1], "Lecciones": len(p["lessons"]), "Preguntas": sum(len(x["quiz"]) for x in p["lessons"]),
                "Recursos": len(p["resources"]), "Glosario": len(p["glossary"])} for k, p in packs.items()]
    practice = None
    if data["Practica"] or data["PracticaSkills"] or data["PracticaRoles"]:
        head = data["Practica"][0] if data["Practica"] else {}
        practice = Practice(_text(head.get("Name")), _text(head.get("Description")),
                            [Term(_text(r["Term"]), tuple(x.strip() for x in _text(r["Aliases"]).split(";") if x.strip()), _text(r["SkillId"]),
                                  _text(r["FamilyId"]), _text(r["Vendor"]), scope_of(_text(r["Scope"]))) for r in data["PracticaSkills"] if _text(r["Term"])],
                            [RoleTerm(_text(r["RoleTitle"]), tuple(x.strip() for x in _text(r["Aliases"]).split(";") if x.strip()),
                                      scope_of(_text(r["Scope"]))) for r in data["PracticaRoles"] if _text(r["RoleTitle"])])
        if catalog:
            fams, ids = {f.id for f in catalog.families}, catalog.skill_ids()
            for t in practice.skills:
                if t.skill_id and t.skill_id not in ids:
                    problems.append(f"[PracticaSkills] '{t.term}': SkillId '{t.skill_id}' no existe en Skills. · is not in Skills.")
                if t.family and t.family not in fams:
                    problems.append(f"[PracticaSkills] '{t.term}': FamilyId '{t.family}' no existe en Familias. · is not in Familias.")
    return {"packs": packs, "materials": materials, "catalog": catalog, "new_catalog": new_catalog, "practice": practice, "problems": problems, "summary": summary,
            "learning_paths": sum(len(v) for v in materials.values()),
            "families": len(catalog.families) if catalog else 0, "skills": len(catalog.skills) if catalog else 0}


def target_file(pack_id: str, lang: str, packs_dir: Path | None = None) -> Path:
    """packs/<id>/pack.json for the course's base language, pack.<lang>.json for a translation."""
    folder = (packs_dir or PACKS_DIR) / pack_id
    base = folder / "pack.json"
    if base.exists():
        base_lang = json.loads(base.read_text(encoding="utf-8"))["meta"].get("language", "es")
        return base if lang == base_lang else folder / f"pack.{lang}.json"
    return base if lang == "es" or not folder.exists() else folder / f"pack.{lang}.json"


def apply(result: dict, packs_dir: Path | None = None, backup_dir: Path | None = None) -> list[Path]:
    """Write what ``read`` parsed. Refuses while there are problems. Returns the files written (backup first)."""
    if result["problems"]:
        raise ValueError("El Excel tiene problemas; no se guardó nada. · The workbook has problems; nothing was saved.")
    root = packs_dir or PACKS_DIR
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = (backup_dir or root.parent / "data" / "content_backups") / stamp
    written = []
    # a brand-new course written in one language only: that language is its base file
    new_ids = {k[0] for k in result["packs"] if not (root / k[0] / "pack.json").exists()}
    base_lang = {pid: next(k[1] for k in result["packs"] if k[0] == pid) for pid in new_ids}
    for (pid, lang), pack in result["packs"].items():
        path = root / pid / "pack.json" if base_lang.get(pid) == lang else target_file(pid, lang, root)
        if pid in new_ids and base_lang[pid] != lang:
            path = root / pid / f"pack.{lang}.json"
        if path.exists():
            (backup / pid).mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup / pid / path.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(pack, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        written.append(path)
    mp, cp, pp = materials_path(), catalog_path(), practice_path()
    if result.get("practice") is not None:
        if pp.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pp, backup / pp.name)
        written.append(save_practice(result["practice"]))
    for f in (mp, cp):
        if f.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, backup / f.name)
    if result.get("new_catalog") and result.get("catalog"):
        written.append(save_catalog(result["catalog"], source="Archivo de contenido", updated=datetime.now().date().isoformat()))
    written.append(save_materials(result["materials"]))
    return written
