"""Demand analysis: what the role requests ask for, what of it belongs to the practice, and what has a course.

Input: the roles file (CSV or Excel export) with the columns in ``COLUMNS``. It lives next to the content file:

    content/demanda_roles.csv            (or the file named by ACADEMY_DEMAND)

Each role's skills (primary, secondary, other, combined) are matched against the practice definition
(academy/practice.py, edited in the content file): a skill is core, third-party or emerging for the practice, or
outside it. The matched skills are crossed with the skills catalog to see which already have lessons or a learning
path and which are a gap worth a course. Everything here is pure logic; the screen lives in academy/demand_page.py.
"""

from __future__ import annotations

import csv
import html
import io
import os
import re
from collections import Counter
from pathlib import Path

from academy.catalog import slug
from academy.practice import CORE, EMERGING, OUTSIDE, THIRD, Practice

ROOT = Path(__file__).resolve().parents[1]
DEMAND_FILE = ROOT / "content" / "demanda_roles.csv"
COLUMNS = ["Timestamp", "Client", "Governance Lead", "Project", "Role ID", "Role Title", "Role Description", "Combined Skills",
           "Role Career Level From", "Role Career Level To", "Role Status", "Role Is Sold", "Role Start Date", "Role End Date",
           "Role Market Unit", "Role Primary Contact (Email ID)", "Role Job Family Group", "Role Country/Territory", "Role Location Path",
           "Role Fulfillment Entity Path", "Role Primary Skill", "Skill Category", "Role Secondary Skill", "Role Other Skills",
           "Project Country/Territory", "Role Created By (Email ID)", "Role Location Type", "Role Work Location", "Role Source Location",
           "Role Accepting Resumes", "Role Has Security/Nationality Restriction", "Role Recruiting Status", "Project Location Path",
           "Industry Level 1", "Industry Level 2"]
NEEDED = ["Role ID", "Role Title", "Role Primary Skill"]  # without these a row cannot be analyzed; every other column may be empty
SKILL_COLUMNS = ["Role Primary Skill", "Role Secondary Skill", "Role Other Skills", "Combined Skills"]
# chart colors by scope (validated as a categorical set, colorblind-safe); text never wears them
COLOR = {CORE: "#eb6834", THIRD: "#2a78d6", EMERGING: "#1baf7a", OUTSIDE: "#4a3aa7"}
SCOPE_NAME = {CORE: ("De la práctica", "Core of the practice"), THIRD: ("Otros vendors que manejamos", "Other vendors we handle"),
              EMERGING: ("Foco nuevo", "Emerging focus"), OUTSIDE: ("Fuera de la práctica", "Outside the practice")}
COVER = {"lessons": ("Con curso", "Has a course"), "path": ("Solo learning path", "Learning path only"),
         "none": ("Sin contenido", "No content"), "new": ("No está en el catálogo", "Not in the catalog")}


def demand_path() -> Path:
    return Path(os.environ.get("ACADEMY_DEMAND") or DEMAND_FILE)


def _l(lang: str, pair: tuple[str, str]) -> str:
    return pair[1] if lang == "en" else pair[0]


# ------------------------------------------------------------------------------------------------ reading
def parse(raw: bytes) -> tuple[list[dict], list[str]]:
    """Rows of a roles file (CSV with comma / semicolon / tab, or .xlsx) and the problems found."""
    problems: list[str] = []
    if raw[:2] == b"PK":
        from openpyxl import load_workbook

        try:
            ws = load_workbook(io.BytesIO(raw), read_only=True, data_only=True).worksheets[0]
        except Exception as e:
            return [], [f"No pude abrir el Excel · could not open the workbook: {e}"]
        table = [["" if v is None else str(v) for v in row] for row in ws.iter_rows(values_only=True)]
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
        first = text.split("\n", 1)[0]
        delim = ";" if first.count(";") > first.count(",") else ("\t" if first.count("\t") > first.count(",") else ",")
        table = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
    if not table:
        return [], ["El archivo está vacío. · The file is empty."]
    head = [h.strip() for h in table[0]]
    missing = [c for c in NEEDED if c not in head]
    if missing:
        return [], [f"Faltan columnas · missing columns: {', '.join(missing)}."]
    absent = [c for c in COLUMNS if c not in head]
    if absent:
        problems.append(f"Aviso: columnas ausentes (se analizan vacías) · warning, absent columns (analyzed as empty): {', '.join(absent)}.")
    rows = []
    for row in table[1:]:
        if any(str(c).strip() for c in row):
            rec = {k: str(v).strip() for k, v in zip(head, row)}
            rows.append({c: rec.get(c, "") for c in COLUMNS})
    return rows, problems


def to_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(COLUMNS)
    for r in rows:
        w.writerow([r.get(c, "") for c in COLUMNS])
    return buf.getvalue().encode("utf-8-sig")


def load(path: str | Path | None = None) -> list[dict]:
    p = Path(path) if path else demand_path()
    return parse(p.read_bytes())[0] if p.exists() else []


