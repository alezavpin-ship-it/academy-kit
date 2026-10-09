"""The learning structure of a practice, as the practice runs it:

    Practice -> Role family (lead = champion, SMEs) -> Vendor -> Learning path (e.g. AZ-900) -> Skill -> Module -> Course

* Vendors (VendorId: MSFT, CISCO, AWS…) are shared by every family; a family uses the vendors of its learning paths.
* Job roles belong to a role family (sysadmin, architect…). A person's role is set in People (CourseRole) by owners and
  champions; it decides which learning paths and certifications they see.
* A learning path belongs to one family and one vendor, may lead to a certification (CertId) and may be limited to some
  job roles (empty = every role of the family).
* Skills (catalog/skills.json) are placed in a learning path, with an order; Modules group the courses of a skill.
* Courses are the classes of each skill (catalog/materials.json): title, link, kind (course, doc, guide, video, exam,
  certification…), location (SharePoint, Percipio, Workday MyLearning, vendor site, repo…), status required / optional /
  off and the module they belong to.

Everything can be switched on and off (Active / Status) by the family's champion without deleting it. The structure is
kept in catalog/paths.json of each practice (apart from skills.json, so importing a new gap report never wipes it); when
the file does not exist yet it is built from the catalog: one learning path per family and vendor.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

LOCATIONS = ["SharePoint", "Percipio", "Workday MyLearning", "Vendor site", "Repo", "Academy file", "Other"]
KINDS = ["course", "module", "path", "lab", "tutorial", "doc", "guide", "video", "exam", "certification", "deck"]
KIND_ICON = {"course": "🎓", "module": "📘", "path": "🧭", "lab": "🧪", "tutorial": "🛠️", "doc": "📄", "guide": "📗", "video": "▶️",
             "exam": "📝", "certification": "🏅", "deck": "📊"}
DEFAULT_MODULE = "Core"
VENDOR_IDS = {"Microsoft": "MSFT", "Cisco": "CISCO", "AWS": "AWS", "GCP": "GCP", "IBM": "IBM", "Palo Alto Networks": "PANW",
              "Fortinet": "FTNT", "CrowdStrike": "CRWD", "GitHub": "GITHUB", "Anthropic": "ANTHROPIC", "Vendor-neutral": "NEUTRAL"}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")


def vendor_id(name: str) -> str:
    return VENDOR_IDS.get(name, re.sub(r"[^A-Z0-9]+", "", str(name or "").upper())[:12] or "OTHER")


@dataclass(frozen=True)
class Vendor:
    id: str
    name: str
    url: str = ""
    active: bool = True


@dataclass(frozen=True)
class JobRole:
    id: str
    family: str
    name: str
    description: str = ""
    active: bool = True


@dataclass(frozen=True)
class LearningPath:
    id: str
    family: str
    vendor: str  # VendorId
    name: str
    cert: str = ""  # the certification it prepares (code, e.g. AZ-500)
    roles: tuple[str, ...] = ()  # job role ids of the family; empty = every role
    order: int = 0
    active: bool = True
    description: str = ""


@dataclass(frozen=True)
class Placement:
    path: str = ""
    order: int = 0
    active: bool = True


@dataclass
class Structure:
    vendors: list[Vendor] = field(default_factory=list)
    roles: list[JobRole] = field(default_factory=list)
    paths: list[LearningPath] = field(default_factory=list)
    skills: dict[str, Placement] = field(default_factory=dict)

    # ---------------------------------------------------------------- look-ups
    def vendor_name(self, vid: str) -> str:
        return next((v.name for v in self.vendors if v.id == vid), vid)

    def roles_of(self, family: str, active_only: bool = True) -> list[JobRole]:
        return [r for r in self.roles if r.family == family and (r.active or not active_only)]

    def role_of(self, family: str, text: str) -> JobRole | None:
        """The family's job role written as ``text`` (its id or its name, any case)."""
        t = str(text or "").strip().lower()
        return next((r for r in self.roles if r.family == family and t and t in (r.id.lower(), r.name.lower())), None) if t else None

    def paths_of(self, family: str, role: str | None = None, active_only: bool = True) -> list[LearningPath]:
        """The family's learning paths for a job role id (None = all of them), in order."""
        out = [p for p in self.paths if p.family == family and (p.active or not active_only)
               and (role is None or not p.roles or role in p.roles)]
        return sorted(out, key=lambda p: (p.order or 9999, p.name.lower()))

    def place(self, skill_id: str) -> Placement:
        return self.skills.get(skill_id, Placement())

    def skills_of(self, path_id: str, catalog, active_only: bool = True) -> list:
        sk = [s for s in catalog.skills if self.place(s.id).path == path_id and (self.place(s.id).active or not active_only)]
        return sorted(sk, key=lambda s: (self.place(s.id).order or 9999, s.name.lower()))

    def path(self, pid: str) -> LearningPath | None:
        return next((p for p in self.paths if p.id == pid), None)


# ------------------------------------------------------------------------------------------------ courses
def location_of(item: dict) -> str:
    """Where a course lives: the one written, or what its link says."""
    if item.get("location") in LOCATIONS:
        return item["location"]
    url = str(item.get("url", "")).lower()
    if url.startswith("file:"):
        return "Academy file"
    for loc, words in (("SharePoint", ("sharepoint.com",)), ("Percipio", ("percipio",)), ("Workday MyLearning", ("workday", "myworkday")),
                       ("Repo", ("github.com", "dev.azure.com", "gitlab"))):
        if any(w in url for w in words):
            return loc
    return "Vendor site" if url.startswith("https://") else "Other"


