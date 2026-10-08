"""Demand analysis: what the role requests ask for, what of it belongs to the practice, and what has a course.

Input: the roles file (CSV or Excel export) with the columns in ``COLUMNS``. It lives next to the content file:

    content/demand_roles.csv             (or the file named by ACADEMY_DEMAND)

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
DEMAND_FILE = ROOT / "content" / "demand_roles.csv"
COLUMNS = ["Timestamp", "Client", "Governance Lead", "Project", "Role ID", "Role Title", "Role Description", "Combined Skills",
           "Matrix cross-skills Practice",
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
SCOPE_NAME = {CORE: "Core of the practice", THIRD: "Other vendors we handle",
              EMERGING: "Emerging focus", OUTSIDE: "Outside the practice"}
COVER = {"lessons": "Has a course", "path": "Learning path only",
         "none": "No content", "new": "Not in the catalog"}


def demand_path() -> Path:
    return Path(os.environ.get("ACADEMY_DEMAND") or DEMAND_FILE)


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
        return [], ["The file is empty."]
    head = [h.strip() for h in table[0]]
    missing = [c for c in NEEDED if c not in head]
    if missing:
        return [], [f"Missing columns: {', '.join(missing)}."]
    absent = [c for c in COLUMNS if c not in head]
    if absent:
        problems.append(f"Warning: absent columns (analyzed as empty): {', '.join(absent)}.")
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
#     content/demand_history/demand_2026-10-07.csv
def history_dir() -> Path:
    return demand_path().parent / "demand_history"


def snapshot_date(rows: list[dict], fallback: str = "") -> str:
    """The date a roles file speaks for: the most recent Timestamp in it (YYYY-MM-DD), else ``fallback``, else today."""
    dates = [d.isoformat() for d in (parse_date(r.get("Timestamp", "")) for r in rows) if d]
    if dates:
        return max(dates)
    from datetime import date

    return fallback or date.today().isoformat()


def snapshots() -> list[tuple[str, Path]]:
    """(date, file) of every snapshot, oldest first."""
    d = history_dir()
    out = []
    for f in sorted(d.glob("deman*_*.csv")) if d.exists() else []:
        m = re.match(r"demanda?_(\d{4}-\d{2}-\d{2})\.csv$", f.name)  # demanda_: files of earlier versions
        if m:
            out.append((m.group(1), f))
    return out


def save_snapshot(rows: list[dict], day: str = "") -> str:
    """Keep ``rows`` as the snapshot of ``day`` (replacing that day's, if any) and make the newest snapshot the current file."""
    day = day or snapshot_date(rows)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        raise ValueError(day)
    history_dir().mkdir(parents=True, exist_ok=True)
    (history_dir() / f"demand_{day}.csv").write_bytes(to_csv(rows))
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
        (history_dir() / f"demand_{day}.csv").write_bytes(raw)


def trend(history: list[tuple[str, list[dict]]], practice: Practice, lang: str = "es", top: int = 20) -> dict:
    """How the demand moves between snapshots. history: (date, rows), oldest first.

    points - per snapshot: roles in total and by scope; skills - the most requested skills with their count in every
    snapshot and the change against the previous one; new_roles / gone_roles - Role IDs that appeared / disappeared."""
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
    k = {"skill": "Skill", "scope": "Scope", "change": "Change vs previous",
         "id": "Role ID", "title": "Role title", "pskill": "Primary skill",
         "client": "Client"}
    if not history:
        return {"lang": lang, "keys": k, "dates": [], "points": [], "skills": [], "new_roles": [], "gone_roles": [], "new_skills": []}
    last = counts[-1]
    prev = counts[-2] if len(counts) > 1 else Counter()
    terms = [t for t, _ in _top(last, top)]
    terms += [t for t, _ in _top(prev, top) if t not in terms][:5]  # skills that were in demand and dropped out stay visible
    skills = []
    for t in terms:
        row = {k["skill"]: t, k["scope"]: (SCOPE_NAME[scope_of_term[t]])}
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
        dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{COLOR[s]}" stroke="#fff" stroke-width="2"><title>{html.escape(SCOPE_NAME[s])} · '
                       f'{html.escape(p["date"])}: {p[s]}</title></circle>' for (x, y), p in zip(pts, points))
        ly = pts[-1][1] + 4
        while any(abs(ly - u) < 13 for u in used):  # end labels never overlap
            ly += 13
        used.append(ly)
        lines.append(f'<path d="{path}" fill="none" stroke="{COLOR[s]}" stroke-width="2"/>{dots}'
                     f'<text x="{pts[-1][0] + 10:.1f}" y="{ly:.1f}" class="lb">{html.escape(SCOPE_NAME[s])}: <tspan class="vl">{points[-1][s]}</tspan></text>')
    return (f'<figure class="chart"><figcaption>{html.escape(title)}</figcaption><svg viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{html.escape(title)}" width="100%">{grid}{xs}{"".join(lines)}</svg></figure>')