def merge(old: list[dict], new: list[dict]) -> list[dict]:
    """New rows replace the old ones with the same Role ID; the rest are kept."""
    by_id = {r["Role ID"]: r for r in old if r.get("Role ID")}
    by_id.update({r["Role ID"]: r for r in new if r.get("Role ID")})
    return list(by_id.values()) + [r for r in new if not r.get("Role ID")]


def save(rows: list[dict], path: str | Path | None = None) -> Path:
    p = Path(path) if path else demand_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(to_csv(rows))
    return p


# ------------------------------------------------------------------------------------------------ snapshots (history)
# Every roles file that is loaded is kept as a dated snapshot, so the demand can be compared week over week:
#     content/demanda_historial/demanda_2026-10-07.csv
def history_dir() -> Path:
    return demand_path().parent / "demanda_historial"


def snapshot_date(rows: list[dict], fallback: str = "") -> str:
    """The date a roles file speaks for: the most recent Timestamp in it (YYYY-MM-DD), else ``fallback``, else today."""
    dates = []
    for r in rows:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", r.get("Timestamp", "")) or re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", r.get("Timestamp", ""))
        if m:
            dates.append(m.group(1) if len(m.groups()) == 1 else f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}")
    if dates:
        return max(dates)
    from datetime import date

    return fallback or date.today().isoformat()


def snapshots() -> list[tuple[str, Path]]:
    """(date, file) of every snapshot, oldest first."""
    d = history_dir()
    out = []
    for f in sorted(d.glob("demanda_*.csv")) if d.exists() else []:
        m = re.match(r"demanda_(\d{4}-\d{2}-\d{2})\.csv$", f.name)
        if m:
            out.append((m.group(1), f))
    return out


def save_snapshot(rows: list[dict], day: str = "") -> str:
    """Keep ``rows`` as the snapshot of ``day`` (replacing that day's, if any) and make the newest snapshot the current file."""
    day = day or snapshot_date(rows)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        raise ValueError(day)
    history_dir().mkdir(parents=True, exist_ok=True)
    (history_dir() / f"demanda_{day}.csv").write_bytes(to_csv(rows))
    latest = snapshots()[-1][1]
    save(parse(latest.read_bytes())[0])
    return day


def sync_history() -> None:
    """When the current roles file was replaced by hand (not through the app), keep it as a snapshot too."""
    p = demand_path()
    if not p.exists():
        return
    raw = p.read_bytes()
    snaps = snapshots()
    if snaps and snaps[-1][1].read_bytes() == raw:
        return
    rows = parse(raw)[0]
    if rows and not any(f.read_bytes() == raw for _, f in snaps):
        from datetime import date

        day = snapshot_date(rows, date.fromtimestamp(p.stat().st_mtime).isoformat())
        history_dir().mkdir(parents=True, exist_ok=True)
        (history_dir() / f"demanda_{day}.csv").write_bytes(raw)


def trend(history: list[tuple[str, list[dict]]], practice: Practice, lang: str = "es", top: int = 20) -> dict:
    """How the demand moves between snapshots. history: (date, rows), oldest first.

    points - per snapshot: roles in total and by scope; skills - the most requested skills with their count in every
    snapshot and the change against the previous one; new_roles / gone_roles - Role IDs that appeared / disappeared."""
    en = lang == "en"
    counts: list[Counter] = []
    scope_of_term: dict[str, str] = {}
    points = []
    for day, rows in history:
        c, scopes = Counter(), Counter()
        for r in rows:
            t = practice.match_skill(r["Role Primary Skill"]) if r["Role Primary Skill"] else None
            role = practice.match_role(r["Role Title"])
            scopes[t.scope if t else (role.scope if role else OUTSIDE)] += 1
            seen = set()
            for s in role_skills(r):
                m = practice.match_skill(s)
                term = m.term if m else s.strip()
                scope_of_term[term] = m.scope if m else OUTSIDE
                if term not in seen:
                    seen.add(term)
                    c[term] += 1
        counts.append(c)
        points.append({"date": day, "roles": len(rows), **{s: scopes.get(s, 0) for s in (CORE, THIRD, EMERGING, OUTSIDE)}})
    k = {"skill": "Skill", "scope": "Scope" if en else "Alcance", "change": "Change vs previous" if en else "Cambio vs anterior",
         "id": "Role ID", "title": "Role title" if en else "Título del rol", "pskill": "Primary skill" if en else "Skill primario",
         "client": "Client" if en else "Cliente"}
    if not history:
        return {"lang": lang, "keys": k, "dates": [], "points": [], "skills": [], "new_roles": [], "gone_roles": [], "new_skills": []}
    last = counts[-1]
    prev = counts[-2] if len(counts) > 1 else Counter()
    terms = [t for t, _ in _top(last, top)]
    terms += [t for t, _ in _top(prev, top) if t not in terms][:5]  # skills that were in demand and dropped out stay visible
    skills = []
    for t in terms:
        row = {k["skill"]: t, k["scope"]: _l(lang, SCOPE_NAME[scope_of_term[t]])}
        row.update({day: c.get(t, 0) for (day, _), c in zip(history, counts)})
        delta = last.get(t, 0) - prev.get(t, 0) if len(counts) > 1 else 0
        row[k["change"]] = (f"{delta:+d}" if delta else "0") if len(counts) > 1 else "—"
        skills.append(row | {"_scope": scope_of_term[t], "_delta": delta})
    new_roles = gone_roles = []
    if len(history) > 1:
        a_rows, b_rows = history[-2][1], history[-1][1]
        a_ids, b_ids = {r["Role ID"] for r in a_rows}, {r["Role ID"] for r in b_rows}

        def brief(r: dict) -> dict:
            return {k["id"]: r["Role ID"], k["title"]: r["Role Title"], k["pskill"]: r["Role Primary Skill"], k["client"]: r["Client"]}

        new_roles = [brief(r) for r in b_rows if r["Role ID"] not in a_ids]
        gone_roles = [brief(r) for r in a_rows if r["Role ID"] not in b_ids]
    return {"lang": lang, "keys": k, "dates": [d for d, _ in history], "points": points, "skills": skills, "new_roles": new_roles,
            "gone_roles": gone_roles, "new_skills": sorted(t for t in last if t not in prev) if len(counts) > 1 else []}


