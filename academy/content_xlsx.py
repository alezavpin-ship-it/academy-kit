"""The academy content as an Excel workbook: export everything, edit it in Excel (or in the app's edit mode), import it back.

One workbook holds every course (pack), the skills catalog with its learning paths, and the practice definition. Everything
is in English: one row per thing, no language columns.

    Families         the main role families (editable): gap, roles affected, champion
    Skills           the skills of each family, each with its technology / vendor and category
    LearningPaths    the career path of each skill: class 1, class 2… from any source (Microsoft Learn, the vendor's free
                     training, the company's own portal such as Workday Learning)
    Practice         the practice the academy serves: its name and description (one row)
    PracticeSkills   the skills of the practice as the demand writes them: term, aliases, catalog skill, family, vendor, scope
    PracticeRoles    the role titles the practice can staff, with aliases
    NewsSources      the security news sites the practice follows (Knowledge exchange; also catalog/news_sources.csv)
    People           who is who: owners, champions and SMEs of each family (also catalog/people.csv)
    StudyMaterial    recommended training content by theme, e.g. John Savill's videos (also catalog/study_material.csv)
    Courses          one row per course (title, subtitle, version…)
    Levels / Ranks / Topics / Roles   the levels, ranks, video-library topics and roles of each course
    Lessons          one row per lesson: level, title, summary, key points, practice link, skills
    Questions        the 3 check questions of each lesson (options A-D and the correct letter)
    Resources        the videos and links (title, URL, channel, topic…)
    LessonResources  which videos each lesson shows, in order
    Glossary         terms and definitions

The same content also travels as ONE CSV file (``export_csv``): every row starts with the column ``Table``.

Files written by earlier versions (Spanish sheet names, a ``Lang`` column, the ``VBD`` sheet) are still read: sheets are
matched by their former names, only the English rows are kept and retired sheets are ignored.

``export_bytes`` builds the workbook; ``read`` parses one and reports every problem; ``build`` does the same from tables in
memory (the in-app editor); ``apply`` writes the files (after a backup). Nothing is written while there are problems.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
from datetime import datetime
from pathlib import Path

from academy import news, people, study
from academy.catalog import (Catalog, Family, Skill, catalog_path, load_catalog, load_materials, materials_path, save_catalog, save_materials,
                             validate_catalog, validate_materials, vendor_of)
from academy.pack import _parse, packs_dir as _packs_dir, validate
from academy.practice import Practice, RoleTerm, Term, load_practice, practice_path, save_practice, scope_of
from academy.family_path import status_of
from academy.route import class_order

LANGUAGE = "en"  # the only language of the academy
MAX_POINTS = 8
LETTERS = "ABCD"
SHEETS: dict[str, list[str]] = {
    "Families": ["FamilyId", "Name", "GapVolume", "RoleImpact", "Champion", "ChampionEmail"],
    "Skills": ["SkillId", "Name", "FamilyId", "Vendor", "Category", "Confirmed", "Severity", "Target", "ImpactedRoles"],
    "LearningPaths": ["SkillId", "Family", "Vendor", "Skill", "Class", "Title", "Url", "Kind", "Provider", "Status", "Minutes", "Notes", "Verified"],
    "Practice": ["Name", "Description"],
    "PracticeSkills": ["Term", "Aliases", "SkillId", "FamilyId", "Vendor", "Scope"],
    "PracticeRoles": ["RoleTitle", "Aliases", "Scope"],
    "NewsSources": ["Name", "Category", "Url", "FeedUrl", "Splash", "Enabled", "Description"],
    "People": ["Person", "Email", "Role", "Families", "Active", "CourseRole"],
    "StudyMaterial": ["Title", "Url", "Source", "Category", "Theme", "Kind", "Level", "SkillId", "Notes"],
    "Courses": ["PackId", "Title", "Subtitle", "Disclaimer", "Version", "Updated"],
    "Levels": ["PackId", "SortOrder", "Level"],
    "Ranks": ["PackId", "Name", "Points", "Emoji", "Color", "Image"],
    "Topics": ["PackId", "TopicId", "Name"],
    "Roles": ["PackId", "Role", "Skills"],
    "Lessons": ["PackId", "LessonId", "Level", "Title", "Summary"] + [f"Point{i}" for i in range(1, MAX_POINTS + 1)]
               + ["PracticeLabel", "PracticeUrl", "Skills", "CatalogSkills"],
    "Questions": ["PackId", "LessonId", "SortOrder", "Question", "OptionA", "OptionB", "OptionC", "OptionD", "AnswerLetter", "Why"],
    "Resources": ["PackId", "ResourceKey", "Title", "Url", "Channel", "TopicId", "Kind", "Level", "Who", "Verified", "Why"],
    "LessonResources": ["PackId", "LessonId", "SortOrder", "ResourceKey", "Note"],
    "Glossary": ["PackId", "Term", "Category", "Definition"],
}
# The workbook groups the tables by what they manage; each group has its tab color (the order of the tabs follows it).
SECTIONS = [
    ("Skills catalog", "FF5800", ["Families", "Skills", "LearningPaths"],
     "Role families, their skills (with vendor) and each skill's career path (class 1, 2, 3…)."),
    ("Practice", "2A78D6", ["Practice", "PracticeSkills", "PracticeRoles", "NewsSources", "People"],
     "What the practice is, the skills and roles it covers (demand analysis), the news it follows and who is who (owners, champions, SMEs)."),
    ("Courses", "6B6762", ["Courses", "Levels", "Ranks", "Topics", "Roles"],
     "General data of each course: levels, ranks, topics of the video library and roles."),
    ("Lessons", "1C1C1E", ["Lessons", "Questions"], "Each lesson with its key points and its 3 check questions."),
    ("Videos and links", "1BAF7A", ["Resources", "LessonResources", "StudyMaterial"],
     "The videos and links (URL, channel), the lessons that show them, and the study material bank (Knowledge exchange, Video library)."),
    ("Glossary", "4A3AA7", ["Glossary"], "Terms and definitions of each course."),
]
SHEETS = {name: SHEETS[name] for _, _, names, _ in SECTIONS for name in names}
TAB_COLOR = {name: color for _, color, names, _ in SECTIONS for name in names}
# fixed values offered as a drop-down list (in the workbook and in the app's edit mode); anything else is reported on import
CHOICES = {"AnswerLetter": list("ABCD"), "Confirmed": ["yes", "no"], "Severity": ["High", "Medium", "Low"],
           "Scope": ["core", "third-party", "emerging"],
           ("Resources", "Kind"): ["video", "playlist", "link"], ("Resources", "Level"): ["basic", "intermediate", "advanced"],
           ("NewsSources", "Splash"): ["yes", "no"], ("NewsSources", "Enabled"): ["yes", "no"],
           ("People", "Role"): ["owner", "champion", "sme", "learner"], ("People", "Active"): ["yes", "no"],
           ("StudyMaterial", "Kind"): ["video", "playlist", "search", "page"], ("StudyMaterial", "Level"): ["basic", "intermediate", "advanced"],
           ("LearningPaths", "Kind"): ["path", "module", "course", "lab", "tutorial", "deck", "doc", "guide", "video", "exam"],
           ("LearningPaths", "Status"): ["required", "optional", "off"]}
NEW_COLUMNS = {"Status", "Minutes", "Notes"}  # columns added later: files written before them still import
OPTIONAL = {"Families", "Skills", "Practice", "PracticeSkills", "PracticeRoles", "NewsSources", "People", "StudyMaterial"}  # without them the catalog / practice on disk stays
TABLE = "Table"  # first column of the single CSV: the sheet each row belongs to
# names used by earlier versions of the file
LEGACY_SHEETS = {"Cursos": "Courses", "Niveles": "Levels", "Rangos": "Ranks", "Temas": "Topics", "Lecciones": "Lessons", "Preguntas": "Questions",
                 "Recursos": "Resources", "LeccionRecursos": "LessonResources", "Glosario": "Glossary", "Familias": "Families",
                 "Practica": "Practice", "PracticaSkills": "PracticeSkills", "PracticaRoles": "PracticeRoles"}
RETIRED = {"VBD", "LEEME", "README"}  # sheets that are not content tables (or no longer exist): ignored on import
LEGACY_TABLE = "Tabla"
LEVEL_EN = {"básico": "basic", "basico": "basic", "intermedio": "intermediate", "avanzado": "advanced"}
_KEYS = ["PackId", "LessonId", "ResourceKey", "FamilyId", "SkillId", "SortOrder"]  # the columns that tie rows together go first
CSV_COLUMNS = [TABLE] + _KEYS + [c for c in dict.fromkeys(c for cols in SHEETS.values() for c in cols) if c not in _KEYS]
README = [
    "Academia - Cloud · academy content",
    "",
    "Edit the sheets and import the file back in the app (Team tab → Practice content), use the app's ✏️ Edit mode, or run",
    "     python tools/content.py import <file.xlsx | file.csv>",
    "",
    "Rules",
    "1. Do not rename tabs or columns; add rows freely. Columns with a drop-down list only take those values.",
    "2. PackId identifies the course. Every course is in English.",
    "3. Each lesson needs 3 questions with 4 distinct options and AnswerLetter = A, B, C or D.",
    "4. Each lesson needs at least 2 videos (LessonResources) from 2 different channels.",
    "5. Kind in Resources: video | playlist | link. Videos must be YouTube; anything else is a link.",
    "6. LearningPaths: Kind = path | module | course | lab | tutorial counts as a route step; doc | guide | video is reference.",
    "7. Families and Skills are the skills catalog: FamilyId and SkillId are the ids used by Lessons (CatalogSkills) and LearningPaths.",
    "8. Structure: Family -> Vendor (Microsoft, AWS, GCP, Cisco, IBM...) -> Skill -> classes. In Skills write Vendor and, optionally, Category.",
    "9. LearningPaths: Class = 1, 2, 3... is the order of the classes; Provider is the source (Microsoft Learn, the vendor,",
    "   Workday Learning...). The Family, Vendor and Skill columns are informative: they come from Skills.",
    "10. Practice, PracticeSkills and PracticeRoles define the practice for the demand analysis: Term is the skill as the demand",
    "    writes it, Aliases its other names (separated by ;), Scope = core | third-party | emerging. Anything else is outside the practice.",
    "11. NewsSources: the sites of the Knowledge exchange. FeedUrl is the RSS / Atom feed (optional); Splash = yes opens the academy",
    "    with that source's latest news; Enabled = no hides it. Addresses must start with https://.",
    "12. People: Role = owner | champion | sme | learner; Families = family ids separated by ; (champions and SMEs).",
    "    A champion listed here becomes the champion of those families in Families.",
    "13. StudyMaterial: Kind = video | playlist | search | page; SkillId (optional) ties an item to a skill of the catalog.",
    "",
    "On import the app checks everything and saves nothing if it finds a problem; it makes a backup before saving.",
]


# ------------------------------------------------------------------------------------------------ files on disk
def pack_files(packs_dir: Path | None = None) -> list[Path]:
    """Every course file: packs/<id>/pack.json (template folders, starting with '_', excluded)."""
    root = packs_dir or _packs_dir()
    if not root.is_dir():
        return []
    return [d / "pack.json" for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")) if (d / "pack.json").exists()]


def load_all(packs_dir: Path | None = None) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in pack_files(packs_dir)]


# ------------------------------------------------------------------------------------------------ export
def _rows(packs: list[dict], materials: dict[str, list[dict]], catalog, practice=None) -> dict[str, list[list]]:
    out: dict[str, list[list]] = {k: [] for k in SHEETS}
    practice = load_practice() if practice is None else practice
    if practice.name or practice.skills or practice.roles:
        out["Practice"] = [[practice.name, practice.description]]
        out["PracticeSkills"] = [[t.term, "; ".join(t.aliases), t.skill_id, t.family, t.vendor, t.scope] for t in practice.skills]
        out["PracticeRoles"] = [[r.title, "; ".join(r.aliases), r.scope] for r in practice.roles]
    out["NewsSources"] = [[x.name, x.category, x.url, x.feed, "yes" if x.splash else "no", "yes" if x.enabled else "no", x.description]
                          for x in news.load_sources()]
    from academy import workspace

    out["People"] = [x.sheet_row() for x in people.members(people.load(), workspace.current(), workspace.default_id())]
    out["StudyMaterial"] = [x.row() for x in study.load()]
    for d in packs:
        m = d["meta"]
        key = [m["id"]]
        out["Courses"].append(key + [m.get("title", ""), m.get("subtitle", ""), m.get("disclaimer", ""), str(m.get("version", "")),
                                     str(m.get("updated", ""))])
        out["Levels"] += [key + [i, lv] for i, lv in enumerate(d.get("levels", []), start=1)]
        out["Ranks"] += [key + [r["name"], r["points"], r.get("emoji", ""), r.get("color", ""), r.get("image", "")] for r in m.get("ranks", [])]
        out["Topics"] += [key + [k, v] for k, v in d.get("topics", {}).items()]
        out["Roles"] += [key + [k, "; ".join(v)] for k, v in d.get("roles", {}).items()]
        for les in d["lessons"]:
            lk = key + [les["id"]]
            pts = list(les.get("points", []))[:MAX_POINTS]
            pr = les.get("practice") or {}
            out["Lessons"].append(lk + [les["level"], les["title"], les["summary"]] + pts + [""] * (MAX_POINTS - len(pts))
                                  + [pr.get("label", ""), pr.get("url", ""), "; ".join(les.get("skills", [])),
                                     "; ".join(les.get("catalog_skills", []))])
            for n, q in enumerate(les.get("quiz", []), start=1):
                opts = (list(q["options"]) + [""] * 4)[:4]
                out["Questions"].append(lk + [n, q["q"]] + opts + [LETTERS[q["answer"]] if 0 <= q["answer"] < 4 else "", q["why"]])
            notes = les.get("resource_notes") or {}
            out["LessonResources"] += [lk + [n, rk, notes.get(rk, "")] for n, rk in enumerate(les.get("resources", []), start=1)]
        for rk, r in d.get("resources", {}).items():
            out["Resources"].append(key + [rk, r["title"], r["url"], r["channel"], r.get("topic", ""), r.get("kind", "video"),
                                           LEVEL_EN.get(r.get("level", ""), r.get("level", "")), r.get("who", ""), r.get("verified", ""), r.get("why", "")])
        out["Glossary"] += [key + [g["term"], g.get("category", ""), g["definition"]] for g in d.get("glossary", [])]
    if catalog:
        out["Families"] = [[f.id, f.name, f.gap_volume, f.role_impact, f.champion, f.champion_email] for f in catalog.families]
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
            out["LearningPaths"].append(head + [n, i.get("title", ""), i.get("url", ""), i.get("kind", ""), i.get("provider", ""),
                                                status_of(i), i.get("minutes", ""), i.get("notes", ""), i.get("verified", "")])
        for i in materials[sid]:
            if i not in steps:
                out["LearningPaths"].append(head + [i.get("order", ""), i.get("title", ""), i.get("url", ""), i.get("kind", ""), i.get("provider", ""),
                                                    status_of(i), i.get("minutes", ""), i.get("notes", ""), i.get("verified", "")])
    return out


def tables(packs: list[dict] | None = None, materials: dict | None = None, catalog=None, practice=None) -> dict[str, list[dict]]:
    """The current content as tables ({sheet: [row dicts keyed by column]}): what the in-app editor shows."""
    packs = load_all() if packs is None else packs
    materials = load_materials() if materials is None else materials
    catalog = catalog if catalog is not None else load_catalog()
    return {name: [dict(zip(SHEETS[name], r)) for r in rows] for name, rows in _rows(packs, materials, catalog, practice).items()}


def export_bytes(packs: list[dict] | None = None, materials: dict | None = None, catalog=None) -> bytes:
    """The workbook with everything on disk (or with the given packs / materials)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    packs = load_all() if packs is None else packs
    materials = load_materials() if materials is None else materials
    catalog = catalog if catalog is not None else load_catalog()
    rows = _rows(packs, materials, catalog)
    wb = Workbook()
    ws = wb.active
    ws.title = "README"
    ws.sheet_properties.tabColor = "FF5800"
    ws.append(["Academia - Cloud · academy content"])
    ws["A1"].font = Font(bold=True, size=16)
    ws.append(["One tab per table, grouped by section (the tab color shows the section)."])
    ws.append([])
    ws.append(["Section", "Tab", "What it holds", "Rows"])
    for cell in ws[4]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1C1C1E")
    for title, color, names, about in SECTIONS:
        for i, name in enumerate(names):
            ws.append([title if i == 0 else "", name, about if i == 0 else "", len(rows[name])])
            ws.cell(ws.max_row, 2).hyperlink = f"#'{name}'!A1"
            ws.cell(ws.max_row, 2).font = Font(bold=True, color=color, underline="single")
            ws.cell(ws.max_row, 1).fill = PatternFill("solid", fgColor=color)
            ws.cell(ws.max_row, 1).font = Font(bold=True, color="FFFFFF" if color in ("2A78D6", "4A3AA7", "1C1C1E", "6B6762") else "1C1C1E")
    ws.append([])
    for line in README[2:]:
        ws.append([line])
    for col, width in zip("ABCD", (24, 20, 100, 10)):
        ws.column_dimensions[col].width = width
    wide = {"Summary", "Question", "Why", "Definition", "Title", "Subtitle", "Disclaimer", "Url", "Note", "Description", "Aliases", "Term"}
    for name, cols in SHEETS.items():
        ws = wb.create_sheet(name)
        ws.sheet_properties.tabColor = TAB_COLOR[name]
        ws.append(cols)
        light = TAB_COLOR[name] in ("FF5800", "1BAF7A")
        for cell in ws[1]:
            cell.font = Font(bold=True, color="1C1C1E" if light else "FFFFFF")
            cell.fill = PatternFill("solid", fgColor=TAB_COLOR[name])
        for r in rows[name]:
            ws.append(r)
        last = max(ws.max_row, 2) + 500  # room to add rows that keep the drop-down lists
        for n, col in enumerate(cols, start=1):
            options = CHOICES.get((name, col)) or CHOICES.get(col)
            if options:
                dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True, showErrorMessage=True,
                                    errorTitle=col, error=" | ".join(options))
                ws.add_data_validation(dv)
                dv.add(f"{get_column_letter(n)}2:{get_column_letter(n)}{last}")
        for n, col in enumerate(cols, start=1):
            long = col in wide or col.startswith(("Point", "Option"))
            ws.column_dimensions[get_column_letter(n)].width = 46 if long else 18
            if long:
                for cell in ws[get_column_letter(n)][1:]:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "C2" if name in ("Lessons", "Questions", "LessonResources", "Resources") else "B2"
        ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_csv(packs: list[dict] | None = None, materials: dict | None = None, catalog=None) -> str:
    """Everything in ONE CSV: the column ``Table`` says which table a row belongs to; the rest are that table's columns."""
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


