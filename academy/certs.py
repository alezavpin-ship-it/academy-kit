"""Certification register: what each person holds today and what they are aiming for, and what each role family asks for.

* requirements - per role family, the certifications it requires or finds desirable (run by the family's champion / owners).
* records      - per person, their certifications: ``current`` (held, with dates and the credential link) or ``desired``.
                 Each learner keeps their own; owners and champions can correct them or set someone's desired ones.

Both travel as CSV (import / export) with fixed columns:

    records       Learner, Code, Name, Vendor, Status, Obtained, Expires, CredentialUrl
    requirements  FamilyId, Code, Name, Vendor, Level, Url

Requirements are per role family. Level = required | desirable | off (off keeps the certification in the plan without
asking for it). A learning path that prepares a certification (its CertId) also asks for it, as required, of everyone in
its family: ``asked`` joins both, and a requirement written for the family wins over the path's (to make it desirable or
off). Files and databases of the time families had job roles («Roles») still load; the roles are ignored.

Importing records replaces the certifications of the people who appear in the file (other people are untouched);
importing requirements replaces those of the families that appear in the file.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import date, datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS cert_requirements (
    family TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', vendor TEXT NOT NULL DEFAULT '',
    level TEXT NOT NULL DEFAULT 'desirable', url TEXT NOT NULL DEFAULT '', PRIMARY KEY (family, code)
);
CREATE TABLE IF NOT EXISTS cert_records (
    learner TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', vendor TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'current', obtained TEXT NOT NULL DEFAULT '', expires TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL DEFAULT '', updated_by TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (learner, code)
);
"""
CURRENT, DESIRED = "current", "desired"
REQUIRED, DESIRABLE, OFF = "required", "desirable", "off"
RECORD_COLUMNS = ["Learner", "Code", "Name", "Vendor", "Status", "Obtained", "Expires", "CredentialUrl"]
REQUIREMENT_COLUMNS = ["FamilyId", "Code", "Name", "Vendor", "Level", "Url"]
OPTIONAL_COLUMNS: set[str] = set()  # columns a file may leave out (an extra column, such as the retired «Roles», is ignored)
EXPIRING_DAYS = 90
_STATUS = {CURRENT: CURRENT, "actual": CURRENT, "obtenida": CURRENT, "vigente": CURRENT, "held": CURRENT, "": CURRENT,
           DESIRED: DESIRED, "deseable": DESIRED, "deseada": DESIRED, "planned": DESIRED, "planeada": DESIRED, "en curso": DESIRED}
_LEVEL = {REQUIRED: REQUIRED, "requerida": REQUIRED, "obligatoria": REQUIRED, "": DESIRABLE, DESIRABLE: DESIRABLE, "deseable": DESIRABLE,
          "desired": DESIRABLE, "opcional": DESIRABLE, OFF: OFF, "inactive": OFF, "disabled": OFF}
# A starting point an owner can load and then edit: Microsoft role-based certifications that match each family. Nothing is
# required until the family's champion says so, so they all start as «desirable».
SUGGESTED = {
    "identity-access-management": [("SC-300", "Microsoft Identity and Access Administrator")],
    "cyber-defense-security-operations": [("SC-200", "Microsoft Security Operations Analyst")],
    "data-protection-risk-compliance": [("SC-401", "Microsoft Information Security Administrator")],
    "cloud-network-security": [("AZ-500", "Microsoft Azure Security Engineer"), ("SC-900", "Microsoft Security, Compliance, and Identity Fundamentals")],
    "application-security-devsecops": [("AZ-400", "Microsoft DevOps Engineer")],
    "microsoft-365-security": [("MS-102", "Microsoft 365 Administrator")],
    "cloud-infrastructure-engineering": [("AZ-104", "Microsoft Azure Administrator")],
    "technical-delivery-leadership": [("SC-100", "Microsoft Cybersecurity Architect")],
    "ai-security-governance": [("AI-901", "Microsoft Azure AI Fundamentals")],
}


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def _date(v) -> str:
    """ISO date from what Excel may write (2026-03-01, 01/03/2026, 2026-03-01 00:00:00); '' if empty; raises if unreadable."""
    s = _text(v)
    if not s:
        return ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(s)