def line_chart(points: list[dict], title: str, lang: str = "es", width: int = 760, height: int = 260) -> str:
    """Roles per snapshot, one line per scope (direct labels at the end + legend). One y axis, starting at zero."""
    if len(points) < 2:
        return ""
    left, right, topm, bottom = 40, 240, 14, 30
    top_v = max(max(p[s] for s in (CORE, THIRD, EMERGING, OUTSIDE)) for p in points) or 1
    step = (width - left - right) / (len(points) - 1)

    def xy(i: int, v: int) -> tuple[float, float]:
        return left + i * step, topm + (height - topm - bottom) * (1 - v / top_v)

    grid = "".join(f'<line x1="{left}" y1="{xy(0, v)[1]:.1f}" x2="{width - right}" y2="{xy(0, v)[1]:.1f}" class="gr"/>'
                   f'<text x="{left - 6}" y="{xy(0, v)[1] + 4:.1f}" text-anchor="end" class="lb">{v}</text>' for v in sorted({0, top_v // 2, top_v}))
    xs = "".join(f'<text x="{xy(i, 0)[0]:.1f}" y="{height - 8}" text-anchor="middle" class="lb">{html.escape(p["date"])}</text>' for i, p in enumerate(points))
    lines, used = [], []
    for s in (CORE, THIRD, EMERGING, OUTSIDE):
        pts = [xy(i, p[s]) for i, p in enumerate(points)]
        path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
        dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{COLOR[s]}" stroke="#fff" stroke-width="2"><title>{html.escape(_l(lang, SCOPE_NAME[s]))} · '
                       f'{html.escape(p["date"])}: {p[s]}</title></circle>' for (x, y), p in zip(pts, points))
        ly = pts[-1][1] + 4
        while any(abs(ly - u) < 13 for u in used):  # end labels never overlap
            ly += 13
        used.append(ly)
        lines.append(f'<path d="{path}" fill="none" stroke="{COLOR[s]}" stroke-width="2"/>{dots}'
                     f'<text x="{pts[-1][0] + 10:.1f}" y="{ly:.1f}" class="lb">{html.escape(_l(lang, SCOPE_NAME[s]))}: <tspan class="vl">{points[-1][s]}</tspan></text>')
    return (f'<figure class="chart"><figcaption>{html.escape(title)}</figcaption><svg viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{html.escape(title)}" width="100%">{grid}{xs}{"".join(lines)}</svg></figure>')


def trend_charts(t: dict, top: int = 10) -> dict[str, str]:
    lang, k = t["lang"], t["keys"]
    en = lang == "en"
    up = sorted((r for r in t["skills"] if r["_delta"] > 0), key=lambda r: -r["_delta"])[:top]
    down = sorted((r for r in t["skills"] if r["_delta"] < 0), key=lambda r: r["_delta"])[:top]
    return {"lines": line_chart(t["points"], "Roles per upload, by scope" if en else "Roles por carga, según alcance", lang),
            "up": bar_chart([(r[k["skill"]], r["_delta"], r["_scope"]) for r in up],
                            "Skills growing the most (more roles than in the previous upload)" if en else "Skills que más crecen (roles de más frente a la carga anterior)", lang),
            "down": bar_chart([(r[k["skill"]], -r["_delta"], r["_scope"]) for r in down],
                              "Skills dropping the most (fewer roles than in the previous upload)" if en else "Skills que más bajan (roles de menos frente a la carga anterior)", lang)}


def split_skills(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[;,|\n]+", text or "") if s.strip()]


def role_skills(row: dict) -> list[str]:
    """Every skill a role asks for, once each, primary first."""
    out: dict[str, str] = {}
    for col in SKILL_COLUMNS:
        for s in split_skills(row.get(col, "")):
            out.setdefault(s.lower(), s)
    return list(out.values())


# ------------------------------------------------------------------------------------------------ analysis
def _top(counter: Counter, n: int | None = None) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0].lower()))[:n]


