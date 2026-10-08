"""Who sees what: two views, end user and owner.

* End user: own course, glossary, videos, own progress, skills map (without the team's gap numbers) and certifications.
* Owner (owners and leaders of the skills-development team): everything above plus the whole team's measurements, the
  notices queue, the gap numbers and the catalog administration.
* Champion of a role family: the end-user view plus the measurements, notices and gap numbers of THEIR families only.

Offline there is no real sign-in, so this is a separation of views with an optional PIN, not a security boundary: anyone
with the files can read the local database. The real enforcement arrives with Microsoft 365, where ``is_leader`` becomes
"is a member of the owners security group". The list lives in config/access.json (or the file named by ACADEMY_ACCESS).
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

ACCESS_PATH = Path(__file__).resolve().parents[1] / "config" / "access.json"


def access_path() -> Path:
    return Path(os.environ.get("ACADEMY_ACCESS") or ACCESS_PATH)


def _norm(s: str) -> str:
    return (s or "").strip().lower()


@dataclass
class Access:
    owners: list[str] = field(default_factory=list)  # names or e-mails, as typed in «Tu nombre» / «Tu correo»
    security_group: str = ""  # the Entra ID group that will replace this list once the app runs in Microsoft 365
    salt: str = ""
    pin_hash: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.owners)

    def has_pin(self) -> bool:
        return bool(self.pin_hash)

    def check_pin(self, pin: str) -> bool:
        return not self.pin_hash or secrets.compare_digest(_hash(pin, self.salt), self.pin_hash)

    def set_pin(self, pin: str) -> None:
        if pin:
            self.salt = secrets.token_hex(8)
            self.pin_hash = _hash(pin, self.salt)
        else:
            self.salt = self.pin_hash = ""

    def is_owner(self, learner: str, email: str = "") -> bool:
        """Listed as owner or leader of the skills-development team: sees the whole team."""
        me = {_norm(learner), _norm(email)} - {""}
        return bool(me & {_norm(o) for o in self.owners})

    @staticmethod
    def champion_families(learner: str, email: str = "", catalog=None) -> set[str]:
        """Ids of the role families this person champions (matched by name or e-mail): they see only those."""
        me = {_norm(learner), _norm(email)} - {""}
        if catalog is None or not me:
            return set()
        return {f.id for f in catalog.families if me & ({_norm(f.champion), _norm(f.champion_email)} - {""})}

    def is_leader(self, learner: str, email: str = "", catalog=None) -> bool:
        """Owner, or champion of at least one family."""
        return self.is_owner(learner, email) or bool(self.champion_families(learner, email, catalog))


def _hash(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()


def load_access(path: str | Path | None = None) -> Access:
    p = Path(path) if path else access_path()
    if not p.exists():
        return Access()
    d = json.loads(p.read_text(encoding="utf-8"))
    return Access(list(d.get("owners", [])), d.get("security_group", ""), d.get("salt", ""), d.get("pin_hash", ""))


def save_access(acc: Access, path: str | Path | None = None) -> Path:
    p = Path(path) if path else access_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    owners = list(dict.fromkeys(o.strip() for o in acc.owners if o and o.strip()))
    p.write_text(json.dumps({"owners": owners, "security_group": acc.security_group, "salt": acc.salt, "pin_hash": acc.pin_hash},
                            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p