def _english(rec: dict) -> bool:
    """Rows of a former two-language file: only the English ones are kept (and only English videos)."""
    return _text(rec.get("Lang")).lower() in ("", LANGUAGE) and _text(rec.get("VideoLang")).lower() in ("", LANGUAGE)


_DROPPED: set[str] = set()  # videos of another language left out while reading a former file


def _keep(rec: dict) -> bool:
    if _english(rec):
        return True
    if _text(rec.get("Lang")).lower() in ("", LANGUAGE) and _text(rec.get("ResourceKey")):
        _DROPPED.add(_text(rec.get("ResourceKey")))
    return False


def _sheet(wb, name: str, problems: list[str]) -> list[dict]:
    """Rows of a sheet as dictionaries keyed by its header; reports missing sheets and columns."""
    found = name if name in wb.sheetnames else next((old for old, new in LEGACY_SHEETS.items() if new == name and old in wb.sheetnames), None)
    if found is None:
        problems.append(f'Sheet "{name}" is missing.')
        return []
    it = wb[found].iter_rows(values_only=True)
    head = [_text(h) for h in next(it, [])]
    missing = [c for c in SHEETS[name] if c not in head and c not in NEW_COLUMNS]
    if missing:
        problems.append(f"[{name}] missing columns: {', '.join(missing)}.")
        return []
    out = []
    for n, row in enumerate(it, start=2):
        rec = dict(zip(head, row))
        if any(_text(v) for v in row) and _keep(rec):
            rec["_row"] = n
            out.append(rec)
    return out