def analyze(rows: list[dict], practice: Practice, catalog=None, packs: list | None = None, materials: dict | None = None, lang: str = "es") -> dict:
    """Everything the report shows. Counts are numbers of ROLES (a skill counts once per role that asks for it)."""
    en = lang == "en"
    materials, packs = materials or {}, packs or []
    lessons_of = catalog.coverage(packs) if catalog else {}
    fam_name = {f.id: f.name for f in catalog.families} if catalog else {}
    known = catalog.skill_ids() if catalog else set()

    def canon(text: str) -> tuple[str, str, object]:
        t = practice.match_skill(text)
        return (t.term, t.scope, t) if t else (text.strip(), OUTSIDE, None)

    skills, primary, titles, combos = Counter(), Counter(), Counter(), Counter()
    info: dict[str, tuple[str, object]] = {}
    title_scope: dict[str, str] = {}
    by = {k: Counter() for k in ("Skill Category", "Client", "Industry Level 1", "Role Country/Territory", "Role Status", "Role Market Unit",
                                 "Role Career Level From", "month")}
    scope_roles, outside_roles = Counter(), []
    for r in rows:
        p_term, p_scope, p_entry = canon(r["Role Primary Skill"]) if r["Role Primary Skill"] else ("—", OUTSIDE, None)
        role = practice.match_role(r["Role Title"])
        scope = p_scope if p_scope != OUTSIDE else (role.scope if role else OUTSIDE)  # a role is ours by its primary skill or by its title
        scope_roles[scope] += 1
        title = r["Role Title"] or "—"
        titles[title] += 1
        title_scope[title] = scope if title_scope.get(title, OUTSIDE) == OUTSIDE else title_scope[title]
        primary[p_term] += 1
        info[p_term] = (p_scope, p_entry)
        combos[(title, p_term)] += 1
        seen = set()
        for s in role_skills(r):
            term, sc, entry = canon(s)
            if term not in seen:  # two names of the same practice skill (Sentinel, KQL) count once per role
                seen.add(term)
                skills[term] += 1
                info[term] = (sc, entry)
        for k in by:
            if k != "month" and r.get(k):
                by[k][r[k]] += 1
        m = re.match(r"(\d{4})-(\d{2})", r.get("Role Start Date", "")) or re.match(r"\d{1,2}/(\d{1,2})/(\d{4})", r.get("Role Start Date", ""))
        if m:
            by["month"][f"{m.group(1)}-{m.group(2)}" if len(m.group(1)) == 4 else f"{m.group(2)}-{int(m.group(1)):02d}"] += 1
        if scope == OUTSIDE:
            outside_roles.append(r)

    k = {"skill": "Skill", "scope": "Scope" if en else "Alcance", "roles": "Roles", "primary": "As primary skill" if en else "Como skill primario",
         "family": "Skill family" if en else "Familia de skills", "vendor": "Vendor", "catalog": "Catalog skill" if en else "Skill del catálogo",
         "lessons": "Lessons" if en else "Lecciones", "classes": "Learning path classes" if en else "Clases de learning path",
         "cover": "Content" if en else "Contenido", "title": "Role title" if en else "Título del rol", "share": "Share" if en else "Participación",
         "pskill": "Primary skill" if en else "Skill primario", "client": "Client" if en else "Cliente", "project": "Project" if en else "Proyecto",
         "id": "Role ID", "status": "Status" if en else "Estado"}
    total = len(rows) or 1

    def cover(entry) -> tuple[str, int, int]:
        if entry is None or not entry.skill_id or entry.skill_id not in known:
            return "new", 0, 0
        n_les = len(lessons_of.get(entry.skill_id, []))
        n_cls = sum(1 for m in materials.get(entry.skill_id, []) if m.get("kind") in ("path", "module", "course", "lab", "tutorial"))
        return ("lessons" if n_les else "path" if n_cls else "none"), n_les, n_cls

    skill_rows = []
    for term, n in _top(skills):
        sc, entry = info[term]
        cv, n_les, n_cls = cover(entry) if sc != OUTSIDE else ("new", 0, 0)
        skill_rows.append({k["skill"]: term, k["scope"]: _l(lang, SCOPE_NAME[sc]), k["roles"]: n, k["primary"]: primary.get(term, 0),
                           k["family"]: fam_name.get(entry.family, entry.family) if entry else "—", k["vendor"]: entry.vendor if entry else "—",
                           k["catalog"]: entry.skill_id if entry and entry.skill_id else "—", k["lessons"]: n_les, k["classes"]: n_cls,
                           k["cover"]: _l(lang, COVER[cv]) if sc != OUTSIDE else "—", "_scope": sc, "_cover": cv, "_entry": entry})
    primary_rows = [{k["pskill"]: t, k["scope"]: _l(lang, SCOPE_NAME[info[t][0]]), k["roles"]: n, k["share"]: f"{round(100 * n / total)} %",
                     "_scope": info[t][0]} for t, n in _top(primary)]
    title_rows = [{k["title"]: t, k["scope"]: _l(lang, SCOPE_NAME[title_scope[t]]), k["roles"]: n, k["share"]: f"{round(100 * n / total)} %",
                   "_scope": title_scope[t]} for t, n in _top(titles)]
    combo_rows = [{k["title"]: t, k["pskill"]: s, k["scope"]: _l(lang, SCOPE_NAME[info[s][0]]), k["roles"]: n, "_scope": info[s][0]}
                  for (t, s), n in sorted(combos.items(), key=lambda kv: (-kv[1], kv[0]))]
    outside_rows = [{k["id"]: r["Role ID"], k["title"]: r["Role Title"], k["pskill"]: r["Role Primary Skill"], k["client"]: r["Client"],
                     k["project"]: r["Project"], k["status"]: r["Role Status"]} for r in outside_roles]
    # what to build next: demanded skills of the practice without a course, most requested first
    backlog = [{x: r[x] for x in (k["skill"], k["scope"], k["roles"], k["primary"], k["family"], k["vendor"], k["catalog"], k["lessons"],
                                  k["classes"], k["cover"])} | {"_scope": r["_scope"], "_cover": r["_cover"], "_entry": r["_entry"]}
               for r in skill_rows if r["_scope"] != OUTSIDE and r["_cover"] != "lessons"]
    in_practice = sum(n for sc, n in scope_roles.items() if sc != OUTSIDE)
    return {"lang": lang, "keys": k, "rows": len(rows), "skills": skill_rows, "primary": primary_rows, "titles": title_rows, "combos": combo_rows,
            "outside_roles": outside_rows, "backlog": backlog, "scope_roles": dict(scope_roles),
            "by": {name: _top(c) for name, c in by.items() if name != "month"}, "months": sorted(by["month"].items()),
            "summary": {"roles": len(rows), "in_practice": in_practice, "outside": len(rows) - in_practice,
                        "in_practice_pct": round(100 * in_practice / total) if rows else 0, "clients": len(by["Client"]),
                        "skills": len(skills), "skills_outside": sum(1 for r in skill_rows if r["_scope"] == OUTSIDE),
                        "sold": sum(1 for r in rows if r.get("Role Is Sold", "").strip().lower() in ("yes", "true", "y", "si", "sí", "1")),
                        "no_course": len(backlog)}}


