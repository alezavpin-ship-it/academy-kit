"""Rhythm: the meetings that keep the upskilling alive, each with an agenda built from the academy's own data.

Three kinds of series:

* monthly  - review between the owner lead and the skill family champions: families in red, people behind, certifications
             about to expire, and the demand against the bench (what roles ask for, who can take them, what has no course);
* weekly   - one per skill family, led by its champion with the family's members: blockers, people to follow up, forum
             questions waiting, a short demo by a member (rotating), the certifications the family asks for;
* study    - a study group for one certification with an exam date: a domain of the exam per session, the members' best
             mock exam against the pass mark, and the countdown to the exam.

Every meeting carries action items (what, who, by when); the open ones open the next meeting. Invitations are .ics files
(Outlook / Teams) with the recurrence and the attendees; times are local ("floating"), the way a team in one region reads them.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

MONTHLY, WEEKLY, STUDY = "monthly", "weekly", "study"
KINDS = {MONTHLY: "Monthly review", WEEKLY: "Family sync", STUDY: "Study group"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKS = {1: "first", 2: "second", 3: "third", 4: "fourth", -1: "last"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS rhythm_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, title TEXT NOT NULL, family TEXT NOT NULL DEFAULT '',
    cert TEXT NOT NULL DEFAULT '', lead TEXT NOT NULL DEFAULT '', weekday INTEGER NOT NULL DEFAULT 1, week INTEGER NOT NULL DEFAULT 1,
    time TEXT NOT NULL DEFAULT '10:00', minutes INTEGER NOT NULL DEFAULT 60, every INTEGER NOT NULL DEFAULT 1,
    start TEXT NOT NULL DEFAULT '', end TEXT NOT NULL DEFAULT '', place TEXT NOT NULL DEFAULT '', open INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS rhythm_members (
    series INTEGER NOT NULL, learner TEXT NOT NULL, joined TEXT NOT NULL DEFAULT '', PRIMARY KEY (series, learner)
);
CREATE TABLE IF NOT EXISTS rhythm_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, series INTEGER NOT NULL, meeting TEXT NOT NULL DEFAULT '', text TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT '', due TEXT NOT NULL DEFAULT '', done INTEGER NOT NULL DEFAULT 0, done_at TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '', created TEXT NOT NULL DEFAULT ''
);
"""


@dataclass
class Series:
    id: int
    kind: str
    title: str
    family: str = ""
    cert: str = ""
    lead: str = ""
    weekday: int = 1  # 0 = Monday
    week: int = 1  # monthly: 1-4 or -1 (last)
    time: str = "10:00"
    minutes: int = 60
    every: int = 1  # weekly / study: every N weeks
    start: str = ""  # YYYY-MM-DD
    end: str = ""  # study group: the exam date (sessions stop before it)
    place: str = ""  # a Teams link or a room
    open: bool = True  # study group: anyone can join
    active: bool = True

    def when(self) -> str:
        day = WEEKDAYS[self.weekday]
        if self.kind == MONTHLY:
            return f"{WEEKS.get(self.week, 'first').capitalize()} {day} of the month · {self.time} · {self.minutes} min"
        often = "Every week" if self.every == 1 else f"Every {self.every} weeks"
        return f"{often} on {day} · {self.time} · {self.minutes} min" + (f" · until the exam on {self.end}" if self.kind == STUDY and self.end else "")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _day(text: str) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


# ------------------------------------------------------------------------------------------------ dates
def nth_weekday(year: int, month: int, weekday: int, week: int) -> date:
    """The ``week``-th ``weekday`` of a month (week -1 = the last one)."""
    days = [d for d in calendar.Calendar().itermonthdates(year, month) if d.month == month and d.weekday() == weekday]
    return days[-1] if week == -1 or week > len(days) else days[week - 1]