def _yes(v) -> bool:
    return _text(v).lower() not in ("no", "false", "0", "n")


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
        text = raw.decode("cp1252", errors="replace")  # Excel's «CSV (comma delimited)» in Windows
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") > first.count(",") else ("\t" if first.count("\t") > first.count(",") else ",")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
    data: dict[str, list[dict]] = {name: [] for name in SHEETS}
    head = [h.strip() for h in rows[0]] if rows else []
    marker = TABLE if TABLE in head else (LEGACY_TABLE if LEGACY_TABLE in head else None)
    if marker is None:
        problems.append(f'The CSV has no "{TABLE}" column in its first row.')
        return data
    for name, cols in SHEETS.items():
        missing = [c for c in cols if c not in head and c not in NEW_COLUMNS]
        if missing and name not in OPTIONAL:
            problems.append(f"[{name}] missing columns: {', '.join(missing)}.")
    for n, row in enumerate(rows[1:], start=2):
        rec = dict(zip(head, row))
        name = _text(rec.get(marker))
        name = LEGACY_SHEETS.get(name, name)
        if not any(_text(v) for v in row) or name in RETIRED or not _keep(rec):
            continue
        if name not in SHEETS:
            problems.append(f"[row {n}] {TABLE} = '{name}' is not a known table ({', '.join(SHEETS)}).")
            continue
        out = {c: rec.get(c, "") for c in SHEETS[name]}
        out["_row"] = n
        data[name].append(out)
    return data