def visible(rows: list[dict]) -> list[dict]:
    return [{a: b for a, b in r.items() if not a.startswith("_")} for r in rows]


def catalog_suggestions(analysis: dict) -> bytes:
    """Demanded skills of the practice that are not in the skills catalog yet, as rows ready to paste into the content
    file (table Skills): add them there and the academy can attach learning paths and lessons to them."""
    from academy.content_xlsx import CSV_COLUMNS, TABLE

    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(CSV_COLUMNS)
    for r in analysis["backlog"]:
        e = r["_entry"]
        if r["_cover"] == "new" and e is not None:
            rec = {TABLE: "Skills", "SkillId": slug(e.term), "Name": e.term, "FamilyId": e.family, "Vendor": e.vendor, "Confirmed": "yes",
                   "ImpactedRoles": r[analysis["keys"]["roles"]]}
            w.writerow([rec.get(c, "") for c in CSV_COLUMNS])
    return buf.getvalue().encode("utf-8-sig")


# ------------------------------------------------------------------------------------------------ charts and report
def bar_chart(items: list[tuple[str, int, str]], title: str, lang: str = "es", width: int = 760) -> str:
    """Horizontal bars as inline SVG. items: (label, value, scope). Every bar carries its value; color = scope."""
    if not items:
        return ""
    top = max(v for _, v, _ in items) or 1
    row, label_w, pad = 30, 290, 54
    h = len(items) * row + 8
    bars = []
    for i, (label, value, scope) in enumerate(items):
        y = i * row + 4
        w = max(2, round((width - label_w - pad) * value / top))
        text = html.escape(label if len(label) <= 40 else label[:39] + "…")
        tip = html.escape(f"{label}: {value} · {_l(lang, SCOPE_NAME[scope])}")
        bars.append(f'<g class="bar"><title>{tip}</title><text x="{label_w - 10}" y="{y + 16}" text-anchor="end" class="lb">{text}</text>'
                    f'<path d="M{label_w},{y} h{max(w - 4, 0)} a4,4 0 0 1 4,4 v14 a4,4 0 0 1 -4,4 h-{max(w - 4, 0)} z" fill="{COLOR[scope]}"/>'
                    f'<text x="{label_w + w + 8}" y="{y + 16}" class="vl">{value}</text></g>')
    return (f'<figure class="chart"><figcaption>{html.escape(title)}</figcaption>'
            f'<svg viewBox="0 0 {width} {h}" role="img" aria-label="{html.escape(title)}" width="100%">'
            f'<line x1="{label_w}" y1="0" x2="{label_w}" y2="{h}" class="ax"/>{"".join(bars)}</svg></figure>')


def legend(lang: str, scopes: list[str] | None = None) -> str:
    return '<div class="legend">' + "".join(f'<span><i style="background:{COLOR[s]}"></i>{html.escape(_l(lang, SCOPE_NAME[s]))}</span>'
                                              for s in (scopes or [CORE, THIRD, EMERGING, OUTSIDE])) + "</div>"