def occurrences(s: Series, start: date, end: date) -> list[date]:
    """Meeting dates of a series between ``start`` and ``end`` (both included)."""
    begin = max(start, _day(s.start) or start)
    stop = end
    if s.kind == STUDY and _day(s.end):
        stop = min(end, _day(s.end) - timedelta(days=1))
    out: list[date] = []
    if begin > stop:
        return out
    if s.kind == MONTHLY:
        y, m = begin.year, begin.month
        while date(y, m, 1) <= stop:
            d = nth_weekday(y, m, s.weekday, s.week)
            if begin <= d <= stop:
                out.append(d)
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out
    anchor = _day(s.start) or begin
    first = anchor + timedelta(days=(s.weekday - anchor.weekday()) % 7)
    step = timedelta(weeks=max(1, s.every))
    d = first
    while d < begin:
        d += step
    while d <= stop:
        out.append(d)
        d += step
    return out


def session_number(s: Series, day: date) -> tuple[int, int]:
    """(this session's number, how many sessions until the exam) for a study group."""
    start = _day(s.start) or day
    allx = occurrences(s, start, _day(s.end) or day + timedelta(weeks=8))
    n = next((i for i, d in enumerate(allx, start=1) if d >= day), len(allx))
    return n, len(allx)


# ------------------------------------------------------------------------------------------------ storage
class Rhythm:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        conn.executescript(SCHEMA)

    @staticmethod
    def _series(r) -> Series:
        return Series(r["id"], r["kind"], r["title"], r["family"], r["cert"], r["lead"], r["weekday"], r["week"], r["time"], r["minutes"],
                      r["every"], r["start"], r["end"], r["place"], bool(r["open"]), bool(r["active"]))

    def all(self, active: bool | None = True) -> list[Series]:
        rows = self.conn.execute("SELECT * FROM rhythm_series ORDER BY CASE kind WHEN 'monthly' THEN 0 WHEN 'weekly' THEN 1 ELSE 2 END, title").fetchall()
        return [self._series(r) for r in rows if active is None or bool(r["active"]) == active]

    def get(self, sid: int) -> Series:
        r = self.conn.execute("SELECT * FROM rhythm_series WHERE id=?", (sid,)).fetchone()
        if r is None:
            raise KeyError(sid)
        return self._series(r)

    def create(self, kind: str, title: str, **kw) -> int:
        if kind not in KINDS:
            raise ValueError(kind)
        if kind == STUDY and not (kw.get("cert") and _day(kw.get("end", ""))):
            raise ValueError("A study group needs a certification and an exam date.")
        fields = {"family": "", "cert": "", "lead": "", "weekday": 1, "week": 1, "time": "10:00", "minutes": 60, "every": 1,
                  "start": date.today().isoformat(), "end": "", "place": "", "open": 1}
        fields.update({k: v for k, v in kw.items() if k in fields})
        _check_time(fields["time"])
        with self.conn:
            cur = self.conn.execute("INSERT INTO rhythm_series(kind, title, family, cert, lead, weekday, week, time, minutes, every, start, end, place, open, "
                                    "active, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)",
                                    (kind, title.strip(), fields["family"], str(fields["cert"]).upper(), fields["lead"].strip(), int(fields["weekday"]),
                                     int(fields["week"]), fields["time"], int(fields["minutes"]), max(1, int(fields["every"])), fields["start"],
                                     fields["end"], fields["place"].strip(), int(bool(fields["open"])), _now()))
        return int(cur.lastrowid)

    def update(self, sid: int, **kw) -> None:
        allowed = {"title", "lead", "weekday", "week", "time", "minutes", "every", "start", "end", "place", "open", "active"}
        kw = {k: v for k, v in kw.items() if k in allowed}
        if "time" in kw:
            _check_time(kw["time"])
        if kw:
            with self.conn:
                self.conn.execute(f"UPDATE rhythm_series SET {', '.join(f'{k}=?' for k in kw)} WHERE id=?",  # noqa: S608 - fixed column names
                                  [int(v) if isinstance(v, bool) else v for v in kw.values()] + [sid])

    def delete(self, sid: int) -> None:
        with self.conn:
            for t, col in (("rhythm_members", "series"), ("rhythm_actions", "series"), ("rhythm_series", "id")):
                self.conn.execute(f"DELETE FROM {t} WHERE {col}=?", (sid,))  # noqa: S608 - fixed table names

    # -------------------------------------------------------------- people
    def members(self, sid: int) -> list[str]:
        return [r["learner"] for r in self.conn.execute("SELECT learner FROM rhythm_members WHERE series=? ORDER BY joined", (sid,))]

    def join(self, sid: int, learner: str) -> None:
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO rhythm_members(series, learner, joined) VALUES (?,?,?)", (sid, learner.strip(), _now()))

    def leave(self, sid: int, learner: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM rhythm_members WHERE series=? AND lower(learner)=lower(?)", (sid, learner.strip()))

    def attendees(self, s: Series, owners: list[str], champions: dict[str, str], family_people: list[str] | None = None) -> list[str]:
        """Who is invited: monthly = owners + every champion; weekly = the family's champion, members and people working on it;
        study = the lead and the members. ``champions``: family id -> champion name."""
        if s.kind == MONTHLY:
            people = list(owners) + [c for c in champions.values() if c]
        elif s.kind == WEEKLY:
            people = [champions.get(s.family, "")] + (family_people or [])
        else:
            people = []
        people = [s.lead] + people + self.members(s.id)
        seen, out = set(), []
        for p in people:
            if p and p.lower() not in seen:
                seen.add(p.lower())
                out.append(p)
        return out

    # -------------------------------------------------------------- actions
    def actions(self, sid: int | None = None, open_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM rhythm_actions" + (" WHERE series=?" if sid is not None else "") + " ORDER BY done, due = '', due, id"
        rows = self.conn.execute(sql, (sid,) if sid is not None else ()).fetchall()
        return [dict(r) for r in rows if not (open_only and r["done"])]

    def add_action(self, sid: int, meeting: str, text: str, owner: str = "", due: str = "", by: str = "") -> int:
        if not text.strip():
            raise ValueError("text")
        if due and not _day(due):
            raise ValueError("due")
        with self.conn:
            cur = self.conn.execute("INSERT INTO rhythm_actions(series, meeting, text, owner, due, created_by, created) VALUES (?,?,?,?,?,?,?)",
                                    (sid, meeting, text.strip(), owner.strip(), due, by, _now()))
        return int(cur.lastrowid)

    def set_done(self, action_id: int, done: bool = True) -> None:
        with self.conn:
            self.conn.execute("UPDATE rhythm_actions SET done=?, done_at=? WHERE id=?", (int(done), _now()[:10] if done else "", action_id))

    # -------------------------------------------------------------- calendar
    def upcoming(self, days: int = 35, today: date | None = None, only: set[int] | None = None) -> list[tuple[date, Series]]:
        today = today or date.today()
        out = [(d, s) for s in self.all() if only is None or s.id in only for d in occurrences(s, today, today + timedelta(days=days))]
        return sorted(out, key=lambda x: (x[0], x[1].time))

    def standard(self, families: list, owner: str, today: date | None = None) -> list[int]:
        """The recommended rhythm, created once: the monthly review and one sync per family (led by its champion).
        Families that already have their sync are skipped."""
        today = today or date.today()
        have = {(s.kind, s.family) for s in self.all(None)}
        made = []
        if (MONTHLY, "") not in have:
            made.append(self.create(MONTHLY, "Monthly upskilling review: owner lead and champions", lead=owner, weekday=1, week=1, time="10:00",
                                    minutes=60, start=today.isoformat()))
        for n, f in enumerate(families):
            if (WEEKLY, f.id) not in have:
                made.append(self.create(WEEKLY, f"{f.name}: family sync", family=f.id, lead=f.champion or owner, weekday=3,
                                        time=["09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00"][n % 9],
                                        minutes=30, every=1, start=today.isoformat()))
        return made


def _check_time(text: str) -> None:
    try:
        datetime.strptime(text, "%H:%M")
    except ValueError as e:
        raise ValueError(f"Time must be HH:MM (24 h), not '{text}'.") from e


# ------------------------------------------------------------------------------------------------ invitations (.ics)
def _esc(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines of at most 75 octets, continued with a space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def ics(s: Series, attendees: dict[str, str], organizer: str = "", description: str = "", first: date | None = None) -> bytes:
    """One recurring event for the series. ``attendees``: name -> e-mail (people without e-mail are left out)."""
    first = first or (occurrences(s, date.today(), date.today() + timedelta(days=400)) or [date.today()])[0]
    h, m = (int(x) for x in s.time.split(":"))
    begin = datetime(first.year, first.month, first.day, h, m)
    end = begin + timedelta(minutes=s.minutes)
    day = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][s.weekday]
    if s.kind == MONTHLY:
        rule = f"FREQ=MONTHLY;BYDAY={s.week if s.week != -1 else -1}{day}"
    else:
        rule = f"FREQ=WEEKLY;INTERVAL={max(1, s.every)};BYDAY={day}"
        if s.kind == STUDY and _day(s.end):
            last = _day(s.end) - timedelta(days=1)
            rule += f";UNTIL={last.strftime('%Y%m%d')}T235959"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Academia - Cloud//Rhythm//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "BEGIN:VEVENT", f"UID:rhythm-{s.id}-{s.kind}@academia-cloud", f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
             f"DTSTART:{begin.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}", f"RRULE:{rule}",
             f"SUMMARY:{_esc(s.title)}", f"DESCRIPTION:{_esc(description or KINDS[s.kind] + ' · Academia - Cloud')}"]
    if s.place:
        lines.append(f"LOCATION:{_esc(s.place)}")
    if organizer and "@" in organizer:
        lines.append(f"ORGANIZER:mailto:{organizer}")
    for name, mail in attendees.items():
        if mail and "@" in mail:
            lines.append(f"ATTENDEE;CN={_esc(name)};ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{mail}")
    lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Reminder", "TRIGGER:-PT15M", "END:VALARM", "END:VEVENT", "END:VCALENDAR"]
    return ("\r\n".join(_fold(x) for x in lines) + "\r\n").encode("utf-8")


# ------------------------------------------------------------------------------------------------ agendas
def agenda(conn, s: Series, day: date, packs: list, exams: list, catalog, owners: list[str] | None = None) -> list[tuple[str, list[str]]]:
    """The meeting's agenda as (heading, lines), built from the academy's data on the day it is opened."""
    from academy import report

    rh = Rhythm(conn)
    out: list[tuple[str, list[str]]] = []
    open_actions = [a for a in rh.actions(s.id, open_only=True)]
    late = sum(1 for a in open_actions if a["due"] and a["due"] < day.isoformat())
    out.append((f"Open actions ({len(open_actions)}{f', {late} late' if late else ''})",
                [f"{a['text']} — {a['owner'] or 'no owner'}{' · due ' + a['due'] if a['due'] else ''}" for a in open_actions] or ["None: a clean start."]))
    if s.kind == MONTHLY:
        rep = report.build(conn, packs, exams, catalog, "en")
        sm = rep["summary"]
        red = [r for r in rep["status"] if r["_state"] != report.ON_TRACK]
        out.append(("Skill families", [f"{sm['families']} families · {sm['on_track']} on track · {sm['no_champion']} without champion"]
                    + [f"{r['Skill family']}: {r['Status']} (champion: {r['Champion']})" for r in red[:8]]))
        out.append(("People", [f"{sm.get('behind', 0)} behind or at risk · {sm.get('not_started', 0)} not started · {sm['people']} with activity"]))
        from academy.certs import Certs

        crep = Certs(conn).report(catalog, "en", roster=report.roster(conn))
        cs = crep["summary"]
        out.append(("Certifications", [f"{cs['current']} current · {cs['desired']} desired · {cs['expiring']} expire within 90 days"]
                    + [f"{r['Person']}: {r['Certification']} expires {r['Expires']}" for r in crep["expiring"][:5]]))
        out.append(("Demand against the bench", _demand_lines(conn, catalog, packs)))
        out.append(("Study groups", [f"{g.title}: exam {g.end}, {len(rh.members(g.id))} members" for g in rh.all() if g.kind == STUDY] or
                    ["No study group running: pick the certification with the most demand and the fewest holders."]))
        out.append(("Decisions", ["Record each decision as an action with an owner and a date."]))
    elif s.kind == WEEKLY:
        rep = report.build(conn, packs, exams, catalog, "en", only={s.family})
        row = rep["status"][0] if rep["status"] else None
        if row:
            out.append(("The family this week", [f"{row['People']} people · {row['Active']} active · {row['Need follow-up']} need follow-up · "
                                                 f"lessons {row['Lesson progress']} · route {row['Route progress']}"]))
        late_people = [r for r in rep["followup"] if r["_late"]]
        out.append(("People to follow up", [f"{r['Person']}: {r['Days idle'] if r['Days idle'] is not None else '—'} days idle · {r['Suggested action']}"
                                            for r in late_people[:8]] or ["Nobody: everyone is moving."]))
        from academy.forum import Forum

        waiting = [q for q in Forum(conn).waiting({s.family})][:5]
        out.append(("Forum questions waiting", [q.title for q in waiting] or ["None."]))
        members = [m for m in rh.members(s.id)] or [r["Person"] for r in rep["followup"]]
        if members:
            week = day.isocalendar()[1]
            out.append(("Demo of the week (5 min)", [f"{members[week % len(members)]}: something learned or built this week."]))
        from academy.certs import Certs

        reqs = Certs(conn).requirements({s.family})
        out.append(("Certifications this family asks for", [f"{r['Code']} ({r['Level']})" for r in reqs] or ["None defined yet."]))
    else:
        n, total = session_number(s, day)
        left = (_day(s.end) - day).days if _day(s.end) else None
        out.append(("Where we are", [f"Session {n} of {total} · exam {s.cert} on {s.end}" + (f" ({left} days left)" if left is not None else "")]))
        exam = next((e for e in exams if e.code.upper() == s.cert.upper()), None)
        if exam:
            plan = study_plan(exam, total)
            topic = plan[min(n, len(plan)) - 1] if plan else ""
            out.append(("This session", [topic or "Review and mock exam."]))
            from academy.exam import ExamTracker

            lines = []
            for who in rh.members(s.id):
                best = max((a.get("score", 0) for a in ExamTracker(conn, exam, who).attempts()), default=None)
                lines.append(f"{who}: " + (f"best mock {best} / pass {exam.pass_score}" + (" ✓" if best >= exam.pass_score else "") if best is not None
                                            else "no mock exam yet"))
            out.append(("Readiness", lines or ["No members yet."]))
        else:
            out.append(("This session", [f"Pick the domain of the {s.cert} study guide for this week and share the Microsoft Learn path."]))
            out.append(("Members", rh.members(s.id) or ["No members yet."]))
    return out


def study_plan(exam, sessions: int) -> list[str]:
    """One topic per session: the exam's modules in order, the last two sessions for a mock exam and the review."""
    mods = [m.title for m in exam.modules]
    if sessions <= 2 or not mods:
        return mods[:sessions] or []
    work = sessions - 2
    per = max(1, -(-len(mods) // work))
    plan = [" + ".join(mods[i:i + per]) for i in range(0, len(mods), per)][:work]
    return plan + ["Mock exam in the academy, then review of the weakest modules", "Final review: exam logistics and last doubts"]


def _demand_lines(conn, catalog, packs) -> list[str]:
    """The most requested practice skills of the latest roles file, with how many people can take them (level 3+)."""
    from academy import demand
    from academy.catalog import load_materials
    from academy.inventory import Inventory
    from academy.practice import load_practice

    try:
        snaps = demand.snapshots()
        rows = demand.load(snaps[-1][1]) if snaps else demand.load()
    except Exception:
        rows = []
    if not rows:
        return ["No roles file yet: load it in the Demand tab to compare the demand with the bench."]
    a = demand.analyze(rows, load_practice(), catalog, packs, load_materials(), "en")
    k = a["keys"]
    top = [r for r in a["skills"] if r["_scope"] != "outside"][:6]
    ids = [r["_entry"].skill_id for r in top if r.get("_entry") is not None and r["_entry"].skill_id]
    bench = Inventory(conn).coverage(ids)
    lines = []
    for r in top:
        sid = r["_entry"].skill_id if r.get("_entry") is not None else ""
        lines.append(f"{r[k['skill']]}: {r[k['roles']]} roles · {bench.get(sid, 0)} people at level 3+ · {r[k['cover']]}")
    return lines + [f"{a['summary']['outside']} roles fall outside the practice."]