def _catalog(data: dict, previous, problems: list[str]):
    """The skills catalog from the Families / Skills tables; the one on disk when the file does not carry them."""
    if not data["Families"] and not data["Skills"]:
        return previous, False
    old = {s.id: s for s in previous.skills} if previous else {}
    fams = [Family(_text(f["FamilyId"]), _text(f["Name"]), _int(f["GapVolume"]), _int(f["RoleImpact"]), _text(f["Champion"]),
                   _text(f["ChampionEmail"])) for f in data["Families"]]
    skills = []
    for x in data["Skills"]:
        sid = _text(x["SkillId"])
        skills.append(Skill(sid, _text(x["Name"]), _text(x["FamilyId"]), _yes(x["Confirmed"]), _text(x["Severity"]), _text(x["Target"]),
                            _int(x["ImpactedRoles"]), list(old[sid].roles) if sid in old else [],  # role names never travel in the file
                            _text(x.get("Vendor")), _text(x.get("Category"))))
    for f in fams:
        if not f.id or not f.name:
            problems.append("[Families] a row has no FamilyId or no Name.")
    for x in skills:
        if not x.id or not x.name:
            problems.append("[Skills] a row has no SkillId or no Name.")
    cat = Catalog(fams, skills)
    problems += [f"[catalog] {e}" for e in validate_catalog(cat)]
    return cat, True


