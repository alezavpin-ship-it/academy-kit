"""Status and follow-up reports by role family, for owners (every family) and champions (their own families).

* status    - one row per family: who leads it, the gap it must close, how much content it has, how many people are
              working on it and how far they are, and a one-word state.
* follow-up - one row per person and family: last activity, days idle, progress and the suggested action.

Pure logic plus two exports (Excel and PDF, see academy/report_pdf.py). Numbers come from the same sources as the Team tab
(notify.family_team), so a champion never sees people outside their families.
"""

from __future__ import annotations

import io
import sqlite3
from datetime import date, datetime, timezone

from academy import notify
from academy.catalog import load_materials
from academy.route import build_routes

# state of a family, worst first (also the order of the report)
NO_CHAMPION, NO_CONTENT, NOT_STARTED, FOLLOW_UP, ON_TRACK = "no_champion", "no_content", "not_started", "follow_up", "on_track"
STATE = {NO_CHAMPION: "No champion", NO_CONTENT: "No content",
         NOT_STARTED: "Not started", FOLLOW_UP: "Needs follow-up",
         ON_TRACK: "On track"}


# how a person stands on a family's career path, worst first
BEHIND, AT_RISK, NOT_STARTED, GOING, DONE = "behind", "at_risk", "not_started", "going", "done"
PATH_ORDER = [BEHIND, AT_RISK, NOT_STARTED, GOING, DONE]
PATH = {BEHIND: "Not keeping up", AT_RISK: "At risk", NOT_STARTED: "Not started",
        GOING: "On track", DONE: "Completed"}


def roster(conn: sqlite3.Connection) -> list[str]:
    """Everyone the academy knows: whoever did something, registered an e-mail or registered a certification."""
    names: dict[str, str] = {}
    queries = ["SELECT DISTINCT learner FROM events", "SELECT learner FROM people", "SELECT DISTINCT learner FROM cert_records",
               "SELECT DISTINCT learner FROM skill_records"]
    for q in queries:
        try:
            for r in conn.execute(q):
                names.setdefault(r[0].strip().lower(), r[0].strip())
        except sqlite3.OperationalError:  # that table does not exist yet
            pass
    return sorted((n for n in names.values() if n), key=str.lower)


def _frac(text: str) -> tuple[int, int]:
    """'3/8' -> (3, 8); anything else -> (0, 0)."""
    try:
        a, b = str(text).split("/")
        return int(a), int(b)
    except ValueError:
        return 0, 0


def _pct(done: int, total: int) -> str:
    return f"{round(100 * done / total)} %" if total else "—"


def _idle(last: str, today: date) -> int | None:
    try:
        return (today - date.fromisoformat(last[:10])).days
    except ValueError:
        return None


