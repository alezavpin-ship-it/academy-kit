"""Status and follow-up reports by skill family, for owners (every family) and champions (their own families).

* status    - one row per family: who leads it, the gap it must close, how much content it has, how many people are
              working on it and how far they are, and a one-word state.
* follow-up - one row per person and family: last activity, days idle, progress and the suggested action.

Pure logic plus two exports (Excel and a printable HTML page). Numbers come from the same sources as the Team tab
(notify.family_team), so a champion never sees people outside their families.
"""

from __future__ import annotations

import html
import io
import sqlite3
from datetime import date, datetime, timezone

from academy import notify
from academy.catalog import load_materials
from academy.route import build_routes

# state of a family, worst first (also the order of the report)
NO_CHAMPION, NO_CONTENT, NOT_STARTED, FOLLOW_UP, ON_TRACK = "no_champion", "no_content", "not_started", "follow_up", "on_track"
STATE = {NO_CHAMPION: ("Sin champion", "No champion"), NO_CONTENT: ("Sin contenido", "No content"),
         NOT_STARTED: ("Sin iniciar", "Not started"), FOLLOW_UP: ("Requiere seguimiento", "Needs follow-up"),
         ON_TRACK: ("En marcha", "On track")}


# how a person stands on a family's career path, worst first
BEHIND, AT_RISK, NOT_STARTED, GOING, DONE = "behind", "at_risk", "not_started", "going", "done"
PATH_ORDER = [BEHIND, AT_RISK, NOT_STARTED, GOING, DONE]
PATH = {BEHIND: ("No está cumpliendo", "Not keeping up"), AT_RISK: ("En riesgo", "At risk"), NOT_STARTED: ("Sin iniciar", "Not started"),
        GOING: ("Al corriente", "On track"), DONE: ("Cumplido", "Completed")}


def roster(conn: sqlite3.Connection) -> list[str]:
    """Everyone the academy knows: whoever did something, registered an e-mail or registered a certification."""
    names: dict[str, str] = {}
    queries = ["SELECT DISTINCT learner FROM events", "SELECT learner FROM people", "SELECT DISTINCT learner FROM cert_records"]
    for q in queries:
        try:
            for r in conn.execute(q):
                names.setdefault(r[0].strip().lower(), r[0].strip())
        except sqlite3.OperationalError:  # that table does not exist yet
            pass
    return sorted((n for n in names.values() if n), key=str.lower)