def read(source, catalog=None) -> dict:
    """Parse a content file: the Excel workbook or the single CSV (bytes, a path or a file-like object).

    Returns {"packs": {id: dict}, "materials": {...}, "catalog": Catalog | None, "problems": [...], "summary": [...]}.
    ``problems`` lists everything that must be fixed in the file before it can be applied (empty = ready)."""
    from openpyxl import load_workbook

    problems: list[str] = []
    _DROPPED.clear()
    if isinstance(source, (str, Path)):
        raw = Path(source).read_bytes()
    else:
        raw = source if isinstance(source, (bytes, bytearray)) else source.read()
    if raw[:2] == b"PK":  # an .xlsx is a zip
        try:
            wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except Exception as e:  # damaged, password protected…
            return {"packs": {}, "materials": {}, "catalog": None, "new_catalog": False,
                    "problems": [f"Could not open the file: {e}"], "summary": [], "learning_paths": 0}
        present = set(wb.sheetnames) | {LEGACY_SHEETS[s] for s in wb.sheetnames if s in LEGACY_SHEETS}
        data = {name: ([] if name in OPTIONAL and name not in present else _sheet(wb, name, problems)) for name in SHEETS}
    else:
        data = _load_csv(bytes(raw), problems)
    if _DROPPED:  # a former file: the lessons stop pointing to the videos of another language
        data["LessonResources"] = [r for r in data["LessonResources"] if _text(r.get("ResourceKey")) not in _DROPPED]
        _DROPPED.clear()
    return build(data, catalog, problems)


