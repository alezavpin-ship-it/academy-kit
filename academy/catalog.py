"""Skills catalog: the team's skill families (with their gap numbers and champion) and the skills inside each one.

It lives in catalog/skills.json, outside the packs, because it is the one vocabulary every pack, role and profile shares.
Lessons point to it with ``catalog_skills``; ``coverage`` answers "which lessons teach this skill?".
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "catalog" / "skills.json"
DEFAULT_SHEET = "Upskilling Plan"
SEVERITIES = ["High", "Medium", "Low"]


def catalog_path() -> Path:
    """catalog/skills.json, or the file named by ACADEMY_CATALOG."""
    return Path(os.environ.get("ACADEMY_CATALOG") or CATALOG_PATH)


def slug(name: str) -> str:
    """Stable id from a name: 'Encryption / Key Vault / HSM' -> 'encryption-key-vault-hsm'."""
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


@dataclass(frozen=True)
class Family:
    id: str
    name: str
    gap_volume: int | None = None  # missing skills across the roles we receive (from the team's gap report)
    role_impact: int | None = None  # roles affected by those gaps
    champion: str = ""  # the person who leads upskilling for this family
    champion_email: str = ""  # where notices about this family are copied


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    family: str
    confirmed: bool = True  # False = the family was proposed, not yet confirmed by the team
    severity: str = ""  # gap severity / priority band: High | Medium | Low
    target: str = ""  # required target proficiency, e.g. "P3 - Advanced"
    impacted_roles: int | None = None  # how many received roles show this gap
    roles: list[str] = field(default_factory=list)  # their names; only kept when the importer is told to
    vendor: str = ""  # technology / vendor the skill belongs to: Microsoft, AWS, GCP, Cisco, IBM… ("" = work it out, see vendor_of)
    category: str = ""  # optional grouping inside the vendor, e.g. "SIEM", "Identity"


# Structure of the catalog: skill family -> technology / vendor -> skills (optionally by category) -> learning path (classes).
NEUTRAL = "Vendor-neutral"
VENDORS = ["Microsoft", "AWS", "GCP", "Cisco", "IBM", "Palo Alto Networks", "Fortinet", "CrowdStrike", "GitHub", "Anthropic", NEUTRAL]
_VENDOR_WORDS = [("Microsoft", ("microsoft", "azure", "entra", "defender", "sentinel", "purview", "intune", "exchange", "m365", "office 365",
                                "key vault", "conditional access", "copilot", "power platform", "sharepoint", "teams")),
                 ("AWS", ("aws", "amazon")), ("GCP", ("gcp", "google cloud")), ("Cisco", ("cisco",)), ("IBM", ("ibm", "qradar")),
                 ("Palo Alto Networks", ("palo alto", "prisma", "cortex")), ("Fortinet", ("fortinet", "fortigate")),
                 ("CrowdStrike", ("crowdstrike", "falcon")), ("Anthropic", ("claude", "anthropic")), ("GitHub", ("github",))]
_PROVIDER_VENDOR = {"microsoft learn": "Microsoft", "aws skill builder": "AWS", "google cloud skills boost": "GCP", "cisco networking academy": "Cisco",
                    "ibm skillsbuild": "IBM", "anthropic academy": "Anthropic", "github": "GitHub"}


def vendor_of(skill: Skill, materials: dict[str, list[dict]] | None = None) -> str:
    """The technology / vendor of a skill: the one written in the catalog; otherwise what its name says; otherwise the
    vendor whose official training it follows; otherwise vendor-neutral."""
    if skill.vendor:
        return skill.vendor
    name = skill.name.lower()
    for vendor, words in _VENDOR_WORDS:
        if any(w in name for w in words):
            return vendor
    for m in (materials or {}).get(skill.id, []):
        v = _PROVIDER_VENDOR.get(str(m.get("provider", "")).strip().lower())
        if v:
            return v
    return NEUTRAL


@dataclass
class Catalog:
    families: list[Family]
    skills: list[Skill]

    def skill_ids(self) -> set[str]:
        return {s.id for s in self.skills}

    def in_family(self, family_id: str) -> list[Skill]:
        return [s for s in self.skills if s.family == family_id]

    def by_gap(self) -> list[Family]:
        """Families with the biggest gap first; families without numbers go last."""
        return sorted(self.families, key=lambda f: (f.gap_volume is None, -(f.gap_volume or 0)))

    def coverage(self, packs) -> dict[str, list[tuple[str, str]]]:
        """skill id -> [(pack title, lesson title)] for every lesson that declares the skill."""
        out: dict[str, list[tuple[str, str]]] = {s.id: [] for s in self.skills}
        for pack in packs:
            for les in pack.lessons:
                for sid in les.catalog_skills:
                    if sid in out:
                        out[sid].append((pack.title, les.title))
        return out


def load_catalog(path: str | Path | None = None) -> Catalog | None:
    p = Path(path) if path else catalog_path()
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    fams = [Family(f["id"], f["name"], f.get("gap_volume"), f.get("role_impact"), f.get("champion", "") or "", f.get("champion_email", "") or "")
            for f in data["families"]]
    skills = [Skill(s["id"], s["name"], s["family"], bool(s.get("confirmed", True)), s.get("severity", "") or "", s.get("target", "") or "",
                    s.get("impacted_roles"), list(s.get("roles", [])), s.get("vendor", "") or "", s.get("category", "") or "")
              for s in data["skills"]]
    return Catalog(fams, skills)


def to_dict(cat: Catalog, source: str = "", updated: str = "") -> dict:
    skills = []
    for s in cat.skills:
        d = {"id": s.id, "name": s.name, "family": s.family, "confirmed": s.confirmed}
        d.update({k: v for k, v in (("vendor", s.vendor), ("category", s.category), ("severity", s.severity), ("target", s.target),
                                    ("impacted_roles", s.impacted_roles), ("roles", s.roles)) if v not in ("", None, [])})
        skills.append(d)
    return {"meta": {"title": "Skills catalog", "updated": updated, "source": source},
            "families": [{"id": f.id, "name": f.name, "gap_volume": f.gap_volume, "role_impact": f.role_impact, "champion": f.champion,
                          "champion_email": f.champion_email}
                         for f in cat.families],
            "skills": skills}


def save_catalog(cat: Catalog, path: str | Path | None = None, source: str = "", updated: str = "") -> Path:
    p = Path(path) if path else catalog_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(to_dict(cat, source, updated), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def validate_catalog(cat: Catalog) -> list[str]:
    errs: list[str] = []
    fids = [f.id for f in cat.families]
    sids = [s.id for s in cat.skills]
    if not fids or not sids:
        errs.append("The catalog needs at least one family and one skill.")
    if len(fids) != len(set(fids)):
        errs.append("There are repeated families.")
    if len(sids) != len(set(sids)):
        dup = sorted({x for x in sids if sids.count(x) > 1})
        errs.append("There are repeated skills: " + ", ".join(dup) + ".")
    for s in cat.skills:
        if s.family not in fids:
            errs.append(f"[skill {s.id}] the family '{s.family}' does not exist.")
    for f in cat.families:
        if not cat.in_family(f.id):
            errs.append(f"[family {f.id}] has no skills.")
    return errs


# ---------------------------------------------------------------------------------------------- import
# The importer reads ONE sheet (by default "Upskilling Plan") as a plain grid of cells and looks for two tables in it:
#   1. the remediation table: Skill Family | Unaligned / Missing Skill | Gap Severity | Impacted Roles | Required Target | Champion
#   2. the summary table (optional): Skill Family | Gap Volume | Role Impact Count
# It never needs the rest of the workbook, and by default it keeps only HOW MANY roles are impacted, not which ones.
_COLS = {"family": ("skill family",), "skill": ("missing skill", "unaligned", "skill"), "severity": ("severity", "priority"),
         "roles": ("impacted role",), "target": ("target proficiency", "required target", "proficiency"), "champion": ("champion", "owner")}


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _num(v) -> int | None:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def sheet_names(file) -> list[str]:
    from openpyxl import load_workbook

    wb = load_workbook(file, read_only=True, data_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def read_xlsx(file, sheet: str) -> list[list]:
    """The cells of ONE sheet (cached values, not formulas). No other sheet is read."""
    from openpyxl import load_workbook

    wb = load_workbook(file, read_only=True, data_only=True)
    try:
        return [list(r) for r in wb[sheet].iter_rows(values_only=True)]
    finally:
        wb.close()


def parse_text(text: str) -> list[list]:
    """Cells copied from Excel (tab-separated); also accepts ';' or ',' separated lines."""
    lines = [ln for ln in text.replace("\r", "").split("\n") if ln.strip()]
    sep = "\t" if any("\t" in ln for ln in lines) else (";" if sum(ln.count(";") for ln in lines) >= len(lines) else ",")
    return [[c.strip() for c in ln.split(sep)] for ln in lines]


def _find_header(rows: list[list]) -> tuple[int, dict[str, int]] | None:
    for i, row in enumerate(rows):
        cells = [_txt(c).lower() for c in row]
        fam = next((j for j, c in enumerate(cells) if c.startswith("skill family")), None)
        if fam is None:
            continue
        cols = {"family": fam}
        for key in ("skill", "severity", "roles", "target", "champion"):
            for j, c in enumerate(cells):
                if j > fam and j not in cols.values() and c and not c.startswith("gap vol") and any(k in c for k in _COLS[key]):
                    cols[key] = j
                    break
        if "skill" in cols:
            return i, cols
    return None


def _find_summary(rows: list[list]) -> dict[str, tuple[int | None, int | None]]:
    for i, row in enumerate(rows):
        cells = [_txt(c).lower() for c in row]
        for j, c in enumerate(cells):
            if c.startswith("skill family") and j + 1 < len(cells) and cells[j + 1].startswith("gap vol"):
                out = {}
                for r in rows[i + 1:]:
                    name = _txt(r[j]) if j < len(r) else ""
                    if not name:
                        break
                    out[name] = (_num(r[j + 1]) if j + 1 < len(r) else None, _num(r[j + 2]) if j + 2 < len(r) else None)
                return out
    return {}


def parse_grid(rows: list[list], keep_roles: bool = False, previous: Catalog | None = None) -> tuple[Catalog | None, dict]:
    """Build a catalog from the cells of the upskilling sheet. Returns (catalog, report); catalog is None when no table was found.

    ``previous``: the catalog in use; champions already assigned there are kept.
    """
    found = _find_header(rows)
    if not found:
        return None, {"error": 'I could not find a table with the columns "Skill Family" and "Unaligned / Missing Skill".'}
    hdr, cols = found

    def cell(r, key):
        j = cols.get(key)
        return _txt(r[j]) if j is not None and j < len(r) else ""

    fam_order: list[str] = []
    skills: dict[str, Skill] = {}
    champs: dict[str, Counter] = {}
    fam_roles: dict[str, set] = {}
    fam_gap: dict[str, int] = {}
    last_family, blanks, dupes = "", 0, []
    for r in rows[hdr + 1:]:
        name = cell(r, "skill")
        family = cell(r, "family") or (last_family if name else "")
        if not name:
            blanks += 1
            if blanks >= 3:
                break
            continue
        blanks, last_family = 0, family
        if not family:
            continue
        if family not in fam_order:
            fam_order.append(family)
        role_list = [x.strip() for x in re.split(r"[;\n]", cell(r, "roles")) if x.strip()]
        sev = next((s for s in SEVERITIES if cell(r, "severity").lower().startswith(s.lower())), cell(r, "severity"))
        sid = slug(name)
        if sid in skills:
            dupes.append(name)
            continue
        was = next((s for s in previous.skills if s.id == sid), None) if previous else None  # vendor / category survive a new gap report
        skills[sid] = Skill(sid, name, slug(family), True, sev, cell(r, "target"), len(role_list) if "roles" in cols else None,
                            role_list if keep_roles else [], was.vendor if was else "", was.category if was else "")
        if cell(r, "champion"):
            champs.setdefault(family, Counter())[cell(r, "champion")] += 1
        fam_roles.setdefault(family, set()).update(role_list)
        fam_gap[family] = fam_gap.get(family, 0) + len(role_list)
    if not skills:
        return None, {"error": "I found the headers, but no rows with skills below them."}
    summary = _find_summary(rows)
    old = {f.id: f.champion for f in previous.families} if previous else {}
    old_mail = {f.id: f.champion_email for f in previous.families} if previous else {}
    fams = []
    for name in fam_order:
        gap, impact = summary.get(name, (None, None))
        if name not in summary and "roles" in cols:
            gap, impact = fam_gap.get(name), len(fam_roles.get(name, ()))
        champion = old.get(slug(name)) or (champs[name].most_common(1)[0][0] if name in champs else "")
        fams.append(Family(slug(name), name, gap, impact, champion, old_mail.get(slug(name), "")))
    report = {"families": len(fams), "skills": len(skills), "header_row": hdr + 1, "columns": sorted(cols), "summary": bool(summary),
              "duplicates": dupes, "missing_columns": [k for k in ("severity", "roles", "target", "champion") if k not in cols]}
    return Catalog(fams, list(skills.values())), report


def catalog_from_tables(families: list[dict], skills: list[dict], previous: Catalog | None = None) -> Catalog:
    """Catalog from the two hand-edited tables (rows as dicts). Lesson-facing ids stay the slug of each name."""
    def blank(v) -> bool:
        try:
            return v is None or bool(v != v)  # NaN is the only value different from itself
        except TypeError:  # pandas.NA refuses to be a bool
            return True

    def clean(v) -> str:
        return "" if blank(v) else str(v).strip()

    def num(v):
        try:
            return None if blank(v) else int(v)
        except (TypeError, ValueError):
            return None

    fams = [Family(slug(clean(f.get("name"))), clean(f.get("name")), num(f.get("gap")), num(f.get("impact")), clean(f.get("champion")),
                   clean(f.get("email")))
            for f in families if clean(f.get("name"))]
    old = {s.id: s for s in previous.skills} if previous else {}
    out = []
    for s in skills:
        name = clean(s.get("name"))
        if not name:
            continue
        prev = old.get(slug(name))
        out.append(Skill(slug(name), name, slug(clean(s.get("family"))), True, clean(s.get("severity")), clean(s.get("target")),
                         num(s.get("impact")), prev.roles if prev else [],
                         clean(s.get("vendor")) if "vendor" in s else (prev.vendor if prev else ""),
                         clean(s.get("category")) if "category" in s else (prev.category if prev else "")))
    return Catalog(fams, out)


# ---------------------------------------------------------------------------------------------- support materials
# Existing material per skill (Microsoft Learn or any other provider), kept apart from skills.json so that importing a
# new gap report never wipes it: catalog/materials.json = {skill id: [{title, url, provider, kind, verified}]}.
def materials_path() -> Path:
    return catalog_path().parent / "materials.json"


def load_materials(path: str | Path | None = None) -> dict[str, list[dict]]:
    p = Path(path) if path else materials_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_materials(materials: dict[str, list[dict]], path: str | Path | None = None) -> Path:
    p = Path(path) if path else materials_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in materials.items() if v}
    p.write_text(json.dumps(clean, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p


def validate_materials(materials: dict[str, list[dict]], cat: Catalog | None = None) -> list[str]:
    errs = []
    known = cat.skill_ids() if cat else None
    for sid, items in materials.items():
        if known is not None and sid not in known:
            errs.append(f"[material] the skill '{sid}' does not exist in the catalog.")
        for m in items:
            if not m.get("title") or not str(m.get("url", "")).startswith(("https://", "file:")):
                errs.append(f"[material of {sid}] the title is missing or the URL is not https.")
    return errs