def _l(lang: str, es: str, en: str) -> str:
    return en if lang == "en" else es


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
    c = {k: _l(lang, es, en) for k, (es, en) in {
        "family": ("Familia de skills", "Skill family"), "champion": ("Champion", "Champion"), "gap": ("Brecha", "Gap volume"),
        "roles": ("Roles afectados", "Roles affected"), "skills": ("Skills", "Skills"),
        "uncovered": ("Skills sin formación oficial", "Skills without official training"), "lessons": ("Lecciones", "Lessons"),
        "steps": ("Pasos de ruta", "Route steps"), "certs": ("Certificaciones", "Certifications"), "people": ("Personas", "People"),
        "active": ("Activas", "Active"), "follow": ("Por dar seguimiento", "Need follow-up"),
        "lessons_pct": ("Avance en lecciones", "Lesson progress"), "steps_pct": ("Avance en ruta", "Route progress"),
        "passed": ("Simulacros aprobados", "Mock exams passed"), "last": ("Última actividad", "Last activity"),
        "state": ("Estado", "Status"), "person": ("Persona", "Person"), "idle": ("Días sin actividad", "Days idle"),
        "route": ("Ruta", "Route"), "vbds": ("VBDs", "VBDs"), "best": ("Mejor simulacro", "Best mock exam"),
        "action": ("Acción sugerida", "Suggested action"), "forum": ("Foro: sin contestar", "Forum: waiting")}.items()}
    from academy.forum import Forum

    forum = Forum(conn).counts()  # questions of each family still waiting for an expert
    status, followup, paths = [], [], []
    everyone = roster(conn)
    path_name = {k: _l(lang, *v) for k, v in PATH.items()}
    c.update(path=_l(lang, "Ruta de carrera", "Career path"), fams_open=_l(lang, "Familias en curso", "Families in progress"),
             fams_done=_l(lang, "Familias completadas", "Families completed"), classes=_l(lang, "Clases de ruta", "Route classes"))
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
            last = r["Última actividad"] or ""
            idle = _idle(last, today)
            ld, lt = _frac(r["Lecciones de la familia"])
            sd, st = _frac(r["Ruta (pasos del proveedor)"])
            l_done, l_total, s_done, s_total = l_done + ld, l_total + lt, s_done + sd, s_total + st
            best = r["Mejor simulacro"]
            ok_exam = pass_mark is not None and best is not None and best >= pass_mark
            passed += ok_exam
            last_seen = max(last_seen, last)
            finished = (lt == 0 or ld == lt) and (st == 0 or sd == st) and (pass_mark is None or ok_exam)
            if finished:
                action, late, pstate = _l(lang, "Completó el contenido disponible: validar el siguiente paso con el champion", "Completed the available content: agree on the next step with the champion"), False, DONE
            elif idle is None or idle >= notify.STALLED_DAYS:
                action, late, pstate = _l(lang, "Contactar hoy: acordar el siguiente paso y una fecha", "Contact today: agree on the next step and a date"), True, BEHIND
            elif idle >= notify.INACTIVE_DAYS:
                action, late, pstate = _l(lang, "Enviar recordatorio", "Send a reminder"), True, AT_RISK
            else:
                action, late, pstate = _l(lang, "Sin acción: va avanzando", "No action: making progress"), False, GOING
            paths.append({c["family"]: fam.name, c["person"]: r["Persona"], c["classes"]: r["Ruta (pasos del proveedor)"] if st else "—",
                          c["lessons"]: r["Lecciones de la familia"], c["vbds"]: r["VBDs"], c["best"]: best, c["last"]: last or "—",
                          c["idle"]: idle, c["path"]: path_name[pstate], "_path": pstate})
            me = per_person.setdefault(r["Persona"], {"open": 0, "done": 0, "s": 0, "st": 0, "l": 0, "lt": 0, "last": "", "worst": NOT_STARTED})
            me["done" if pstate == DONE else "open"] += 1
            me.update(s=me["s"] + sd, st=me["st"] + st, l=me["l"] + ld, lt=me["lt"] + lt, last=max(me["last"], last))
            me["worst"] = pstate if me["worst"] == NOT_STARTED else min(me["worst"], pstate, key=PATH_ORDER.index)
            active, need = active + (not late), need + late
            followup.append({c["family"]: fam.name, c["champion"]: fam.champion or "—", c["person"]: r["Persona"], c["last"]: last or "—",
                             c["idle"]: idle, c["route"]: r["Ruta (pasos del proveedor)"] if st else "—", c["lessons"]: r["Lecciones de la familia"],
                             c["vbds"]: r["VBDs"], c["best"]: best, c["action"]: action, "_late": late})
            totals["people"].add(r["Persona"])
        if lessons or steps or fam_exams:  # people of the academy who have not touched this family's path
            started = {r["Persona"].lower() for r in rows}
            paths += [{c["family"]: fam.name, c["person"]: w, c["classes"]: f"0/{steps}" if steps else "—",
                       c["lessons"]: f"0/{lessons}" if lessons else "—", c["vbds"]: 0, c["best"]: None, c["last"]: "—", c["idle"]: None,
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
                       c["last"]: last_seen or "—", c["state"]: _l(lang, *STATE[state]), "_state": state})
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
    return {"report": _l(lang, "Reporte de estado y seguimiento por familia de skills", "Status and follow-up report by skill family"),
            "status": _l(lang, "Estado por familia", "Status by family"),
            "followup": _l(lang, "Seguimiento por persona", "Follow-up by person"),
            "people": _l(lang, "Avance por persona", "Progress by person"),
            "paths": _l(lang, "Ruta de carrera por familia y persona", "Career path by family and person"),
            "behind": _l(lang, "Personas atrasadas o en riesgo", "People behind or at risk"),
            "not_started": _l(lang, "Personas sin iniciar", "People who have not started"),
            "certs_fam": _l(lang, "Certificaciones por familia", "Certifications by family"),
            "certs_people": _l(lang, "Certificaciones por persona", "Certifications by person"),
            "certs_exp": _l(lang, "Certificaciones por vencer", "Certifications about to expire"),
            "generated": _l(lang, "Generado", "Generated"),
            "families": _l(lang, "Familias", "Families"), "active_people": _l(lang, "Personas con actividad", "People with activity"),
            "follow": _l(lang, "Por dar seguimiento", "Need follow-up"), "on_track": _l(lang, "Familias en marcha", "Families on track"),
            "no_champion": _l(lang, "Familias sin champion", "Families without champion"),
            "empty": _l(lang, "Todavía nadie ha empezado contenido de estas familias.", "Nobody has started content of these families yet."),
            "rules": _l(lang, f"Recordatorio a los {notify.INACTIVE_DAYS} días sin actividad; contacto directo a los {notify.STALLED_DAYS}.",
                        f"Reminder after {notify.INACTIVE_DAYS} days without activity; direct contact after {notify.STALLED_DAYS}.")}


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