def _read_csv(raw: bytes, columns: list[str]) -> tuple[list[dict], list[str]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") > first.count(",") else ("\t" if first.count("\t") > first.count(",") else ",")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
    if not rows:
        return [], ["The file is empty."]
    head = [h.strip() for h in rows[0]]
    missing = [c for c in columns if c not in head and c not in OPTIONAL_COLUMNS]
    if missing:
        return [], [f"Missing columns: {', '.join(missing)}. Expected: {', '.join(columns)}."]
    out = []
    for n, row in enumerate(rows[1:], start=2):
        if any(c.strip() for c in row):
            rec = {**{c: "" for c in columns}, **{k: _text(v) for k, v in zip(head, row)}}
            rec["_row"] = n
            out.append(rec)
    return out, []


def _csv(columns: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(columns)
    for r in rows:
        w.writerow([r.get(c, "") for c in columns])
    return buf.getvalue().encode("utf-8-sig")


class Certs:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        conn.executescript(SCHEMA)
        # «roles» held the job roles of a requirement while families had them; it is kept (always empty) so older databases work
        if "roles" not in {r[1] for r in conn.execute("PRAGMA table_info(cert_requirements)")}:
            with conn:
                conn.execute("ALTER TABLE cert_requirements ADD COLUMN roles TEXT NOT NULL DEFAULT ''")

    # ------------------------------------------------------------------ requirements per family
    def requirements(self, families: set[str] | None = None, include_off: bool = False) -> list[dict]:
        """What the families ask for, as written for each family. «off» ones only with ``include_off``."""
        rows = self.conn.execute("SELECT * FROM cert_requirements ORDER BY family, level DESC, code").fetchall()
        return [{"FamilyId": r["family"], "Code": r["code"], "Name": r["name"], "Vendor": r["vendor"], "Level": r["level"], "Url": r["url"]}
                for r in rows if (families is None or r["family"] in families) and (include_off or r["level"] != OFF)]

    def asked(self, families: set[str] | None = None, structure=None) -> list[dict]:
        """Everything the families ask for: their requirements plus the certification of each active learning path (as
        required, «Path» = the path's name). A requirement written for the family wins over its path's, so a champion can
        make a path's certification desirable or switch it off."""
        out = self.requirements(families)
        if structure is None:
            return out
        written = {(r["FamilyId"], r["Code"]) for r in self.requirements(families, include_off=True)}
        fams = {p.family for p in structure.paths} if families is None else families
        for fam in sorted(fams):
            for p in structure.certs_of(fam):
                if (fam, p.cert) not in written:
                    written.add((fam, p.cert))
                    out.append({"FamilyId": fam, "Code": p.cert, "Name": p.name, "Vendor": structure.vendor_name(p.vendor), "Level": REQUIRED,
                                "Url": "", "Path": p.name})
        return out

    def set_requirements(self, family: str, rows: list[dict]) -> None:
        """Replace what a family asks for. Rows: Code, Name, Vendor, Level (required | desirable | off), Url."""
        clean = {}
        for r in rows:
            code = _text(r.get("Code")).upper()
            if code:
                clean[code] = (family, code, _text(r.get("Name")), _text(r.get("Vendor")), _LEVEL.get(_text(r.get("Level")).lower(), DESIRABLE),
                               _text(r.get("Url")), "")
        with self.conn:
            self.conn.execute("DELETE FROM cert_requirements WHERE family=?", (family,))
            self.conn.executemany("INSERT INTO cert_requirements(family, code, name, vendor, level, url, roles) VALUES (?,?,?,?,?,?,?)",
                                  list(clean.values()))

    def load_suggested(self, family_ids: set[str]) -> int:
        """Add the suggested certifications (as desirable) to the families that have none yet. Returns how many were added."""
        have = {r["FamilyId"] for r in self.requirements()}
        n = 0
        for fam, items in SUGGESTED.items():
            if fam in family_ids and fam not in have:
                self.set_requirements(fam, [{"Code": c, "Name": name, "Vendor": "Microsoft", "Level": DESIRABLE} for c, name in items])
                n += len(items)
        return n

    # ------------------------------------------------------------------ records per person
    def records(self, learner: str | None = None) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM cert_records ORDER BY learner COLLATE NOCASE, status, code").fetchall()
        return [{"Learner": r["learner"], "Code": r["code"], "Name": r["name"], "Vendor": r["vendor"], "Status": r["status"],
                 "Obtained": r["obtained"], "Expires": r["expires"], "CredentialUrl": r["url"]}
                for r in rows if learner is None or r["learner"].lower() == learner.strip().lower()]

    def set_records(self, learner: str, rows: list[dict], by: str = "") -> None:
        """Replace one person's certifications."""
        learner = learner.strip()
        if not learner:
            raise ValueError("learner")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        clean = {}
        for r in rows:
            code = _text(r.get("Code")).upper()
            if not code:
                continue
            status = _STATUS.get(_text(r.get("Status")).lower(), CURRENT)
            clean[code] = (learner, code, _text(r.get("Name")), _text(r.get("Vendor")), status,
                           _date(r.get("Obtained")) if status == CURRENT else "", _date(r.get("Expires")) if status == CURRENT else "",
                           _text(r.get("CredentialUrl")), now, by or learner)
        with self.conn:
            self.conn.execute("DELETE FROM cert_records WHERE lower(learner)=lower(?)", (learner,))
            self.conn.executemany("INSERT INTO cert_records(learner, code, name, vendor, status, obtained, expires, url, updated, updated_by) "
                                  "VALUES (?,?,?,?,?,?,?,?,?,?)", list(clean.values()))

    def learners(self) -> list[str]:
        return [r["learner"] for r in self.conn.execute("SELECT DISTINCT learner FROM cert_records ORDER BY learner COLLATE NOCASE")]

    # ------------------------------------------------------------------ CSV
    def records_csv(self, learner: str | None = None) -> bytes:
        return _csv(RECORD_COLUMNS, self.records(learner))

    def requirements_csv(self, families: set[str] | None = None) -> bytes:
        return _csv(REQUIREMENT_COLUMNS, self.requirements(families, include_off=True))

    @staticmethod
    def parse_records(raw: bytes, only_learner: str | None = None) -> tuple[dict[str, list[dict]], list[str]]:
        """{learner: rows} and the problems found. ``only_learner``: a learner importing their own file may only carry their rows."""
        rows, problems = _read_csv(raw, RECORD_COLUMNS)
        out: dict[str, list[dict]] = {}
        for r in rows:
            tag = f"[row {r['_row']}]"
            who = r["Learner"] or (only_learner or "")
            if not who or not r["Code"]:
                problems.append(f"{tag} Learner or Code is missing.")
                continue
            if only_learner and who.lower() != only_learner.strip().lower():
                problems.append(f"{tag} that row belongs to '{who}': you can only import your own certifications.")
                continue
            if r["Status"].lower() not in _STATUS:
                problems.append(f"{tag} Status must be current or desired.")
            for col in ("Obtained", "Expires"):
                try:
                    _date(r[col])
                except ValueError:
                    problems.append(f"{tag} {col} = '{r[col]}' is not a date (use YYYY-MM-DD).")
            if r["CredentialUrl"] and not r["CredentialUrl"].startswith("https://"):
                problems.append(f"{tag} CredentialUrl must start with https://.")
            out.setdefault(only_learner.strip() if only_learner else who, []).append(r)
        return out, problems

    @staticmethod
    def parse_requirements(raw: bytes, known_families: set[str], allowed: set[str] | None = None) -> tuple[dict[str, list[dict]], list[str]]:
        """{family id: rows} and the problems found. ``allowed``: the families this person runs (None = all)."""
        rows, problems = _read_csv(raw, REQUIREMENT_COLUMNS)
        out: dict[str, list[dict]] = {}
        for r in rows:
            tag = f"[row {r['_row']}]"
            if not r["FamilyId"] or not r["Code"]:
                problems.append(f"{tag} FamilyId or Code is missing.")
            elif r["FamilyId"] not in known_families:
                problems.append(f"{tag} FamilyId '{r['FamilyId']}' is not in the catalog.")
            elif allowed is not None and r["FamilyId"] not in allowed:
                problems.append(f"{tag} you do not run the family '{r['FamilyId']}'.")
            elif r["Level"].lower() not in _LEVEL:
                problems.append(f"{tag} Level must be required, desirable or off.")
            else:
                out.setdefault(r["FamilyId"], []).append(r)
        return out, problems

    # ------------------------------------------------------------------ reports
    def report(self, catalog, lang: str = "es", only: set[str] | None = None, roster: list[str] | None = None, today: date | None = None,
               structure=None) -> dict:
        """{"families": one row per family and certification it asks for, "people": one row per person, "expiring": [...]}.

        ``only``: the families a champion runs. ``roster``: everyone in the academy, so people without any record show up too.
        ``structure``: the learning structure (loaded from the practice when left out) whose paths' certifications count too."""
        today = today or datetime.now(timezone.utc).date()
        recs = self.records()
        fam_name = {f.id: f.name for f in catalog.families} if catalog else {}
        holders: dict[str, list[str]] = {}
        wanting: dict[str, list[str]] = {}
        for r in recs:
            (holders if r["Status"] == CURRENT else wanting).setdefault(r["Code"], []).append(r["Learner"])
        k = {"family": "Role family", "cert": "Certification",
             "level": "Level", "have": "Hold it", "want": "Aiming for it",
             "who": "Who holds it", "person": "Person",
             "current": "Current certifications", "n": "Current",
             "desired": "Desired certifications", "exp": "Expires",
             "next": "Next to expire", "missing": "Required and missing",
             "days": "Days left"}
        level = {REQUIRED: "Required", DESIRABLE: "Desirable"}
        if structure is None and catalog:
            from academy import paths as pathmod

            structure = pathmod.load(catalog)
        reqs = self.asked(only, structure)
        families = [{k["family"]: fam_name.get(r["FamilyId"], r["FamilyId"]), k["cert"]: f"{r['Code']} · {r['Name']}".rstrip(" ·"),
                     k["level"]: level[r["Level"]], k["have"]: len(holders.get(r["Code"], [])), k["want"]: len(wanting.get(r["Code"], [])),
                     k["who"]: ", ".join(sorted(holders.get(r["Code"], []), key=str.lower)) or "—"} for r in reqs]
        required = sorted({r["Code"] for r in reqs if r["Level"] == REQUIRED})
        names = list(dict.fromkeys(list(roster or []) + [r["Learner"] for r in recs]))
        people, expiring = [], []
        for who in sorted(names, key=str.lower):
            mine = [r for r in recs if r["Learner"].lower() == who.lower()]
            cur = [r for r in mine if r["Status"] == CURRENT]
            dated = sorted((r for r in cur if r["Expires"]), key=lambda r: r["Expires"])
            have = {r["Code"] for r in cur}
            people.append({k["person"]: who, k["n"]: len(cur), k["current"]: ", ".join(r["Code"] for r in cur) or "—",
                           k["desired"]: ", ".join(r["Code"] for r in mine if r["Status"] == DESIRED) or "—",
                           k["missing"]: ", ".join(c for c in required if c not in have) or "—",
                           k["next"]: f"{dated[0]['Code']} · {dated[0]['Expires']}" if dated else "—"})
            for r in dated:
                left = (date.fromisoformat(r["Expires"]) - today).days
                if left <= EXPIRING_DAYS:
                    expiring.append({k["person"]: who, k["cert"]: f"{r['Code']} · {r['Name']}".rstrip(" ·"), k["exp"]: r["Expires"], k["days"]: left})
        expiring.sort(key=lambda r: r[k["days"]])
        return {"families": families, "people": people, "expiring": expiring,
                "summary": {"people_with": sum(1 for p in people if p[k["n"]]), "people": len(people), "current": sum(p[k["n"]] for p in people),
                            "desired": sum(1 for r in recs if r["Status"] == DESIRED), "expiring": len(expiring)}}