def trend_charts(t: dict, top: int = 10) -> dict[str, str]:
    lang, k = t["lang"], t["keys"]
    up = sorted((r for r in t["skills"] if r["_delta"] > 0), key=lambda r: -r["_delta"])[:top]
    down = sorted((r for r in t["skills"] if r["_delta"] < 0), key=lambda r: r["_delta"])[:top]
    return {"lines": line_chart(t["points"], "Roles per upload, by scope", lang),
            "up": bar_chart([(r[k["skill"]], r["_delta"], r["_scope"]) for r in up],
                            "Skills growing the most (more roles than in the previous upload)", lang),
            "down": bar_chart([(r[k["skill"]], -r["_delta"], r["_scope"]) for r in down],
                              "Skills dropping the most (fewer roles than in the previous upload)", lang)}


def clean_skill(text: str) -> tuple[str, str]:
    """(skill, proficiency) from what the roles report writes: '1 - User Research      (P2 - Intermediate)' -> ('User Research', 'P2')."""
    t = re.sub(r"\s+", " ", text or "").strip()
    level = ""
    m = re.search(r"\(\s*(P\d)\s*(?:-[^)]*)?\)\s*$", t, re.I)
    if m:
        level, t = m.group(1).upper(), t[:m.start()].strip()
    t = re.sub(r"^\d+\s*[-–.)]\s+", "", t)  # the position number of the skill in the role
    return t.strip(" -"), level


def clean_title(text: str) -> str:
    """'123456-00001_Solution Architect' -> 'Solution Architect' (the report prefixes the titles with internal codes)."""
    return re.sub(r"^\s*\d+(?:-\d+)*_\s*", "", text or "").strip()


def split_skills(text: str) -> list[str]:
    return [clean_skill(s)[0] for s in re.split(r"[;,|\n]+", text or "") if clean_skill(s)[0]]


def role_skills(row: dict) -> list[str]:
    """Every skill a role asks for, once each, primary first (the skill category, repeated in Combined Skills, is left out)."""
    out: dict[str, str] = {}
    category = clean_skill(row.get("Skill Category", ""))[0].lower()
    for col in SKILL_COLUMNS:
        for s in split_skills(row.get(col, "")):
            if s.lower() != category:
                out.setdefault(s.lower(), s)
    return list(out.values())


def practice_matrix(text: str) -> dict[str, list[tuple[str, str]]]:
    """The «Matrix cross-skills Practice» column: {"aligned": [(family, skill)], "gaps": [(family, skill)]}.

        • Practice Matches (Aligned Capabilities)
        - Data Protection, Risk & Compliance: Compliance / Risk Assessment
        • Unaligned Skills & Gaps
        - Technical Delivery Leadership: Technical Project / Program Management, Remediation Leadership"""
    out: dict[str, list[tuple[str, str]]] = {"aligned": [], "gaps": []}
    part = None
    for line in (text or "").splitlines():
        low = line.strip().lower()
        if not low:
            continue
        if "unaligned" in low or "gap" in low and ":" not in low:
            part = "gaps"
            continue
        if "match" in low or "aligned" in low and ":" not in low:
            part = "aligned"
            continue
        m = re.match(r"^[-•*·\s]*([^:]+):\s*(.+)$", line.strip())
        if part and m:
            family = m.group(1).strip()
            for skill in re.split(r",(?![^()]*\))|;", m.group(2)):
                if skill.strip():
                    out[part].append((family, skill.strip()))
    return out


def parse_date(text: str):
    """A date from the formats the report and Excel write: 2026-09-15, 9/15/2026 (US), 15/9/2026, 5-Nov-26, Excel datetimes."""
    from datetime import date, datetime

    t = (text or "").strip()
    if not t or t == "-":
        return None
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", t)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        month, day = (b, a) if a > 12 else (a, b)  # US order (month/day) unless the first number cannot be a month
        try:
            return date(y, month, day)
        except ValueError:
            return None
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d %b %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    return None