def share_bar(scope_roles: dict, lang: str) -> str:
    """One stacked bar: how the roles split by scope (each segment labelled with its count and share)."""
    total = sum(scope_roles.values()) or 1
    ink = {CORE: "#1C1C1E", EMERGING: "#1C1C1E", THIRD: "#FFFFFF", OUTSIDE: "#FFFFFF"}  # readable text on each fill
    segs = "".join(f'<div style="flex:{n};background:{COLOR[s]};color:{ink[s]}" title="{html.escape(_l(lang, SCOPE_NAME[s]))}: {n}"><b>{n}</b> · {round(100 * n / total)} %</div>'
                   for s, n in ((s, scope_roles.get(s, 0)) for s in (CORE, THIRD, EMERGING, OUTSIDE)) if n)
    return f'<div class="share">{segs}</div>'


CHART_CSS = """.chart{margin:0 0 8px;max-width:760px}.chart figcaption{font-weight:700;font-size:16px;margin:0 0 8px} .chart .lb{font-size:13px;fill:currentColor}.chart .vl{font-size:13px;font-weight:700;fill:currentColor}.chart .ax{stroke:#C9C5BF;stroke-width:1} .chart .gr{stroke:#E4E0DB;stroke-width:1} .chart .bar:hover path{opacity:.78} .legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;margin:6px 0 14px;color:#3A3835} .legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px} .share{display:flex;gap:2px;height:44px;border-radius:8px;overflow:hidden;margin:6px 0 4px} .share div{display:flex;align-items:center;justify-content:center;font-size:13px;white-space:nowrap;min-width:64px;gap:4px}"""


def _table(rows: list[dict], limit: int | None = None) -> str:
    rows = visible(rows)[:limit]
    if not rows:
        return "<p>—</p>"
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in rows[0])
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in r.values()) + "</tr>" for r in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def charts(a: dict, top: int = 15) -> dict[str, str]:
    """The report's charts as SVG / HTML snippets, by name."""
    lang, k = a["lang"], a["keys"]
    en = lang == "en"
    return {
        "share": share_bar(a["scope_roles"], lang),
        "skills": bar_chart([(r[k["skill"]], r[k["roles"]], r["_scope"]) for r in a["skills"][:top]],
                            f"Top {top} most requested skills (roles that ask for each)" if en else f"Los {top} skills más solicitados (roles que piden cada uno)", lang),
        "primary": bar_chart([(r[k["pskill"]], r[k["roles"]], r["_scope"]) for r in a["primary"][:top]],
                             "Most requested primary skills" if en else "Skills primarios más solicitados", lang),
        "titles": bar_chart([(r[k["title"]], r[k["roles"]], r["_scope"]) for r in a["titles"][:top]],
                            "Most requested role titles" if en else "Títulos de rol más solicitados", lang),
        "outside": bar_chart([(r[k["skill"]], r[k["roles"]], OUTSIDE) for r in a["skills"] if r["_scope"] == OUTSIDE][:top],
                             "Most requested skills outside the practice" if en else "Skills más solicitados fuera de la práctica", lang),
        "backlog": bar_chart([(r[k["skill"]], r[k["roles"]], r["_scope"]) for r in a["backlog"][:top]],
                             "Practice skills in demand without a course (course backlog)" if en else "Skills de la práctica con demanda y sin curso (cursos por crear)", lang),
    }


