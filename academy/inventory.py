"""Team inventory: the certifications and the hands-on skills of every person of the practice, in ONE collection file.

The file is what the team fills in (CSV or the Excel template with drop-down lists), one row per certification or skill:

    Person, Email, Type, Name, Code, Vendor, Level, Years, Status, Obtained, Expires, EvidenceUrl, Notes

* Type = certification  -> goes to the certification register (Code like AZ-500; Status current | desired; dates; Credly link)
* Type = skill          -> goes to the skills inventory (Name like KQL; Level 1-5; Years; Status current | desired)

Skill levels (the same scale for everyone, so the matrix can be compared):
    1 Aware · 2 Basic · 3 Practitioner (works alone) · 4 Advanced (leads it on a project) · 5 Expert (teaches it, designs it)

Each skill is matched to the skills catalog and to the practice definition (aliases: "KQL" -> Microsoft Sentinel / KQL…),
so the matrix speaks the same language as the gap report and the demand analysis. A champion can validate a person's
level; until then it is self-reported. Importing replaces the inventory of the people who appear in the file.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timezone

from academy.certs import CURRENT, DESIRED, Certs, _date, _STATUS

COLUMNS = ["Person", "Email", "Type", "Name", "Code", "Vendor", "Level", "Years", "Status", "Obtained", "Expires", "EvidenceUrl", "Notes"]
TYPES = ["certification", "skill"]
LEVELS = {1: "1 · Aware", 2: "2 · Basic", 3: "3 · Practitioner", 4: "4 · Advanced", 5: "5 · Expert"}
LEVEL_HELP = {1: "Knows what it is and when it is used", 2: "Has used it with guidance or in labs", 3: "Works with it alone on a project",
              4: "Leads it on projects, solves hard cases", 5: "Designs it, teaches it, is the go-to person"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS skill_records (
    learner TEXT NOT NULL, skill TEXT NOT NULL, skill_id TEXT NOT NULL DEFAULT '', vendor TEXT NOT NULL DEFAULT '',
    level INTEGER NOT NULL DEFAULT 0, years REAL, status TEXT NOT NULL DEFAULT 'current', evidence TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '', validated_by TEXT NOT NULL DEFAULT '', validated_at TEXT NOT NULL DEFAULT '',
    updated TEXT NOT NULL DEFAULT '', updated_by TEXT NOT NULL DEFAULT '', PRIMARY KEY (learner, skill)
);
"""
# One example person, so whoever fills the template sees the expected shape: the practice owner's certifications and
# experience as he listed them. The skill levels are left empty on purpose: each person rates their own (1-5).
EXAMPLE = [
    ("certification", "Azure Fundamentals", "AZ-900", "Microsoft", "", "", "current", "", "", "", ""),
    ("certification", "Security Operations Analyst", "SC-200", "Microsoft", "", "", "current", "", "", "", ""),
    ("certification", "Azure Security Engineer Associate", "AZ-500", "Microsoft", "", "", "current", "", "", "", ""),
    ("certification", "Azure AI Fundamentals", "AI-901", "Microsoft", "", "", "current", "", "", "", ""),
    ("skill", "Cisco CCNA (routing and switching)", "", "Cisco", "", "", "current", "", "", "", "Experience, not certified"),
    ("skill", "ServiceNow", "", "ServiceNow", "", "", "current", "", "", "", ""),
    ("skill", "Microsoft 365 / Office 365", "", "Microsoft", "", "", "current", "", "", "", ""),
    ("skill", "PowerShell", "", "Microsoft", "", "", "current", "", "", "", ""),
    ("skill", "KQL", "", "Microsoft", "", "", "current", "", "", "", ""),
    ("skill", "SQL", "", "Vendor-neutral", "", "", "current", "", "", "", ""),
]
EXAMPLE_PERSON, EXAMPLE_EMAIL = "Alejandro Zavala", "alejandro.zavala@company.com"


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def level_of(v) -> int:
    """'4', '4 · Advanced', 'advanced', 'P4 - Expert' -> 4; '' -> 0."""
    s = _text(v).lower()
    if not s:
        return 0
    for ch in s:
        if ch.isdigit():
            return max(0, min(5, int(ch)))
    words = {"aware": 1, "basic": 2, "beginner": 2, "practitioner": 3, "intermediate": 3, "advanced": 4, "expert": 5}
    return next((n for w, n in words.items() if w in s), 0)


# ------------------------------------------------------------------------------------------------ template
def template_rows(example: bool = True) -> list[dict]:
    if not example:
        return []
    return [dict(zip(COLUMNS, (EXAMPLE_PERSON, EXAMPLE_EMAIL) + row)) for row in EXAMPLE]