def module_of(item: dict) -> str:
    return str(item.get("module") or "").strip() or DEFAULT_MODULE


def modules(items: list[dict]) -> list[tuple[str, list[dict]]]:
    """The courses of a skill grouped by module, modules in the order their first course appears."""
    out: dict[str, list[dict]] = {}
    for m in items:
        out.setdefault(module_of(m), []).append(m)
    return list(out.items())


# ------------------------------------------------------------------------------------------------ file
def structure_path() -> Path:
    from academy.catalog import catalog_path

    return catalog_path().parent / "paths.json"


def to_dict(s: Structure) -> dict:
    return {"vendors": [vars(v) for v in s.vendors],
            "roles": [vars(r) for r in s.roles],
            "paths": [{**vars(p), "roles": list(p.roles)} for p in s.paths],
            "skills": {k: vars(v) for k, v in s.skills.items()}}


def from_dict(d: dict) -> Structure:
    return Structure([Vendor(**v) for v in d.get("vendors", [])], [JobRole(**r) for r in d.get("roles", [])],
                     [LearningPath(**{**p, "roles": tuple(p.get("roles", []))}) for p in d.get("paths", [])],
                     {k: Placement(**v) for k, v in d.get("skills", {}).items()})


def default(catalog, materials: dict | None = None) -> Structure:
    """The starting structure from a catalog: one learning path per family and vendor, every skill in its family's path of
    its vendor, in catalog order."""
    from academy.catalog import vendor_of

    s = Structure()
    if not catalog:
        return s
    for fam in catalog.families:
        mine = [(vendor_of(sk, materials), sk) for sk in catalog.in_family(fam.id)]
        names = list(dict.fromkeys(v for v, _ in mine))
        names.sort(key=lambda v: (v != "Microsoft", v == "Vendor-neutral"))  # Microsoft first; stable otherwise
        mine.sort(key=lambda x: names.index(x[0]))
        for n, (vname, sk) in enumerate(mine, start=1):
            vid = vendor_id(vname)
            if not any(v.id == vid for v in s.vendors):
                s.vendors.append(Vendor(vid, vname))
            pid = f"{fam.id}-{vid.lower()}"
            if not s.path(pid):
                order = 1 + sum(1 for p in s.paths if p.family == fam.id)
                s.paths.append(LearningPath(pid, fam.id, vid, f"{vname} learning path", order=order))
            s.skills[sk.id] = Placement(pid, n)
    return s


def complete(s: Structure, catalog, materials: dict | None = None) -> Structure:
    """Skills added to the catalog after the structure was written go to their family's path of their vendor (made if needed)."""
    if not catalog:
        return s
    missing = [sk for sk in catalog.skills if sk.id not in s.skills or not s.path(s.skills[sk.id].path)]
    if not missing:
        return s
    base = default(type(catalog)(catalog.families, missing), materials)
    out = Structure(list(s.vendors), list(s.roles), list(s.paths), dict(s.skills))
    for v in base.vendors:
        if not any(x.id == v.id for x in out.vendors):
            out.vendors.append(v)
    for p in base.paths:
        if not out.path(p.id):
            out.paths.append(replace(p, order=1 + sum(1 for x in out.paths if x.family == p.family)))
    for k, v in base.skills.items():
        out.skills[k] = Placement(v.path, (s.skills.get(k) or v).order or v.order, (s.skills.get(k) or v).active)
    return out


def load(catalog=None, materials: dict | None = None, path: Path | None = None) -> Structure:
    """The structure of the practice in use (built from the catalog the first time, and written so ids stay stable)."""
    from academy.catalog import load_catalog, load_materials

    p = path or structure_path()
    on_disk = catalog is None
    catalog = catalog if catalog is not None else load_catalog()
    if p.exists():
        try:
            return complete(from_dict(json.loads(p.read_text(encoding="utf-8"))), catalog, materials)
        except (ValueError, TypeError, KeyError):
            pass
    s = default(catalog, load_materials() if materials is None else materials)
    if catalog and on_disk:  # the practice's own catalog: written once so the ids stay stable
        try:
            save(s, p)
        except OSError:
            pass
    return s


def save(s: Structure, path: Path | None = None) -> Path:
    p = path or structure_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(to_dict(s), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p


def validate(s: Structure, catalog) -> list[str]:
    errs = []
    fams = {f.id for f in catalog.families} if catalog else set()
    vids = [v.id for v in s.vendors]
    if len(vids) != len(set(vids)):
        errs.append("[Vendors] a VendorId is repeated.")
    keys = [(r.family, r.id) for r in s.roles]
    if len(keys) != len(set(keys)):
        errs.append("[JobRoles] a RoleId is repeated inside a family.")
    for r in s.roles:
        if fams and r.family not in fams:
            errs.append(f"[JobRoles] '{r.name}': the family '{r.family}' does not exist.")
    pids = [p.id for p in s.paths]
    if len(pids) != len(set(pids)):
        errs.append("[Paths] a PathId is repeated.")
    for p in s.paths:
        if fams and p.family not in fams:
            errs.append(f"[Paths] '{p.name}': the family '{p.family}' does not exist.")
        if p.vendor not in vids:
            errs.append(f"[Paths] '{p.name}': the vendor '{p.vendor}' is not in Vendors.")
        for r in p.roles:
            if not any(x.family == p.family and x.id == r for x in s.roles):
                errs.append(f"[Paths] '{p.name}': the role '{r}' is not a job role of its family.")
    for sid, pl in s.skills.items():
        if pl.path and pl.path not in pids:
            errs.append(f"[Skills] '{sid}': the learning path '{pl.path}' does not exist.")
    return errs