def to_html(a: dict, practice: Practice, generated: str = "", tr: dict | None = None) -> str:
    """Standalone report with charts: open it in a browser, print it or save it as PDF. ``tr``: the trend (see ``trend``)."""
    lang, k, s = a["lang"], a["keys"], a["summary"]
    trend_html = ""
    if tr and len(tr["dates"]) > 1:
        tc, tk, e2 = trend_charts(tr), tr["keys"], a["lang"] == "en"
        trend_html = (f"<h2>{'Demand trend' if e2 else 'Tendencia de la demanda'} · {tr['dates'][0]} → {tr['dates'][-1]}</h2>"
                      f"{tc['lines']}{legend(lang)}<div class=\"grid\"><div>{tc['up']}</div><div>{tc['down']}</div></div>"
                      f"<h3>{'Most requested skills in every upload' if e2 else 'Skills más solicitados en cada carga'}</h3>{_table(tr['skills'])}"
                      f"<details><summary>{'New roles since the previous upload' if e2 else 'Roles nuevos desde la carga anterior'} ({len(tr['new_roles'])})</summary>{_table(tr['new_roles'])}</details>"
                      f"<details><summary>{'Roles no longer in the file' if e2 else 'Roles que ya no vienen en el archivo'} ({len(tr['gone_roles'])})</summary>{_table(tr['gone_roles'])}</details>")
    en = lang == "en"
    c = charts(a)
    kp = [("Roles", s["roles"]), ("In the practice" if en else "En la práctica", f"{s['in_practice']} · {s['in_practice_pct']} %"),
          ("Outside the practice" if en else "Fuera de la práctica", s["outside"]), ("Clients" if en else "Clientes", s["clients"]),
          ("Distinct skills" if en else "Skills distintos", s["skills"]),
          ("Practice skills without a course" if en else "Skills de la práctica sin curso", s["no_course"])]
    kpis = "".join(f'<div class="kpi"><b>{html.escape(str(v))}</b><span>{html.escape(n)}</span></div>' for n, v in kp)
    h = (lambda es, en_: en_ if en else es)
    extra = "".join(f"<h3>{html.escape(name)}</h3>{_table([{name: a_, 'Roles': n} for a_, n in items], 12)}" for name, items in a["by"].items() if items)
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><title>{h('Análisis de demanda', 'Demand analysis')} · {html.escape(practice.name)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;color:#1C1C1E;margin:32px auto;max-width:1100px;padding:0 20px;line-height:1.45;background:#fcfcfb}}
h1{{font-size:28px;margin:0 0 4px;letter-spacing:-.01em}}h2{{font-size:20px;margin:36px 0 12px}}h3{{font-size:15px;margin:22px 0 8px}}
.meta{{color:#55524E;font-size:13px}}.rule{{height:6px;width:72px;background:#FF5800;border-radius:3px;margin-bottom:14px}}
.kpis{{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0 8px}}.kpi{{border:1px solid #E4E0DB;border-radius:10px;padding:12px 16px;min-width:150px;background:#fff}}
.kpi b{{display:block;font-size:24px}}.kpi span{{font-size:13px;color:#55524E}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(440px,1fr));gap:28px}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:12.5px;background:#fff}}
th{{background:#1C1C1E;color:#fff;text-align:left;padding:8px 10px}}td{{padding:7px 10px;border-bottom:1px solid #E4E0DB;vertical-align:top}}
details{{margin:10px 0}}summary{{cursor:pointer;font-weight:600}}
{CHART_CSS}
@media print{{body{{margin:10mm;max-width:none}}th,.share div,.legend i{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
</style></head><body>
<div class="rule"></div><h1>{h('Análisis de demanda de roles', 'Role demand analysis')} · {html.escape(practice.name)}</h1>
<div class="meta">Academia - Cloud · {h('Generado', 'Generated')}: {html.escape(generated)} · {h('Los conteos son roles: un skill cuenta una vez por cada rol que lo pide.', 'Counts are roles: a skill counts once per role that asks for it.')}</div>
<div class="kpis">{kpis}</div>
<h2>{h('¿Cuánto de la demanda es de nuestra práctica?', 'How much of the demand belongs to our practice?')}</h2>
{c['share']}{legend(lang)}
<h2>{h('Qué se está pidiendo', 'What is being requested')}</h2>
<div class="grid"><div>{c['skills']}</div><div>{c['primary']}</div><div>{c['titles']}</div><div>{c['outside']}</div></div>
<h2>{h('Demanda contra cursos existentes', 'Demand against existing courses')}</h2>
<p class="meta">{h('Skills de la práctica que se piden y todavía no tienen lecciones en la academia: son los cursos por crear, del más pedido al menos pedido.', 'Practice skills in demand that still have no lessons in the academy: the courses to build, most requested first.')}</p>
{c['backlog']}
{_table(a['backlog'])}
{trend_html}
<h2>{h('Detalle', 'Detail')}</h2>
<details open><summary>{h('Skills solicitados', 'Requested skills')}</summary>{_table(a['skills'])}</details>
<details><summary>{h('Títulos de rol', 'Role titles')}</summary>{_table(a['titles'])}</details>
<details><summary>{h('Título de rol y skill primario', 'Role title and primary skill')}</summary>{_table(a['combos'])}</details>
<details><summary>{h('Roles fuera de la práctica', 'Roles outside the practice')}</summary>{_table(a['outside_roles'])}</details>
<details><summary>{h('Otras vistas', 'Other views')}</summary>{extra}</details>
</body></html>"""


# ------------------------------------------------------------------------------------------------ sample file
def sample_history() -> list[tuple[str, list[dict]]]:
    """Two made-up weekly uploads, to try the trend: last week's and this week's (most roles repeat, some close, some are new)."""
    now = sample_rows()
    before = [dict(r, Timestamp="2026-09-30 10:00") for r in now[:34]] + [dict(r, Timestamp="2026-09-30 10:00") for r in sample_rows(10, seed=3, first=900)]
    return [("2026-09-30", before), ("2026-10-07", [dict(r, Timestamp="2026-10-07 10:00") for r in now])]


def sample_rows(n: int = 48, seed: int = 7, first: int = 100200) -> list[dict]:
    """Made-up roles to try the module (fictional clients and people). Replace them with the real export."""
    import random

    rng = random.Random(seed)
    roles = [  # (title, primary, secondary, others, category, job family)
        ("Cloud Security Engineer", "Microsoft Defender for Cloud", "Microsoft Sentinel", "Azure; Zero Trust; KQL", "Security", "Technology"),
        ("Cloud Security Engineer", "Microsoft Sentinel", "Microsoft Defender XDR", "KQL; Azure; Incident Response", "Security", "Technology"),
        ("Identity Engineer", "Microsoft Entra ID", "Conditional Access", "PIM; MFA; SSO; Identity Governance", "Identity", "Technology"),
        ("IAM Consultant", "Okta", "SSO", "MFA; Active Directory", "Identity", "Technology"),
        ("Data Protection Engineer", "Microsoft Purview", "DLP", "Information Protection; Microsoft 365", "Data Security", "Technology"),
        ("Infrastructure Engineer", "Azure", "Terraform", "Azure Networking; Windows Server; Linux", "Infrastructure", "Technology"),
        ("Technical Project Manager", "Project Management", "Azure", "Stakeholder Management; Agile", "Delivery", "Delivery"),
        ("DevSecOps Engineer", "Azure DevOps", "GitHub Actions", "Terraform; Kubernetes; SAST", "Application Security", "Technology"),
        ("Endpoint Engineer", "Intune", "Microsoft Defender for Endpoint", "Windows 11; Conditional Access", "Endpoint", "Technology"),
        ("AI Security Consultant", "Azure AI Security", "Microsoft Purview", "Azure OpenAI; Responsible AI", "AI", "Technology"),
        ("Network Security Engineer", "Palo Alto", "Fortinet", "Cisco; Azure Firewall", "Network", "Technology"),
        ("Cloud Engineer", "AWS", "Terraform", "Kubernetes; Linux", "Infrastructure", "Technology"),
        ("ServiceNow Developer", "ServiceNow ITSM", "JavaScript", "ServiceNow SecOps; REST APIs", "Platforms", "Technology"),
        ("SAP Security Consultant", "SAP GRC", "SAP S/4HANA", "SAP Fiori", "ERP", "Technology"),
        ("Data Engineer", "Azure Databricks", "Python", "Azure Data Factory; SQL", "Data & AI", "Technology"),
        ("Full Stack Developer", "Java", "React", "Spring Boot; SQL", "Software Engineering", "Technology"),
        ("Salesforce Administrator", "Salesforce", "Apex", "Salesforce Sales Cloud", "Platforms", "Technology"),
        ("Power BI Analyst", "Power BI", "SQL", "DAX; Excel", "Data & AI", "Technology"),
    ]
    weights = [7, 6, 6, 2, 4, 5, 3, 3, 3, 2, 2, 2, 3, 2, 2, 3, 1, 2]
    clients = [("Cliente Demo A", "Banking", "Retail Banking"), ("Cliente Demo B", "Retail", "Consumer Goods"), ("Cliente Demo C", "Energy", "Utilities"),
               ("Cliente Demo D", "Health", "Providers"), ("Cliente Demo E", "Public Service", "Government"), ("Cliente Demo F", "Insurance", "Life")]
    leads = ["lead.uno@example.com", "lead.dos@example.com", "lead.tres@example.com"]
    out = []
    for i in range(n):
        title, prim, sec, other, cat, fam = rng.choices(roles, weights)[0]
        client, ind1, ind2 = rng.choice(clients)
        month = rng.randint(1, 6)
        level = rng.choice([8, 9, 10, 11])
        country = rng.choice(["Mexico", "Mexico", "United States", "Brazil", "Spain"])
        combined = "; ".join(dict.fromkeys([prim, sec] + split_skills(other)))
        out.append({"Timestamp": f"2026-{rng.randint(7, 9):02d}-{rng.randint(1, 28):02d} 10:{rng.randint(10, 59)}", "Client": client,
                    "Governance Lead": rng.choice(leads), "Project": f"Proyecto Demo {rng.randint(1, 12):02d}", "Role ID": f"R-{first + i}",
                    "Role Title": title, "Role Description": f"(mock) {title} for {client}: {prim} with {sec}.", "Combined Skills": combined,
                    "Role Career Level From": str(level), "Role Career Level To": str(level - 1),
                    "Role Status": rng.choice(["Open", "Open", "Open", "Filled", "Cancelled"]), "Role Is Sold": rng.choice(["Yes", "Yes", "No"]),
                    "Role Start Date": f"2026-{month + 6:02d}-01", "Role End Date": f"2027-{month:02d}-28", "Role Market Unit": "Growth Markets",
                    "Role Primary Contact (Email ID)": rng.choice(leads), "Role Job Family Group": fam, "Role Country/Territory": country,
                    "Role Location Path": f"Global/{country}", "Role Fulfillment Entity Path": "Global/Technology/Security",
                    "Role Primary Skill": prim, "Skill Category": cat, "Role Secondary Skill": sec, "Role Other Skills": other,
                    "Project Country/Territory": country, "Role Created By (Email ID)": rng.choice(leads),
                    "Role Location Type": rng.choice(["Remote", "Hybrid", "Onsite"]), "Role Work Location": country, "Role Source Location": country,
                    "Role Accepting Resumes": rng.choice(["Yes", "No"]), "Role Has Security/Nationality Restriction": rng.choice(["No", "No", "Yes"]),
                    "Role Recruiting Status": rng.choice(["Not started", "In progress", "Closed"]), "Project Location Path": f"Global/{country}",
                    "Industry Level 1": ind1, "Industry Level 2": ind2})
    return out