def template_csv(example: bool = True) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(COLUMNS)
    for r in template_rows(example):
        w.writerow([r[c] for c in COLUMNS])
    return buf.getvalue().encode("utf-8-sig")


def template_xlsx(example: bool = True, skills: list[str] | None = None) -> bytes:
    """The same template as an Excel file: instructions, drop-down lists and the practice's skills as suggestions."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Inventory"
    ws.append(COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="1C1C1E")
        cell.fill = PatternFill("solid", fgColor="FF5800")
    for r in template_rows(example):
        ws.append([int(r[c]) if c == "Level" and r[c] else r[c] for c in COLUMNS])
    lists = {"Type": TYPES, "Status": [CURRENT, DESIRED], "Level": ["1", "2", "3", "4", "5"]}
    for col, options in lists.items():
        dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
        ws.add_data_validation(dv)
        letter = get_column_letter(COLUMNS.index(col) + 1)
        dv.add(f"{letter}2:{letter}2000")
    for n, col in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(n)].width = {"Name": 38, "Notes": 34, "EvidenceUrl": 34, "Email": 30, "Person": 22}.get(col, 13)
    ws.freeze_panes = "C2"
    help_ = wb.create_sheet("How to fill it")
    lines = ["Academia - Cloud · team inventory (certifications and skills)", "",
             "One row per certification or skill. Keep your name and e-mail the same on every row.",
             "Type = certification: write the exam Code (AZ-500, SC-200…), Status current (you hold it) or desired (you aim for it),",
             "      the dates (YYYY-MM-DD) and the link to your Credly badge or Microsoft Learn transcript in EvidenceUrl.",
             "Type = skill: write the skill or technology in Name (KQL, PowerShell, Cisco routing…), your Level 1-5 and Years of use.",
             "      Status desired = a skill you want to learn.", "", "Levels"]
    lines += [f"  {LEVELS[n]}: {LEVEL_HELP[n]}" for n in LEVELS]
    lines += ["", "The example rows show the expected shape: replace them with yours.", "",
              "Skills of the practice (use these names when they apply; any other skill is welcome too):"]
    lines += [f"  {s}" for s in (skills or [])]
    for line in lines:
        help_.append([line])
    help_["A1"].font = Font(bold=True, size=14)
    help_.column_dimensions["A"].width = 120
    for row in help_.iter_rows():
        row[0].alignment = Alignment(wrap_text=False)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------------------------------------ reading the file
def _rows(raw: bytes) -> tuple[list[dict], list[str]]:
    if raw[:2] == b"PK":  # the Excel template
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb["Inventory"] if "Inventory" in wb.sheetnames else wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        head = [_text(h) for h in next(it, [])]
        rows = [dict(zip(head, r)) for r in it]
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
        first = text.split("\n", 1)[0]
        delim = ";" if first.count(";") > first.count(",") else ("\t" if first.count("\t") > first.count(",") else ",")
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delim)
        head = [h.strip() for h in (reader.fieldnames or [])]
        rows = [{(k or "").strip(): v for k, v in r.items()} for r in reader]
    missing = [c for c in ("Person", "Type", "Name") if c not in head]
    if missing:
        return [], [f"Missing columns: {', '.join(missing)}. Expected: {', '.join(COLUMNS)}."]
    return rows, []


def parse(raw: bytes, practice=None, catalog=None, only_person: str | None = None) -> dict:
    """{"certs": {person: [cert rows]}, "skills": {person: [skill rows]}, "emails": {person: e-mail}, "problems": [...]}."""
    rows, problems = _rows(raw)
    certs: dict[str, list[dict]] = {}
    skills: dict[str, list[dict]] = {}
    emails: dict[str, str] = {}
    names = {s.name.lower(): s for s in (catalog.skills if catalog else [])}
    for n, r in enumerate(rows, start=2):
        who, kind = _text(r.get("Person")), _text(r.get("Type")).lower()
        if not any(_text(v) for v in r.values()):
            continue
        tag = f"[row {n}]"
        if not who:
            problems.append(f"{tag} Person is missing.")
            continue
        if only_person and who.lower() != only_person.strip().lower():
            problems.append(f"{tag} that row belongs to '{who}': you can only import your own inventory.")
            continue
        if _text(r.get("Email")):
            emails[who] = _text(r.get("Email"))
        status = _STATUS.get(_text(r.get("Status")).lower())
        if status is None:
            problems.append(f"{tag} Status must be current or desired.")
            continue
        if kind in ("certification", "cert", "certificación", "certificacion"):
            code = _text(r.get("Code")).upper() or _text(r.get("Name")).upper()
            try:
                obtained, expires = _date(r.get("Obtained")), _date(r.get("Expires"))
            except ValueError as e:
                problems.append(f"{tag} '{e}' is not a date (use YYYY-MM-DD).")
                continue
            url = _text(r.get("EvidenceUrl"))
            if url and not url.startswith("https://"):
                problems.append(f"{tag} EvidenceUrl must start with https://.")
                continue
            certs.setdefault(who, []).append({"Code": code, "Name": _text(r.get("Name")), "Vendor": _text(r.get("Vendor")), "Status": status,
                                              "Obtained": obtained, "Expires": expires, "CredentialUrl": url})
        elif kind in ("skill", "experience", "experiencia", "habilidad"):
            name = _text(r.get("Name"))
            if not name:
                problems.append(f"{tag} the skill Name is missing.")
                continue
            level = level_of(r.get("Level"))
            if status == CURRENT and not level:
                problems.append(f"{tag} '{name}': Level must be 1 to 5.")
                continue
            try:
                years = float(_text(r.get("Years"))) if _text(r.get("Years")) else None
            except ValueError:
                problems.append(f"{tag} Years must be a number.")
                continue
            skills.setdefault(who, []).append({"Skill": name, "SkillId": match(name, practice, names), "Vendor": _text(r.get("Vendor")),
                                               "Level": level, "Years": years, "Status": status, "Evidence": _text(r.get("EvidenceUrl")),
                                               "Notes": _text(r.get("Notes"))})
        else:
            problems.append(f"{tag} Type must be certification or skill.")
    return {"certs": certs, "skills": skills, "emails": emails, "problems": problems,
            "people": sorted(set(certs) | set(skills), key=str.lower)}


def match(name: str, practice=None, catalog_names: dict | None = None) -> str:
    """The catalog skill id a free skill name maps to ('' = not in the catalog)."""
    if catalog_names and name.lower() in catalog_names:
        return catalog_names[name.lower()].id
    term = practice.match_skill(name) if practice else None
    return term.skill_id if term and term.skill_id else ""


# ------------------------------------------------------------------------------------------------ storage
class Inventory:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        conn.executescript(SCHEMA)

    def skills(self, learner: str | None = None) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM skill_records ORDER BY learner COLLATE NOCASE, level DESC, skill COLLATE NOCASE").fetchall()
        return [{"Person": r["learner"], "Skill": r["skill"], "SkillId": r["skill_id"], "Vendor": r["vendor"], "Level": r["level"],
                 "Years": r["years"], "Status": r["status"], "Evidence": r["evidence"], "Notes": r["notes"],
                 "ValidatedBy": r["validated_by"], "ValidatedAt": r["validated_at"]}
                for r in rows if learner is None or r["learner"].lower() == learner.strip().lower()]

    def set_skills(self, learner: str, rows: list[dict], by: str = "") -> None:
        """Replace one person's skills. A validation survives only while the level stays the same."""
        learner = learner.strip()
        if not learner:
            raise ValueError("learner")
        before = {r["Skill"].lower(): r for r in self.skills(learner)}
        clean = {}
        for r in rows:
            name = _text(r.get("Skill"))
            if not name:
                continue
            level = level_of(r.get("Level"))
            old = before.get(name.lower())
            keep = old and old["Level"] == level and old["ValidatedBy"]
            years = r.get("Years")
            clean[name.lower()] = (learner, name, _text(r.get("SkillId")), _text(r.get("Vendor")), level,
                                   None if years in (None, "") or years != years else float(years),
                                   _STATUS.get(_text(r.get("Status")).lower(), CURRENT), _text(r.get("Evidence")), _text(r.get("Notes")),
                                   old["ValidatedBy"] if keep else "", old["ValidatedAt"] if keep else "", _now(), by or learner)
        with self.conn:
            self.conn.execute("DELETE FROM skill_records WHERE lower(learner)=lower(?)", (learner,))
            self.conn.executemany("INSERT INTO skill_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", list(clean.values()))

    def validate(self, learner: str, skill: str, by: str, ok: bool = True) -> None:
        with self.conn:
            self.conn.execute("UPDATE skill_records SET validated_by=?, validated_at=? WHERE lower(learner)=lower(?) AND lower(skill)=lower(?)",
                              (by if ok else "", _now()[:10] if ok else "", learner, skill))

    def people(self) -> list[str]:
        return [r["learner"] for r in self.conn.execute("SELECT DISTINCT learner FROM skill_records ORDER BY learner COLLATE NOCASE")]

    # -------------------------------------------------------------- import / export
    def apply(self, parsed: dict, by: str) -> list[str]:
        """Write what ``parse`` read: certifications and skills of the people in the file (others untouched)."""
        from academy import notify

        certs = Certs(self.conn)
        for who in parsed["people"]:
            if who in parsed["certs"]:
                certs.set_records(who, parsed["certs"][who], by=by)
            if who in parsed["skills"]:
                self.set_skills(who, parsed["skills"][who], by=by)
        for who, mail in parsed["emails"].items():
            if "@" in mail:
                notify.set_email(self.conn, who, mail)
        return parsed["people"]

    def export_csv(self, learner: str | None = None) -> bytes:
        """The whole inventory (or one person's) in the collection format: edit it and import it back."""
        from academy import notify

        mails = notify.emails(self.conn)
        rows = []
        for r in Certs(self.conn).records(learner):
            rows.append({"Person": r["Learner"], "Email": mails.get(r["Learner"], ""), "Type": "certification", "Name": r["Name"], "Code": r["Code"],
                         "Vendor": r["Vendor"], "Status": r["Status"], "Obtained": r["Obtained"], "Expires": r["Expires"], "EvidenceUrl": r["CredentialUrl"]})
        for r in self.skills(learner):
            rows.append({"Person": r["Person"], "Email": mails.get(r["Person"], ""), "Type": "skill", "Name": r["Skill"], "Vendor": r["Vendor"],
                         "Level": r["Level"] or "", "Years": "" if r["Years"] is None else (int(r["Years"]) if float(r["Years"]).is_integer() else r["Years"]),
                         "Status": r["Status"], "EvidenceUrl": r["Evidence"], "Notes": r["Notes"]})
        rows.sort(key=lambda r: (r["Person"].lower(), r["Type"], r.get("Code", "") or r["Name"]))
        buf = io.StringIO(newline="")
        w = csv.writer(buf, lineterminator="\r\n")
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([r.get(c, "") for c in COLUMNS])
        return buf.getvalue().encode("utf-8-sig")

    # -------------------------------------------------------------- views
    def matrix(self, catalog=None, only_people: set[str] | None = None) -> tuple[list[str], list[dict]]:
        """(skill columns, one row per person: level per skill, "✓" when a champion validated it)."""
        recs = [r for r in self.skills() if r["Status"] == CURRENT and (only_people is None or r["Person"] in only_people)]
        label = {s.id: s.name for s in (catalog.skills if catalog else [])}
        name = (lambda r: label.get(r["SkillId"], r["Skill"]))
        counts: dict[str, int] = {}
        for r in recs:
            counts[name(r)] = counts.get(name(r), 0) + 1
        cols = sorted(counts, key=lambda k: (-counts[k], k.lower()))
        people: dict[str, dict] = {}
        for r in recs:
            row = people.setdefault(r["Person"], {"Person": r["Person"]})
            key = name(r)
            cell = f"{r['Level']}{' ✓' if r['ValidatedBy'] else ''}"
            if key not in row or int(str(row[key]).split()[0]) < r["Level"]:
                row[key] = cell
        return cols, [people[p] for p in sorted(people, key=str.lower)]

    def who_has(self, skills: list[str], min_level: int = 3, catalog=None) -> list[dict]:
        """People with ALL these skills (catalog names or free names) at ``min_level`` or more, best first, with their certifications."""
        label = {s.id: s.name for s in (catalog.skills if catalog else [])}
        want = [s.lower() for s in skills]
        by_person: dict[str, dict[str, dict]] = {}
        for r in self.skills():
            if r["Status"] != CURRENT:
                continue
            for key in {r["Skill"].lower(), label.get(r["SkillId"], "").lower()} - {""}:
                if key in want and r["Level"] >= min_level:
                    by_person.setdefault(r["Person"], {})[key] = r
        certs = {}
        for c in Certs(self.conn).records():
            if c["Status"] == CURRENT:
                certs.setdefault(c["Learner"], []).append(c["Code"])
        out = []
        for who, found in by_person.items():
            if all(w in found for w in want):
                out.append({"Person": who, "Levels": ", ".join(f"{found[w]['Skill']} {found[w]['Level']}{' ✓' if found[w]['ValidatedBy'] else ''}" for w in want),
                            "Average": round(sum(found[w]["Level"] for w in want) / len(want), 1),
                            "Certifications": ", ".join(sorted(certs.get(who, []))) or "—", "_validated": all(found[w]["ValidatedBy"] for w in want)})
        return sorted(out, key=lambda r: (-r["Average"], not r["_validated"], r["Person"].lower()))

    def coverage(self, skill_ids: list[str], min_level: int = 3) -> dict[str, int]:
        """How many people hold each catalog skill at ``min_level`` or more (used by the monthly agenda against the demand)."""
        out = {sid: 0 for sid in skill_ids}
        seen = set()
        for r in self.skills():
            if r["Status"] == CURRENT and r["SkillId"] in out and r["Level"] >= min_level and (r["Person"], r["SkillId"]) not in seen:
                seen.add((r["Person"], r["SkillId"]))
                out[r["SkillId"]] += 1
        return out