def build(data: dict[str, list[dict]], catalog=None, problems: list[str] | None = None) -> dict:
    """The content from its tables ({sheet: [row dicts keyed by column]}): the same result as ``read``. The in-app editor
    sends the tables it edited here, so a change made in the app passes exactly the checks of an imported file."""
    problems = [] if problems is None else problems
    data = {name: [r if "_row" in r else {**r, "_row": n} for n, r in enumerate(data.get(name, []), start=2)] for name in SHEETS}
    catalog = catalog if catalog is not None else load_catalog()
    catalog, new_catalog = _catalog(data, catalog, problems)

    def of(name: str, pid: str) -> list[dict]:
        return [r for r in data[name] if _text(r["PackId"]) == pid]

    packs: dict[str, dict] = {}
    for c in data["Courses"]:
        pid = _text(c["PackId"])
        tag = f"[{pid}]"
        if not pid:
            problems.append(f"[Courses row {c['_row']}] PackId is missing.")
            continue
        if pid in packs:
            problems.append(f"{tag} is repeated in Courses.")
            continue
        ranks = []
        for r in of("Ranks", pid):
            try:
                rank = {"name": _text(r["Name"]), "points": int(float(_text(r["Points"]) or 0)), "emoji": _text(r["Emoji"]), "color": _text(r["Color"])}
            except ValueError:
                problems.append(f"{tag} [Ranks row {r['_row']}] Points must be a number.")
                continue
            if _text(r.get("Image")):
                rank["image"] = _text(r["Image"])
            ranks.append(rank)
        meta = {"id": pid, "title": _text(c["Title"]), "subtitle": _text(c["Subtitle"]), "language": LANGUAGE, "version": _text(c["Version"]) or "1.0",
                "updated": _text(c["Updated"]), "disclaimer": _text(c["Disclaimer"]), "ranks": ranks}
        levels = [_text(r["Level"]) for r in sorted(of("Levels", pid), key=lambda r: float(_text(r["SortOrder"]) or 0))]
        quiz_rows, lr_rows = of("Questions", pid), of("LessonResources", pid)
        lessons = []
        for r in of("Lessons", pid):
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
                    problems.append(f"{tag} [Questions row {q['_row']}] AnswerLetter must be A, B, C or D.")
                    letter = "A"
                quiz.append({"q": _text(q["Question"]), "options": [_text(q[f"Option{x}"]) for x in LETTERS], "answer": LETTERS.index(letter),
                             "why": _text(q["Why"])})
            les["quiz"] = quiz
            mine = sorted((x for x in lr_rows if _text(x["LessonId"]) == lid), key=lambda x: float(_text(x["SortOrder"]) or 0))
            les["resources"] = [_text(x["ResourceKey"]) for x in mine]
            notes = {_text(x["ResourceKey"]): _text(x["Note"]) for x in mine if _text(x["Note"])}
            if notes:
                les["resource_notes"] = notes
            lessons.append(les)
        known = {les["id"] for les in lessons}
        for name in ("Questions", "LessonResources"):
            for x in of(name, pid):
                if _text(x["LessonId"]) not in known:
                    problems.append(f"{tag} [{name} row {x['_row']}] lesson '{_text(x['LessonId'])}' is not in Lessons.")
        resources = {}
        for r in of("Resources", pid):
            rk = _text(r["ResourceKey"])
            if rk in resources:
                problems.append(f"{tag} [Resources row {r['_row']}] ResourceKey '{rk}' is repeated.")
            level = _text(r["Level"]) or "basic"
            resources[rk] = {"title": _text(r["Title"]), "url": _text(r["Url"]), "channel": _text(r["Channel"]), "lang": LANGUAGE,
                             "topic": _text(r["TopicId"]), "why": _text(r["Why"]), "kind": _text(r["Kind"]) or "video",
                             "level": LEVEL_EN.get(level, level), "who": _text(r["Who"]), "verified": _text(r["Verified"])}
        pack = {"meta": meta, "levels": levels, "roles": {_text(r["Role"]): _list(r["Skills"]) for r in of("Roles", pid)},
                "topics": {_text(r["TopicId"]): _text(r["Name"]) for r in of("Topics", pid)}, "lessons": lessons,
                "glossary": [{"term": _text(g["Term"]), "category": _text(g["Category"]), "definition": _text(g["Definition"])} for g in of("Glossary", pid)],
                "resources": resources}
        packs[pid] = pack
        if not ranks:
            problems.append(f"{tag} has no ranks in the Ranks sheet.")
        else:
            try:
                problems += [f"{tag} {e}" for e in validate(_parse(pack), catalog)]
            except Exception as e:  # a structural hole the checks above did not name
                problems.append(f"{tag} incomplete content: {e}")
    if not packs:
        problems.append("The Courses sheet has no course.")
    materials: dict[str, list[dict]] = {}
    for r in sorted(data["LearningPaths"], key=lambda r: (_int(r.get("Class")) is None, _int(r.get("Class")) or 0)):  # stable: class 1, 2, 3…
        item = {"title": _text(r["Title"]), "url": _text(r["Url"]), "kind": _text(r["Kind"]), "provider": _text(r["Provider"]),
                "status": _text(r.get("Status")).lower(), "minutes": _int(r.get("Minutes")), "notes": _text(r.get("Notes")),
                "verified": _text(r["Verified"])}
        item = {k: v for k, v in item.items() if v}
        if _int(r.get("Class")):
            item["order"] = _int(r["Class"])
        materials.setdefault(_text(r["SkillId"]), []).append(item)
    problems += validate_materials(materials, catalog)
    summary = [{"Course": pid, "Lessons": len(p["lessons"]), "Questions": sum(len(x["quiz"]) for x in p["lessons"]),
                "Resources": len(p["resources"]), "Glossary": len(p["glossary"])} for pid, p in packs.items()]
    practice = None
    if len([r for r in data["Practice"] if any(_text(v) for v in r.values())]) > 1:
        problems.append("[Practice] this table describes the practice of this content file (one row). To add a practice, use "
                        "Team → 🏢 Practices: each practice gets its own courses, role families, people and content file.")
    if data["Practice"] or data["PracticeSkills"] or data["PracticeRoles"]:
        head = data["Practice"][0] if data["Practice"] else {}
        practice = Practice(_text(head.get("Name")), _text(head.get("Description")),
                            [Term(_text(r["Term"]), tuple(x.strip() for x in _text(r["Aliases"]).split(";") if x.strip()), _text(r["SkillId"]),
                                  _text(r["FamilyId"]), _text(r["Vendor"]), scope_of(_text(r["Scope"]))) for r in data["PracticeSkills"] if _text(r["Term"])],
                            [RoleTerm(_text(r["RoleTitle"]), tuple(x.strip() for x in _text(r["Aliases"]).split(";") if x.strip()),
                                      scope_of(_text(r["Scope"]))) for r in data["PracticeRoles"] if _text(r["RoleTitle"])])
        if catalog:
            fams, ids = {f.id for f in catalog.families}, catalog.skill_ids()
            for t in practice.skills:
                if t.skill_id and t.skill_id not in ids:
                    problems.append(f"[PracticeSkills] '{t.term}': SkillId '{t.skill_id}' is not in Skills.")
                if t.family and t.family not in fams:
                    problems.append(f"[PracticeSkills] '{t.term}': FamilyId '{t.family}' is not in Families.")
    sources = None
    if data["NewsSources"]:
        sources, bad = news.parse_sources(news.to_csv([]) + "\r\n".join(
            ",".join('"' + _text(r.get(c)).replace('"', '""') + '"' for c in news.COLUMNS) for r in data["NewsSources"]).encode("utf-8"))
        problems += bad
    directory = None
    if data["People"]:
        directory, bad = people.parse(_as_csv(people.SHEET_COLUMNS, data["People"]), {f.id for f in catalog.families} if catalog else None)
        problems += bad
        course_roles = {_text(r.get("Role")) for r in data["Roles"]}
        problems += [f"[People] '{x.name}': course role '{x.course_role}' is not a course role ({', '.join(sorted(course_roles)) or 'none yet'})."
                     for x in directory if x.course_role and x.course_role not in course_roles]
        if catalog and not bad:
            catalog, moved = people.sync_catalog(directory, catalog)
            new_catalog = new_catalog or moved
    bank = None
    if data["StudyMaterial"]:
        bank, bad = study.parse(_as_csv(study.COLUMNS, data["StudyMaterial"]))
        problems += bad
        known = catalog.skill_ids() if catalog else set()
        problems += [f"[StudyMaterial] '{i.title}': SkillId '{i.skill_id}' is not in Skills." for i in bank if i.skill_id and known and i.skill_id not in known]
    return {"packs": packs, "materials": materials, "catalog": catalog, "new_catalog": new_catalog, "practice": practice, "news": sources,
            "people": directory, "study": bank,
            "problems": problems, "summary": summary,
            "learning_paths": sum(len(v) for v in materials.values()),
            "families": len(catalog.families) if catalog else 0, "skills": len(catalog.skills) if catalog else 0}