def _table(rows: list[dict], flag: str | None = None) -> str:
    if not rows:
        return ""
    cols = [k for k in rows[0] if not k.startswith("_")]
    head = "".join(f"<th>{html.escape(str(k))}</th>" for k in cols)
    body = []
    for r in rows:
        cls = ""
        if flag == "_state":
            cls = {ON_TRACK: "ok", FOLLOW_UP: "warn", NOT_STARTED: "idle"}.get(r["_state"], "bad")
        elif flag == "_late":
            cls = "warn" if r["_late"] else "ok"
        elif flag == "_path":
            cls = "warn" if r["_path"] in (BEHIND, AT_RISK) else ("idle" if r["_path"] == NOT_STARTED else "ok")
        cells = "".join(f"<td>{html.escape('—' if r[k] is None else str(r[k]))}</td>" for k in cols)
        body.append(f'<tr class="{cls}">{cells}</tr>')
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def to_html(rep: dict) -> str:
    """A standalone page: open it in the browser and print it (or save it as PDF) for the follow-up meeting."""
    t, s = titles(rep["lang"]), rep["summary"]
    kpis = "".join(f'<div class="kpi"><b>{v}</b><span>{html.escape(k)}</span></div>' for k, v in (
        (t["families"], s["families"]), (t["on_track"], s["on_track"]), (t["no_champion"], s["no_champion"]),
        (t["active_people"], s["people"]), (t["follow"], s["follow"]), (t["behind"], s.get("behind", 0)),
        (t["not_started"], s.get("not_started", 0))))
    certs = rep.get("certs") or {}
    extra = "".join(f'<h2>{html.escape(t[k])}</h2><div class="scroll">{_table(certs[c])}</div>'
                    for k, c in (("certs_fam", "families"), ("certs_people", "people"), ("certs_exp", "expiring")) if certs.get(c))
    follow = _table(rep["followup"], "_late") or f"<p>{html.escape(t['empty'])}</p>"
    return f"""<!doctype html>
<html lang="{rep['lang']}"><head><meta charset="utf-8"><title>{html.escape(t['report'])}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;color:#1C1C1E;margin:32px;line-height:1.45}}
h1{{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}}h2{{font-size:18px;margin:32px 0 10px}}
.meta{{color:#55524E;font-size:13px}}.bar{{height:6px;width:72px;background:#FF5800;border-radius:3px;margin-bottom:14px}}
.kpis{{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0 4px}}
.kpi{{border:1px solid #E4E0DB;border-radius:10px;padding:12px 16px;min-width:150px}}
.kpi b{{display:block;font-size:26px}}.kpi span{{font-size:13px;color:#55524E}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:12.5px}}
th{{background:#1C1C1E;color:#FFFFFF;text-align:left;padding:8px 10px;vertical-align:bottom}}
td{{padding:7px 10px;border-bottom:1px solid #E4E0DB;vertical-align:top}}
tr.warn td:first-child{{box-shadow:inset 4px 0 0 #FF5800}}tr.bad td:first-child{{box-shadow:inset 4px 0 0 #1C1C1E}}
tr.warn td:last-child,tr.bad td:last-child{{font-weight:700}}
@media print{{body{{margin:12mm}}th{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
</style></head><body>
<div class="bar"></div><h1>{html.escape(t['report'])}</h1>
<div class="meta">Academia - Cloud · {html.escape(t['generated'])}: {rep['generated']} · {html.escape(t['rules'])}</div>
<div class="kpis">{kpis}</div>
<h2>{html.escape(t['status'])}</h2><div class="scroll">{_table(rep['status'], '_state')}</div>
<h2>{html.escape(t['people'])}</h2><div class="scroll">{_table(rep.get('people', []), '_path')}</div>
<h2>{html.escape(t['paths'])}</h2><div class="scroll">{_table(rep.get('paths', []), '_path')}</div>
<h2>{html.escape(t['followup'])}</h2><div class="scroll">{follow}</div>
{extra}
</body></html>"""
