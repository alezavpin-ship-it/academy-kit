"""The people directory: who is who in the academy and what role they have. One CSV, editable in Excel, in the content
workbook (tab People) or in the app's edit mode:

    catalog/people.csv      (or the file named by ACADEMY_PEOPLE)

    Person, Email, Role, Families, Active

* Role = owner (sees and runs everything; at most 3 active owners, ACADEMY_MAX_OWNERS changes it) | champion (runs the role families listed in Families) | sme (answers in the
  forum as the expert of the families listed) | learner.
* Families = family ids separated by ";" (for champions and SMEs).
* Active = no keeps the person in the file without showing them in the list of names.

While the academy has no real sign-in, the sidebar offers these names («Who are you?»), and the roles are matched by name
or e-mail. Owners listed in config/access.json (with the optional PIN) and champions written in the skills catalog keep
working; when the directory names a family's champion, the catalog's champion of that family is updated to match, so
reports and notices copy the right person.
"""

from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PEOPLE_FILE = ROOT / "catalog" / "people.csv"
COLUMNS = ["Person", "Email", "Role", "Families", "Active"]
OWNER, CHAMPION, SME, LEARNER = "owner", "champion", "sme", "learner"
ROLES = [OWNER, CHAMPION, SME, LEARNER]
MAX_OWNERS = 3


def max_owners() -> int:
    try:
        return max(1, int(os.environ.get("ACADEMY_MAX_OWNERS", MAX_OWNERS)))
    except ValueError:
        return MAX_OWNERS


@dataclass(frozen=True)
class Person:
    name: str
    email: str = ""
    role: str = LEARNER
    families: tuple[str, ...] = ()
    active: bool = True

    def row(self) -> list[str]:
        return [self.name, self.email, self.role, "; ".join(self.families), "yes" if self.active else "no"]

    def matches(self, learner: str, email: str = "") -> bool:
        me = {_norm(learner), _norm(email)} - {""}
        return bool(me & ({_norm(self.name), _norm(self.email)} - {""}))


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def people_path() -> Path:
    return Path(os.environ.get("ACADEMY_PEOPLE") or PEOPLE_FILE)


def parse(raw: bytes, family_ids: set[str] | None = None) -> tuple[list[Person], list[str]]:
    text = raw.decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    rows = list(csv.DictReader(io.StringIO(text, newline=""), delimiter=";" if first.count(";") > first.count(",") else ","))
    if rows and "Person" not in rows[0]:
        return [], [f"Missing column Person ({', '.join(COLUMNS)})."]
    out, problems, seen = [], [], set()
    for n, r in enumerate(rows, start=2):
        name = (r.get("Person") or "").strip()
        if not name:
            continue
        role = (r.get("Role") or LEARNER).strip().lower() or LEARNER
        email = (r.get("Email") or "").strip()
        fams = tuple(x.strip() for x in (r.get("Families") or "").replace(",", ";").split(";") if x.strip())
        if role not in ROLES:
            problems.append(f"[people row {n}] Role must be one of: {', '.join(ROLES)}.")
            continue
        if email and "@" not in email:
            problems.append(f"[people row {n}] '{email}' is not an e-mail address.")
            continue
        if role in (CHAMPION, SME) and not fams:
            problems.append(f"[people row {n}] a {role} needs the Families they cover.")
            continue
        unknown = [f for f in fams if family_ids is not None and f not in family_ids]
        if unknown:
            problems.append(f"[people row {n}] unknown family id(s): {', '.join(unknown)}.")
            continue
        if name.lower() in seen:
            problems.append(f"[people row {n}] '{name}' is repeated.")
            continue
        seen.add(name.lower())
        out.append(Person(name, email, role, fams, (r.get("Active") or "yes").strip().lower() not in ("no", "n", "false", "0")))
    active = [p.name for p in out if p.role == OWNER and p.active]
    if len(active) > max_owners():
        problems.append(f"[people] at most {max_owners()} active owners: {', '.join(active)}. Make the others champions or learners.")
    return out, problems


def to_csv(people: list[Person]) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(COLUMNS)
    w.writerows(p.row() for p in people)
    return buf.getvalue().encode("utf-8-sig")


def load(path: str | Path | None = None) -> list[Person]:
    p = Path(path) if path else people_path()
    return parse(p.read_bytes())[0] if p.exists() else []


def save(people: list[Person], path: str | Path | None = None) -> Path:
    p = Path(path) if path else people_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(to_csv(people))
    return p


def find(people: list[Person], learner: str, email: str = "") -> Person | None:
    return next((p for p in people if p.matches(learner, email)), None)


def is_owner(people: list[Person], learner: str, email: str = "") -> bool:
    return any(p.role == OWNER and p.matches(learner, email) for p in people)


def owners(people: list[Person]) -> list[Person]:
    return [p for p in people if p.role == OWNER and p.active]


def set_owners(people: list[Person], new: list[tuple[str, str]]) -> tuple[list[Person], list[str]]:
    """The directory with exactly these owners ((name, e-mail) pairs). A person already in the directory keeps their row and
    becomes owner; an owner left out becomes a learner (a champion's families stay with them as champion). Returns the new
    directory and the problems (nothing is changed when there are any)."""
    from dataclasses import replace

    new = [(n.strip(), e.strip()) for n, e in new if n.strip() or e.strip()]
    problems = []
    if not new:
        problems.append("At least one owner must remain.")
    if len(new) > max_owners():
        problems.append(f"At most {max_owners()} owners.")
    for n, e in new:
        if not n or not e or "@" not in e:
            problems.append(f"«{n or e}»: each owner needs a name and a work e-mail (the one they sign in with).")
    if len({e.lower() for _, e in new}) < len(new):
        problems.append("The same e-mail is repeated.")
    if problems:
        return people, problems
    out, used = [], set()
    for p in people:
        hit = next((i for i, (n, e) in enumerate(new) if i not in used and (_norm(e) == _norm(p.email) or _norm(n) == _norm(p.name))), None)
        if hit is not None:
            used.add(hit)
            n, e = new[hit]
            out.append(replace(p, name=n, email=e, role=OWNER, active=True))
        elif p.role == OWNER:
            out.append(replace(p, role=CHAMPION if p.families else LEARNER))
        else:
            out.append(p)
    out += [Person(n, e, OWNER) for i, (n, e) in enumerate(new) if i not in used]
    return out, []


def families_of(people: list[Person], learner: str, email: str = "", role: str = CHAMPION) -> set[str]:
    return {f for p in people if p.role == role and p.matches(learner, email) for f in p.families}


def smes(people: list[Person]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for p in people:
        if p.role == SME:
            for f in p.families:
                out.setdefault(f, []).append(p.name)
    return out


def sync_catalog(people: list[Person], catalog):
    """The catalog with each family's champion taken from the directory (the first champion listed for the family)."""
    from dataclasses import replace

    champ: dict[str, Person] = {}
    for p in people:
        if p.role == CHAMPION and p.active:
            for f in p.families:
                champ.setdefault(f, p)
    if not catalog or not champ:
        return catalog, False
    fams, changed = [], False
    for f in catalog.families:
        c = champ.get(f.id)
        if c and (f.champion, f.champion_email) != (c.name, c.email):
            f, changed = replace(f, champion=c.name, champion_email=c.email), True
        fams.append(f)
    return type(catalog)(fams, catalog.skills), changed