# ------------------------------------------------------------------------------------------------ analysis
def _top(counter: Counter, n: int | None = None) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0].lower()))[:n]


def analyze(rows: list[dict], practice: Practice, catalog=None, packs: list | None = None, materials: dict | None = None, lang: str = "es") -> dict:
    """Everything the report shows. Counts are numbers of ROLES (a skill counts once per role that asks for it)."""
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
    from collections import defaultdict

    matrix: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in rows:
        p_term, p_scope, p_entry = canon(clean_skill(r["Role Primary Skill"])[0]) if r["Role Primary Skill"] else ("—", OUTSIDE, None)
        title = clean_title(r["Role Title"]) or "—"
        role = practice.match_role(title)
        scope = p_scope if p_scope != OUTSIDE else (role.scope if role else OUTSIDE)  # a role is ours by its primary skill or by its title
        scope_roles[scope] += 1
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
            v = clean_skill(r.get(k, ""))[0] if k == "Skill Category" else (r.get(k) or "").strip()
            if k != "month" and v and v != "-":
                by[k][v] += 1
        start = parse_date(r.get("Role Start Date", ""))
        if start:
            by["month"][f"{start.year}-{start.month:02d}"] += 1
        mx = practice_matrix(r.get("Matrix cross-skills Practice", ""))
        for part in ("aligned", "gaps"):
            for pair in dict.fromkeys(mx[part]):
                matrix[pair][part] += 1
        if scope == OUTSIDE:
            outside_roles.append(r)

    k = {"skill": "Skill", "scope": "Scope", "roles": "Roles", "primary": "As primary skill",
         "family": "Role family", "vendor": "Vendor", "catalog": "Catalog skill",
         "lessons": "Lessons", "classes": "Learning path classes",
         "cover": "Content", "title": "Role title", "share": "Share",
         "pskill": "Primary skill", "client": "Client", "project": "Project",
         "id": "Role ID", "status": "Status"}
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
        skill_rows.append({k["skill"]: term, k["scope"]: SCOPE_NAME[sc], k["roles"]: n, k["primary"]: primary.get(term, 0),
                           k["family"]: fam_name.get(entry.family, entry.family) if entry else "—", k["vendor"]: entry.vendor if entry else "—",
                           k["catalog"]: entry.skill_id if entry and entry.skill_id else "—", k["lessons"]: n_les, k["classes"]: n_cls,
                           k["cover"]: COVER[cv] if sc != OUTSIDE else "—", "_scope": sc, "_cover": cv, "_entry": entry})
    primary_rows = [{k["pskill"]: t, k["scope"]: (SCOPE_NAME[info[t][0]]), k["roles"]: n, k["share"]: f"{round(100 * n / total)} %",
                     "_scope": info[t][0]} for t, n in _top(primary)]
    title_rows = [{k["title"]: t, k["scope"]: (SCOPE_NAME[title_scope[t]]), k["roles"]: n, k["share"]: f"{round(100 * n / total)} %",
                   "_scope": title_scope[t]} for t, n in _top(titles)]
    combo_rows = [{k["title"]: t, k["pskill"]: s, k["scope"]: (SCOPE_NAME[info[s][0]]), k["roles"]: n, "_scope": info[s][0]}
                  for (t, s), n in sorted(combos.items(), key=lambda kv: (-kv[1], kv[0]))]
    outside_rows = [{k["id"]: r["Role ID"], k["title"]: clean_title(r["Role Title"]), k["pskill"]: clean_skill(r["Role Primary Skill"])[0], k["client"]: r["Client"],
                     k["project"]: r["Project"], k["status"]: r["Role Status"]} for r in outside_roles]
    # what to build next: demanded skills of the practice without a course, most requested first
    backlog = [{x: r[x] for x in (k["skill"], k["scope"], k["roles"], k["primary"], k["family"], k["vendor"], k["catalog"], k["lessons"],
                                  k["classes"], k["cover"])} | {"_scope": r["_scope"], "_cover": r["_cover"], "_entry": r["_entry"]}
               for r in skill_rows if r["_scope"] != OUTSIDE and r["_cover"] != "lessons"]
    in_practice = sum(n for sc, n in scope_roles.items() if sc != OUTSIDE)
    names = {s.name.lower(): s.id for s in catalog.skills} if catalog else {}

    def in_academy(skill: str) -> str:
        t = practice.match_skill(skill)
        sid = (t.skill_id if t else "") or names.get(skill.lower(), "")
        if not sid or sid not in known:
            return COVER["new"]
        return COVER["lessons"] if lessons_of.get(sid) else (COVER["path"] if materials.get(sid) else COVER["none"])

    matrix_rows = [{"Role family": fam, "Skill": skill, "Roles where it is a gap": c["gaps"], "Roles where it is aligned": c["aligned"],
                    "In the academy": in_academy(skill)} for (fam, skill), c in sorted(matrix.items(), key=lambda kv: (-kv[1]["gaps"], -kv[1]["aligned"], kv[0]))]
    return {"lang": lang, "keys": k, "rows": len(rows), "skills": skill_rows, "matrix": matrix_rows, "primary": primary_rows, "titles": title_rows, "combos": combo_rows,
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
    """Demanded skills of the practice that are not in the skills catalog yet, with the columns of the «Skills» tab of the
    content workbook, in the same order: copy the rows and paste them at the end of that tab."""
    from academy.content_xlsx import SHEETS

    cols = SHEETS["Skills"]
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(cols)
    for r in analysis["backlog"]:
        e = r["_entry"]
        if r["_cover"] == "new" and e is not None:
            rec = {"SkillId": slug(e.term), "Name": e.term, "FamilyId": e.family, "Vendor": e.vendor, "Confirmed": "yes",
                   "ImpactedRoles": r[analysis["keys"]["roles"]]}
            w.writerow([rec.get(c, "") for c in cols])
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
        tip = html.escape(f"{label}: {value} · {SCOPE_NAME[scope]}")
        bars.append(f'<g class="bar"><title>{tip}</title><text x="{label_w - 10}" y="{y + 16}" text-anchor="end" class="lb">{text}</text>'
                    f'<path d="M{label_w},{y} h{max(w - 4, 0)} a4,4 0 0 1 4,4 v14 a4,4 0 0 1 -4,4 h-{max(w - 4, 0)} z" fill="{COLOR[scope]}"/>'
                    f'<text x="{label_w + w + 8}" y="{y + 16}" class="vl">{value}</text></g>')
    return (f'<figure class="chart"><figcaption>{html.escape(title)}</figcaption>'
            f'<svg viewBox="0 0 {width} {h}" role="img" aria-label="{html.escape(title)}" width="100%">'
            f'<line x1="{label_w}" y1="0" x2="{label_w}" y2="{h}" class="ax"/>{"".join(bars)}</svg></figure>')


def legend(lang: str, scopes: list[str] | None = None) -> str:
    return '<div class="legend">' + "".join(f'<span><i style="background:{COLOR[s]}"></i>{html.escape(SCOPE_NAME[s])}</span>'
                                              for s in (scopes or [CORE, THIRD, EMERGING, OUTSIDE])) + "</div>"


def share_bar(scope_roles: dict, lang: str) -> str:
    """One stacked bar: how the roles split by scope (each segment labelled with its count and share)."""
    total = sum(scope_roles.values()) or 1
    ink = {CORE: "#1C1C1E", EMERGING: "#1C1C1E", THIRD: "#FFFFFF", OUTSIDE: "#FFFFFF"}  # readable text on each fill
    segs = "".join(f'<div style="flex:{n};background:{COLOR[s]};color:{ink[s]}" title="{html.escape(SCOPE_NAME[s])}: {n}"><b>{n}</b> · {round(100 * n / total)} %</div>'
                   for s, n in ((s, scope_roles.get(s, 0)) for s in (CORE, THIRD, EMERGING, OUTSIDE)) if n)
    return f'<div class="share">{segs}</div>'


CHART_CSS = """.chart{margin:0 0 8px;max-width:760px}.chart figcaption{font-weight:700;font-size:16px;margin:0 0 8px} .chart .lb{font-size:13px;fill:currentColor}.chart .vl{font-size:13px;font-weight:700;fill:currentColor}.chart .ax{stroke:#C9C5BF;stroke-width:1} .chart .gr{stroke:#E4E0DB;stroke-width:1} .chart .bar:hover path{opacity:.78} .legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;margin:6px 0 14px;color:#3A3835} .legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px} .share{display:flex;gap:2px;height:44px;border-radius:8px;overflow:hidden;margin:6px 0 4px} .share div{display:flex;align-items:center;justify-content:center;font-size:13px;white-space:nowrap;min-width:64px;gap:4px}"""


def charts(a: dict, top: int = 15) -> dict[str, str]:
    """The report's charts as SVG / HTML snippets, by name."""
    lang, k = a["lang"], a["keys"]
    return {
        "share": share_bar(a["scope_roles"], lang),
        "skills": bar_chart([(r[k["skill"]], r[k["roles"]], r["_scope"]) for r in a["skills"][:top]],
                            f"Top {top} most requested skills (roles that ask for each)", lang),
        "primary": bar_chart([(r[k["pskill"]], r[k["roles"]], r["_scope"]) for r in a["primary"][:top]],
                             "Most requested primary skills", lang),
        "titles": bar_chart([(r[k["title"]], r[k["roles"]], r["_scope"]) for r in a["titles"][:top]],
                            "Most requested role titles", lang),
        "outside": bar_chart([(r[k["skill"]], r[k["roles"]], OUTSIDE) for r in a["skills"] if r["_scope"] == OUTSIDE][:top],
                             "Most requested skills outside the practice", lang),
        "backlog": bar_chart([(r[k["skill"]], r[k["roles"]], r["_scope"]) for r in a["backlog"][:top]],
                             "Practice skills in demand without a course (course backlog)", lang),
    }


def sample_history() -> list[tuple[str, list[dict]]]:
    """Two made-up weekly uploads, to try the trend: last week's and this week's (most roles repeat, some close, some are new)."""
    now = sample_rows()
    before = [dict(r, Timestamp="9/30/2026") for r in now[:34]] + [dict(r, Timestamp="9/30/2026") for r in sample_rows(10, seed=3, first=109000)]
    return [("2026-09-30", before), ("2026-10-07", [dict(r, Timestamp="10/7/2026") for r in now])]


PROFICIENCY = {"P1": "P1 - Basic", "P2": "P2 - Intermediate", "P3": "P3 - Advanced", "P4": "P4 - Expert"}
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# The made-up roles of the sample, in the shape of the organization's report:
# (title, [(skill, proficiency)] primary first, skill category, job family, {practice family: aligned skills}, {family: gaps})
SAMPLE_ROLES = [
    ("Cloud Security Engineer", [("Microsoft Defender for Cloud", "P3"), ("Microsoft Sentinel", "P2"), ("Azure", "P2"), ("Zero Trust", "P2"), ("KQL", "P2")],
     "Security Operations", "Technology",
     {"Cyber Defense & Security Operations": ["Microsoft Defender for Cloud", "Microsoft Sentinel", "KQL"], "Cloud & Network Security": ["Zero Trust"]},
     {"Cloud / Infrastructure Engineering": ["Azure Landing Zones"]}),
    ("Security Operations Analyst", [("Microsoft Sentinel", "P3"), ("Microsoft Defender XDR", "P2"), ("KQL", "P3"), ("Incident Response", "P2")],
     "Security Operations", "Technology",
     {"Cyber Defense & Security Operations": ["Microsoft Sentinel", "Microsoft Defender XDR", "KQL"]},
     {"Cyber Defense & Security Operations": ["Incident Response", "Threat Hunting"]}),
    ("Identity Engineer", [("Microsoft Entra ID", "P3"), ("Conditional Access", "P3"), ("PIM", "P2"), ("MFA", "P2"), ("Identity Governance", "P2")],
     "Identity", "Technology",
     {"Identity & Access Management": ["Microsoft Entra ID", "Conditional Access", "PIM"]},
     {"Identity & Access Management": ["Identity Governance"]}),
    ("IAM Consultant", [("Okta", "P3"), ("SSO", "P2"), ("MFA", "P2"), ("Active Directory", "P2")], "Identity", "Technology",
     {"Identity & Access Management": ["SSO", "MFA", "Active Directory"]}, {"Identity & Access Management": ["Okta"]}),
    ("Data Protection Engineer", [("Microsoft Purview", "P3"), ("DLP", "P2"), ("Information Protection", "P2"), ("Microsoft 365", "P2")],
     "Data Security", "Technology",
     {"Data Protection, Risk & Compliance": ["Microsoft Purview"], "Microsoft 365 Security": ["Microsoft 365"]},
     {"Data Protection, Risk & Compliance": ["DLP / Information Protection"]}),
    ("Infrastructure Engineer", [("Azure", "P3"), ("Terraform", "P2"), ("Azure Networking", "P2"), ("Windows Server", "P2"), ("Linux", "P1")],
     "Infrastructure", "Technology",
     {"Cloud / Infrastructure Engineering": ["Azure", "Windows Server"], "Cloud & Network Security": ["Azure Networking"]},
     {"Cloud / Infrastructure Engineering": ["Terraform", "Linux"]}),
    ("Technical Project Manager", [("Project Management", "P3"), ("Azure", "P1"), ("Stakeholder Management", "P3"), ("Agile", "P2")],
     "Delivery", "Delivery",
     {"Technical Delivery Leadership": ["Technical Project / Program Management"]},
     {"Technical Delivery Leadership": ["Stakeholder Management", "Agile Delivery"]}),
    ("DevSecOps Engineer", [("Azure DevOps", "P3"), ("GitHub Actions", "P2"), ("Terraform", "P2"), ("Kubernetes", "P2"), ("SAST", "P2")],
     "Application Security", "Technology",
     {"Application Security & DevSecOps": ["Azure DevOps", "GitHub Actions"]},
     {"Application Security & DevSecOps": ["SAST", "Kubernetes"]}),
    ("Endpoint Engineer", [("Intune", "P3"), ("Microsoft Defender for Endpoint", "P2"), ("Windows 11", "P2"), ("Conditional Access", "P1")],
     "Endpoint", "Technology",
     {"Microsoft 365 Security": ["Intune", "Microsoft Defender for Endpoint"], "Identity & Access Management": ["Conditional Access"]}, {}),
    ("AI Security Consultant", [("Azure AI Security", "P3"), ("Microsoft Purview", "P2"), ("Azure OpenAI", "P2"), ("Responsible AI", "P2")],
     "AI", "Technology",
     {"AI Security & Governance": ["Azure AI Security", "Azure OpenAI"], "Data Protection, Risk & Compliance": ["Microsoft Purview"]},
     {"AI Security & Governance": ["Responsible AI"]}),
    ("Network Security Engineer", [("Palo Alto", "P3"), ("Fortinet", "P2"), ("Cisco", "P2"), ("Azure Firewall", "P2")], "Network", "Technology",
     {"Cloud & Network Security": ["Azure Firewall"]}, {"Cloud & Network Security": ["Palo Alto", "Fortinet", "Cisco"]}),
    ("Cloud Engineer", [("AWS", "P3"), ("Terraform", "P2"), ("Kubernetes", "P2"), ("Linux", "P2")], "Infrastructure", "Technology",
     {}, {"Cloud / Infrastructure Engineering": ["AWS", "Terraform", "Kubernetes"]}),
    ("ServiceNow Developer", [("ServiceNow ITSM", "P3"), ("JavaScript", "P2"), ("ServiceNow SecOps", "P2"), ("REST APIs", "P2")],
     "Platforms", "Technology", {}, {"Other": ["ServiceNow ITSM", "JavaScript"]}),
    ("SAP Security Consultant", [("SAP GRC", "P3"), ("SAP S/4HANA", "P2"), ("SAP Fiori", "P1")], "ERP", "Technology",
     {}, {"Other": ["SAP GRC", "SAP S/4HANA"]}),
    ("Data Engineer", [("Azure Databricks", "P3"), ("Python", "P2"), ("Azure Data Factory", "P2"), ("SQL", "P2")], "Data & AI", "Technology",
     {}, {"Other": ["Azure Databricks", "Python"]}),
    ("Full Stack Developer", [("Java", "P3"), ("React", "P2"), ("Spring Boot", "P2"), ("SQL", "P2")], "Software Engineering", "Technology",
     {}, {"Other": ["Java", "React"]}),
    ("Salesforce Administrator", [("Salesforce", "P3"), ("Apex", "P2"), ("Salesforce Sales Cloud", "P2")], "Platforms", "Technology",
     {}, {"Other": ["Salesforce"]}),
    ("Power BI Analyst", [("Power BI", "P3"), ("SQL", "P2"), ("DAX", "P2"), ("Excel", "P1")], "Data & AI", "Technology",
     {}, {"Other": ["Power BI", "DAX"]}),
]


def sample_skill(n: int, name: str, level: str) -> str:
    """A skill written the way the report writes it: '1 - Microsoft Sentinel            (P3 - Advanced)'."""
    return f"{f'{n} - {name}':<40}({PROFICIENCY[level]})"


def sample_matrix(aligned: dict[str, list[str]], gaps: dict[str, list[str]]) -> str:
    """The «Matrix cross-skills Practice» cell, in the report's layout."""
    parts = []
    for head, groups in (("• Practice Matches (Aligned Capabilities)", aligned), ("• Unaligned Skills & Gaps", gaps)):
        if groups:
            parts.append("\n".join([head] + [f"- {fam}: {', '.join(skills)}" for fam, skills in groups.items()]))
    return "\n\n".join(parts)


def sample_rows(n: int = 48, seed: int = 7, first: int = 100200) -> list[dict]:
    """Made-up roles in the same shape as the organization's roles report (fictional clients, codes and people): numbered
    skills with their proficiency, titles with an internal code, US dates, '-' for empty cells and the practice matrix.
    Replace them with the real export (which is read for the session only, unless an owner saves it)."""
    import random

    rng = random.Random(seed)
    weights = [7, 4, 6, 2, 4, 5, 3, 3, 3, 2, 2, 2, 3, 2, 2, 3, 1, 2]
    clients = [("Demo Client A", "Banking", "Retail Banking"), ("Demo Client B", "Retail", "Consumer Goods"), ("Demo Client C", "Energy", "Utilities"),
               ("Demo Client D", "Health", "Providers"), ("Demo Client E", "Public Service", "-"), ("Demo Client F", "-", "-")]
    leads = ["lead.one@example.com", "lead.two@example.com", "lead.three@example.com"]

    def short(y: int, m: int, d: int) -> str:  # 1-Oct-26
        return f"{d}-{_MONTHS[m - 1]}-{y % 100:02d}"

    out = []
    for i in range(n):
        title, skills, cat, fam, aligned, gaps = rng.choices(SAMPLE_ROLES, weights)[0]
        client, ind1, ind2 = rng.choice(clients)
        month = rng.randint(1, 6)
        level = rng.choice([8, 9, 10, 11])
        country = rng.choice(["Mexico", "Mexico", "United States", "Brazil", "Spain"])
        numbered = [sample_skill(k, name, lvl) for k, (name, lvl) in enumerate(skills, start=1)]
        out.append({"Timestamp": f"{rng.randint(7, 9)}/{rng.randint(1, 28)}/2026", "Client": client,
                    "Governance Lead": rng.choice(leads), "Project": f"Demo Project {rng.randint(1, 12):02d}", "Role ID": str(first + i),
                    "Role Title": f"{rng.randint(100000, 999999)}-{rng.randint(10000, 99999)}_{title}",
                    "Role Description": f"(mock) {title} for {client}: {skills[0][0]} with {skills[1][0]}.",
                    "Combined Skills": " | ".join([numbered[0], cat] + numbered[1:]), "Matrix cross-skills Practice": sample_matrix(aligned, gaps),
                    "Role Career Level From": str(level), "Role Career Level To": str(level - 1),
                    "Role Status": rng.choice(["Open", "Open", "Open", "Filled", "Cancelled"]), "Role Is Sold": rng.choice(["Yes", "Yes", "No"]),
                    "Role Start Date": short(2026, month + 6, 1), "Role End Date": short(2027, month, 28), "Role Market Unit": "Growth Markets",
                    "Role Primary Contact (Email ID)": rng.choice(leads), "Role Job Family Group": fam, "Role Country/Territory": country,
                    "Role Location Path": f"Global/{country}", "Role Fulfillment Entity Path": "Global/Technology/Security",
                    "Role Primary Skill": numbered[0], "Skill Category": cat, "Role Secondary Skill": numbered[1],
                    "Role Other Skills": " | ".join(numbered[2:]) or "-",
                    "Project Country/Territory": country, "Role Created By (Email ID)": rng.choice(leads),
                    "Role Location Type": rng.choice(["Remote", "Hybrid", "Onsite"]), "Role Work Location": country, "Role Source Location": country,
                    "Role Accepting Resumes": rng.choice(["Yes", "No"]), "Role Has Security/Nationality Restriction": rng.choice(["No", "No", "Yes"]),
                    "Role Recruiting Status": rng.choice(["Not started", "In progress", "Closed"]), "Project Location Path": f"Global/{country}",
                    "Industry Level 1": ind1, "Industry Level 2": ind2})
    return out