def build(conn: sqlite3.Connection, packs: list, exams: list, catalog, lang: str = "es", only: set[str] | None = None,
          now: datetime | None = None) -> dict:
    """{"status": [...], "followup": [...], "summary": {...}, "generated": "YYYY-MM-DD HH:MM UTC"}.

    ``only``: family ids to include (a champion's families); None = every family (owners)."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    fam_of = {s.id: s.family for s in catalog.skills}
    routes = {r.family_id: r for r in build_routes(catalog, load_materials())}
    c = {
        "family": "Role family", "champion": "Champion", "gap": "Gap volume",
        "roles": "Roles affected", "skills": "Skills",
        "uncovered": "Skills without official training", "lessons": "Lessons",
        "steps": "Route steps", "certs": "Certifications", "people": "People",
        "active": "Active", "follow": "Need follow-up",
        "lessons_pct": "Lesson progress", "steps_pct": "Route progress",
        "passed": "Mock exams passed", "last": "Last activity",
        "state": "Status", "person": "Person", "idle": "Days idle",
        "route": "Route", "best": "Best mock exam",
        "action": "Suggested action", "forum": "Forum: waiting"}
    from academy.forum import Forum

    forum = Forum(conn).counts()  # questions of each family still waiting for an expert
    status, followup, paths = [], [], []
    everyone = roster(conn)
    path_name = dict(PATH)
    c.update(path="Career path", fams_open="Families in progress",
             fams_done="Families completed", classes="Route classes")
    per_person: dict[str, dict] = {w: {"open": 0, "done": 0, "s": 0, "st": 0, "l": 0, "lt": 0, "last": "", "worst": NOT_STARTED} for w in everyone}
    totals = {"families": 0, "people": set(), "follow": 0, "on_track": 0, "no_champion": 0}
    for fam in catalog.by_gap():
        if only is not None and fam.id not in only:
            continue
        skills = catalog.in_family(fam.id)
        lessons = sum(1 for p in packs for les in p.lessons if {fam_of.get(s) for s in les.catalog_skills} & {fam.id})
        route = routes.get(fam.id)
        steps = len(route.steps) if route else 0
        fam_exams = [e for e in exams if e.family == fam.id]
        rows = notify.family_team(conn, packs, exams, catalog, {fam.id})
        pass_mark = min((e.pass_score for e in fam_exams), default=None)
        active = need = passed = 0
        l_done = l_total = s_done = s_total = 0
        last_seen = ""
        for r in rows:
            last = r["Last activity"] or ""
            idle = _idle(last, today)
            ld, lt = _frac(r["Family lessons"])
            sd, st = _frac(r["Route (provider steps)"])
            l_done, l_total, s_done, s_total = l_done + ld, l_total + lt, s_done + sd, s_total + st
            best = r["Best mock exam"]
            ok_exam = pass_mark is not None and best is not None and best >= pass_mark
            passed += ok_exam
            last_seen = max(last_seen, last)
            finished = (lt == 0 or ld == lt) and (st == 0 or sd == st) and (pass_mark is None or ok_exam)
            if finished:
                action, late, pstate = "Completed the available content: agree on the next step with the champion", False, DONE
            elif idle is None or idle >= notify.STALLED_DAYS:
                action, late, pstate = "Contact today: agree on the next step and a date", True, BEHIND
            elif idle >= notify.INACTIVE_DAYS:
                action, late, pstate = "Send a reminder", True, AT_RISK
            else:
                action, late, pstate = "No action: making progress", False, GOING
            paths.append({c["family"]: fam.name, c["person"]: r["Person"], c["classes"]: r["Route (provider steps)"] if st else "—",
                          c["lessons"]: r["Family lessons"], c["best"]: best, c["last"]: last or "—",
                          c["idle"]: idle, c["path"]: path_name[pstate], "_path": pstate})
            me = per_person.setdefault(r["Person"], {"open": 0, "done": 0, "s": 0, "st": 0, "l": 0, "lt": 0, "last": "", "worst": NOT_STARTED})
            me["done" if pstate == DONE else "open"] += 1
            me.update(s=me["s"] + sd, st=me["st"] + st, l=me["l"] + ld, lt=me["lt"] + lt, last=max(me["last"], last))
            me["worst"] = pstate if me["worst"] == NOT_STARTED else min(me["worst"], pstate, key=PATH_ORDER.index)
            active, need = active + (not late), need + late
            followup.append({c["family"]: fam.name, c["champion"]: fam.champion or "—", c["person"]: r["Person"], c["last"]: last or "—",
                             c["idle"]: idle, c["route"]: r["Route (provider steps)"] if st else "—", c["lessons"]: r["Family lessons"],
                             c["best"]: best, c["action"]: action, "_late": late})
            totals["people"].add(r["Person"])
        if lessons or steps or fam_exams:  # people of the academy who have not touched this family's path
            started = {r["Person"].lower() for r in rows}
            paths += [{c["family"]: fam.name, c["person"]: w, c["classes"]: f"0/{steps}" if steps else "—",
                       c["lessons"]: f"0/{lessons}" if lessons else "—", c["best"]: None, c["last"]: "—", c["idle"]: None,
                       c["path"]: path_name[NOT_STARTED], "_path": NOT_STARTED} for w in everyone if w.lower() not in started]
        if not fam.champion:
            state = NO_CHAMPION
        elif not (lessons or steps or fam_exams):
            state = NO_CONTENT
        elif not rows:
            state = NOT_STARTED
        elif need > active:
            state = FOLLOW_UP
        else:
            state = ON_TRACK
        status.append({c["family"]: fam.name, c["champion"]: fam.champion or "—", c["gap"]: fam.gap_volume, c["roles"]: fam.role_impact,
                       c["skills"]: len(skills), c["uncovered"]: len(route.uncovered) if route else len(skills), c["lessons"]: lessons,
                       c["steps"]: steps, c["certs"]: len(fam_exams), c["people"]: len(rows), c["active"]: active, c["follow"]: need,
                       c["lessons_pct"]: _pct(l_done, l_total), c["steps_pct"]: _pct(s_done, s_total), c["passed"]: passed,
                       c["forum"]: forum.get(fam.id, {}).get("waiting", 0),
                       c["last"]: last_seen or "—", c["state"]: STATE[state], "_state": state})
        totals["families"] += 1
        totals["follow"] += need
        totals["on_track"] += state == ON_TRACK
        totals["no_champion"] += state == NO_CHAMPION
    followup.sort(key=lambda r: (not r["_late"], -(r[c["idle"]] if r[c["idle"]] is not None else 10**6)))
    paths.sort(key=lambda r: (PATH_ORDER.index(r["_path"]), r[c["family"]], str(r[c["person"]]).lower()))
    people = []
    for who, m in sorted(per_person.items(), key=lambda kv: (PATH_ORDER.index(kv[1]["worst"]), kv[0].lower())):
        people.append({c["person"]: who, c["fams_open"]: m["open"], c["fams_done"]: m["done"],
                       c["classes"]: f"{m['s']}/{m['st']}" if m["st"] else "—", c["lessons"]: f"{m['l']}/{m['lt']}" if m["lt"] else "—",
                       c["last"]: m["last"] or "—", c["idle"]: _idle(m["last"], today), c["path"]: path_name[m["worst"]], "_path": m["worst"]})
    summary = {"families": totals["families"], "people": len(totals["people"]), "follow": totals["follow"],
               "on_track": totals["on_track"], "no_champion": totals["no_champion"]}
    summary["behind"] = sum(1 for p in people if p["_path"] in (BEHIND, AT_RISK))
    summary["not_started"] = sum(1 for p in people if p["_path"] == NOT_STARTED)
    return {"status": status, "followup": followup, "paths": paths, "people": people, "summary": summary, "generated": now.strftime("%Y-%m-%d %H:%M UTC"), "lang": lang}


def visible(rows: list[dict]) -> list[dict]:
    """The rows without the internal keys (those starting with '_')."""
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


def titles(lang: str) -> dict[str, str]:
    return {"report": "Status and follow-up report by role family",
            "status": "Status by family",
            "followup": "Follow-up by person",
            "people": "Progress by person",
            "paths": "Career path by family and person",
            "behind": "People behind or at risk",
            "not_started": "People who have not started",
            "certs_fam": "Certifications by family",
            "certs_people": "Certifications by person",
            "certs_exp": "Certifications about to expire",
            "generated": "Generated",
            "families": "Families", "active_people": "People with activity",
            "follow": "Need follow-up", "on_track": "Families on track",
            "no_champion": "Families without champion",
            "empty": "Nobody has started content of these families yet.",
            "rules": f"Reminder after {notify.INACTIVE_DAYS} days without activity; direct contact after {notify.STALLED_DAYS}."}


def to_xlsx(rep: dict) -> bytes:
    """Excel workbook with two sheets (status, follow-up), ready to share in Teams or attach to a mail."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    t = titles(rep["lang"])
    wb = Workbook()
    sheets = [(t["status"], visible(rep["status"])), (t["people"], visible(rep.get("people", []))), (t["paths"], visible(rep.get("paths", []))),
              (t["followup"], visible(rep["followup"]))]
    certs = rep.get("certs") or {}
    sheets += [(t[k], certs[c]) for k, c in (("certs_fam", "families"), ("certs_people", "people"), ("certs_exp", "expiring")) if certs.get(c)]
    for i, (name, rows) in enumerate(sheets):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = name[:31]
        ws.append([t["report"]])
        ws.append([f"{name} · {t['generated']}: {rep['generated']}"])
        ws["A1"].font = Font(bold=True, size=14)
        ws.append([])
        cols = list(rows[0]) if rows else [t["empty"]]
        ws.append(cols)
        for cell in ws[4]:
            cell.font = Font(bold=True, color="1C1C1E")
            cell.fill = PatternFill("solid", fgColor="FF5800")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for r in rows:
            ws.append([r[k] for k in cols])
        for n, col in enumerate(cols, start=1):
            width = max([len(str(col))] + [len(str(r[col])) for r in rows]) if rows else len(str(col))
            ws.column_dimensions[get_column_letter(n)].width = min(max(width + 2, 10), 48)
        ws.freeze_panes = "A5"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
