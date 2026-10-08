"""What the practice is: its description, the skills / technologies it works with and the roles it can staff.

It is DATA, edited in the content file (tables Practica, PracticaSkills, PracticaRoles) and stored in
catalog/practice.json, so another practice (ServiceNow, SAP…) reuses the whole academy by changing those tables:

* skills - a term as the demand writes it, its aliases, the catalog skill / family it maps to, its vendor and its scope:
           core (what the practice does), third-party (other vendors it also handles) or emerging (where it wants to grow).
* roles  - the role titles the practice can provide, with aliases.

``match_skill`` / ``match_role`` turn a free text of a role request into one of those entries (or None = outside the practice).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from academy.catalog import catalog_path

CORE, THIRD, EMERGING, OUTSIDE = "core", "third-party", "emerging", "outside"
SCOPES = [CORE, THIRD, EMERGING]
_SCOPE = {"": CORE, "core": CORE, "principal": CORE, "third-party": THIRD, "third party": THIRD, "tercero": THIRD, "terceros": THIRD,
          "3rd party": THIRD, "emerging": EMERGING, "emergente": EMERGING, "nuevo": EMERGING}


def practice_path() -> Path:
    return catalog_path().parent / "practice.json"


def norm(s: str) -> str:
    """Lower case, without punctuation or double spaces: 'Azure AD (B2C)' -> 'azure ad b2c'."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#.áéíóúñ]+", " ", str(s or "").lower())).strip()


def scope_of(text: str) -> str:
    return _SCOPE.get(str(text or "").strip().lower(), CORE)


@dataclass(frozen=True)
class Term:
    term: str
    aliases: tuple[str, ...] = ()
    skill_id: str = ""  # skill of the catalog it maps to ('' = not in the catalog yet)
    family: str = ""  # role family id
    vendor: str = ""
    scope: str = CORE


@dataclass(frozen=True)
class RoleTerm:
    title: str
    aliases: tuple[str, ...] = ()
    scope: str = CORE


@dataclass
class Practice:
    name: str = ""
    description: str = ""
    skills: list[Term] = field(default_factory=list)
    roles: list[RoleTerm] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._skills = self._index([(t, [t.term, *t.aliases]) for t in self.skills])
        self._roles = self._index([(r, [r.title, *r.aliases]) for r in self.roles])

    @staticmethod
    def _index(entries):
        """(normalized text, entry) pairs, longest first, so 'defender for cloud apps' wins over 'defender for cloud'."""
        pairs = [(norm(text), e) for e, texts in entries for text in texts if norm(text)]
        return sorted(pairs, key=lambda p: -len(p[0]))

    @staticmethod
    def _match(index, text: str):
        n = norm(text)
        if not n:
            return None
        for key, entry in index:  # the whole text is the term or one of its aliases
            if key == n:
                return entry
        for key, entry in index:  # the term appears inside as whole words; short aliases (PIM, DLP…) only match exactly
            if len(key) >= 4 and re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", n):
                return entry
        return None

    def match_skill(self, text: str) -> Term | None:
        return self._match(self._skills, text)

    def match_role(self, text: str) -> RoleTerm | None:
        return self._match(self._roles, text)


def to_dict(p: Practice) -> dict:
    return {"name": p.name, "description": p.description,
            "skills": [{"term": t.term, "aliases": list(t.aliases), "skill_id": t.skill_id, "family": t.family, "vendor": t.vendor, "scope": t.scope}
                       for t in p.skills],
            "roles": [{"title": r.title, "aliases": list(r.aliases), "scope": r.scope} for r in p.roles]}


def from_dict(d: dict) -> Practice:
    return Practice(d.get("name", ""), d.get("description", ""),
                    [Term(s["term"], tuple(s.get("aliases", [])), s.get("skill_id", ""), s.get("family", ""), s.get("vendor", ""),
                          scope_of(s.get("scope", ""))) for s in d.get("skills", []) if s.get("term")],
                    [RoleTerm(r["title"], tuple(r.get("aliases", [])), scope_of(r.get("scope", ""))) for r in d.get("roles", []) if r.get("title")])


def load_practice(path: str | Path | None = None) -> Practice:
    p = Path(path) if path else practice_path()
    return from_dict(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else Practice()


def save_practice(practice: Practice, path: str | Path | None = None) -> Path:
    p = Path(path) if path else practice_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(to_dict(practice), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p