def _as_csv(columns: list[str], rows: list[dict]) -> bytes:
    """Rows of a sheet as the CSV their module reads (so the workbook and the CSV file pass the same checks)."""
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(columns)
    w.writerows([_text(r.get(c)) for c in columns] for r in rows)
    return buf.getvalue().encode("utf-8")


def target_file(pack_id: str, packs_dir: Path | None = None) -> Path:
    return (packs_dir or _packs_dir()) / pack_id / "pack.json"


def apply(result: dict, packs_dir: Path | None = None, backup_dir: Path | None = None) -> list[Path]:
    """Write what ``read`` / ``build`` parsed. Refuses while there are problems. Returns the files written (backup first)."""
    if result["problems"]:
        raise ValueError("The content has problems; nothing was saved.")
    root = packs_dir or _packs_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = (backup_dir or root.parent / "data" / "content_backups") / stamp
    written = []
    for pid, pack in result["packs"].items():
        path = target_file(pid, root)
        if path.exists():
            (backup / pid).mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup / pid / path.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(pack, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        written.append(path)
    if result.get("news") is not None:
        np_ = news.sources_path()
        if np_.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(np_, backup / np_.name)
        written.append(news.save_sources(result["news"]))
    from academy import workspace

    for key, path_of, save in (("people", people.people_path, people.save), ("study", study.study_path, study.save)):
        if result.get(key) is not None:
            f = path_of()
            if f.exists():
                backup.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, backup / f.name)
            value = result[key]
            if key == "people":  # the sheet holds this practice's people: the others (and the global owners) stay
                value = people.replace_members(people.load(), workspace.current(), workspace.default_id(), value)
            written.append(save(value))
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
        written.append(save_catalog(result["catalog"], source="Content file", updated=datetime.now().date().isoformat()))
    written.append(save_materials(result["materials"]))
    from academy import family_path

    family_path.refresh(result.get("catalog"), result["materials"])  # the CSV of each family follows
    return written
