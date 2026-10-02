"""Notices to learners, with copy to the champion (owner) of the skill family.

Offline, the app only PREPARES each message (recipient, copy, subject, body): a person sends it from Outlook with one
click, or downloads the queue as CSV. In Microsoft 365 the same rules and texts feed a Power Automate flow that sends
them automatically. Rules:
* course_done  - finished every lesson of a course            -> congratulations
* exam_passed  - passed a mock certification exam             -> congratulations
* inactive     - no activity at all for INACTIVE_DAYS days    -> "no has tomado cursos en N días"
* stalled      - active, but no progress for STALLED_DAYS     -> "no has avanzado"
A notice is identified by (learner, kind, ref); once marked as sent it is not proposed again.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote

from academy.exam import ExamTracker
from academy.progress import Tracker

INACTIVE_DAYS = 5
STALLED_DAYS = 7
KINDS = {"course_done": "Curso terminado", "exam_passed": "Simulacro aprobado", "inactive": "Sin actividad", "stalled": "Sin avance"}
SIGN = "Academia - Cloud"


@dataclass
class Notice:
    learner: str
    kind: str
    ref: str  # what makes this notice unique: the course, the exam, or the date of the last activity
    subject: str
    body: str
    to: str = ""
    cc: list[str] = field(default_factory=list)
    champions: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.learner, self.kind, self.ref)


# ---------------------------------------------------------------------------------------------- people
def set_email(conn: sqlite3.Connection, learner: str, email: str) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO people(learner, email) VALUES (?,?)", (learner.strip(), email.strip()))


def emails(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["learner"]: r["email"] for r in conn.execute("SELECT learner, email FROM people").fetchall() if r["email"]}


def _address(learner: str, known: dict[str, str]) -> str:
    return known.get(learner) or (learner if "@" in learner else "")


# ---------------------------------------------------------------------------------------------- owners
def owner_families(pack, catalog) -> list:
    """Families a course belongs to, the one with most lessons first (its champion goes in copy)."""
    if catalog is None:
        return []
    fam_of = {s.id: s.family for s in catalog.skills}
    count: dict[str, int] = {}
    for les in pack.lessons:
        for sid in les.catalog_skills:
            if sid in fam_of:
                count[fam_of[sid]] = count.get(fam_of[sid], 0) + 1
    by_id = {f.id: f for f in catalog.families}
    return [by_id[k] for k in sorted(count, key=count.get, reverse=True) if k in by_id]


def _champions(families) -> tuple[list[str], list[str]]:
    names, mails = [], []
    for f in families:
        if f.champion and f.champion not in names:
            names.append(f.champion)
        if f.champion_email and f.champion_email not in mails:
            mails.append(f.champion_email)
    return names, mails


def _first_name(learner: str) -> str:
    base = learner.split("@")[0].replace(".", " ").replace("_", " ").strip()
    return base.split()[0].capitalize() if base else learner


def _foot(champions: list[str], lang: str = "es") -> str:
    if not champions:
        return SIGN
    names = ", ".join(champions)
    who = (f"Copied to {names}, champion of the skill family, who can support you.\n\n" if lang == "en"
           else f"Con copia a {names}, champion de la familia de skills, que puede apoyarte.\n\n")
    return f"{who}{SIGN}"


# ---------------------------------------------------------------------------------------------- rules
def _parse(t: str) -> datetime:
    d = datetime.fromisoformat(t)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def pending(conn: sqlite3.Connection, packs: list, exams: list, catalog, now: datetime | None = None,
            learner: str | None = None, include_sent: bool = False, lang: str = "es") -> list[Notice]:
    """Notices that apply right now (for everyone, or for one learner), written in ``lang``."""
    en = lang == "en"
    hi = "Hi" if en else "Hola"
    now = now or datetime.now(timezone.utc)
    known = emails(conn)
    sent = set() if include_sent else {(r["learner"], r["kind"], r["ref"]) for r in conn.execute("SELECT learner, kind, ref FROM notices")}
    people = [learner] if learner else [r["learner"] for r in conn.execute("SELECT DISTINCT learner FROM events ORDER BY learner")]
    fam_by_id = {f.id: f for f in catalog.families} if catalog else {}
    out: list[Notice] = []
    for who in people:
        rows = conn.execute("SELECT pack, time, points FROM events WHERE learner=? ORDER BY time", (who,)).fetchall()
        if not rows:
            continue
        name, to = _first_name(who), _address(who, known)
        started = {r["pack"] for r in rows}
        open_fams, next_step = [], ""
        for pack in packs:
            if pack.id not in started:
                continue
            done = Tracker(conn, pack, who).completed_lessons()
            fams = owner_families(pack, catalog)
            if len(done) == len(pack.lessons):
                names, mails = _champions(fams[:1])
                subject = f"Congratulations! You finished \"{pack.title}\"" if en else f"¡Felicidades! Terminaste «{pack.title}»"
                body = ((f"Congratulations! You completed the {len(pack.lessons)} lessons of \"{pack.title}\". "
                         "What you learned already counts toward covering the roles the team receives.\n\n"
                         "Next step: deliver the VBDs you still have pending or start the next course.\n\n") if en else
                        (f"¡Felicidades! Completaste las {len(pack.lessons)} lecciones de «{pack.title}». "
                         "Lo que aprendiste ya cuenta para cubrir los roles que recibe el equipo.\n\n"
                         "Siguiente paso: entrega los VBD que te falten o empieza el siguiente curso.\n\n"))
                out.append(Notice(who, "course_done", pack.id, subject, f"{hi} {name}:\n\n{body}" + _foot(names, lang), to, mails, names))
            else:
                open_fams += [f for f in fams[:1] if f not in open_fams]
                next_step = next_step or next((f"\"{les.title}\" ({pack.title})" if en else f"«{les.title}» ({pack.title})")
                                              for les in pack.lessons if les.id not in done)
        for exam in exams:
            if exam.pack_id not in started:
                continue
            tr = ExamTracker(conn, exam, who)
            fams = [fam_by_id[exam.family]] if exam.family in fam_by_id else []
            if tr.passed():
                names, mails = _champions(fams)
                best = max(a.get("score", 0) for a in tr.attempts())
                subject = (f"Congratulations! You passed the {exam.code} mock exam" if en
                           else f"¡Felicidades! Aprobaste el simulacro de {exam.code}")
                body = ((f"Congratulations! You passed the mock exam of {exam.name} with {best} out of 1000 "
                         f"(the pass mark is {exam.pass_score}).\n\nNext step: book the official exam while it is fresh.\n\n") if en else
                        (f"¡Felicidades! Aprobaste el simulacro de {exam.name} con {best} de 1000 "
                         f"(se aprueba con {exam.pass_score}).\n\nSiguiente paso: agenda el examen oficial mientras lo tienes fresco.\n\n"))
                out.append(Notice(who, "exam_passed", exam.id, subject, f"{hi} {name}:\n\n{body}" + _foot(names, lang), to, mails, names))
            else:
                open_fams += [f for f in fams if f not in open_fams]
                next_step = next_step or (f"practice for {exam.code}" if en else f"practicar para {exam.code}")
        last = _parse(rows[-1]["time"])
        idle = (now - last).days
        gains = [_parse(r["time"]) for r in rows if r["points"] > 0]
        names, mails = _champions(open_fams)
        tip = (f"Your next step: {next_step}. " if en else f"Tu siguiente paso: {next_step}. ") if next_step else ""
        if idle >= INACTIVE_DAYS:
            subject = f"You have not taken any course in {idle} days" if en else f"No has tomado cursos en {idle} días"
            body = (f"It has been {idle} days since your last activity in Academia - Cloud. {tip}"
                    "Twenty minutes is enough to get back into the rhythm.\n\n") if en else (
                    f"Han pasado {idle} días desde tu última actividad en Academia - Cloud. {tip}"
                    "Con 20 minutos retomas el ritmo.\n\n")
            out.append(Notice(who, "inactive", last.date().isoformat(), subject, f"{hi} {name}:\n\n{body}" + _foot(names, lang),
                              to, mails, names))
        elif next_step and (now - (gains[-1] if gains else _parse(rows[0]["time"]))).days >= STALLED_DAYS:
            since = gains[-1] if gains else _parse(rows[0]["time"])
            subject = "You have not made progress on your route" if en else "No has avanzado en tu ruta"
            body = (f"You have opened Academia - Cloud, but it has been {(now - since).days} days without progress. {tip}"
                    "If something is holding you back, reply to your champion: they are there to help.\n\n") if en else (
                    f"Has entrado a Academia - Cloud, pero llevas {(now - since).days} días sin avanzar. {tip}"
                    "Si algo te está frenando, respóndele a tu champion: está para ayudarte.\n\n")
            out.append(Notice(who, "stalled", since.date().isoformat(), subject, f"{hi} {name}:\n\n{body}" + _foot(names, lang),
                              to, mails, names))
    return [n for n in out if n.key not in sent]


def mark_sent(conn: sqlite3.Connection, notice: Notice) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO notices(learner, kind, ref, sent) VALUES (?,?,?,?)",
                     (*notice.key, datetime.now(timezone.utc).isoformat(timespec="seconds")))


def mailto(n: Notice) -> str:
    """A link that opens the message, already written, in the mail app (Outlook)."""
    q = [f"subject={quote(n.subject)}", f"body={quote(n.body)}"]
    if n.cc:
        q.insert(0, f"cc={quote(';'.join(n.cc))}")
    return f"mailto:{quote(n.to)}?{'&'.join(q)}"


def queue_rows(notices: list[Notice]) -> list[dict]:
    """The queue in the shape a Power Automate flow (or a mail merge) consumes."""
    return [{"To": n.to, "Cc": ";".join(n.cc), "Subject": n.subject, "Body": n.body, "Kind": n.kind, "Learner": n.learner, "Ref": n.ref,
             "Champion": ", ".join(n.champions)} for n in notices]


# ---------------------------------------------------------------------------------------------- one family's people
def family_team(conn: sqlite3.Connection, packs: list, exams: list, catalog, family_ids: set[str]) -> list[dict]:
    """Who is working on these skill families and how far they are: one row per person, counting only the lessons and
    certifications that belong to the families (what a champion is allowed to see)."""
    fam_of = {s.id: s.family for s in catalog.skills} if catalog else {}
    rows: dict[str, dict] = {}

    def row(who: str) -> dict:
        return rows.setdefault(who, {"Persona": who, "Lecciones": 0, "De": 0, "VBDs": 0, "Mejor simulacro": None, "Última actividad": ""})

    for pack in packs:
        mine = [les for les in pack.lessons if {fam_of.get(sid) for sid in les.catalog_skills} & family_ids]
        if not mine:
            continue
        ids = {les.id for les in mine}
        for r in conn.execute("SELECT learner, item, kind, time FROM events WHERE pack=? ORDER BY time", (pack.id,)).fetchall():
            if r["item"].split(":")[0] not in ids:
                continue
            row(r["learner"])["Última actividad"] = r["time"][:10]
        for who in [w for w in rows]:
            t = Tracker(conn, pack, who)
            if any(x in ids for x in {e.split(":")[0] for e in t.events()["item"].tolist()}):
                row(who)["Lecciones"] += len(t.completed_lessons() & ids)
                row(who)["De"] += len(ids)
                row(who)["VBDs"] += len(t.vbds_done() & ids)
    for exam in exams:
        if exam.family not in family_ids:
            continue
        for r in conn.execute("SELECT DISTINCT learner FROM events WHERE pack=?", (exam.pack_id,)).fetchall():
            tr = ExamTracker(conn, exam, r["learner"])
            at = tr.attempts()
            cur = row(r["learner"])
            best = max((a.get("score", 0) for a in at), default=None)
            cur["Mejor simulacro"] = best if cur["Mejor simulacro"] is None else max(cur["Mejor simulacro"], best or 0)
            last = conn.execute("SELECT MAX(time) AS t FROM events WHERE pack=? AND learner=?", (exam.pack_id, r["learner"])).fetchone()["t"]
            cur["Última actividad"] = max(cur["Última actividad"], (last or "")[:10])
    route_done: dict[str, set] = {}
    route_total = 0
    if catalog:
        from academy.catalog import load_materials
        from academy.route import ROUTE_PACK, build_routes

        keys = {st.key for rt in build_routes(catalog, load_materials()) if rt.family_id in family_ids for st in rt.steps}
        route_total = len(keys)
        for r in conn.execute("SELECT learner, item, time FROM events WHERE pack=? AND kind='learn_item' ORDER BY time", (ROUTE_PACK,)).fetchall():
            if r["item"] in keys:
                cur = row(r["learner"])
                route_done.setdefault(r["learner"], set()).add(r["item"])
                cur["Última actividad"] = max(cur["Última actividad"], r["time"][:10])
    out = []
    for r in sorted(rows.values(), key=lambda x: x["Última actividad"], reverse=True):
        out.append({"Persona": r["Persona"], "Ruta (pasos del proveedor)": f"{len(route_done.get(r['Persona'], ()))}/{route_total}",
                    "Lecciones de la familia": f"{r['Lecciones']}/{r['De']}" if r["De"] else "—", "VBDs": r["VBDs"],
                    "Mejor simulacro": r["Mejor simulacro"], "Última actividad": r["Última actividad"]})
    return out
